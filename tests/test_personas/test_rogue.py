"""Tests for the Rogue persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.rogue import Rogue


@pytest.fixture
def persona():
    return Rogue()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "rogue"
    assert persona.model == "haiku"
    assert persona.reads == ["architect"]
    assert persona.writes == "rogue"
    assert persona.emoji == "\U0001f608"
    assert persona.max_tokens == 512


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_activates_on_complex(persona):
    assert persona.should_activate("complex", {}) is True


def test_activates_on_moderate_with_security_override(persona):
    ctx = {"agent_manager": {"security_override": True}}
    assert persona.should_activate("moderate", ctx) is True


def test_does_not_activate_on_moderate_without_override(persona):
    assert persona.should_activate("moderate", {}) is False


def test_does_not_activate_on_moderate_with_false_override(persona):
    ctx = {"agent_manager": {"security_override": False}}
    assert persona.should_activate("moderate", ctx) is False


def test_does_not_activate_on_simple(persona):
    assert persona.should_activate("simple", {}) is False


def test_does_not_activate_on_deep(persona):
    assert persona.should_activate("deep", {}) is False


# ---------------------------------------------------------------------------
# Run (mocked API)
# ---------------------------------------------------------------------------

def test_run_returns_parsed_output(monkeypatch, persona):
    output = {
        "stress_scenarios": [
            {"scenario": "10x traffic spike", "impact": "DB connection pool exhaustion", "likelihood": "medium"}
        ],
        "verdict": "fragile",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Add connection pool"}})
    result.pop("_usage", None)
    assert result == output


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    result.pop("_usage", None)
    assert result == {"raw": "not json"}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_with_inputs(persona):
    inputs = {
        "architect": {
            "proposal": "Add connection pool",
            "data_model": "Pool(max=10)",
            "api_surface": "/api/query",
            "files_affected": ["db/pool.py"],
        },
    }
    content = persona._build_user_content(inputs)
    assert "Add connection pool" in content
    assert "Pool(max=10)" in content
    assert "/api/query" in content
    assert "db/pool.py" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
