# tests/test_bot_run_trigger.py
"""Tests for @Shellack run: trigger, thread reply routing, and error handling."""

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

    with patch("bot_unified.SlackSession", return_value=mock_session), patch(
        "bot_unified.APIBackend"
    ), patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch.dict(
        "os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}
    ):

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

    with patch("bot_unified.SlackSession", return_value=mock_session), patch(
        "bot_unified.MaxBackend"
    ) as MockMax, patch(
        "bot_unified.get_channel_name", return_value="shellack-dev"
    ), patch.dict(
        "os.environ", {"SESSION_BACKEND": "max"}
    ):

        MockMax.available.return_value = True
        event = _make_event("<@BOT> run: do stuff")
        bot_unified.handle_mention(event, say=MagicMock())

    MockMax.assert_called_once()


def test_thread_run_prefix_does_not_create_session():
    """run: in a thread reply must NOT trigger a new session."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, patch(
        "bot_unified.get_channel_name", return_value="alpha-dev"
    ), patch("bot_unified.is_orchestrator_channel", return_value=False), patch(
        "bot_unified.is_peer_review_channel", return_value=False
    ):

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

    with patch("bot_unified.handle_project_message") as mock_proj, patch(
        "bot_unified.get_channel_name", return_value="alpha-dev"
    ), patch("bot_unified.is_orchestrator_channel", return_value=False), patch(
        "bot_unified.is_peer_review_channel", return_value=False
    ):

        event = _make_event("<@BOT> what files are in Settings?")
        bot_unified.handle_mention(event, say=MagicMock())

    assert bot_unified.RUN_SESSIONS == {}
    mock_proj.assert_called_once()


# ---------------------------------------------------------------------------
# Error sanitization — agent exceptions must NOT leak to Slack
# ---------------------------------------------------------------------------


def test_agent_error_does_not_leak_exception_text():
    """When the agent raises, the error posted to Slack must NOT contain the exception message."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    secret_error = "ANTHROPIC_API_KEY=sk-ant-secret123 connection refused"

    # Set up channel routing so handle_project_message reaches the agent
    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha"}}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.agent_factory"
    ) as mock_factory, patch(
        "bot_unified.ThinkingIndicator"
    ) as MockIndicator, patch(
        "bot_unified.app"
    ) as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.side_effect = RuntimeError(secret_error)
        mock_factory.get_agent.return_value = mock_agent

        mock_indicator = MagicMock()
        MockIndicator.return_value = mock_indicator

        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()
        mock_app.client.chat_postMessage = MagicMock()

        event = _make_event("<@BOT> explain the auth system", channel="C123")
        event["user"] = "U_USER"
        bot_unified.handle_mention(event, say=MagicMock())

    # Verify chat_postMessage was called with a generic error
    mock_app.client.chat_postMessage.assert_called_once()
    posted_text = mock_app.client.chat_postMessage.call_args[1]["text"]
    # The secret error text must NOT appear in the posted message
    assert secret_error not in posted_text
    assert "sk-ant-secret123" not in posted_text
    # It should be a generic message
    assert "error occurred" in posted_text.lower() or "try again" in posted_text.lower()
