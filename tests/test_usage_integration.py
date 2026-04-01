# tests/test_usage_integration.py
"""Tests that usage_tracker is called at the right integration points."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def test_run_session_close_records_session():
    """When a run: session closes, usage_tracker.record_session is called."""
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch.object(bot_unified.usage_tracker, "record_session") as mock_record, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):

        event = {"text": "<@BOT> run: do the thing", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_mention(event, say=MagicMock())

        # Simulate session close by calling the on_close callback
        on_close_fn = bot_unified.SlackSession.call_args[1]["on_close"]
        on_close_fn()

    mock_record.assert_called_once_with(
        "api", "claude-sonnet-4-6"
    )


def test_project_message_records_mention():
    """handle_project_message calls usage_tracker.record_mention with SESSION_MODEL."""
    import bot_unified
    importlib.reload(bot_unified)

    mock_app = MagicMock()
    mock_app.client.reactions_add = MagicMock()
    mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "101.0"})
    mock_app.client.chat_delete = MagicMock()
    mock_app.client.reactions_remove = MagicMock()

    fake_routing = {"alpha-dev": {"mode": "dedicated", "project": "alpha", "channel_id": "C_ALPHA"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp", "language": "python"}}

    with patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.app", mock_app), \
         patch("bot_unified.CHANNEL_ROUTING", fake_routing), \
         patch("bot_unified.PROJECTS", fake_projects), \
         patch("bot_unified.ThinkingIndicator") as mock_indicator_cls, \
         patch.object(bot_unified.usage_tracker, "record_mention") as mock_record, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):
        mock_indicator_cls.return_value = MagicMock()
        mock_factory.get_agent.return_value.handle.return_value = ("done", "AlphaAgent")
        event = {"text": "hello", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="alpha-dev")

    mock_record.assert_called_once_with("api", "claude-sonnet-4-6")
