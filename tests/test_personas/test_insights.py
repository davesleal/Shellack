"""Tests for the Insights persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.insights import Insights


@pytest.fixture
def persona():
    return Insights()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "insights"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "dreamer"]
    assert persona.writes == "insights"
    assert persona.emoji == "\U0001f4c9"
    assert persona.max_tokens == 512


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_activates_on_complex(persona):
    assert persona.should_activate("complex", {}) is True


def test_does_not_activate_on_moderate(persona):
    assert persona.should_activate("moderate", {}) is False


def test_does_not_activate_on_simple(persona):
    assert persona.should_activate("simple", {}) is False


def test_does_not_activate_on_deep(persona):
    assert persona.should_activate("deep", {}) is False


# ---------------------------------------------------------------------------
# Run (mocked API)
# ---------------------------------------------------------------------------

def test_run_returns_parsed_output(monkeypatch, persona):
    output = {
        "success_criteria": ["Reduce p95 latency below 200ms"],
        "metrics": ["p95_latency", "error_rate"],
        "instrumentation": ["Add OpenTelemetry span to /api/query"],
        "verdict": "measurable",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Optimize query layer"}})
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
        "architect": {"proposal": "Optimize queries", "data_model": "Query(id, sql, ts)"},
        "dreamer": {
            "vision": "Sub-100ms queries globally",
            "next_step": "Add read replicas",
            "platform_potential": "Web",
            "time_horizon": "quarter",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Optimize queries" in content
    assert "Sub-100ms queries globally" in content
    assert "Add read replicas" in content
    assert "Web" in content
    assert "quarter" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
