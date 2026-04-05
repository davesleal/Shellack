"""Tests for the Connector persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.connector import Connector


@pytest.fixture
def persona():
    return Connector()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "connector"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "token_cart"]
    assert persona.writes == "connector"
    assert persona.emoji == "\U0001f517"
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
        "similar_patterns": [
            {"project": "Atmos", "pattern": "pub/sub", "relevance": "same event model"}
        ],
        "reuse_opportunities": ["shared event bus"],
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Use event bus"}})
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

def test_build_user_content_with_architect(persona):
    inputs = {
        "architect": {"proposal": "Build a cache layer", "api_surface": "/api/cache"},
    }
    content = persona._build_user_content(inputs)
    assert "Build a cache layer" in content
    assert "/api/cache" in content


def test_build_user_content_with_token_cart(persona):
    inputs = {
        "token_cart": {"enriched_prompt": "enriched", "registry": "projects list"},
    }
    content = persona._build_user_content(inputs)
    assert "enriched" in content
    assert "projects list" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
