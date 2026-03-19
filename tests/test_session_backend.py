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
