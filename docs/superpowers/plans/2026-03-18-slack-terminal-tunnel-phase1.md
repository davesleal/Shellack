# Slack Terminal Tunnel — Phase 1: Session Core

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable `@Shellack run: <task>` in any project channel to start a full bidirectional Claude session in that Slack thread — output streamed in chunks, input via typed thread replies.

**Architecture:** A `SessionBackend` abstraction with two implementations. `APIBackend` uses the Anthropic SDK with streaming and manages conversation history in memory. `MaxBackend` spawns a fresh `claude -p` subprocess per turn, using `--session-id <uuid>` on the first turn to pre-assign an ID and `--resume <uuid>` on subsequent turns — this isolates concurrent sessions cleanly without any `--continue` collision risk. A `SlackSession` owns one thread lifecycle: runs the backend in a background thread, buffers output, posts chunks to Slack, and routes typed thread replies back to the backend. `bot_unified.py` detects `run:` in top-level mentions, creates sessions, and routes thread replies.

**Tech Stack:** Python 3.9+, Slack Bolt (sync/threading), `anthropic` SDK, `subprocess` (claude CLI with `--output-format stream-json --verbose`), `threading.Timer`, `threading.Lock`

**Important CLI detail:** `claude --output-format stream-json` requires `--verbose`. Verified working command: `claude -p "task" --output-format stream-json --verbose --session-id <uuid>`. Session continuation: `claude -p "input" --output-format stream-json --verbose --resume <uuid>`.

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/session_backend.py` | Create | `SessionBackend` ABC, `MaxBackend`, `APIBackend` |
| `tools/slack_session.py` | Create | `SlackSession` thread lifecycle, output chunking, idle timers |
| `bot_unified.py` | Modify | Add `RUN_SESSIONS`, `run:` trigger (top-level mentions only), thread reply routing |
| `tests/test_session_backend.py` | Create | Backend unit tests |
| `tests/test_slack_session.py` | Create | Session lifecycle tests |
| `tests/test_bot_run_trigger.py` | Create | Bot integration tests for run: flow |

---

## Task 1: `SessionBackend` ABC + `APIBackend`

**Files:**
- Create: `tools/session_backend.py`
- Create: `tests/test_session_backend.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_session_backend.py
import json
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# APIBackend
# ---------------------------------------------------------------------------

def _make_stream(texts):
    """Return a mock context manager whose text_stream yields texts."""
    stream = MagicMock()
    stream.__enter__ = MagicMock(return_value=stream)
    stream.__exit__ = MagicMock(return_value=False)
    stream.text_stream = iter(texts)
    return stream


def test_api_backend_first_turn_yields_chunks():
    from tools.session_backend import APIBackend
    with patch("tools.session_backend.Anthropic") as MockAnthropic:
        client = MockAnthropic.return_value
        client.messages.stream.return_value = _make_stream(["Hello", " world"])
        backend = APIBackend(model="claude-sonnet-4-6")
        chunks = list(backend.first_turn("say hello"))
    assert chunks == ["Hello", " world"]


def test_api_backend_builds_history():
    from tools.session_backend import APIBackend
    with patch("tools.session_backend.Anthropic") as MockAnthropic:
        client = MockAnthropic.return_value
        client.messages.stream.side_effect = [
            _make_stream(["response1"]),
            _make_stream(["response2"]),
        ]
        backend = APIBackend()
        list(backend.first_turn("question 1"))
        list(backend.next_turn("question 2"))
        call_kwargs = client.messages.stream.call_args_list[1][1]
        messages = call_kwargs["messages"]
    assert messages[0] == {"role": "user", "content": "question 1"}
    assert messages[1] == {"role": "assistant", "content": "response1"}
    assert messages[2] == {"role": "user", "content": "question 2"}


def test_api_backend_passes_system_prompt():
    from tools.session_backend import APIBackend
    with patch("tools.session_backend.Anthropic") as MockAnthropic:
        client = MockAnthropic.return_value
        client.messages.stream.return_value = _make_stream(["ok"])
        backend = APIBackend()
        list(backend.first_turn("task", system_prompt="You are helpful."))
        call_kwargs = client.messages.stream.call_args[1]
    assert call_kwargs["system"] == "You are helpful."


def test_api_backend_next_turn_raises_without_first_turn():
    from tools.session_backend import APIBackend
    with patch("tools.session_backend.Anthropic"):
        backend = APIBackend()
        with pytest.raises(RuntimeError, match="first_turn"):
            list(backend.next_turn("follow up"))


