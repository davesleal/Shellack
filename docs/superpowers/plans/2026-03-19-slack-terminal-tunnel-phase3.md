# Phase 3 — Plugin Management

**Date:** 2026-03-19
**Author:** Maestro (Claude)
**Status:** Ready to implement

---

## Goal

Add plugin management commands to Shellack so the operator can install, remove, and list Claude Code plugins, MCP servers, and Shellack bot extensions — all from Slack, without touching a terminal.

---

## Architecture

Three plugin namespaces under one unified interface:

1. **Claude Code Plugins** — thin wrappers around `claude plugin install/uninstall`
2. **MCP Servers** — thin wrappers around `claude mcp add/remove`
3. **Shellack Bot Extensions** — git-clone from GitHub into `extensions/<name>/`, hot-reload via `importlib`

All shell operations use `subprocess.run([...], capture_output=True, text=True, timeout=60)` — never `shell=True`. Bot extensions are tracked in a module-level `_bot_extensions: dict` registry in `bot_unified.py`. Error messages are sent ephemerally to the triggering user only.

Plugin/MCP changes apply on the next `run:` session. Bot extensions hot-reload immediately after `add bot-plugin`.

---

## Tech Stack

- Python 3.11+
- `subprocess` — shelling out to `claude` CLI
- `subprocess` — `git clone` for bot-plugin installs
- `importlib.import_module` + `importlib.reload` — hot-reload of bot extensions
- `shutil.rmtree` — bot-plugin removal
- `json` — reading `~/.claude/settings.json` for MCP listing
- Slack Bolt — `client.chat_postEphemeral` for error messages
- `pytest` + `unittest.mock` — all tests

---

## File Structure

| File | Purpose |
|------|---------|
| `tools/plugin_manager.py` | `PluginManager` class — all three namespaces |
| `tests/test_plugin_manager.py` | Unit tests for `PluginManager` |
| `bot_unified.py` | Wire plugin commands into `_handle_plugin_command`, register `_bot_extensions` dict |
| `tests/test_bot_plugin_commands.py` | Integration tests for plugin bot commands |
| `extensions/` | Directory created at runtime; holds hot-loaded bot extensions |

---

## Task 1 — `PluginManager` class + unit tests

### 1.1 Write the failing tests first

**File:** `tests/test_plugin_manager.py`

