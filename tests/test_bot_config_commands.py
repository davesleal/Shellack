# tests/test_bot_config_commands.py
"""Tests for @Shellack set mode, set model, usage, config commands."""
import importlib
import os
import pytest
from unittest.mock import MagicMock, patch

_OWNER_ID = "U_OWNER"
_NON_OWNER_ID = "U_INTRUDER"


def _make_say():
    return MagicMock()


def _make_event(text, ts="100.0", thread_ts=None, user=_OWNER_ID):
    e = {"text": text, "channel": "C123", "ts": ts, "user": user}
    if thread_ts:
        e["thread_ts"] = thread_ts
    return e


def _owner_env(**extra):
    d = {"OWNER_SLACK_USER_ID": _OWNER_ID}
    d.update(extra)
    return d


# ---------------------------------------------------------------------------
# Happy-path config commands (owner authenticated)
# ---------------------------------------------------------------------------

def test_set_mode_max_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch("bot_unified.shutil.which", return_value="/usr/local/bin/claude"), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> set mode max")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "max")
    say.assert_called_once()
    assert "max" in say.call_args[1]["text"].lower()


def test_set_mode_api_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> set mode api")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "api")


def test_set_model_sonnet_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> set model sonnet")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_MODEL", "claude-sonnet-4-6")


def test_usage_command_posts_stats():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.usage_tracker, "format_usage_message", return_value="stats"), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> usage")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "stats" in say.call_args[1]["text"]


def test_set_mode_max_fails_when_claude_not_found():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch("bot_unified.shutil.which", return_value=None), \
         patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> set mode max")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_not_called()
    say.assert_called_once()
    assert "claude" in say.call_args[1]["text"].lower()


def test_config_command_posts_settings():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch.dict("os.environ", _owner_env(SESSION_BACKEND="api", SESSION_MODEL="claude-sonnet-4-6")):
        event = _make_event("<@BOT> config")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "api" in say.call_args[1]["text"].lower()


# ---------------------------------------------------------------------------
# Owner gate — config commands restricted to owner
# ---------------------------------------------------------------------------

_RESTRICTED_CONFIG_COMMANDS = [
    "set mode api",
    "set model sonnet",
    "set triage on",
]


@pytest.mark.parametrize("command", _RESTRICTED_CONFIG_COMMANDS)
def test_non_owner_blocked_from_config_commands(command):
    """Non-owner user is blocked from set mode, set model, set triage."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", {"OWNER_SLACK_USER_ID": _OWNER_ID}), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event(f"<@BOT> {command}", user=_NON_OWNER_ID)
        bot_unified.handle_mention(event, say=say)

    say.assert_called_once()
    text = say.call_args[0][0] if say.call_args[0] else say.call_args[1].get("text", "")
    assert "restricted" in text.lower() or "owner" in text.lower()


@pytest.mark.parametrize("command", _RESTRICTED_CONFIG_COMMANDS)
def test_owner_allowed_config_commands(command):
    """Owner user passes the gate for config commands."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", {"OWNER_SLACK_USER_ID": _OWNER_ID}), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch("bot_unified.set_env_var"):
        event = _make_event(f"<@BOT> {command}", user=_OWNER_ID)
        bot_unified.handle_mention(event, say=say)

    say.assert_called_once()
    text = say.call_args[0][0] if say.call_args[0] else say.call_args[1].get("text", "")
    assert "restricted" not in text.lower()


@pytest.mark.parametrize("command", _RESTRICTED_CONFIG_COMMANDS)
def test_config_owner_env_unset_blocks_all_users(command):
    """When OWNER_SLACK_USER_ID is not set, config commands are fail-closed (blocked)."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    env = {k: v for k, v in os.environ.items() if k != "OWNER_SLACK_USER_ID"}
    with patch.dict("os.environ", env, clear=True), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event(f"<@BOT> {command}", user="U_ANYONE")
        bot_unified.handle_mention(event, say=say)

    say.assert_called_once()
    text = say.call_args[0][0] if say.call_args[0] else say.call_args[1].get("text", "")
    assert "not configured" in text.lower() or "disabled" in text.lower()


# ---------------------------------------------------------------------------
# Feature toggle commands — config <feature> on/off
# ---------------------------------------------------------------------------

_TEST_PROJECT = {
    "name": "Alpha",
    "channel_id": "C123",
    "path": "/tmp/alpha",
    "features": {"token-cart": True, "gut-check": True, "registry": False},
}


def _feature_env():
    return {"OWNER_SLACK_USER_ID": _OWNER_ID}


def _patch_project(project_dict):
    """Patch PROJECTS and CHANNEL_ROUTING so config commands resolve a project."""
    return (
        patch("bot_unified.PROJECTS", {"alpha": project_dict}),
        patch("bot_unified.CHANNEL_ROUTING", {"shellack-dev": {"project": "alpha"}}),
    )


def test_config_feature_toggle_on():
    """@Shellack config token-cart off disables token cart."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    project = {**_TEST_PROJECT, "features": {**_TEST_PROJECT["features"]}}
    p_projects, p_routing = _patch_project(project)
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         p_projects, p_routing:
        event = _make_event("<@BOT> config token-cart off")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "off" in text
    assert "token-cart" in text
    assert project["features"]["token-cart"] is False


def test_config_feature_toggle_enables():
    """@Shellack config registry on enables the feature."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    project = {**_TEST_PROJECT, "features": {**_TEST_PROJECT["features"]}}
    p_projects, p_routing = _patch_project(project)
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         p_projects, p_routing:
        event = _make_event("<@BOT> config registry on")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "on" in text
    assert project["features"]["registry"] is True


def test_config_feature_toggle_invalid():
    """Invalid feature name returns error."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    project = {**_TEST_PROJECT, "features": {**_TEST_PROJECT["features"]}}
    p_projects, p_routing = _patch_project(project)
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         p_projects, p_routing:
        event = _make_event("<@BOT> config foobar off")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "unknown feature" in text.lower()


def test_config_show_lists_features():
    """@Shellack config show lists all feature flags."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    project = {**_TEST_PROJECT, "features": {**_TEST_PROJECT["features"]}}
    p_projects, p_routing = _patch_project(project)
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         p_projects, p_routing:
        event = _make_event("<@BOT> config show")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "token-cart" in text
    assert "gut-check" in text
    assert "registry" in text
    assert "Alpha" in text


def test_config_feature_no_project():
    """Feature toggle in unmapped channel returns error."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="random-channel"), \
         patch("bot_unified.PROJECTS", {}), \
         patch("bot_unified.CHANNEL_ROUTING", {}):
        event = _make_event("<@BOT> config token-cart on")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "no project" in text.lower()


def test_config_feature_non_owner_blocked():
    """Non-owner cannot toggle features."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> config token-cart off", user=_NON_OWNER_ID)
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    text = say.call_args[0][0] if say.call_args[0] else say.call_args[1].get("text", "")
    assert "restricted" in text.lower() or "owner" in text.lower()


def test_config_feature_creates_features_dict():
    """Toggle works even if project has no features dict yet."""
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    project = {"name": "Beta", "channel_id": "C123", "path": "/tmp/beta"}
    p_projects, p_routing = _patch_project(project)
    with patch.dict("os.environ", _feature_env()), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         p_projects, p_routing:
        event = _make_event("<@BOT> config gut-check on")
        bot_unified.handle_mention(event, say=say)
    assert project["features"]["gut-check"] is True
