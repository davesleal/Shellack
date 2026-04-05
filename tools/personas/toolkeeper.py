"""Toolkeeper — auto-executes safe commands to gather context the agent needs.

Sits between Token Cart and cognitive phases. Analyzes the prompt to determine
what files or commands would help answer the question, executes them within
the project directory, and injects results into TurnContext.

Only runs safe, read-only commands. Never writes, deletes, or modifies.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path

from tools.personas import Persona

logger = logging.getLogger(__name__)

_MAX_OUTPUT = 4000  # chars per command
_MAX_COMMANDS = 3  # max commands per turn
_TIMEOUT = 10  # seconds per command

# Commands that are always safe to run (read-only)
_SAFE_COMMANDS = {
    "cat", "head", "tail", "grep", "rg", "find", "ls", "wc",
    "git", "echo", "psql", "sqlite3", "jq", "sort", "uniq",
    "awk", "sed", "cut", "tr", "diff", "file", "stat",
}

# Git subcommands that are safe (read-only)
_SAFE_GIT = {
    "log", "show", "diff", "status", "branch", "tag",
    "blame", "shortlog", "describe", "rev-parse",
}

# Patterns that indicate destructive intent
_DANGEROUS_PATTERNS = [
    r"\brm\b", r"\brmdir\b", r"\bmv\b", r"\bcp\b.*>",
    r"\bchmod\b", r"\bchown\b", r"\bkill\b", r"\bpkill\b",
    r"\bcurl\b.*-X\s*(POST|PUT|DELETE|PATCH)",
    r"\bwget\b", r"\bnpm\s+(install|uninstall|publish)",
    r"\bpip\s+install", r"\bgit\s+(push|reset|checkout|merge|rebase|commit|stash)",
    r"\bdrop\b", r"\bdelete\b", r"\btruncate\b", r"\binsert\b", r"\bupdate\b",
    r">",  # output redirection
    # Shell injection vectors (LLM-generated commands + shell=True = RCE risk)
    r"\$\(",        # subshell $(...)
    r"`",           # backtick subshell
    r"<\(",         # process substitution <(...)
    r"\bsystem\(",  # awk/perl system() calls
    r"\bsed\b.*-i", # sed in-place edit (destructive)
    r"\beval\b",    # eval command
    r"\bexec\b",    # exec command
    r"\bsource\b",  # source command
    r"\|\s*sh\b",   # pipe to shell
    r"\|\s*bash\b", # pipe to bash
]


def _is_safe_command(cmd: str) -> bool:
    """Check if a command is safe to execute (read-only)."""
    # Check for dangerous patterns
    for pattern in _DANGEROUS_PATTERNS:
        if re.search(pattern, cmd, re.IGNORECASE):
            return False

    # Extract the base command (first word, ignoring env vars)
    parts = cmd.strip().split()
    base = None
    for part in parts:
        if "=" in part:
            continue  # skip env vars like DATABASE_URL=...
        base = part.split("/")[-1]  # handle full paths
        break

    if not base:
        return False

    # Check if base command is in safe list
    if base not in _SAFE_COMMANDS:
        return False

    # Extra check for git: only allow safe subcommands
    if base == "git" and len(parts) > 1:
        subcommand = parts[parts.index("git") + 1] if "git" in parts else parts[1]
        if subcommand not in _SAFE_GIT:
            return False

    # Extra check for psql/sqlite3: only allow if -c flag (single command) is present
    if base in ("psql", "sqlite3"):
        if "-c" not in parts:
            return False

    return True


def _run_command(cmd: str, cwd: str) -> str:
    """Execute a safe command and return output."""
    if not _is_safe_command(cmd):
        return f"BLOCKED: command not in safe list — {cmd[:60]}"

    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=_TIMEOUT,
            env={**os.environ, "SHELLACK_BOT": "1"},
        )
        output = result.stdout.strip()
        if result.stderr.strip():
            output += f"\n--- stderr ---\n{result.stderr.strip()}"
        if len(output) > _MAX_OUTPUT:
            output = output[:_MAX_OUTPUT] + "\n... (truncated)"
        return output or "(no output)"
    except subprocess.TimeoutExpired:
        return f"TIMEOUT: command took >{_TIMEOUT}s — {cmd[:60]}"
    except Exception as exc:
        return f"ERROR: {exc}"


class Toolkeeper(Persona):
    name = "toolkeeper"
    emoji = "\U0001f527"  # 🔧
    model = "haiku"
    reads = ["observer", "token_cart"]
    max_tokens = 512
    system_prompt = """You are the Toolkeeper — you determine what commands to run to gather context the agent needs.