```python
# tests/test_plugin_manager.py
"""Unit tests for PluginManager — all three namespaces."""
import importlib
import json
import os
import sys
import types
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_completed(returncode=0, stdout="", stderr=""):
    m = MagicMock()
    m.returncode = returncode
    m.stdout = stdout
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# import PluginManager after each test that modifies sys.modules
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_plugin_manager():
    """Reload plugin_manager before each test to reset module state."""
    import tools.plugin_manager
    importlib.reload(tools.plugin_manager)
    yield tools.plugin_manager


# ===========================================================================
# Claude Code Plugin tests
# ===========================================================================

class TestInstallPlugin:
    def test_success_returns_ok(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0, "installed")) as mock_run:
            result = pm.install_plugin("my-plugin")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "plugin", "install", "my-plugin"],
            capture_output=True, text=True, timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(1, stderr="not found")):
            result = pm.install_plugin("bad-plugin")
        assert result["ok"] is False
        assert "not found" in result["error"]

    def test_claude_not_found_raises_friendly_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pm.install_plugin("any-plugin")
        assert result["ok"] is False
        assert "claude CLI not found" in result["error"]


class TestUninstallPlugin:
    def test_success(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run:
            result = pm.uninstall_plugin("my-plugin")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "plugin", "uninstall", "my-plugin"],
            capture_output=True, text=True, timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(1, stderr="unknown plugin")):
            result = pm.uninstall_plugin("ghost-plugin")
        assert result["ok"] is False

    def test_claude_not_found(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pm.uninstall_plugin("any")
        assert "claude CLI not found" in result["error"]


# ===========================================================================
# MCP Server tests
# ===========================================================================

class TestAddMcp:
    def test_success(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run:
            result = pm.add_mcp("my-server", "npx my-server")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "mcp", "add", "my-server", "npx my-server"],
            capture_output=True, text=True, timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(1, stderr="bad command")):
            result = pm.add_mcp("x", "bad")
        assert result["ok"] is False
        assert "bad command" in result["error"]

    def test_claude_not_found(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", side_effect=FileNotFoundError):
            result = pm.add_mcp("x", "cmd")
        assert "claude CLI not found" in result["error"]


class TestRemoveMcp:
    def test_success(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run:
            result = pm.remove_mcp("my-server")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "mcp", "remove", "my-server"],
            capture_output=True, text=True, timeout=60,
        )

    def test_failure(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(1, stderr="not found")):
            result = pm.remove_mcp("ghost")
        assert result["ok"] is False


# ===========================================================================
# Bot-plugin (Shellack extension) tests
# ===========================================================================

class TestAddBotPlugin:
    def test_official_org_builds_correct_url(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.hello")
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run, \
             patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("hello")
        assert result["ok"] is True
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0] == [
            "git", "clone",
            "https://github.com/Shellack-plugins/hello",
            str(tmp_path / "hello"),
        ]

    def test_full_https_url_used_verbatim(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myrepo")
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run, \
             patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("https://github.com/user/myrepo")
        assert result["ok"] is True
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0][2] == "https://github.com/user/myrepo"

    def test_bare_name_not_https_goes_to_official_org(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myplugin")
        with patch("subprocess.run", return_value=_make_completed(0)), \
             patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("myplugin")
        assert result["ok"] is True

    def test_git_clone_failure_returns_error(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        with patch("subprocess.run", return_value=_make_completed(1, stderr="repo not found")):
            result = pm.add_bot_plugin("ghost-plugin")
        assert result["ok"] is False
        assert "repo not found" in result["error"]

    def test_module_stored_in_registry(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myext")
        registry: dict = {}
        with patch("subprocess.run", return_value=_make_completed(0)), \
             patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("myext", registry=registry)
        assert result["ok"] is True
        assert "myext" in registry
        assert registry["myext"] is fake_mod

    def test_import_failure_cleans_up_directory(self, fresh_plugin_manager, tmp_path):
        ext_dir = tmp_path / "extensions"
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(ext_dir))
        with patch("subprocess.run", return_value=_make_completed(0)) as mock_run, \
             patch("importlib.import_module", side_effect=ImportError("bad module")):
            result = pm.add_bot_plugin("myplugin")
        assert result["ok"] is False
        assert "Import failed" in result["error"]
        # directory should be cleaned up
        assert not (ext_dir / "myplugin").exists()


class TestRemoveBotPlugin:
    def test_removes_directory_and_unregisters(self, fresh_plugin_manager, tmp_path):
        # Create a fake extension directory
        ext_dir = tmp_path / "myplugin"
        ext_dir.mkdir()
        (ext_dir / "main.py").write_text("# fake")

        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        registry = {"myplugin": MagicMock()}

        result = pm.remove_bot_plugin("myplugin", registry=registry)
        assert result["ok"] is True
        assert not ext_dir.exists()
        assert "myplugin" not in registry

    def test_remove_nonexistent_returns_error(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        result = pm.remove_bot_plugin("ghost", registry={})
        assert result["ok"] is False
        assert "not installed" in result["error"]


# ===========================================================================
# list_all tests
# ===========================================================================

class TestListAll:
    def test_returns_three_keys(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0, stdout="plugin-a\nplugin-b")), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = pm.list_all(registry={})
        assert set(result.keys()) == {"plugins", "mcps", "bot_plugins"}

    def test_plugins_parsed_from_stdout(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", return_value=_make_completed(0, stdout="plugin-a\nplugin-b")), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = pm.list_all(registry={})
        assert "plugin-a" in result["plugins"]
        assert "plugin-b" in result["plugins"]

    def test_mcps_read_from_settings_json(self, fresh_plugin_manager, tmp_path):
        settings = {"mcpServers": {"my-server": {"command": "npx my-server"}}}
        settings_file = tmp_path / "settings.json"
        settings_file.write_text(json.dumps(settings))

        pm = fresh_plugin_manager.PluginManager(claude_settings_path=str(settings_file))
        with patch("subprocess.run", return_value=_make_completed(0, stdout="")):
            result = pm.list_all(registry={})
        assert "my-server" in result["mcps"]

    def test_bot_plugins_from_registry(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        fake_mod = MagicMock()
        registry = {"myplugin": fake_mod}
        with patch("subprocess.run", return_value=_make_completed(0, stdout="")), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = pm.list_all(registry=registry)
        assert "myplugin" in result["bot_plugins"]

    def test_claude_cli_missing_returns_empty_plugins_list(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", side_effect=FileNotFoundError), \
             patch("builtins.open", side_effect=FileNotFoundError):
            result = pm.list_all(registry={})
        assert result["plugins"] == []
```

