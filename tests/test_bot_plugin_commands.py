# tests/test_bot_plugin_commands.py
"""Integration tests for @Shellack plugin management commands."""
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


def _make_client():
    client = MagicMock()
    client.chat_postEphemeral = MagicMock()
    return client


def _owner_env():
    """Context manager dict for patching OWNER_SLACK_USER_ID."""
    return {"OWNER_SLACK_USER_ID": _OWNER_ID}


# ---------------------------------------------------------------------------
# plugins — list_all
# ---------------------------------------------------------------------------

def test_plugins_command_calls_list_all():
    """'plugins' command calls plugin_manager.list_all() and posts formatted output."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    list_all_result = {"plugins": ["p1", "p2"], "mcps": ["mcp1"], "bot_plugins": []}

    with patch.object(bot_unified.plugin_manager, "list_all", return_value=list_all_result) as mock_list, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> plugins")
        bot_unified.handle_mention(event, say=say)

    mock_list.assert_called_once()
    say.assert_called_once()
    text = say.call_args[1]["text"]
    assert "p1" in text or "plugins" in text.lower()


# ---------------------------------------------------------------------------
# add plugin
# ---------------------------------------------------------------------------

def test_add_plugin_calls_install_plugin():
    """'add plugin <name>' calls plugin_manager.install_plugin(name) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "install_plugin", return_value={"ok": True, "stdout": "Installed"}) as mock_install, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> add plugin my-plugin")
        bot_unified.handle_mention(event, say=say)

    mock_install.assert_called_once_with("my-plugin")
    say.assert_called_once()


def test_add_plugin_error_posts_ephemeral():
    """'add plugin <name>' on error posts ephemeral message."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "install_plugin", return_value={"ok": False, "error": "Not found"}) as mock_install, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch("bot_unified.app") as mock_app:
        mock_app.client.chat_postEphemeral = MagicMock()
        event = _make_event("<@BOT> add plugin bad-plugin")
        bot_unified.handle_mention(event, say=say)

    mock_install.assert_called_once_with("bad-plugin")
    mock_app.client.chat_postEphemeral.assert_called_once()
    say.assert_not_called()


# ---------------------------------------------------------------------------
# remove plugin
# ---------------------------------------------------------------------------

def test_remove_plugin_calls_uninstall_plugin():
    """'remove plugin <name>' calls plugin_manager.uninstall_plugin(name) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "uninstall_plugin", return_value={"ok": True, "stdout": "Removed"}) as mock_uninstall, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> remove plugin my-plugin")
        bot_unified.handle_mention(event, say=say)

    mock_uninstall.assert_called_once_with("my-plugin")
    say.assert_called_once()


# ---------------------------------------------------------------------------
# add mcp
# ---------------------------------------------------------------------------

def test_add_mcp_calls_add_mcp():
    """'add mcp <name> <cmd>' calls plugin_manager.add_mcp(name, cmd) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "add_mcp", return_value={"ok": True, "stdout": "Added"}) as mock_add, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> add mcp my-server npx my-server")
        bot_unified.handle_mention(event, say=say)

    mock_add.assert_called_once_with("my-server", "npx my-server")
    say.assert_called_once()


# ---------------------------------------------------------------------------
# remove mcp
# ---------------------------------------------------------------------------

def test_remove_mcp_calls_remove_mcp():
    """'remove mcp <name>' calls plugin_manager.remove_mcp(name) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "remove_mcp", return_value={"ok": True, "stdout": "Removed"}) as mock_remove, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> remove mcp my-server")
        bot_unified.handle_mention(event, say=say)

    mock_remove.assert_called_once_with("my-server")
    say.assert_called_once()


# ---------------------------------------------------------------------------
# add bot-plugin
# ---------------------------------------------------------------------------

def test_add_bot_plugin_calls_add_bot_plugin():
    """'add bot-plugin <name>' calls plugin_manager.add_bot_plugin(name, registry=...) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    mock_module = MagicMock()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "add_bot_plugin", return_value={"ok": True, "name": "cool-ext", "module": mock_module}) as mock_add, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> add bot-plugin cool-ext")
        bot_unified.handle_mention(event, say=say)

    mock_add.assert_called_once_with("cool-ext", registry=bot_unified._bot_extensions)
    say.assert_called_once()


# ---------------------------------------------------------------------------
# remove bot-plugin
# ---------------------------------------------------------------------------

def test_remove_bot_plugin_calls_remove_bot_plugin():
    """'remove bot-plugin <name>' calls plugin_manager.remove_bot_plugin(name, registry=...) and posts success."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "remove_bot_plugin", return_value={"ok": True}) as mock_remove, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"):
        event = _make_event("<@BOT> remove bot-plugin cool-ext")
        bot_unified.handle_mention(event, say=say)

    mock_remove.assert_called_once_with("cool-ext", registry=bot_unified._bot_extensions)
    say.assert_called_once()


