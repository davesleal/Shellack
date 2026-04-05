"""Tests for the DataScientist persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.data_scientist import DataScientist


@pytest.fixture
def persona():
    return DataScientist()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "data_scientist"
    assert persona.model == "haiku"
    assert persona.reads == ["architect"]
    assert persona.writes == "data_scientist"
    assert persona.emoji == "\U0001f4ca"
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
        "scale_concerns": ["N+1 queries"],
        "query_patterns": ["filter by user_id + date range"],
        "index_suggestions": ["CREATE INDEX idx_user_date ON events(user_id, date)"],
        "verdict": "review",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Add analytics table"}})
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

def test_build_user_content_with_architect(persona):
    inputs = {
        "architect": {
            "proposal": "Add analytics table",
            "data_model": "events(id, user_id, ts)",
            "files_affected": ["models/event.py", "db/migrations/001.sql"],
        },
    }
    content = persona._build_user_content(inputs)
    assert "Add analytics table" in content
    assert "events(id, user_id, ts)" in content
    assert "models/event.py" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