### 1.2 Run tests — expect all failures

```bash
cd /path/to/shellack
python -m pytest tests/test_plugin_manager.py -v 2>&1 | head -40
# Expected: ImportError or collection errors — tools/plugin_manager.py does not exist yet
```

### 1.3 Implement `tools/plugin_manager.py`

**File:** `tools/plugin_manager.py`

```python
# tools/plugin_manager.py
"""
PluginManager — manages three plugin namespaces for Shellack.

Namespaces:
  1. Claude Code Plugins  — claude plugin install/uninstall
  2. MCP Servers          — claude mcp add/remove
  3. Shellack Extensions — git clone into extensions/, importlib hot-reload
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

# Default paths — can be overridden in constructor for testing
_DEFAULT_EXTENSIONS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "extensions"
)
_DEFAULT_CLAUDE_SETTINGS = os.path.expanduser("~/.claude/settings.json")
_OFFICIAL_ORG = "https://github.com/Shellack-plugins"


class PluginManager:
    def __init__(
        self,
        extensions_dir: str = _DEFAULT_EXTENSIONS_DIR,
        claude_settings_path: str = _DEFAULT_CLAUDE_SETTINGS,
    ) -> None:
        self.extensions_dir = extensions_dir
        self.claude_settings_path = claude_settings_path

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _run(self, cmd: list[str]) -> dict[str, Any]:
        """Run a shell command safely. Returns {ok, stdout, stderr, error}."""
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=60
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": "claude CLI not found. Install Claude Code first.",
            }
        except subprocess.TimeoutExpired:
            return {"ok": False, "error": f"Command timed out: {' '.join(cmd)}"}

        if proc.returncode != 0:
            return {
                "ok": False,
                "error": proc.stderr.strip() or f"Exit code {proc.returncode}",
            }
        return {"ok": True, "stdout": proc.stdout, "stderr": proc.stderr}

    # -----------------------------------------------------------------------
    # Claude Code Plugins
    # -----------------------------------------------------------------------

    def install_plugin(self, name: str) -> dict[str, Any]:
        """Shell out to: claude plugin install <name>"""
        return self._run(["claude", "plugin", "install", name])

    def uninstall_plugin(self, name: str) -> dict[str, Any]:
        """Shell out to: claude plugin uninstall <name>"""
        return self._run(["claude", "plugin", "uninstall", name])

    # -----------------------------------------------------------------------
    # MCP Servers
    # -----------------------------------------------------------------------

    def add_mcp(self, name: str, command: str) -> dict[str, Any]:
        """Shell out to: claude mcp add <name> <command>"""
        return self._run(["claude", "mcp", "add", name, command])

    def remove_mcp(self, name: str) -> dict[str, Any]:
        """Shell out to: claude mcp remove <name>"""
        return self._run(["claude", "mcp", "remove", name])

    # -----------------------------------------------------------------------
    # Shellack Bot Extensions
    # -----------------------------------------------------------------------

    def add_bot_plugin(
        self,
        name_or_url: str,
        registry: dict | None = None,
    ) -> dict[str, Any]:
        """
        Clone a bot extension and hot-reload it via importlib.

        name_or_url:
          - bare name  → clones from https://github.com/Shellack-plugins/<name>
          - https://…  → clones from provided URL verbatim

        registry: module-level _bot_extensions dict from bot_unified (pass-by-ref).
        """
        if registry is None:
            registry = {}

        if name_or_url.startswith("https://"):
            url = name_or_url
            # Derive a local name from the last path segment
            name = name_or_url.rstrip("/").split("/")[-1]
        else:
            name = name_or_url
            url = f"{_OFFICIAL_ORG}/{name}"

        dest = os.path.join(self.extensions_dir, name)

        # Ensure extensions/ directory exists
        os.makedirs(self.extensions_dir, exist_ok=True)

        # git clone
        clone_result = self._run(["git", "clone", url, dest])
        if not clone_result["ok"]:
            return clone_result

        # Add extensions_dir to sys.path if needed so import works
        if self.extensions_dir not in sys.path:
            sys.path.insert(0, self.extensions_dir)

        # Import (or reload if previously loaded)
        module_name = f"extensions.{name}"
        try:
            if module_name in sys.modules:
                mod = importlib.reload(sys.modules[module_name])
            else:
                mod = importlib.import_module(module_name)
        except Exception as exc:
            # Clean up failed install
            shutil.rmtree(dest, ignore_errors=True)
            return {"ok": False, "error": f"Import failed: {exc}"}

        registry[name] = mod
        return {"ok": True, "name": name, "module": mod}

    def remove_bot_plugin(
        self,
        name: str,
        registry: dict | None = None,
    ) -> dict[str, Any]:
        """Unregister and delete an installed bot extension."""
        if registry is None:
            registry = {}

        dest = os.path.join(self.extensions_dir, name)
        if not os.path.isdir(dest):
            return {"ok": False, "error": f"`{name}` is not installed."}

        # Unregister from sys.modules
        module_name = f"extensions.{name}"
        sys.modules.pop(module_name, None)

        # Remove from registry
        registry.pop(name, None)

        # Delete directory
        shutil.rmtree(dest)
        return {"ok": True}

    # -----------------------------------------------------------------------
    # List all
    # -----------------------------------------------------------------------

    def list_all(self, registry: dict | None = None) -> dict[str, Any]:
        """
        Return a dict with keys: plugins, mcps, bot_plugins.

        plugins:     parsed from `claude plugin list` stdout (one per line)
        mcps:        names from ~/.claude/settings.json["mcpServers"]
        bot_plugins: keys from the registry dict
        """
        if registry is None:
            registry = {}

        # -- plugins --
        try:
            proc = subprocess.run(
                ["claude", "plugin", "list"],
                capture_output=True, text=True, timeout=60,
            )
            plugins = [
                line.strip()
                for line in proc.stdout.splitlines()
                if line.strip()
            ] if proc.returncode == 0 else []
        except (FileNotFoundError, subprocess.TimeoutExpired):
            plugins = []

        # -- mcps --
        mcps: list[str] = []
        try:
            with open(self.claude_settings_path) as f:
                settings = json.load(f)
            mcps = list(settings.get("mcpServers", {}).keys())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            pass

        # -- bot_plugins --
        bot_plugins = list(registry.keys())

        return {"plugins": plugins, "mcps": mcps, "bot_plugins": bot_plugins}
```

