"""Tests for the Inspector persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.inspector import Inspector


@pytest.fixture
def persona():
    return Inspector()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "inspector"
    assert persona.model == "haiku"
    assert persona.reads == ["architect"]
    assert persona.writes == "inspector"
    assert persona.emoji == "\U0001f50d"
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
        "gaps": [
            {"type": "edge_case", "location": "auth.py", "severity": "high"}
        ],
        "verdict": "gaps",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "Add auth middleware"}})
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
            "proposal": "Add auth middleware",
            "data_model": "User(id, role)",
            "api_surface": "/api/auth",
            "files_affected": ["middleware/auth.py", "routes/login.py"],
        },
    }
    content = persona._build_user_content(inputs)
    assert "Add auth middleware" in content
    assert "User(id, role)" in content
    assert "/api/auth" in content
    assert "middleware/auth.py" in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
