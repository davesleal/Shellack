# tests/test_onboarding.py
"""Tests for first-run onboarding flow."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def test_onboarding_skipped_when_complete():
    """check_and_post_onboarding does nothing when ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    with patch.dict("os.environ", {"ONBOARDING_COMPLETE": "true"}), \
         patch.object(bot_unified.app.client, "chat_postMessage") as mock_post:
        bot_unified.check_and_post_onboarding()
    mock_post.assert_not_called()


def test_onboarding_posts_buttons_when_not_complete():
    """check_and_post_onboarding posts Block Kit buttons when flag is absent."""
    import bot_unified
    importlib.reload(bot_unified)
    mock_channel_list = {
        "channels": [{"id": "C999", "name": "alpha-dev"}]
    }
    # Use patch.dict to ensure ONBOARDING_COMPLETE is absent from the environment
    env_without_flag = {k: v for k, v in __import__("os").environ.items() if k != "ONBOARDING_COMPLETE"}
    with patch.dict("os.environ", {**env_without_flag, "ONBOARDING_CHANNEL": "alpha-dev"}, clear=True), \
         patch.object(bot_unified.app.client, "conversations_list", return_value=mock_channel_list), \
         patch.object(bot_unified.app.client, "chat_postMessage") as mock_post:
        bot_unified.check_and_post_onboarding()
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["channel"] == "C999"
    assert "blocks" in call_kwargs


def test_mode_select_max_completes_onboarding():
    """Clicking Max button sets SESSION_BACKEND=max and ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    ack = MagicMock()
    body = {"message": {"ts": "123.0"}, "channel": {"id": "C999"}}
    action = {"value": "max"}
    client = MagicMock()
    with patch("bot_unified.set_env_var") as mock_set:
        bot_unified.handle_onboarding_mode_select(ack, body, action, client)
    ack.assert_called_once()
    calls = {c[0][0]: c[0][1] for c in mock_set.call_args_list}
    assert calls.get("SESSION_BACKEND") == "max"
    assert calls.get("ONBOARDING_COMPLETE") == "true"


def test_model_select_completes_api_onboarding():
    """Clicking a model button sets SESSION_MODEL and ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    ack = MagicMock()
    body = {"message": {"ts": "123.0"}, "channel": {"id": "C999"}}
    action = {"value": "claude-sonnet-4-6"}
    client = MagicMock()
    with patch("bot_unified.set_env_var") as mock_set:
        bot_unified.handle_onboarding_model_select(ack, body, action, client)
    ack.assert_called_once()
    calls = {c[0][0]: c[0][1] for c in mock_set.call_args_list}
    assert calls.get("SESSION_MODEL") == "claude-sonnet-4-6"
    assert calls.get("ONBOARDING_COMPLETE") == "true"