Given a user's request and current context, decide if the agent needs file contents, git history, database schema, or other information to answer well. If so, output the commands to run.

Output ONLY valid JSON:
{"needs_tools": true|false, "commands": ["command1", "command2"], "reasoning": "why these commands help"}

Rules:
- Max 3 commands
- ONLY read-only commands: cat, head, grep, find, ls, git log, git diff, git show, psql -c, sqlite3 -c
- NEVER: rm, mv, cp, git push, git commit, npm install, pip install, any write/delete/modify
- Be specific: "cat src/services/followService.ts" not "look at the service files"
- For database: use psql -c with SELECT only
- Prefer targeted commands over broad ones (grep for specific patterns, not cat of entire files)

IMPORTANT — when to set needs_tools to true:
- Questions about HOW code works, what it does, or why it behaves a certain way → ALWAYS fetch the source file
- Questions mentioning specific files, functions, modules, or systems → ALWAYS fetch them
- "How does X work?" → find and cat the relevant source file
- STATE.md, registry, and handoff context are HIGH-LEVEL SUMMARIES — they do NOT contain implementation details
- Only set needs_tools to false for greetings, opinions, or questions that genuinely need no code context"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        # Activate on moderate+ when the observer summary suggests file/code needs
        if complexity == "simple":
            return False
        return True

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        observer = inputs.get("observer", {})
        token_cart = inputs.get("token_cart", {})

        parts = []
        if observer.get("summary"):
            parts.append(f"## User Request\n{observer['summary']}")
        # Only show file_context (loaded file paths), NOT enriched_prompt or handoff.
        # Showing enriched context makes Haiku think it already has enough info
        # and skip tool use. Toolkeeper should decide based on the QUESTION,
        # not on whether STATE.md mentions the topic.
        if token_cart.get("file_context"):
            parts.append(f"## Already Loaded Files\n{token_cart['file_context'][:200]}")

        # Show available project files so Haiku can target specific paths
        project_path = inputs.get("_project_path", ".")
        if project_path and project_path != ".":
            parts.append(f"## Project Path\n{project_path}")

        return "\n\n".join(parts) if parts else "No context available."

    def run(self, inputs: dict[str, dict]) -> dict:
        """Override run to execute commands after Haiku decides what to run."""
        # First, ask Haiku what commands to run
        result = super().run(inputs)
        usage = result.pop("_usage", {})

        if not result.get("needs_tools", False):
            return {"needs_tools": False, "output": "", "commands_run": [], "_usage": usage}

        commands = result.get("commands", [])
        if not commands:
            return {"needs_tools": False, "output": "", "commands_run": [], "_usage": usage}

        # Get project path from token_cart context
        token_cart = inputs.get("token_cart", {})
        # Try to extract cwd from enriched context or fall back
        cwd = "."
        # The project path will be injected by the pipeline caller
        if "_project_path" in inputs:
            cwd = inputs["_project_path"]

        # Execute commands
        outputs = []
        commands_run = []
        for cmd in commands[:_MAX_COMMANDS]:
            cmd = cmd.strip()
            if not cmd:
                continue
            output = _run_command(cmd, cwd)
            outputs.append(f"$ {cmd}\n{output}")
            commands_run.append(cmd)
            logger.info(f"Toolkeeper executed: {cmd[:60]}")

        combined = "\n\n".join(outputs)

        return {
            "needs_tools": True,
            "output": combined,
            "commands_run": commands_run,
            "_usage": usage,
        }