# ---------------------------------------------------------------------------
# Error path — ephemeral on failure
# ---------------------------------------------------------------------------

def test_add_mcp_error_posts_ephemeral():
    """On error, _handle_plugin_command posts ephemeral message and does not call say."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", _owner_env()), \
         patch.object(bot_unified.plugin_manager, "add_mcp", return_value={"ok": False, "error": "Something went wrong"}) as mock_add, \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch("bot_unified.app") as mock_app:
        mock_app.client.chat_postEphemeral = MagicMock()
        event = _make_event("<@BOT> add mcp broken-server broken-cmd")
        bot_unified.handle_mention(event, say=say)

    mock_add.assert_called_once()
    mock_app.client.chat_postEphemeral.assert_called_once()
    say.assert_not_called()


# ---------------------------------------------------------------------------
# Owner gate — non-owner blocked from all mutating commands
# ---------------------------------------------------------------------------

_MUTATING_COMMANDS = [
    "add plugin evil-pkg",
    "remove plugin legit-pkg",
    "add mcp evil-server evil-cmd",
    "remove mcp legit-server",
    "add bot-plugin evil-ext",
    "remove bot-plugin legit-ext",
]


@pytest.mark.parametrize("command", _MUTATING_COMMANDS)
def test_non_owner_blocked_from_mutating_plugin_commands(command):
    """Non-owner user is blocked from every mutating plugin command."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", {"OWNER_SLACK_USER_ID": _OWNER_ID}), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch("bot_unified.app") as mock_app:
        mock_app.client.chat_postEphemeral = MagicMock()
        event = _make_event(f"<@BOT> {command}", user=_NON_OWNER_ID)
        bot_unified.handle_mention(event, say=say)

    # Command was consumed (returned True) but blocked
    say.assert_not_called()
    mock_app.client.chat_postEphemeral.assert_called_once()
    ephemeral_text = mock_app.client.chat_postEphemeral.call_args[1]["text"]
    assert "restricted" in ephemeral_text.lower() or "owner" in ephemeral_text.lower()


@pytest.mark.parametrize("command", _MUTATING_COMMANDS)
def test_owner_allowed_mutating_plugin_commands(command):
    """Owner user passes the gate for all mutating plugin commands."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", {"OWNER_SLACK_USER_ID": _OWNER_ID}), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch.object(bot_unified.plugin_manager, "install_plugin", return_value={"ok": True, "stdout": "ok"}), \
         patch.object(bot_unified.plugin_manager, "uninstall_plugin", return_value={"ok": True, "stdout": "ok"}), \
         patch.object(bot_unified.plugin_manager, "add_mcp", return_value={"ok": True, "stdout": "ok"}), \
         patch.object(bot_unified.plugin_manager, "remove_mcp", return_value={"ok": True, "stdout": "ok"}), \
         patch.object(bot_unified.plugin_manager, "add_bot_plugin", return_value={"ok": True, "name": "ext", "module": MagicMock()}), \
         patch.object(bot_unified.plugin_manager, "remove_bot_plugin", return_value={"ok": True}):
        event = _make_event(f"<@BOT> {command}", user=_OWNER_ID)
        bot_unified.handle_mention(event, say=say)

    # Owner goes through — say is called (success message)
    say.assert_called_once()


def test_plugins_list_allowed_for_non_owner():
    """The 'plugins' list command works for any user, even non-owner."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    with patch.dict("os.environ", {"OWNER_SLACK_USER_ID": _OWNER_ID}), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch.object(bot_unified.plugin_manager, "list_all", return_value={"plugins": [], "mcps": [], "bot_plugins": []}):
        event = _make_event("<@BOT> plugins", user=_NON_OWNER_ID)
        bot_unified.handle_mention(event, say=say)

    say.assert_called_once()


@pytest.mark.parametrize("command", _MUTATING_COMMANDS)
def test_owner_env_unset_blocks_all_users(command):
    """When OWNER_SLACK_USER_ID is not set, mutating commands are fail-closed (blocked)."""
    import bot_unified
    importlib.reload(bot_unified)

    say = _make_say()
    env = {k: v for k, v in os.environ.items() if k != "OWNER_SLACK_USER_ID"}
    with patch.dict("os.environ", env, clear=True), \
         patch("bot_unified.get_channel_name", return_value="shellack-dev"), \
         patch("bot_unified.app") as mock_app:
        mock_app.client.chat_postEphemeral = MagicMock()
        event = _make_event(f"<@BOT> {command}", user="U_ANYONE")
        bot_unified.handle_mention(event, say=say)

    # Fail-closed: no owner configured => blocked
    say.assert_not_called()
    mock_app.client.chat_postEphemeral.assert_called_once()
    ephemeral_text = mock_app.client.chat_postEphemeral.call_args[1]["text"]
    assert "not configured" in ephemeral_text.lower() or "disabled" in ephemeral_text.lower()
