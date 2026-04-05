"""Tests for the Prioritizer persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.prioritizer import Prioritizer


@pytest.fixture
def persona():
    return Prioritizer()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "prioritizer"
    assert persona.model == "haiku"
    assert persona.reads == ["strategist", "skeptic"]
    assert persona.writes == "prioritizer"
    assert persona.emoji == "\u2696\ufe0f"
    assert persona.max_tokens == 512


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
        "ranked_options": [
            {"option": "Cache hot queries", "impact": "high", "effort": "low", "score": 9.0}
        ],
        "recommendation": "Start with caching hot queries",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"strategist": {"tasks": ["Cache queries", "Add indexes"]}})
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
        "strategist": {
            "tasks": ["Cache queries", "Add indexes"],
            "sequence": [0, 1],
            "estimated_complexity": "moderate",
        },
        "skeptic": {
            "assumptions": [
                {"claim": "Cache will reduce load", "risk": "medium"}
            ],
            "verdict": "proceed_with_caution",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Cache queries" in content
    assert "Add indexes" in content
    assert "Cache will reduce load" in content
    assert "proceed_with_caution" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