def test_api_backend_close_clears_history():
    from tools.session_backend import APIBackend
    with patch("tools.session_backend.Anthropic") as MockAnthropic:
        client = MockAnthropic.return_value
        client.messages.stream.return_value = _make_stream(["hi"])
        backend = APIBackend()
        list(backend.first_turn("hello"))
        backend.close()
    assert backend._history == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /path/to/shellack
source venv/bin/activate
pytest tests/test_session_backend.py -v 2>&1 | head -20
```

Expected: `ModuleNotFoundError` or `ImportError` — file doesn't exist yet.

- [ ] **Step 3: Implement `SessionBackend` ABC + `APIBackend`**

```python
# tools/session_backend.py
"""
Session backends for Slack Terminal Tunnel.

SessionBackend is the abstract interface. Two implementations:
- APIBackend: Anthropic SDK streaming, manages conversation history.
- MaxBackend: claude CLI subprocess per turn, --session-id / --resume for continuity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from typing import Generator, Optional

from anthropic import Anthropic


class SessionBackend(ABC):
    """Abstract base for Claude session backends."""

    @abstractmethod
    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        """Start session with initial task. Yields text chunks."""
        ...

    @abstractmethod
    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        """Continue session with user input. Yields text chunks."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by this backend."""
        ...


class APIBackend(SessionBackend):
    """Anthropic SDK streaming backend. Costs API credits per token."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self._client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))
        self._model = model
        self._history: list[dict] = []
        self._system: str = ""
        self._started = False

    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        self._system = system_prompt
        self._history = [{"role": "user", "content": task}]
        self._started = True
        yield from self._stream()

    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        if not self._started:
            raise RuntimeError("next_turn called before first_turn")
        self._history.append({"role": "user", "content": user_input})
        yield from self._stream()

    def _stream(self) -> Generator[str, None, None]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 8096,
            "messages": self._history,
        }
        if self._system:
            kwargs["system"] = self._system

        assistant_text = ""
        with self._client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                assistant_text += text
                yield text

        self._history.append({"role": "assistant", "content": assistant_text})

    def close(self) -> None:
        self._history.clear()
        self._started = False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_session_backend.py -v
```

Expected: all 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/session_backend.py tests/test_session_backend.py
git commit -m "feat: add SessionBackend ABC and APIBackend"
```

---

## Task 2: `MaxBackend`

**Files:**
- Modify: `tools/session_backend.py` (add `MaxBackend` class at the bottom)
- Modify: `tests/test_session_backend.py` (add MaxBackend tests at the bottom)

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_session_backend.py`:

```python
# ---------------------------------------------------------------------------
# MaxBackend
# ---------------------------------------------------------------------------

def _make_proc(lines):
    """Return a mock Popen process whose stdout yields JSONL lines."""
    proc = MagicMock()
    proc.stdout = iter(lines)
    proc.wait = MagicMock(return_value=0)
    return proc


_ASSISTANT_EVENT = json.dumps({
    "type": "assistant",
    "message": {"content": [{"type": "text", "text": "Hello from Max"}]},
    "session_id": "test-session-abc",
})
_RESULT_EVENT = json.dumps({
    "type": "result", "subtype": "success", "result": "Hello from Max",
    "session_id": "test-session-abc",
})


def test_max_backend_first_turn_yields_text():
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.return_value = _make_proc([
            _ASSISTANT_EVENT + "\n",
            _RESULT_EVENT + "\n",
        ])
        backend = MaxBackend()
        chunks = list(backend.first_turn("say hello", cwd="/tmp"))
    assert "Hello from Max" in chunks


def test_max_backend_first_turn_includes_session_id_flag():
    """--session-id must appear in the first-turn command."""
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.return_value = _make_proc([_RESULT_EVENT + "\n"])
        backend = MaxBackend()
        list(backend.first_turn("task"))
        cmd = MockPopen.call_args[0][0]
    assert "--session-id" in cmd
    # The element after --session-id should be a valid UUID string
    idx = cmd.index("--session-id")
    import uuid as _uuid
    _uuid.UUID(cmd[idx + 1])  # raises ValueError if not a valid UUID


def test_max_backend_next_turn_uses_resume():
    """--resume must appear in subsequent turn commands."""
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.side_effect = [
            _make_proc([_RESULT_EVENT + "\n"]),
            _make_proc([_RESULT_EVENT + "\n"]),
        ]
        backend = MaxBackend()
        list(backend.first_turn("task"))
        list(backend.next_turn("follow up"))
        second_cmd = MockPopen.call_args_list[1][0][0]
    assert "--resume" in second_cmd
    assert "--session-id" not in second_cmd


def test_max_backend_resume_uses_same_session_id():
    """The session_id passed to --resume must match the one from --session-id."""
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.side_effect = [
            _make_proc([_RESULT_EVENT + "\n"]),
            _make_proc([_RESULT_EVENT + "\n"]),
        ]
        backend = MaxBackend()
        list(backend.first_turn("task"))
        first_cmd = MockPopen.call_args_list[0][0][0]
        list(backend.next_turn("follow up"))
        second_cmd = MockPopen.call_args_list[1][0][0]

    first_id = first_cmd[first_cmd.index("--session-id") + 1]
    resume_id = second_cmd[second_cmd.index("--resume") + 1]
    assert first_id == resume_id


def test_max_backend_next_turn_raises_without_first_turn():
    from tools.session_backend import MaxBackend
    backend = MaxBackend()
    with pytest.raises(RuntimeError, match="first_turn"):
        list(backend.next_turn("hello"))


def test_max_backend_skips_non_assistant_events():
    from tools.session_backend import MaxBackend
    rate_limit_event = json.dumps({"type": "rate_limit_event"})
    system_event = json.dumps({"type": "system", "subtype": "init"})
    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.return_value = _make_proc([
            rate_limit_event + "\n",
            system_event + "\n",
            _ASSISTANT_EVENT + "\n",
        ])
        backend = MaxBackend()
        chunks = list(backend.first_turn("task"))
    assert chunks == ["Hello from Max"]


def test_max_backend_available_false_when_no_claude():
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.shutil.which", return_value=None):
        assert MaxBackend.available() is False


def test_max_backend_available_true_when_claude_exists():
    from tools.session_backend import MaxBackend
    with patch("tools.session_backend.shutil.which", return_value="/usr/local/bin/claude"):
        assert MaxBackend.available() is True
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_session_backend.py::test_max_backend_first_turn_yields_text -v
```

Expected: `ImportError` — `MaxBackend` not defined yet.

- [ ] **Step 3: Implement `MaxBackend`**

Add to `tools/session_backend.py` (after `APIBackend`):

```python
class MaxBackend(SessionBackend):
    """Claude CLI subprocess backend. Uses Max subscription — zero API cost.

    Design: each turn spawns a fresh `claude -p` subprocess.
    - first_turn: passes --session-id <uuid> so Claude Code persists the
      conversation under our pre-assigned ID.
    - next_turn: passes --resume <uuid> to continue that exact conversation.

    This gives per-session isolation with no --continue collision risk.
    Requires: `claude` CLI on PATH, `--output-format stream-json --verbose`.
    """

    def __init__(self) -> None:
        self._session_id: Optional[str] = None
        self._cwd: str = "."

    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        self._cwd = cwd
        self._session_id = str(uuid.uuid4())
        cmd = [
            "claude", "-p", task,
            "--output-format", "stream-json",
            "--verbose",
            "--session-id", self._session_id,
        ]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        yield from self._run(cmd)

    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        if self._session_id is None:
            raise RuntimeError("next_turn called before first_turn")
        cmd = [
            "claude", "-p", user_input,
            "--output-format", "stream-json",
            "--verbose",
            "--resume", self._session_id,
        ]
        yield from self._run(cmd)

    def _run(self, cmd: list[str]) -> Generator[str, None, None]:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=self._cwd,
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                for block in event.get("message", {}).get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        yield block["text"]
        proc.wait()

    @classmethod
    def available(cls) -> bool:
        """Return True if `claude` CLI is on PATH."""
        return shutil.which("claude") is not None

    def close(self) -> None:
        self._session_id = None
```

- [ ] **Step 4: Run all session backend tests**

```bash
pytest tests/test_session_backend.py -v
```

Expected: all 13 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/session_backend.py tests/test_session_backend.py
git commit -m "feat: add MaxBackend using claude CLI --session-id / --resume"
```

---

## Task 3: `SlackSession`

**Files:**
- Create: `tools/slack_session.py`
- Create: `tests/test_slack_session.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_slack_session.py
import time
import threading
import pytest
from unittest.mock import MagicMock, patch


# Disable idle timers globally for all tests in this file — prevents
# daemon threads from firing after tests complete.
@pytest.fixture(autouse=True)
def no_idle_timers():
    with patch("tools.slack_session.threading.Timer") as MockTimer:
        mock_instance = MagicMock()
        MockTimer.return_value = mock_instance
        yield


def _make_backend(chunks=None, error=None):
    backend = MagicMock()
    if error:
        backend.first_turn.side_effect = error
        backend.next_turn.side_effect = error
    else:
        backend.first_turn.return_value = iter(chunks or [])
        backend.next_turn.return_value = iter(chunks or [])
    return backend


def _make_client():
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1234.5678"}
    client.chat_update.return_value = {"ts": "1234.5678"}
    return client


def _wait_for(condition, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.05)
    return False


def test_session_posts_output_to_thread():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=["Hello world"])
    session = SlackSession("ts1", "C123", client, backend)
    session.start("do the thing")
    assert _wait_for(lambda: client.chat_postMessage.called)
    call_kwargs = client.chat_postMessage.call_args[1]
    assert call_kwargs["thread_ts"] == "ts1"
    assert call_kwargs["channel"] == "C123"
    assert "Hello world" in call_kwargs["text"]


def test_session_stop_closes_immediately():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    session = SlackSession("ts1", "C123", client, backend)
    session.start("task")
    time.sleep(0.05)
    session.feed_input("stop")
    assert session._closed


def test_session_cancel_word_also_closes():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    session = SlackSession("ts1", "C123", client, backend)
    session.start("task")
    time.sleep(0.05)
    session.feed_input("cancel")
    assert session._closed


def test_session_feed_input_calls_next_turn():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=["done"])
    session = SlackSession("ts1", "C123", client, backend)
    session.start("first task")
    _wait_for(lambda: backend.first_turn.called)
    backend.next_turn.return_value = iter(["follow-up done"])
    session.feed_input("follow up")
    assert _wait_for(lambda: backend.next_turn.called)
    backend.next_turn.assert_called_once_with("follow up")


def test_session_on_close_callback_called():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    on_close = MagicMock()
    session = SlackSession("ts1", "C123", client, backend, on_close=on_close)
    session.start("task")
    time.sleep(0.05)
    session.feed_input("stop")
    time.sleep(0.05)
    on_close.assert_called_once()


def test_post_chunk_edits_when_within_5s():
    """Calling _post_chunk twice rapidly should edit the first message."""
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    session = SlackSession("ts1", "C123", client, backend)
    # Simulate first post having happened just now
    session._last_ts = "existing.ts"
    session._last_ts_time = time.time()
    # Second call — should edit, not post new
    session._post_chunk("updated text")
    client.chat_update.assert_called_once_with(
        channel="C123", ts="existing.ts", text="updated text"
    )
    client.chat_postMessage.assert_not_called()


def test_post_chunk_posts_new_when_beyond_5s():
    """Calling _post_chunk after the edit window posts a new message."""
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    session = SlackSession("ts1", "C123", client, backend)
    session._last_ts = "old.ts"
    session._last_ts_time = time.time() - 10.0  # 10s ago — beyond edit window
    session._post_chunk("new message")
    client.chat_postMessage.assert_called_once()
    client.chat_update.assert_not_called()


def test_session_backend_error_posts_error_message():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(error=RuntimeError("subprocess crashed"))
    session = SlackSession("ts1", "C123", client, backend)
    session.start("task")
    assert _wait_for(lambda: any(
        "❌" in str(c) for c in client.chat_postMessage.call_args_list
    ), timeout=2)
    assert session._closed


def test_session_ignores_input_when_closed():
    from tools.slack_session import SlackSession
    client = _make_client()
    backend = _make_backend(chunks=[])
    session = SlackSession("ts1", "C123", client, backend)
    session._closed = True
    session.feed_input("anything")
    backend.next_turn.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_slack_session.py -v 2>&1 | head -20
```

Expected: `ImportError` — `slack_session` doesn't exist yet.

- [ ] **Step 3: Implement `SlackSession`**

```python
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

_IDLE_W1 = 15 * 60   # 15 min → first warning
_IDLE_W2 = 25 * 60   # 25 min → second warning
_IDLE_MAX = 30 * 60  # 30 min → close session

_CHUNK_PAUSE = 3.0   # seconds between forced flushes
_EDIT_WINDOW = 5.0   # seconds within which we edit the last message


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
        if self._idle_timer:
            self._idle_timer.cancel()
        self._idle_timer = threading.Timer(_IDLE_W1, self._on_idle_15)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _on_idle_15(self) -> None:
        if self._closed:
            return
        self._post_new("Session has been idle for 15 minutes. Still there?")
        self._idle_timer = threading.Timer(_IDLE_W2 - _IDLE_W1, self._on_idle_25)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _on_idle_25(self) -> None:
        if self._closed:
            return
        self._post_new("Session timing out in 5 minutes — reply or click to keep it alive")
        self._idle_timer = threading.Timer(_IDLE_MAX - _IDLE_W2, self._on_idle_30)
        self._idle_timer.daemon = True
        self._idle_timer.start()

    def _on_idle_30(self) -> None:
        self._close("Session timed out after 30 minutes of inactivity.")

    # ------------------------------------------------------------------
    # Internal: close
    # ------------------------------------------------------------------

    def _close(self, message: Optional[str]) -> None:
        if self._closed:
            return
        self._closed = True
        if self._idle_timer:
            self._idle_timer.cancel()
        self._backend.close()
        if message:
            self._post_new(message)
        if self._on_close:
            self._on_close()
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_slack_session.py -v
```

Expected: all 9 tests pass.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -20
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
git add tools/slack_session.py tests/test_slack_session.py
git commit -m "feat: add SlackSession with output chunking and idle timeouts"
```

---

## Task 4: `bot_unified.py` Integration

Wire `run:` trigger, `RUN_SESSIONS`, and thread reply routing into the existing bot.

**Critical constraint:** The `run:` prefix check must only fire for **top-level mentions** (events where `thread_ts` is absent or equals `ts`). Thread replies routed through `handle_mention` via the `active_sessions` fallback must NOT trigger `run:` even if the user happened to type "run:" in a thread reply.

**Files:**
- Modify: `bot_unified.py`
- Create: `tests/test_bot_run_trigger.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_bot_run_trigger.py
"""Tests for @Shellack run: trigger and thread reply routing."""
import pytest
from unittest.mock import MagicMock, patch


def _make_event(text, channel="C123", ts="100.0", thread_ts=None):
    event = {"text": text, "channel": channel, "ts": ts}
    if thread_ts:
        event["thread_ts"] = thread_ts
    return event


def test_run_prefix_creates_slack_session():
    """Top-level @Shellack run: creates a SlackSession in RUN_SESSIONS."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):

        event = _make_event("<@BOT> run: investigate the crash")
        bot_unified.handle_mention(event, say=MagicMock())

    assert "100.0" in bot_unified.RUN_SESSIONS
    mock_session.start.assert_called_once()


