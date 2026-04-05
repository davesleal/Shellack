"""Tests for the Researcher persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.researcher import Researcher


@pytest.fixture
def persona():
    return Researcher()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "researcher"
    assert persona.model == "sonnet"
    assert persona.reads == ["observer", "strategist"]
    assert persona.writes == "researcher"
    assert persona.emoji == "\U0001f310"


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
        "findings": [
            {"source": "docs.python.org", "summary": "asyncio usage", "relevance": "high"}
        ],
        "apis_referenced": ["asyncio", "aiohttp"],
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=80, output_tokens=60)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({
        "observer": {"summary": "Build async HTTP client"},
        "strategist": {"tasks": ["research async libs"], "estimated_complexity": "complex"},
    })
    usage = result.pop("_usage")
    assert result == output
    assert usage == {"input_tokens": 80, "output_tokens": 60}


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="oops")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    usage = result.pop("_usage")
    assert result == {"raw": "oops"}
    assert usage == {"input_tokens": 10, "output_tokens": 5}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_uses_summary(persona):
    inputs = {"observer": {"summary": "Integrate Stripe payments"}}
    content = persona._build_user_content(inputs)
    assert "Integrate Stripe payments" in content


def test_build_user_content_includes_strategist_tasks(persona):
    inputs = {
        "observer": {"summary": "Task"},
        "strategist": {"tasks": ["set up webhook", "validate signature"], "estimated_complexity": "complex"},
    }
    content = persona._build_user_content(inputs)
    assert "set up webhook" in content
    assert "validate signature" in content


def test_build_user_content_includes_estimated_complexity(persona):
    inputs = {
        "strategist": {"tasks": [], "estimated_complexity": "complex"},
    }
    content = persona._build_user_content(inputs)
    assert "complex" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
