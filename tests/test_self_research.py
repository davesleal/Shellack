# tests/test_self_research.py
"""Tests for the self-research autonomous investigation module."""

import json
import pytest
from unittest.mock import MagicMock, patch, call


def _mock_haiku_response(text: str):
    """Create a mock Anthropic message response."""
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    return msg


def _make_client(responses: list[str]):
    """Create a mock Anthropic client that returns canned responses in order."""
    client = MagicMock()
    client.messages.create.side_effect = [
        _mock_haiku_response(r) for r in responses
    ]
    return client


class TestSafetyBlocking:
    """Unsafe commands must be blocked at every step."""

    def test_unsafe_command_blocked(self):
        from tools.self_research import run_research

        # Haiku suggests rm, then says done
        client = _make_client([
            json.dumps({"done": False, "command": "rm -rf /", "summary": "trying rm"}),
            json.dumps({"done": True, "command": None, "summary": "gave up"}),
        ])

        result = run_research("delete everything", "/tmp", client=client)

        assert "rm -rf /" not in result["commands_run"]
        assert "BLOCKED" in result["findings"]

    def test_git_push_blocked(self):
        from tools.self_research import run_research

        client = _make_client([
            json.dumps({"done": False, "command": "git push origin main", "summary": "push"}),
            json.dumps({"done": True, "command": None, "summary": "done"}),
        ])

        result = run_research("push code", "/tmp", client=client)
        assert "git push" not in " ".join(result["commands_run"])

    def test_pipe_to_file_blocked(self):
        from tools.self_research import run_research

        client = _make_client([
            json.dumps({"done": False, "command": "echo bad > /etc/passwd", "summary": "write"}),
            json.dumps({"done": True, "command": None, "summary": "done"}),
        ])

        result = run_research("overwrite passwd", "/tmp", client=client)
        assert len(result["commands_run"]) == 0


class TestMaxStepsCap:
    """Research must stop after max_steps iterations."""

    @patch("tools.self_research._run_command", return_value="some output")
    def test_max_steps_respected(self, mock_run):
        from tools.self_research import run_research

        # Haiku never says done — should stop at max_steps
        responses = [
            json.dumps({"done": False, "command": "ls", "summary": f"step {i}"})
            for i in range(10)
        ]
        client = _make_client(responses)

        result = run_research("what is here", "/tmp", max_steps=3, client=client)

        assert result["steps"] <= 3
        assert len(result["commands_run"]) <= 3

    @patch("tools.self_research._run_command", return_value="some output")
    def test_max_steps_one(self, mock_run):
        from tools.self_research import run_research

        client = _make_client([
            json.dumps({"done": False, "command": "ls -la", "summary": "listing"}),
        ])

        result = run_research("list files", "/tmp", max_steps=1, client=client)
        assert result["steps"] == 1


class TestOutputCap:
    """Total output across all commands must not exceed 8000 chars."""

    @patch("tools.self_research._run_command")
    def test_output_cap_enforced(self, mock_run):
        from tools.self_research import run_research

        # Each command returns 5000 chars — second should be truncated
        mock_run.return_value = "x" * 5000

        client = _make_client([
            json.dumps({"done": False, "command": "cat big1.txt", "summary": "reading"}),
            json.dumps({"done": False, "command": "cat big2.txt", "summary": "reading more"}),
            json.dumps({"done": False, "command": "cat big3.txt", "summary": "reading even more"}),
        ])

        result = run_research("read big files", "/tmp", max_steps=5, client=client)

        # Total output chars in findings should not wildly exceed cap
        # The third command should be stopped by the cap
        total_cmd_output = sum(
            len(mock_run.return_value[:remaining])
            for remaining in [8000, 3000]  # approximate
        )
        # At most 2 commands should have run meaningfully
        assert len(result["commands_run"]) <= 3
        assert "output cap" in result["findings"].lower()