def test_run_prefix_uses_max_backend_when_configured():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.MaxBackend") as MockMax, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "max"}):

        MockMax.available.return_value = True
        event = _make_event("<@BOT> run: do stuff")
        bot_unified.handle_mention(event, say=MagicMock())

    MockMax.assert_called_once()


def test_thread_run_prefix_does_not_create_session():
    """run: in a thread reply must NOT trigger a new session."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, \
         patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False):

        # Thread reply that starts with "run:" — should NOT create a session
        event = _make_event("<@BOT> run: keep going", ts="101.0", thread_ts="99.0")
        bot_unified.handle_mention(event, say=MagicMock())

    assert bot_unified.RUN_SESSIONS == {}
    mock_proj.assert_called_once()  # routed normally


def test_thread_reply_routes_to_active_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False
    bot_unified.RUN_SESSIONS["99.0"] = mock_session

    event = _make_event("keep going", ts="100.0", thread_ts="99.0")
    bot_unified.handle_message(event, say=MagicMock())

    mock_session.feed_input.assert_called_once_with("keep going")


def test_thread_reply_falls_through_when_no_active_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    event = _make_event("hello", ts="200.0", thread_ts="150.0")
    with patch.object(bot_unified, "handle_mention") as mock_handle:
        bot_unified.handle_message(event, say=MagicMock())

    assert "150.0" not in bot_unified.RUN_SESSIONS


def test_non_run_mention_does_not_create_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, \
         patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False):

        event = _make_event("<@BOT> what files are in Settings?")
        bot_unified.handle_mention(event, say=MagicMock())

    assert bot_unified.RUN_SESSIONS == {}
    mock_proj.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_bot_run_trigger.py -v 2>&1 | head -20
```

Expected: `AttributeError` on `bot_unified.RUN_SESSIONS` — not added yet.

- [ ] **Step 3: Add imports and `RUN_SESSIONS` to `bot_unified.py`**

After the existing imports block at the top of `bot_unified.py`, add:

```python
import re
from tools.session_backend import APIBackend, MaxBackend
from tools.slack_session import SlackSession

# run: session registry — keyed by thread_ts, cleaned up when session closes
RUN_SESSIONS: dict = {}
```

- [ ] **Step 4: Update `handle_mention` to detect `run:` in top-level mentions only**

Replace the `handle_mention` function body in `bot_unified.py` with:

```python
@app.event("app_mention")
def handle_mention(event, say):
    """Route messages to the appropriate handler based on channel."""
    channel_id = event["channel"]
    channel_name = get_channel_name(channel_id)
    ts = event.get("ts", "")
    thread_ts = event.get("thread_ts", ts)

    # Strip bot mention to get clean text
    raw_text = event.get("text", "")
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()

    # --- run: session trigger (top-level mentions only) ---
    # Thread replies (thread_ts != ts) skip this check to avoid accidentally
    # creating a new session when a user types "run:" in a follow-up message.
    is_top_level = (thread_ts == ts)
    if is_top_level and clean_text.lower().startswith("run:"):
        task = clean_text[4:].strip()
        if not task:
            say(text="Usage: `@Shellack run: <task description>`", thread_ts=thread_ts)
            return

        # Pick backend
        backend_mode = os.environ.get("SESSION_BACKEND", "api")
        if backend_mode == "max" and MaxBackend.available():
            backend = MaxBackend()
        else:
            model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
            backend = APIBackend(model=model)

        # Get project context from channel
        from orchestrator_config import CHANNEL_ROUTING, PROJECTS
        routing = CHANNEL_ROUTING.get(channel_name, {})
        project_key = routing.get("project")
        system_prompt = ""
        cwd = "."
        if project_key:
            project = PROJECTS.get(project_key, {})
            cwd = project.get("path", ".")
            claude_md_path = os.path.join(cwd, "CLAUDE.md")
            if os.path.exists(claude_md_path):
                try:
                    with open(claude_md_path) as f:
                        system_prompt = f.read()
                except OSError:
                    pass

        session = SlackSession(
            thread_ts=thread_ts,
            channel_id=channel_id,
            client=app.client,
            backend=backend,
            on_close=lambda: RUN_SESSIONS.pop(thread_ts, None),
        )
        RUN_SESSIONS[thread_ts] = session
        session.start(task, system_prompt, cwd)
        print(f"🚀 run: session started in #{channel_name} thread {thread_ts}")
        return

    # --- existing routing ---
    print(f"📬 Message in #{channel_name}")

    if is_orchestrator_channel(channel_name):
        print("🎯 Routing to orchestrator")
        handle_orchestrator_message(event, say)
    elif is_peer_review_channel(channel_name):
        print("🤝 Routing to peer review")
        handle_peer_review_message(event, say)
    else:
        print("🤖 Routing to project agent")
        handle_project_message(event, say, channel_name)
```

- [ ] **Step 5: Update `handle_message` to route thread replies**

Replace the existing `handle_message` function:

```python
@app.event("message")
def handle_message(event, say):
    """Handle threaded messages — route to active run: session or fall through."""
    thread_ts = event.get("thread_ts")

    # Route to active run: session first
    if thread_ts and thread_ts in RUN_SESSIONS:
        session = RUN_SESSIONS[thread_ts]
        if not session._closed:
            text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
            if text:
                session.feed_input(text)
            return

    # Fall through to existing behavior for active_sessions (quick reply threads)
    if thread_ts and thread_ts in active_sessions:
        handle_mention(event, say)
```

- [ ] **Step 6: Run the new bot tests**

```bash
pytest tests/test_bot_run_trigger.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 7: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass, no regressions.

- [ ] **Step 8: Manual smoke test**

Start the bot:
```bash
cd /path/to/shellack
source venv/bin/activate
SESSION_BACKEND=api python bot_unified.py
```

In Slack, in a project channel:
```
@Shellack run: list the python files in the root directory
```

Expected:
- Response appears in thread within a few seconds
- Typing a follow-up in the thread continues the conversation
- Typing `stop` closes the session
- A regular `@Shellack what is this?` still works normally

- [ ] **Step 9: Commit**

```bash
git add bot_unified.py tests/test_bot_run_trigger.py
git commit -m "feat: wire run: trigger and thread reply routing into bot_unified"
```

---

## Phase 1 Complete

```bash
pytest tests/ -v 2>&1 | tail -5
```

All tests green. Phases 2 (config & onboarding) and 3 (plugin management) are separate plans.
