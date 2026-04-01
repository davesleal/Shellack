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
