# tools/plugin_manager.py
"""
PluginManager — manages three plugin namespaces for SlackClaw.

Namespaces:
  1. Claude Code Plugins  — claude plugin install/uninstall
  2. MCP Servers          — claude mcp add/remove
  3. SlackClaw Extensions — git clone into extensions/, importlib hot-reload
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
_OFFICIAL_ORG = "https://github.com/SlackClaw-plugins"


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
    # SlackClaw Bot Extensions
    # -----------------------------------------------------------------------

    def add_bot_plugin(
        self,
        name_or_url: str,
        registry: dict | None = None,
    ) -> dict[str, Any]:
        """
        Clone a bot extension and hot-reload it via importlib.

        name_or_url:
          - bare name  → clones from https://github.com/SlackClaw-plugins/<name>
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
