# tools/slack_session.py
"""
SlackSession — owns one Slack thread's Claude session lifecycle.

Runs the SessionBackend in a background thread, buffers output into chunks,
posts/edits messages in the Slack thread, routes user input back to the backend,
and enforces idle timeouts with warning messages.
"""

from __future__ import annotations

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
    # Internal: Slack posting
    # ------------------------------------------------------------------

    def _post_chunk(self, text: str) -> None:
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
