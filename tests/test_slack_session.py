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
