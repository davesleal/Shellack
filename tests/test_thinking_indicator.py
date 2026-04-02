# tests/test_thinking_indicator.py
"""Tests for ThinkingIndicator Slack message contract."""
import pytest
from unittest.mock import MagicMock, call, patch
import threading


@pytest.fixture
def client():
    c = MagicMock()
    c.chat_postMessage.return_value = {"ts": "100.0"}
    c.chat_update.return_value = {"ts": "100.0"}
    return c


def _make_indicator(client):
    from tools.thinking_indicator import ThinkingIndicator
    return ThinkingIndicator(client, "C1", "99.0")


def test_start_posts_with_empty_text(client):
    ind = _make_indicator(client)
    with patch("tools.thinking_indicator.threading.Thread"):
        ind.start()
    _, kwargs = client.chat_postMessage.call_args
    assert kwargs["text"] == ""
    assert kwargs["attachments"][0]["color"] == "#C17F4E"


def test_start_attachment_has_fallback(client):
    ind = _make_indicator(client)
    with patch("tools.thinking_indicator.threading.Thread"):
        ind.start()
    att = client.chat_postMessage.call_args[1]["attachments"][0]
    assert "fallback" in att
    assert att["fallback"]  # non-empty, used for notifications


def test_done_updates_with_empty_text(client):
    ind = _make_indicator(client)
    with patch("tools.thinking_indicator.threading.Thread"):
        ind.start()
    ind._stop.set()
    ind.done(response="All done.")
    _, kwargs = client.chat_update.call_args
    assert kwargs["text"] == ""
    assert kwargs["attachments"][0]["color"] == "#888888"


def test_done_folds_response_into_attachment(client):
    ind = _make_indicator(client)
    with patch("tools.thinking_indicator.threading.Thread"):
        ind.start()
    ind._stop.set()
    ind.done(response="Here is the answer.")
    att = client.chat_update.call_args[1]["attachments"][0]
    assert "Here is the answer." in att["text"]
    assert "✻ Churned" in att["text"]


def test_done_without_ts_is_noop(client):
    ind = _make_indicator(client)
    # Never called start(), so _ts is None
    ind.done(response="something")
    client.chat_update.assert_not_called()


def test_done_fallback_posts_response_separately_on_update_failure(client):
    """If chat_update fails with response text, fallback posts response as separate message."""
    import time
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    # First chat_update (the done call) raises, fallback header update succeeds
    client.chat_update.side_effect = [Exception("update failed"), None]

    ind.done(response="The answer is 42")

    # Should have tried to post response separately
    post_calls = [c for c in client.chat_postMessage.call_args_list
                  if c.kwargs.get("text") == "The answer is 42"]
    assert len(post_calls) == 1


def test_done_with_cost_summary(client):
    """Cost summary appears in the churned header line."""
    import time
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(response="Answer here.", cost_summary="$0.0140 (2.1k in · 890 out)")
    att = client.chat_update.call_args[1]["attachments"][0]
    assert "$0.0140" in att["text"]
    assert "Churned" in att["text"]
    assert "Answer here." in att["text"]


def test_done_without_cost_summary_no_dot(client):
    """When no cost_summary, the header should not contain a dot separator."""
    import time
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(response="Answer.")
    att = client.chat_update.call_args[1]["attachments"][0]
    header_line = att["text"].split("\n")[0]
    assert "·" not in header_line


def test_done_total_failure_does_not_crash(client):
    """If everything fails, done() must not raise."""
    import time
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    client.chat_update.side_effect = Exception("total failure")
    # Reset postMessage to also fail (after the initial fixture setup)
    client.chat_postMessage.side_effect = Exception("post also fails")

    # Must not raise
    ind.done(response="some text")