### 1.4 Run tests — expect all green

```bash
cd /path/to/shellack
python -m pytest tests/test_plugin_manager.py -v
# Expected: all tests pass
```

### 1.5 Commit

```bash
cd /path/to/shellack
git add tools/plugin_manager.py tests/test_plugin_manager.py
git commit -m "feat: add PluginManager for plugins, MCPs, and bot extensions (Phase 3 Task 1)"
```

---

## Task 2 — Bot integration + integration tests

### 2.1 Write the failing integration tests first

**File:** `tests/test_bot_plugin_commands.py`

```python
# tests/test_bot_plugin_commands.py
"""
Integration tests for plugin commands wired into bot_unified.handle_mention.

Commands under test:
  @Shellack add plugin <name>
  @Shellack remove plugin <name>
  @Shellack add mcp <name> <command>
  @Shellack remove mcp <name>
  @Shellack add bot-plugin <name>
  @Shellack remove bot-plugin <name>
  @Shellack plugins
"""
import importlib
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_say():
    return MagicMock()


def _make_client():
    """Minimal Slack client mock with chat_postEphemeral."""
    c = MagicMock()
    c.chat_postEphemeral = MagicMock()
    return c


def _make_event(text: str, user: str = "U001", ts: str = "100.0", thread_ts: str | None = None):
    e = {"text": text, "channel": "C123", "ts": ts, "user": user}
    if thread_ts:
        e["thread_ts"] = thread_ts
    return e


def _reload_bot():
    import bot_unified
    importlib.reload(bot_unified)
    return bot_unified


# ---------------------------------------------------------------------------
# add plugin
# ---------------------------------------------------------------------------

class TestAddPlugin:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        ok_result = {"ok": True}
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "install_plugin", return_value=ok_result):
            event = _make_event("<@BOT> add plugin my-plugin")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "my-plugin" in say.call_args[1]["text"]
        assert "installed" in say.call_args[1]["text"].lower()

    def test_failure_posts_ephemeral_error(self):
        bot = _reload_bot()
        say = _make_say()
        err_result = {"ok": False, "error": "claude CLI not found. Install Claude Code first."}
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "install_plugin", return_value=err_result), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> add plugin bad-plugin", user="U999")
            bot.handle_mention(event, say=say)
        client.chat_postEphemeral.assert_called_once()
        call_kwargs = client.chat_postEphemeral.call_args[1]
        assert call_kwargs["user"] == "U999"
        assert "claude CLI not found" in call_kwargs["text"]


# ---------------------------------------------------------------------------
# remove plugin
# ---------------------------------------------------------------------------

class TestRemovePlugin:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "uninstall_plugin", return_value={"ok": True}):
            event = _make_event("<@BOT> remove plugin my-plugin")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "my-plugin" in say.call_args[1]["text"]

    def test_failure_posts_ephemeral_error(self):
        bot = _reload_bot()
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "uninstall_plugin", return_value={"ok": False, "error": "not found"}), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> remove plugin ghost", user="U999")
            bot.handle_mention(event, say=_make_say())
        client.chat_postEphemeral.assert_called_once()


# ---------------------------------------------------------------------------
# add mcp
# ---------------------------------------------------------------------------

class TestAddMcp:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "add_mcp", return_value={"ok": True}):
            event = _make_event("<@BOT> add mcp my-server npx my-server")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "my-server" in say.call_args[1]["text"]

    def test_missing_command_posts_usage(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
            event = _make_event("<@BOT> add mcp")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "usage" in say.call_args[1]["text"].lower() or "add mcp" in say.call_args[1]["text"].lower()

    def test_failure_posts_ephemeral_error(self):
        bot = _reload_bot()
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "add_mcp", return_value={"ok": False, "error": "bad cmd"}), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> add mcp x bad", user="U999")
            bot.handle_mention(event, say=_make_say())
        client.chat_postEphemeral.assert_called_once()


# ---------------------------------------------------------------------------
# remove mcp
# ---------------------------------------------------------------------------

class TestRemoveMcp:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "remove_mcp", return_value={"ok": True}):
            event = _make_event("<@BOT> remove mcp my-server")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "my-server" in say.call_args[1]["text"]

    def test_failure_posts_ephemeral(self):
        bot = _reload_bot()
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "remove_mcp", return_value={"ok": False, "error": "not found"}), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> remove mcp ghost", user="U999")
            bot.handle_mention(event, say=_make_say())
        client.chat_postEphemeral.assert_called_once()


# ---------------------------------------------------------------------------
# add bot-plugin
# ---------------------------------------------------------------------------

class TestAddBotPlugin:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "add_bot_plugin", return_value={"ok": True, "name": "hello"}):
            event = _make_event("<@BOT> add bot-plugin hello")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "hello" in say.call_args[1]["text"]
        assert "loaded" in say.call_args[1]["text"].lower() or "installed" in say.call_args[1]["text"].lower()

    def test_failure_posts_ephemeral(self):
        bot = _reload_bot()
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "add_bot_plugin", return_value={"ok": False, "error": "repo not found"}), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> add bot-plugin ghost", user="U999")
            bot.handle_mention(event, say=_make_say())
        client.chat_postEphemeral.assert_called_once()
        assert "repo not found" in client.chat_postEphemeral.call_args[1]["text"]

    def test_registry_receives_module(self):
        bot = _reload_bot()
        import types
        fake_mod = types.ModuleType("extensions.hello")
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "add_bot_plugin", return_value={"ok": True, "name": "hello", "module": fake_mod}) as mock_add:
            event = _make_event("<@BOT> add bot-plugin hello")
            bot.handle_mention(event, say=say)
        # Verify registry= argument passed to add_bot_plugin is the module-level dict
        call_kwargs = mock_add.call_args[1]
        assert "registry" in call_kwargs
        assert call_kwargs["registry"] is bot._bot_extensions


# ---------------------------------------------------------------------------
# remove bot-plugin
# ---------------------------------------------------------------------------

class TestRemoveBotPlugin:
    def test_success_posts_confirmation(self):
        bot = _reload_bot()
        say = _make_say()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "remove_bot_plugin", return_value={"ok": True}):
            event = _make_event("<@BOT> remove bot-plugin hello")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        assert "hello" in say.call_args[1]["text"]

    def test_failure_posts_ephemeral(self):
        bot = _reload_bot()
        client = _make_client()
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "remove_bot_plugin", return_value={"ok": False, "error": "`ghost` is not installed."}), \
             patch("bot_unified.app") as mock_app:
            mock_app.client = client
            event = _make_event("<@BOT> remove bot-plugin ghost", user="U999")
            bot.handle_mention(event, say=_make_say())
        client.chat_postEphemeral.assert_called_once()


# ---------------------------------------------------------------------------
# plugins list
# ---------------------------------------------------------------------------

class TestPluginsList:
    def test_lists_all_three_sections(self):
        bot = _reload_bot()
        say = _make_say()
        list_result = {
            "plugins": ["plugin-a"],
            "mcps": ["my-server"],
            "bot_plugins": ["hello"],
        }
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "list_all", return_value=list_result):
            event = _make_event("<@BOT> plugins")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        text = say.call_args[1]["text"]
        assert "plugin-a" in text
        assert "my-server" in text
        assert "hello" in text

    def test_empty_state_posts_none_installed(self):
        bot = _reload_bot()
        say = _make_say()
        list_result = {"plugins": [], "mcps": [], "bot_plugins": []}
        with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
             patch.object(bot.plugin_manager, "list_all", return_value=list_result):
            event = _make_event("<@BOT> plugins")
            bot.handle_mention(event, say=say)
        say.assert_called_once()
        text = say.call_args[1]["text"].lower()
        assert "none" in text or "no " in text
```

