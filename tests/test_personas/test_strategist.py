"""Tests for the Strategist persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.strategist import Strategist


@pytest.fixture
def persona():
    return Strategist()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "strategist"
    assert persona.model == "haiku"
    assert persona.reads == ["observer", "token_cart"]
    assert persona.writes == "strategist"
    assert persona.emoji == "\U0001f3af"


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
        "tasks": ["step1", "step2"],
        "sequence": [0, 1],
        "dependencies": [],
        "estimated_complexity": "moderate",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"observer": {"summary": "Do the thing"}})
    usage = result.pop("_usage")
    assert result == output
    assert usage == {"input_tokens": 50, "output_tokens": 30}


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    usage = result.pop("_usage")
    assert result == {"raw": "not json"}
    assert usage == {"input_tokens": 10, "output_tokens": 5}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_uses_summary(persona):
    inputs = {"observer": {"summary": "Fix the login bug"}}
    content = persona._build_user_content(inputs)
    assert "Fix the login bug" in content


def test_build_user_content_includes_token_budget(persona):
    inputs = {
        "observer": {"summary": "Task"},
        "token_cart": {"budget_remaining": 2000},
    }
    content = persona._build_user_content(inputs)
    assert "2000" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
