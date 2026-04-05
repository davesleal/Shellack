# tools/slack_session.py
"""
SlackSession — owns one Slack thread's Claude session lifecycle.

Runs the SessionBackend in a background thread, buffers output into chunks,
posts/edits messages in the Slack thread, routes user input back to the backend,
and enforces idle timeouts with warning messages.
"""

from __future__ import annotations

import re
import threading
import time
from typing import Callable, Optional

from slack_sdk import WebClient

from tools.session_backend import SessionBackend

_IDLE_W1 = 15 * 60  # 15 min → first warning
_IDLE_W2 = 25 * 60  # 25 min → second warning
_IDLE_MAX = 30 * 60  # 30 min → close session

_CHUNK_PAUSE = 3.0  # seconds between forced flushes
_EDIT_WINDOW = 5.0  # seconds within which we edit the last message
_MAX_INLINE_CHARS = 800  # longer than this → canvas or truncate

_CODE_FENCE_RE = re.compile(r"```[\s\S]+?```")
# Matches code blocks (multi-line) and inline code — skip these during mrkdwn conversion
_CODE_SEGMENT_RE = re.compile(r"(```[\s\S]*?```|`[^`\n]+`)")

# XML tool call / result blocks the claude CLI may narrate in text output
_TOOL_XML_RE = re.compile(
    r"<(function_calls|function_results|invoke|tool_call|tool_response"
    r"|write_file|read_file|bash|str_replace_editor|create_file|delete_file)"
    r"[^>]*>[\s\S]*?</\1>",
    re.IGNORECASE,
)


def _strip_tool_xml(text: str) -> str:
    """Remove tool call XML blocks from streaming output before posting to Slack."""
    return _TOOL_XML_RE.sub("", text).strip()


