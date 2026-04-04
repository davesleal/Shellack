"""
Integration tests for the challenge phase persona composition.

Verifies which personas activate on moderate vs complex complexity.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.skeptic import Skeptic
from tools.personas.devils_advocate import DevilsAdvocate
from tools.personas.simplifier import Simplifier
from tools.personas.prioritizer import Prioritizer
from tools.pipeline import Phase, TurnContext, run_phase


def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=20, output_tokens=15)
    return mock_msg


def _patch_all(monkeypatch, personas: list, output: dict):
    for persona in personas:
        monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt, _o=output: _make_mock_msg(_o))


@pytest.fixture
def challenge_personas():
    return [Skeptic(), DevilsAdvocate(), Simplifier(), Prioritizer()]


def test_moderate_challenge_skeptic_and_prioritizer_only(monkeypatch, challenge_personas):
    """On moderate complexity, only Skeptic + Prioritizer fire. Devils Advocate and Simplifier don't."""
    output = {
        "assumptions": [],
        "verdict": "proceed",
        "revision_target": None,
        "counter_argument": "",
        "alternative": "",
        "simplifications": [],
        "ranked_options": [],
        "recommendation": "proceed",
    }
    _patch_all(monkeypatch, challenge_personas, output)

    phase = Phase(name="challenge", emoji="\U0001f928", personas=challenge_personas)
    ctx = TurnContext()
    ctx["architect"] = {"proposal": "Use a simple REST API", "data_model": "", "api_surface": "", "files_affected": []}
    ctx["strategist"] = {"tasks": ["Build endpoint"], "sequence": [0], "estimated_complexity": "moderate"}
    ctx["skeptic"] = {"assumptions": [], "verdict": "proceed", "revision_target": None}

    discussion, costs = run_phase(phase, ctx, "moderate")

    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion]
    assert "skeptic" in fired_names
    assert "prioritizer" in fired_names
    assert "devils_advocate" not in fired_names
    assert "simplifier" not in fired_names
    assert len(fired_names) == 2
