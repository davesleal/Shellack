"""Tests for the Tester persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.tester import Tester


@pytest.fixture
def persona():
    return Tester()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "tester"
    assert persona.model == "sonnet"
    assert persona.reads == ["architect", "inspector"]
    assert persona.writes == "tester"
    assert persona.emoji == "\U0001f9ea"
    assert persona.max_tokens == 768


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_activates_on_moderate(persona):
    assert persona.should_activate("moderate", {}) is True


def test_activates_on_complex(persona):
    assert persona.should_activate("complex", {}) is True


def test_does_not_activate_on_simple(persona):
    assert persona.should_activate("simple", {}) is False


def test_does_not_activate_on_deep(persona):
    assert persona.should_activate("deep", {}) is False


# ---------------------------------------------------------------------------
# Run (mocked API)
# ---------------------------------------------------------------------------

def test_run_returns_parsed_output(monkeypatch, persona):
    output = {
        "test_cases": [
            {"name": "test_auth_rejects_expired_token", "type": "unit", "assertion": "returns 401"}
        ],
        "coverage_gaps": ["race condition on concurrent refresh"],
        "verdict": "gaps",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Token refresh"}})
    assert result == output


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    assert result == {"raw": "not json"}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_with_inputs(persona):
    inputs = {
        "architect": {
            "proposal": "Token refresh",
            "api_surface": "/api/refresh",
            "files_affected": ["auth/refresh.py"],
        },
        "inspector": {
            "gaps": [
                {"type": "edge_case", "location": "auth/refresh.py", "severity": "high"}
            ],
            "verdict": "gaps",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Token refresh" in content
    assert "/api/refresh" in content
    assert "auth/refresh.py" in content
    assert "edge_case" in content
    assert "gaps" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
