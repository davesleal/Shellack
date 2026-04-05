"""Tests for the Simplifier persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.simplifier import Simplifier


@pytest.fixture
def persona():
    return Simplifier()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "simplifier"
    assert persona.model == "haiku"
    assert persona.reads == ["architect"]
    assert persona.writes == "simplifier"
    assert persona.emoji == "\u2702\ufe0f"
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
        "simplifications": [
            {"current": "Abstract factory pattern", "proposed": "Simple constructor", "savings": "3 classes removed"}
        ],
        "verdict": "reducible",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Add factory pattern"}})
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
            "proposal": "Add factory pattern",
            "data_model": "Widget(type, config)",
            "api_surface": "/api/widgets",
            "files_affected": ["factories/widget.py"],
        },
    }
    content = persona._build_user_content(inputs)
    assert "Add factory pattern" in content
    assert "Widget(type, config)" in content
    assert "/api/widgets" in content
    assert "factories/widget.py" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
