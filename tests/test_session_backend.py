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


# ---------------------------------------------------------------------------
# MaxBackend
# ---------------------------------------------------------------------------


def _make_proc(lines, returncode=0):
    """Return a mock Popen process whose stdout yields JSONL lines."""
    proc = MagicMock()
    # Wrap the iterator in a MagicMock so .close() and .read() are available
    # while __iter__ still yields the lines.
    stdout_mock = MagicMock()
    stdout_mock.__iter__ = MagicMock(return_value=iter(lines))
    stdout_mock.read.return_value = ""
    proc.stdout = stdout_mock
    proc.wait = MagicMock(return_value=returncode)
    proc.returncode = returncode
    proc.stderr = MagicMock()
    proc.stderr.read.return_value = ""
    return proc


_ASSISTANT_EVENT = json.dumps(
    {
        "type": "assistant",
        "message": {"content": [{"type": "text", "text": "Hello from Max"}]},
        "session_id": "test-session-abc",
    }
)
_RESULT_EVENT = json.dumps(
    {
        "type": "result",
        "subtype": "success",
        "result": "Hello from Max",
        "session_id": "test-session-abc",
    }
)


def test_max_backend_first_turn_yields_text():
    from tools.session_backend import MaxBackend

    with patch("tools.session_backend.subprocess.Popen") as MockPopen:
        MockPopen.return_value = _make_proc(
            [
                _ASSISTANT_EVENT + "\n",
                _RESULT_EVENT + "\n",
            ]
        )
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
        MockPopen.return_value = _make_proc(
            [
                rate_limit_event + "\n",
                system_event + "\n",
                _ASSISTANT_EVENT + "\n",
            ]
        )
        backend = MaxBackend()
        chunks = list(backend.first_turn("task"))
    assert chunks == ["Hello from Max"]


def test_max_backend_available_false_when_no_claude():
    from tools.session_backend import MaxBackend

    with patch("tools.session_backend.shutil.which", return_value=None):
        assert MaxBackend.available() is False


def test_max_backend_available_true_when_claude_exists():
    from tools.session_backend import MaxBackend

    with patch(
        "tools.session_backend.shutil.which", return_value="/usr/local/bin/claude"
    ):
        assert MaxBackend.available() is True
