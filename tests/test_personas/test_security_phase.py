"""
Integration tests for the security phase persona composition.

Verifies activation logic for Rogue, Hacker, and Infosec personas.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.rogue import Rogue
from tools.personas.hacker import Hacker
from tools.personas.infosec import Infosec
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
def security_personas():
    return [Rogue(), Hacker(), Infosec()]


def _make_ctx():
    ctx = TurnContext()
    ctx["architect"] = {
        "proposal": "Build an auth service",
        "data_model": "User table with hashed passwords",
        "api_surface": "POST /login, POST /register",
        "files_affected": ["auth/service.py", "auth/models.py"],
    }
    ctx["rogue"] = {
        "stress_scenarios": [{"scenario": "thundering herd on login", "impact": "DB overload", "likelihood": "high"}],
        "verdict": "fragile",
    }
    ctx["hacker"] = {
        "attack_vectors": [{"vector": "SQL injection in login", "severity": "critical", "exploitability": "easy"}],
        "verdict": "critical",
    }
    return ctx


def test_security_fires_on_complex(monkeypatch, security_personas):
    """All 3 security personas fire on complex complexity."""
    output = {
        "stress_scenarios": [],
        "attack_vectors": [],
        "mitigations": [],
        "verdict": "clear",
    }
    _patch_all(monkeypatch, security_personas, output)

    phase = Phase(name="security", emoji="\U0001f6e1\ufe0f", personas=security_personas)
    ctx = _make_ctx()

    discussion, costs = run_phase(phase, ctx, "complex")

    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion]
    assert "rogue" in fired_names
    assert "hacker" in fired_names
    assert "infosec" in fired_names
    assert len(fired_names) == 3


def test_security_conditional_on_moderate(monkeypatch, security_personas):
    """On moderate, security personas only fire if security_override=True in agent_manager slot."""
    output = {
        "stress_scenarios": [],
        "attack_vectors": [],
        "mitigations": [],
        "verdict": "clear",
    }
    _patch_all(monkeypatch, security_personas, output)

    phase = Phase(name="security", emoji="\U0001f6e1\ufe0f", personas=security_personas)

    # Without override — no personas should fire
    ctx_no_override = _make_ctx()
    discussion_no, _ = run_phase(phase, ctx_no_override, "moderate")
    assert len(discussion_no) == 0, "Security personas must not fire on moderate without security_override"

    # With override — all 3 should fire
    ctx_override = _make_ctx()
    ctx_override["agent_manager"] = {"security_override": True}
    discussion_yes, _ = run_phase(phase, ctx_override, "moderate")

    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion_yes]
    assert "rogue" in fired_names
    assert "hacker" in fired_names
    assert "infosec" in fired_names
    assert len(fired_names) == 3
