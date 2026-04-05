"""Tests for the DevilsAdvocate persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.devils_advocate import DevilsAdvocate


@pytest.fixture
def persona():
    return DevilsAdvocate()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "devils_advocate"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "strategist"]
    assert persona.writes == "devils_advocate"
    assert persona.emoji == "\U0001f479"
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
        "counter_argument": "Microservices add operational complexity for a solo dev",
        "alternative": "Start with a modular monolith",
        "verdict": "has_merit",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Split into microservices"}})
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
            "proposal": "Split into microservices",
            "data_model": "Service(name, port)",
            "api_surface": "/api/gateway",
            "files_affected": ["services/gateway.py", "services/auth.py"],
        },
        "strategist": {
            "tasks": ["Extract auth service", "Add API gateway"],
            "estimated_complexity": "complex",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Split into microservices" in content
    assert "Service(name, port)" in content
    assert "/api/gateway" in content
    assert "services/gateway.py" in content
    assert "Extract auth service" in content
    assert "complex" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
