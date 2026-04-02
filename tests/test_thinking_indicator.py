# tests/test_thinking_indicator.py
"""Tests for ThinkingIndicator Slack message contract."""

import pytest
import time
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
    ind.done(think_block="Some reasoning.")
    _, kwargs = client.chat_update.call_args
    assert kwargs["text"] == ""
    assert kwargs["attachments"][0]["color"] == "#888888"


def test_done_with_think_block(client):
    """done() posts think block as separate message, not in the attachment."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(
        think_block="Let me check the files.\nFound 3 modules.", cost_summary="$0.01"
    )

    # Attachment should be JUST the header — no reasoning
    call_kwargs = client.chat_update.call_args[1]
    body = call_kwargs["attachments"][0]["text"]
    assert "Churned for" in body
    assert "$0.01" in body
    assert "Let me check the files" not in body

    # Reasoning posted as separate message
    client.chat_postMessage.assert_called_once()
    post_text = client.chat_postMessage.call_args[1]["text"]
    assert "💭 Reasoning" in post_text
    assert "Let me check the files" in post_text


def test_done_without_think_block(client):
    """done() with no think block shows only churned header."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(think_block="", cost_summary="$0.01")

    call_kwargs = client.chat_update.call_args[1]
    body = call_kwargs["attachments"][0]["text"]
    assert "Churned for" in body
    assert "\U0001f4ad" not in body


def test_update_interval_is_one_second():
    """_UPDATE_INTERVAL should be 1.0, not 5.0."""
    from tools.thinking_indicator import _UPDATE_INTERVAL

    assert _UPDATE_INTERVAL == 1.0


def test_done_without_ts_is_noop(client):
    ind = _make_indicator(client)
    # Never called start(), so _ts is None
    ind.done(think_block="something")
    client.chat_update.assert_not_called()


def test_done_fallback_on_update_failure(client):
    """If chat_update fails, reasoning still posts as separate message."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    client.chat_update.side_effect = Exception("update failed")

    ind.done(think_block="Some reasoning")

    # chat_update failed but reasoning should still post
    assert client.chat_update.call_count == 1
    client.chat_postMessage.assert_called_once()


def test_done_with_cost_summary(client):
    """Cost summary appears in the churned header line."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(think_block="", cost_summary="$0.0140 (2.1k in \u00b7 890 out)")
    att = client.chat_update.call_args[1]["attachments"][0]
    assert "$0.0140" in att["text"]
    assert "Churned" in att["text"]


def test_done_without_cost_summary_no_dot(client):
    """When no cost_summary, the header should not contain a dot separator."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done()
    att = client.chat_update.call_args[1]["attachments"][0]
    header_line = att["text"].split("\n")[0]
    assert "\u00b7" not in header_line


def test_done_total_failure_does_not_crash(client):
    """If everything fails, done() must not raise."""
    ind = _make_indicator(client)
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    client.chat_update.side_effect = Exception("total failure")

    # Must not raise
    ind.done(think_block="some text")
