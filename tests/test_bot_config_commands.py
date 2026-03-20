# tests/test_bot_config_commands.py
"""Tests for @Shellack set mode, set model, usage, config commands."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def _make_say():
    return MagicMock()


def _make_event(text, ts="100.0", thread_ts=None):
    e = {"text": text, "channel": "C123", "ts": ts}
    if thread_ts:
        e["thread_ts"] = thread_ts
    return e


def test_set_mode_max_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.shutil.which", return_value="/usr/local/bin/claude"), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set mode max")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "max")
    say.assert_called_once()
    assert "max" in say.call_args[1]["text"].lower()


def test_set_mode_api_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set mode api")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "api")


def test_set_model_sonnet_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set model sonnet")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_MODEL", "claude-sonnet-4-6")


def test_usage_command_posts_stats():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.object(bot_unified.usage_tracker, "format_usage_message", return_value="stats"), \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> usage")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "stats" in say.call_args[1]["text"]


def test_set_mode_max_fails_when_claude_not_found():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.shutil.which", return_value=None), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set mode max")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_not_called()
    say.assert_called_once()
    assert "claude" in say.call_args[1]["text"].lower()


def test_config_command_posts_settings():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):
        event = _make_event("<@BOT> config")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "api" in say.call_args[1]["text"].lower()