class TestHappyPath:
    """Multi-step research with mocked Haiku responses."""

    @patch("tools.self_research._run_command")
    def test_two_step_research(self, mock_run):
        from tools.self_research import run_research

        mock_run.side_effect = [
            "src/follow.py\nsrc/follow_service.py",
            "class FollowService:\n    def follow(self, user_id, target_id): ...",
        ]

        client = _make_client([
            json.dumps({
                "done": False,
                "command": "find . -name '*follow*'",
                "summary": "Finding follow-related files",
            }),
            json.dumps({
                "done": False,
                "command": "cat src/follow_service.py",
                "summary": "Reading the service",
            }),
            json.dumps({
                "done": True,
                "command": None,
                "summary": "The follow system uses FollowService with follow() method.",
            }),
        ])

        result = run_research(
            "How does the follow system work?", "/project", client=client
        )

        assert result["steps"] == 3
        assert len(result["commands_run"]) == 2
        assert "find . -name '*follow*'" in result["commands_run"]
        assert "cat src/follow_service.py" in result["commands_run"]
        assert "FollowService" in result["findings"]
        assert "Final Summary" in result["findings"]

    @patch("tools.self_research._run_command")
    def test_three_step_research(self, mock_run):
        from tools.self_research import run_research

        mock_run.side_effect = [
            "v2.1.0\nv2.0.0",
            "abc123 feat: add caching\ndef456 fix: login bug",
            "Added Redis caching layer for API responses.",
        ]

        client = _make_client([
            json.dumps({"done": False, "command": "git tag --sort=-creatordate", "summary": "listing tags"}),
            json.dumps({"done": False, "command": "git log v2.0.0..v2.1.0 --oneline", "summary": "log between tags"}),
            json.dumps({"done": False, "command": "cat CHANGELOG.md", "summary": "reading changelog"}),
            json.dumps({"done": True, "command": None, "summary": "Release v2.1.0 added caching and fixed login."}),
        ])

        result = run_research("What changed in the last release?", "/project", client=client)

        assert result["steps"] == 4
        assert len(result["commands_run"]) == 3


class TestDoneSignal:
    """The done signal should terminate research early."""

    @patch("tools.self_research._run_command", return_value="output")
    def test_immediate_done(self, mock_run):
        from tools.self_research import run_research

        client = _make_client([
            json.dumps({"done": True, "command": None, "summary": "Already know the answer."}),
        ])

        result = run_research("What is 2+2?", "/tmp", max_steps=5, client=client)

        assert result["steps"] == 1
        assert len(result["commands_run"]) == 0
        assert "Already know the answer" in result["findings"]
        mock_run.assert_not_called()

    @patch("tools.self_research._run_command", return_value="output")
    def test_done_after_one_command(self, mock_run):
        from tools.self_research import run_research

        client = _make_client([
            json.dumps({"done": False, "command": "ls", "summary": "checking"}),
            json.dumps({"done": True, "command": None, "summary": "Found it."}),
        ])

        result = run_research("what files", "/tmp", max_steps=10, client=client)

        assert result["steps"] == 2
        assert len(result["commands_run"]) == 1


class TestParsing:
    """Test JSON parsing edge cases."""

    def test_parse_markdown_fenced_json(self):
        from tools.self_research import _parse_decision

        raw = '```json\n{"done": true, "command": null, "summary": "done"}\n```'
        result = _parse_decision(raw)
        assert result is not None
        assert result["done"] is True

    def test_parse_plain_json(self):
        from tools.self_research import _parse_decision

        raw = '{"done": false, "command": "ls", "summary": "listing"}'
        result = _parse_decision(raw)
        assert result is not None
        assert result["command"] == "ls"

    def test_parse_garbage_returns_none(self):
        from tools.self_research import _parse_decision

        assert _parse_decision("not json at all") is None

    def test_parse_json_in_prose(self):
        from tools.self_research import _parse_decision

        raw = 'Here is my response: {"done": true, "command": null, "summary": "answer"} end'
        result = _parse_decision(raw)
        assert result is not None
        assert result["done"] is True
