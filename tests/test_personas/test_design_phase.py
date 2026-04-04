"""
Integration tests for the design phase persona composition.

Verifies which personas activate on moderate vs complex complexity.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.architect import Architect
from tools.personas.specialist import Specialist
from tools.personas.data_scientist import DataScientist
from tools.personas.empathizer import Empathizer
from tools.personas.connector import Connector
from tools.personas.reuser import Reuser
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
def design_personas():
    return [Architect(), Specialist(), DataScientist(), Empathizer(), Connector(), Reuser()]


def test_moderate_design_only_3_personas(monkeypatch, design_personas):
    """On moderate complexity, only Architect + Specialist + Reuser fire (3 of 6)."""
    output = {"verdict": "clean", "proposal": "test", "data_model": "", "api_surface": "", "files_affected": []}
    _patch_all(monkeypatch, design_personas, output)

    phase = Phase(name="design", emoji="\U0001f4d0", personas=design_personas)
    ctx = TurnContext()
    ctx["strategist"] = {"tasks": ["Do something"], "estimated_complexity": "moderate"}
    ctx["historian"] = {"prior_decisions": []}
    ctx["token_cart"] = {"enriched_prompt": "Build a feature", "registry": ""}
    ctx["observer"] = {"summary": "Build a feature", "intent": "add functionality"}

    discussion, costs = run_phase(phase, ctx, "moderate")

    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion]
    assert "architect" in fired_names
    assert "specialist" in fired_names
    assert "reuser" in fired_names
    assert "data_scientist" not in fired_names
    assert "empathizer" not in fired_names
    assert "connector" not in fired_names
    assert len(fired_names) == 3


def test_complex_design_all_6_personas(monkeypatch, design_personas):
    """On complex complexity, all 6 personas fire."""
    output = {"verdict": "clean", "proposal": "test", "data_model": "", "api_surface": "", "files_affected": []}
    _patch_all(monkeypatch, design_personas, output)

    phase = Phase(name="design", emoji="\U0001f4d0", personas=design_personas)
    ctx = TurnContext()
    ctx["strategist"] = {"tasks": ["Do something complex"], "estimated_complexity": "complex"}
    ctx["historian"] = {"prior_decisions": []}
    ctx["token_cart"] = {"enriched_prompt": "Build a complex feature", "registry": ""}
    ctx["observer"] = {"summary": "Build a complex feature", "intent": "major refactor"}

    discussion, costs = run_phase(phase, ctx, "complex")

    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion]
    assert "architect" in fired_names
    assert "specialist" in fired_names
    assert "data_scientist" in fired_names
    assert "empathizer" in fired_names
    assert "connector" in fired_names
    assert "reuser" in fired_names
    assert len(fired_names) == 6
