"""Tests for the Historian persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.historian import Historian


@pytest.fixture
def persona():
    return Historian()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "historian"
    assert persona.model == "haiku"
    assert persona.reads == ["observer", "token_cart"]
    assert persona.writes == "historian"
    assert persona.emoji == "\U0001f4dc"


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
        "prior_decisions": ["Use Postgres for storage"],
        "conflicts": [{"decision": "Use Postgres", "conflict_with": "SQLite request"}],
        "lessons": ["Always check DB choice before recommending"],
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"observer": {"summary": "Switch to SQLite"}})
    usage = result.pop("_usage")
    assert result == output
    assert usage == {"input_tokens": 50, "output_tokens": 30}


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json at all")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    usage = result.pop("_usage")
    assert result == {"raw": "not json at all"}
    assert usage == {"input_tokens": 10, "output_tokens": 5}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_uses_summary(persona):
    inputs = {"observer": {"summary": "Change the database"}}
    content = persona._build_user_content(inputs)
    assert "Change the database" in content


def test_build_user_content_includes_prior_context(persona):
    inputs = {
        "observer": {"summary": "Task", "prior_context": "Last time we used Redis"},
    }
    content = persona._build_user_content(inputs)
    assert "Last time we used Redis" in content


def test_build_user_content_includes_registry_snapshot(persona):
    inputs = {
        "observer": {"summary": "Task"},
        "token_cart": {"registry_snapshot": "project: foo"},
    }
    content = persona._build_user_content(inputs)
    assert "project: foo" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