### 2.2 Run tests — expect all failures

```bash
cd /path/to/shellack
python -m pytest tests/test_bot_plugin_commands.py -v 2>&1 | head -50
# Expected: AttributeError — bot_unified has no plugin_manager, _bot_extensions,
#           or _handle_plugin_command yet
```

### 2.3 Implement bot integration in `bot_unified.py`

Three surgical edits to `bot_unified.py`. **Do not touch any existing logic.**

#### Edit A — Add imports and module-level state (after existing imports block, before `load_dotenv()`)

After the line:
```python
from tools.config_writer import set_env_var
```

Add:
```python
from tools.plugin_manager import PluginManager

# Plugin manager — single instance shared across all commands
plugin_manager = PluginManager()

# Bot extension registry — keyed by extension name, value is the loaded module
_bot_extensions: dict = {}
```

#### Edit B — Add `_handle_plugin_command` helper (insert before `_handle_config_command`)

Insert this complete function before the `_handle_config_command` definition:

```python
def _handle_plugin_command(
    clean_text: str, say, thread_ts: str, channel_id: str, user_id: str
) -> bool:
    """
    Handle plugin/MCP/bot-extension commands.
    Returns True if command was consumed.

    Errors are posted ephemerally to user_id only.
    Success confirmations are posted to the thread via say().
    """
    lower = clean_text.lower()

    def _ephemeral_error(text: str) -> None:
        app.client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=text,
        )

    # ------------------------------------------------------------------
    # plugins (list)
    # ------------------------------------------------------------------
    if lower == "plugins":
        result = plugin_manager.list_all(registry=_bot_extensions)
        lines = ["*Installed Plugins, MCPs, and Extensions*"]

        # Claude Code Plugins
        plugins = result["plugins"]
        lines.append("\n*Claude Code Plugins*")
        lines.append("\n".join(f"  • {p}" for p in plugins) if plugins else "  _none_")

        # MCP Servers
        mcps = result["mcps"]
        lines.append("\n*MCP Servers*")
        lines.append("\n".join(f"  • {m}" for m in mcps) if mcps else "  _none_")

        # Bot Extensions
        bots = result["bot_plugins"]
        lines.append("\n*Shellack Extensions*")
        lines.append("\n".join(f"  • {b}" for b in bots) if bots else "  _none_")

        say(text="\n".join(lines), thread_ts=thread_ts)
        return True

    # ------------------------------------------------------------------
    # add plugin <name>
    # ------------------------------------------------------------------
    if lower.startswith("add plugin "):
        name = clean_text[11:].strip()
        if not name:
            say(
                text="Usage: `@Shellack add plugin <name>`",
                thread_ts=thread_ts,
            )
            return True
        result = plugin_manager.install_plugin(name)
        if result["ok"]:
            say(text=f"✅ Plugin `{name}` installed.", thread_ts=thread_ts)
        else:
            _ephemeral_error(f"❌ Could not install plugin `{name}`: {result['error']}")
        return True

    # ------------------------------------------------------------------
    # remove plugin <name>
    # ------------------------------------------------------------------
    if lower.startswith("remove plugin "):
        name = clean_text[14:].strip()
        if not name:
            say(
                text="Usage: `@Shellack remove plugin <name>`",
                thread_ts=thread_ts,
            )
            return True
        result = plugin_manager.uninstall_plugin(name)
        if result["ok"]:
            say(text=f"✅ Plugin `{name}` removed.", thread_ts=thread_ts)
        else:
            _ephemeral_error(f"❌ Could not remove plugin `{name}`: {result['error']}")
        return True

    # ------------------------------------------------------------------
    # add mcp <name> <command>
    # ------------------------------------------------------------------
    if lower.startswith("add mcp"):
        remainder = clean_text[7:].strip()  # everything after "add mcp"
        parts = remainder.split(None, 1)
        if len(parts) < 2:
            say(
                text="Usage: `@Shellack add mcp <name> <command>`",
                thread_ts=thread_ts,
            )
            return True
        name, command = parts[0], parts[1]
        result = plugin_manager.add_mcp(name, command)
        if result["ok"]:
            say(
                text=f"✅ MCP server `{name}` added. Effective on next `run:` session.",
                thread_ts=thread_ts,
            )
        else:
            _ephemeral_error(f"❌ Could not add MCP `{name}`: {result['error']}")
        return True

    # ------------------------------------------------------------------
    # remove mcp <name>
    # ------------------------------------------------------------------
    if lower.startswith("remove mcp "):
        name = clean_text[11:].strip()
        if not name:
            say(
                text="Usage: `@Shellack remove mcp <name>`",
                thread_ts=thread_ts,
            )
            return True
        result = plugin_manager.remove_mcp(name)
        if result["ok"]:
            say(text=f"✅ MCP server `{name}` removed.", thread_ts=thread_ts)
        else:
            _ephemeral_error(f"❌ Could not remove MCP `{name}`: {result['error']}")
        return True

    # ------------------------------------------------------------------
    # add bot-plugin <name-or-url>
    # ------------------------------------------------------------------
    if lower.startswith("add bot-plugin "):
        name_or_url = clean_text[15:].strip()
        if not name_or_url:
            say(
                text="Usage: `@Shellack add bot-plugin <name>` or `@Shellack add bot-plugin <https://github.com/user/repo>`",
                thread_ts=thread_ts,
            )
            return True
        result = plugin_manager.add_bot_plugin(name_or_url, registry=_bot_extensions)
        if result["ok"]:
            name = result.get("name", name_or_url)
            say(
                text=f"✅ Extension `{name}` installed and loaded.",
                thread_ts=thread_ts,
            )
        else:
            _ephemeral_error(
                f"❌ Could not install extension `{name_or_url}`: {result['error']}"
            )
        return True

    # ------------------------------------------------------------------
    # remove bot-plugin <name>
    # ------------------------------------------------------------------
    if lower.startswith("remove bot-plugin "):
        name = clean_text[18:].strip()
        if not name:
            say(
                text="Usage: `@Shellack remove bot-plugin <name>`",
                thread_ts=thread_ts,
            )
            return True
        result = plugin_manager.remove_bot_plugin(name, registry=_bot_extensions)
        if result["ok"]:
            say(text=f"✅ Extension `{name}` removed.", thread_ts=thread_ts)
        else:
            _ephemeral_error(f"❌ Could not remove extension `{name}`: {result['error']}")
        return True

    return False