def _md_to_mrkdwn(text: str) -> str:
    """Convert Claude markdown to Slack mrkdwn, leaving code blocks untouched."""
    # Convert markdown tables to code blocks before splitting on fences
    text = _convert_tables(text)
    # Auto-close any unclosed triple-backtick fence so the regex splits correctly
    if text.count("```") % 2 != 0:
        text = text.rstrip() + "\n```"
    parts = _CODE_SEGMENT_RE.split(text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # code block — pass through unchanged
            out.append(part)
            continue
        # ## Heading / ### Heading → *Heading*
        part = re.sub(r"^#{1,6}\s+(.+)$", r"*\1*", part, flags=re.MULTILINE)
        # **bold** → *bold*
        part = re.sub(r"\*\*(.+?)\*\*", r"*\1*", part, flags=re.DOTALL)
        # ~~strike~~ → ~strike~
        part = re.sub(r"~~(.+?)~~", r"~\1~", part, flags=re.DOTALL)
        # Bullet lists: "- item" or "* item" → "• item" (only at line start)
        part = re.sub(r"^[ \t]*[-*]\s+", "• ", part, flags=re.MULTILINE)
        # Horizontal rule --- → thin line
        part = re.sub(r"^---+$", "─" * 24, part, flags=re.MULTILINE)
        # Numbered lists: "1. item" → "1. item" (already valid, but indent cleanup)
        part = re.sub(r"^(\d+)\.\s+", r"\1. ", part, flags=re.MULTILINE)
        out.append(part)
    return "".join(out)


# Matches a contiguous block of markdown table rows (header, separator, data)
_TABLE_ROW_RE = re.compile(r"^\|.+\|$", re.MULTILINE)
_TABLE_SEP_RE = re.compile(r"^\|[-:\s|]+\|$", re.MULTILINE)


def _convert_tables(text: str) -> str:
    """Convert markdown tables to Slack code blocks (tables don't render in mrkdwn).

    Skips tables already inside code fences.
    """
    lines = text.split("\n")
    result = []
    table_lines = []
    in_table = False
    in_code_block = False

    for line in lines:
        stripped = line.strip()
        # Track code fences — don't touch anything inside them
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            if in_table:
                # Flush any pending table before code block
                clean = [l for l in table_lines if not _TABLE_SEP_RE.match(l.strip())]
                result.append("```")
                result.extend(clean)
                result.append("```")
                table_lines = []
                in_table = False
            result.append(line)
            continue

        if in_code_block:
            result.append(line)
            continue

        is_table_row = bool(_TABLE_ROW_RE.match(stripped))
        if is_table_row:
            if not in_table:
                in_table = True
            table_lines.append(line)
        else:
            if in_table:
                clean = [l for l in table_lines if not _TABLE_SEP_RE.match(l.strip())]
                result.append("```")
                result.extend(clean)
                result.append("```")
                table_lines = []
                in_table = False
            result.append(line)

    if in_table:
        clean = [l for l in table_lines if not _TABLE_SEP_RE.match(l.strip())]
        result.append("```")
        result.extend(clean)
        result.append("```")

    return "\n".join(result)


class SlackSession:
    def __init__(
        self,
        thread_ts: str,
        channel_id: str,
        client: WebClient,
        backend: SessionBackend,
        on_close: Optional[Callable[[], None]] = None,
    ) -> None:
        self.thread_ts = thread_ts
        self.channel_id = channel_id
        self._client = client
        self._backend = backend
        self._on_close = on_close
        self._closed = False
        self._last_ts: Optional[str] = None
        self._last_ts_time: float = 0.0
        self._ts_lock = threading.Lock()
        self._close_lock = threading.Lock()
        self._timer_lock = threading.Lock()
        self._turn_lock = threading.Lock()
        self._canvas_lock = threading.Lock()
        self._canvas_id: Optional[str] = None
        self._idle_timer: Optional[threading.Timer] = None
        self._reset_idle()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self, task: str, system_prompt: str = "", cwd: str = ".") -> None:
        """Start the session in a background thread."""
        threading.Thread(
            target=self._run_turn,
            args=(task, True, system_prompt, cwd),
            daemon=True,
        ).start()

    def feed_input(self, text: str) -> None:
        """Route user text to the backend, or close on stop/cancel."""
        if self._closed:
            return
        if text.strip().lower() in ("stop", "cancel"):
            self._close("Session cancelled.")
            return
        self._reset_idle()
        threading.Thread(
            target=self._run_turn,
            args=(text, False),
            daemon=True,
        ).start()

    # ------------------------------------------------------------------
    # Internal: turn execution
    # ------------------------------------------------------------------

    def _run_turn(
        self,
        text: str,
        is_first: bool,
        system_prompt: str = "",
        cwd: str = ".",
    ) -> None:
        with self._turn_lock:
            if self._closed:
                return
            try:
                if is_first:
                    chunks = self._backend.first_turn(text, system_prompt, cwd)
                else:
                    chunks = self._backend.next_turn(text)

                buffer = ""
                last_flush = time.time()

                for chunk in chunks:
                    buffer += chunk
                    self._reset_idle()
                    if "\n\n" in buffer or (time.time() - last_flush) >= _CHUNK_PAUSE:
                        self._post_chunk(buffer.strip())
                        buffer = ""
                        last_flush = time.time()

                if buffer.strip():
                    self._post_chunk(buffer.strip())

            except Exception as exc:
                self._post_new("❌ Session error: " + str(exc))
                self._close(None)

    # ------------------------------------------------------------------
    # Internal: canvas
    # ------------------------------------------------------------------

    def _ensure_canvas(self) -> Optional[str]:
        """Create a session canvas if one doesn't exist. Returns canvas_id or None."""
        with self._canvas_lock:
            if self._canvas_id:
                return self._canvas_id
            try:
                resp = self._client.canvases_create(
                    title="🦞 Session Output",
                    document_content={
                        "type": "markdown",
                        "markdown": "# Session Output\n\n_Code and details from this `run:` session are here._\n\n",
                    },
                )
                canvas_id = resp.get("canvas_id") or (resp.get("canvas") or {}).get(
                    "id"
                )
                if canvas_id:
                    self._canvas_id = canvas_id
                    return canvas_id
            except Exception as exc:
                print(f"Canvas creation failed: {exc}")
            return None

    def _append_to_canvas(self, content: str) -> Optional[str]:
        """Append markdown content to the session canvas. Returns canvas_id or None."""
        canvas_id = self._ensure_canvas()
        if not canvas_id:
            return None
        try:
            self._client.canvases_edit(
                canvas_id=canvas_id,
                changes=[
                    {
                        "operation": "insert_at_end",
                        "document_content": {
                            "type": "markdown",
                            "markdown": f"\n{content}\n",
                        },
                    }
                ],
            )
            return canvas_id
        except Exception as exc:
            print(f"Canvas update failed: {exc}")
            return None

    # ------------------------------------------------------------------
    # Internal: Slack posting
    # ------------------------------------------------------------------

    def _post_chunk(self, text: str) -> None:
        if not text:
            return

        text = _strip_tool_xml(text)
        if not text:
            return

        text = _md_to_mrkdwn(text)
        has_code = bool(_CODE_FENCE_RE.search(text))
        is_long = len(text) > _MAX_INLINE_CHARS

        if has_code or is_long:
            canvas_id = self._append_to_canvas(text)
            if canvas_id:
                # Extract a brief prose summary (text before the first code block)
                summary = _CODE_FENCE_RE.split(text)[0].strip()
                if summary:
                    summary = summary[:300].rstrip()
                notice = (summary + "\n" if summary else "") + (
                    f"📄 Added to session canvas (`{canvas_id}`)"
                )
                self._post_inline(notice)
                return
            # Canvas unavailable — fall through with truncation
            if is_long:
                text = text[:_MAX_INLINE_CHARS] + "… _(output truncated)_"

        self._post_inline(text)

    def _post_inline(self, text: str) -> None:
        """Post text to thread, editing last message if within edit window."""
        if not text:
            return
        now = time.time()
        with self._ts_lock:
            if self._last_ts and (now - self._last_ts_time) < _EDIT_WINDOW:
                try:
                    self._client.chat_update(
                        channel=self.channel_id,
                        ts=self._last_ts,
                        text=text,
                    )
                    self._last_ts_time = now
                    return
                except Exception:
                    pass  # fall through to new message
        self._post_new(text)

    def _post_new(self, text: str) -> None:
        try:
            resp = self._client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=self.thread_ts,
                text=text,
            )
            with self._ts_lock:
                self._last_ts = resp["ts"]
                self._last_ts_time = time.time()
        except Exception:
            pass  # never crash the session on a Slack API failure

    # ------------------------------------------------------------------
    # Internal: idle timer chain
    # ------------------------------------------------------------------

    def _reset_idle(self) -> None:
        if self._closed:
            return
        with self._timer_lock:
            if self._idle_timer:
                self._idle_timer.cancel()
            self._idle_timer = threading.Timer(_IDLE_W1, self._on_idle_15)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _on_idle_15(self) -> None:
        if self._closed:
            return
        self._post_new("Session has been idle for 15 minutes. Still there?")
        with self._timer_lock:
            self._idle_timer = threading.Timer(_IDLE_W2 - _IDLE_W1, self._on_idle_25)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _on_idle_25(self) -> None:
        if self._closed:
            return
        self._post_new(
            "Session timing out in 5 minutes — reply or click to keep it alive"
        )
        with self._timer_lock:
            self._idle_timer = threading.Timer(_IDLE_MAX - _IDLE_W2, self._on_idle_30)
            self._idle_timer.daemon = True
            self._idle_timer.start()

    def _on_idle_30(self) -> None:
        self._close("Session timed out after 30 minutes of inactivity.")

    # ------------------------------------------------------------------
    # Internal: close
    # ------------------------------------------------------------------

    def _close(self, message: Optional[str]) -> None:
        with self._close_lock:
            if self._closed:
                return
            self._closed = True
        with self._timer_lock:
            if self._idle_timer:
                self._idle_timer.cancel()
        self._backend.close()
        if message:
            self._post_new(message)
        if self._on_close:
            self._on_close()
