"""Tests for the Dreamer persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.dreamer import Dreamer


@pytest.fixture
def persona():
    return Dreamer()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "dreamer"
    assert persona.model == "sonnet"
    assert persona.reads == ["architect", "token_cart"]
    assert persona.writes == "dreamer"
    assert persona.emoji == "\U0001f52e"
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
        "vision": "A unified design system across all platforms",
        "next_step": "Extract shared tokens from Atmos",
        "platform_potential": "iOS and macOS",
        "time_horizon": "quarter",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Build design tokens"}})
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
            "proposal": "Build design tokens",
            "data_model": "Token(name, value, platform)",
            "api_surface": "/api/tokens",
        },
        "token_cart": {"budget_remaining": 5000},
    }
    content = persona._build_user_content(inputs)
    assert "Build design tokens" in content
    assert "Token(name, value, platform)" in content
    assert "/api/tokens" in content
    assert "budget_remaining" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