```

#### Edit C — Call `_handle_plugin_command` inside `handle_mention` (after the config command check)

In `handle_mention`, after:
```python
    # --- config commands (any channel, any context) ---
    if _handle_config_command(clean_text, say, thread_ts):
        return
```

Add immediately after it:

```python
    # --- plugin commands (any channel, any context) ---
    user_id = event.get("user", "")
    if _handle_plugin_command(clean_text, say, thread_ts, channel_id, user_id):
        return
```

Note: `user_id` is extracted from `event.get("user", "")`. This line must appear after `channel_id = event["channel"]` (already present at the top of `handle_mention`) and before the `run:` trigger block.

### 2.4 Run tests — expect all green

```bash
cd /path/to/shellack
python -m pytest tests/test_bot_plugin_commands.py -v
# Expected: all tests pass

# Also run the full test suite to confirm no regressions
python -m pytest tests/ -v
# Expected: all existing tests still pass
```

### 2.5 Commit

```bash
cd /path/to/shellack
git add bot_unified.py tests/test_bot_plugin_commands.py
git commit -m "feat: wire plugin commands into bot_unified (Phase 3 Task 2)"
```

---

## Error Handling Reference

| Scenario | Response |
|----------|----------|
| `claude` CLI not found | `_ephemeral_error("claude CLI not found. Install Claude Code first.")` |
| `claude plugin install` non-zero exit | `_ephemeral_error(f"... {stderr}")` |
| `claude mcp add` non-zero exit | `_ephemeral_error(f"... {stderr}")` |
| `git clone` failure for bot-plugin | `_ephemeral_error(f"... {stderr}")` |
| `importlib.import_module` raises | `_ephemeral_error("Import failed: ...")` + delete cloned dir |
| `remove bot-plugin` name not in extensions/ | `_ephemeral_error("`<name>` is not installed.")` |
| Malformed `add mcp` (missing command) | `say(usage_hint)` — not ephemeral, it's a user mistake not a system error |

---

## Verification Checklist

Before marking Phase 3 complete:

- [ ] `python -m pytest tests/test_plugin_manager.py -v` — all pass
- [ ] `python -m pytest tests/test_bot_plugin_commands.py -v` — all pass
- [ ] `python -m pytest tests/ -v` — no regressions in Phases 1 & 2 tests
- [ ] Manual smoke test: `@Shellack plugins` in #slackclaw-dev posts a well-formatted list
- [ ] Manual smoke test: `@Shellack add plugin bad-name` posts ephemeral error (not visible to channel)
- [ ] `extensions/` directory is in `.gitignore` (bot-plugin clones are runtime state, not source)
