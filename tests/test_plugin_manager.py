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
        with patch(
            "subprocess.run", return_value=_make_completed(0, "installed")
        ) as mock_run:
            result = pm.install_plugin("my-plugin")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "plugin", "install", "my-plugin"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch(
            "subprocess.run", return_value=_make_completed(1, stderr="not found")
        ):
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
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch(
            "subprocess.run", return_value=_make_completed(1, stderr="unknown plugin")
        ):
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
            result = pm.add_mcp("mymcp", "npx my-server")
        assert result["ok"] is True
        mock_run.assert_called_once_with(
            ["claude", "mcp", "add", "mymcp", "npx", "my-server"],
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_failure_returns_error(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch(
            "subprocess.run", return_value=_make_completed(1, stderr="bad command")
        ):
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
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_failure(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch(
            "subprocess.run", return_value=_make_completed(1, stderr="not found")
        ):
            result = pm.remove_mcp("ghost")
        assert result["ok"] is False


# ===========================================================================
# Bot-plugin (Shellack extension) tests
# ===========================================================================


class TestAddBotPlugin:
    def test_official_org_builds_correct_url(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.hello")
        with patch(
            "subprocess.run", return_value=_make_completed(0)
        ) as mock_run, patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("hello")
        assert result["ok"] is True
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0] == [
            "git",
            "clone",
            "https://github.com/Shellack-plugins/hello",
            str(tmp_path / "hello"),
        ]

    def test_full_https_url_used_verbatim(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myrepo")
        with patch(
            "subprocess.run", return_value=_make_completed(0)
        ) as mock_run, patch("importlib.import_module", return_value=fake_mod):
            result = pm.add_bot_plugin("https://github.com/user/myrepo")
        assert result["ok"] is True
        clone_call = mock_run.call_args_list[0]
        assert clone_call[0][0][2] == "https://github.com/user/myrepo"

    def test_bare_name_not_https_goes_to_official_org(
        self, fresh_plugin_manager, tmp_path
    ):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myplugin")
        with patch("subprocess.run", return_value=_make_completed(0)), patch(
            "importlib.import_module", return_value=fake_mod
        ):
            result = pm.add_bot_plugin("myplugin")
        assert result["ok"] is True

    def test_git_clone_failure_returns_error(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        with patch(
            "subprocess.run", return_value=_make_completed(1, stderr="repo not found")
        ):
            result = pm.add_bot_plugin("ghost-plugin")
        assert result["ok"] is False
        assert "repo not found" in result["error"]

    def test_module_stored_in_registry(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(tmp_path))
        fake_mod = types.ModuleType("extensions.myext")
        registry: dict = {}
        with patch("subprocess.run", return_value=_make_completed(0)), patch(
            "importlib.import_module", return_value=fake_mod
        ):
            result = pm.add_bot_plugin("myext", registry=registry)
        assert result["ok"] is True
        assert "myext" in registry
        assert registry["myext"] is fake_mod

    def test_unknown_org_returns_error(self, fresh_plugin_manager, tmp_path):
        pm = fresh_plugin_manager.PluginManager(
            extensions_dir=str(tmp_path / "extensions")
        )
        result = pm.add_bot_plugin("someorg/myrepo")
        assert result["ok"] is False
        assert "Unknown plugin source" in result["error"]

    def test_import_failure_cleans_up_directory(self, fresh_plugin_manager, tmp_path):
        ext_dir = tmp_path / "extensions"
        pm = fresh_plugin_manager.PluginManager(extensions_dir=str(ext_dir))
        with patch(
            "subprocess.run", return_value=_make_completed(0)
        ) as mock_run, patch(
            "importlib.import_module", side_effect=ImportError("bad module")
        ):
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
        with patch(
            "subprocess.run",
            return_value=_make_completed(0, stdout="plugin-a\nplugin-b"),
        ), patch("builtins.open", side_effect=FileNotFoundError):
            result = pm.list_all(registry={})
        assert set(result.keys()) == {"plugins", "mcps", "bot_plugins"}

    def test_plugins_parsed_from_stdout(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch(
            "subprocess.run",
            return_value=_make_completed(0, stdout="plugin-a\nplugin-b"),
        ), patch("builtins.open", side_effect=FileNotFoundError):
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
        with patch("subprocess.run", return_value=_make_completed(0, stdout="")), patch(
            "builtins.open", side_effect=FileNotFoundError
        ):
            result = pm.list_all(registry=registry)
        assert "myplugin" in result["bot_plugins"]

    def test_claude_cli_missing_returns_empty_plugins_list(self, fresh_plugin_manager):
        pm = fresh_plugin_manager.PluginManager()
        with patch("subprocess.run", side_effect=FileNotFoundError), patch(
            "builtins.open", side_effect=FileNotFoundError
        ):
            result = pm.list_all(registry={})
        assert result["plugins"] == []
