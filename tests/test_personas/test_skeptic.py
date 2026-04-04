"""Tests for the Skeptic persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.skeptic import Skeptic


@pytest.fixture
def persona():
    return Skeptic()


def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=20, output_tokens=15)
    return mock_msg


def test_skeptic_metadata(persona):
    assert persona.name == "skeptic"
    assert persona.emoji == "\U0001f928"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "strategist"]
    assert persona.writes == "skeptic"


def test_skeptic_activates_moderate_and_complex(persona):
    assert persona.should_activate("moderate", {}) is True
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False


def test_skeptic_proceed_verdict(monkeypatch, persona):
    output = {
        "assumptions": [
            {"claim": "API is stable", "evidence": "No versioning docs", "risk": "Breaking change"},
        ],
        "verdict": "proceed",
        "revision_target": None,
    }
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: _make_mock_msg(output))

    result = persona.run({"architect": {"proposal": "Use REST API"}, "strategist": {"tasks": ["Build it"]}})

    assert result["verdict"] == "proceed"
    assert result["revision_target"] is None


def test_skeptic_reconsider_verdict(monkeypatch, persona):
    output = {
        "assumptions": [
            {"claim": "DB can handle scale", "evidence": "No load testing", "risk": "Outage at 10k users"},
        ],
        "verdict": "reconsider",
        "revision_target": "architect",
    }
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: _make_mock_msg(output))

    result = persona.run({"architect": {"proposal": "Use single DB"}, "strategist": {"tasks": ["Build it"]}})

    assert result["verdict"] == "reconsider"
    assert result["revision_target"] == "architect"
