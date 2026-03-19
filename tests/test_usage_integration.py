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
         patch("bot_unified.get_channel_name", return_value="dayist-dev"), \
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
    """handle_project_message calls usage_tracker.record_mention."""
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.agent_factory") as mock_factory, \
         patch.object(bot_unified.usage_tracker, "record_mention") as mock_record, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):
        mock_factory.get_agent.return_value.handle.return_value = ("done", "DayistAgent")
        event = {"text": "hello", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

    mock_record.assert_called_once()
