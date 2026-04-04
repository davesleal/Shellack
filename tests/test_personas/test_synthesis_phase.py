"""
Tests for the synthesis phase: Learner, Coach, OutputEditor personas.

Covers:
  1. synthesis personas only fire on complex (not moderate)
  2. Coach receives blocker verdict from infosec slot
  3. Learner receives the full TurnContext (all slots)
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.learner import Learner
from tools.personas.coach import Coach
from tools.personas.output_editor import OutputEditor
from tools.pipeline import Phase, TurnContext, run_phase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=20, output_tokens=10)
    return mock_msg


def _patch_all(monkeypatch, personas: list, output: dict):
    for persona in personas:
        monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt, _o=output: _make_mock_msg(_o))


@pytest.fixture
def synthesis_personas():
    return [Learner(), Coach(), OutputEditor()]


def _make_ctx():
    ctx = TurnContext()
    ctx["architect"] = {"proposal": "Build a feature", "api_surface": "POST /feature"}
    ctx["infosec"] = {"mitigations": [], "verdict": "clear"}
    ctx["coach"] = {"verdict": "ship", "confidence": 0.9, "reasoning": "All checks passed."}
    ctx["token_cart"] = {"total_tokens": 500}
    return ctx


# ---------------------------------------------------------------------------
# Test 1: synthesis only fires on complex
# ---------------------------------------------------------------------------

def test_synthesis_only_on_complex(monkeypatch, synthesis_personas):
    """Learner, Coach, and OutputEditor must not fire on moderate; all fire on complex."""
    learner, coach, output_editor = synthesis_personas

    learner_output = {"lessons": [], "corrections": []}
    coach_output = {"verdict": "ship", "confidence": 0.95, "reasoning": "All checks passed."}
    editor_output = {"polished_output": "Done.", "format": "slack"}

    monkeypatch.setattr(learner, "_call_api", lambda s, u, m, mt: _make_mock_msg(learner_output))
    monkeypatch.setattr(coach, "_call_api", lambda s, u, m, mt: _make_mock_msg(coach_output))
    monkeypatch.setattr(output_editor, "_call_api", lambda s, u, m, mt: _make_mock_msg(editor_output))

    phase = Phase(name="synthesis", emoji="\U0001f9e0", personas=synthesis_personas)
    ctx = _make_ctx()

    # On moderate — none should fire
    discussion_moderate, _ = run_phase(phase, ctx, "moderate")
    assert discussion_moderate == [], "Synthesis personas must not fire on moderate"

    # On complex — all three should fire
    discussion_complex, _ = run_phase(phase, ctx, "complex")
    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion_complex]
    assert "learner" in fired_names
    assert "coach" in fired_names
    assert "output_editor" in fired_names
    assert len(fired_names) == 3


# ---------------------------------------------------------------------------
# Test 2: Coach sees blocker verdict from infosec slot
# ---------------------------------------------------------------------------

def test_coach_detects_blocker(monkeypatch):
    """When infosec slot has verdict 'blocker', Coach receives it in its inputs."""
    coach = Coach()
    received_inputs: dict = {}

    def capture_run(inputs):
        received_inputs.update(inputs)
        return {"verdict": "hold", "confidence": 1.0, "reasoning": "Blocker detected."}

    monkeypatch.setattr(coach, "run", capture_run)

    ctx = TurnContext()
    ctx["infosec"] = {"mitigations": [], "verdict": "blocker"}
    ctx["architect"] = {"proposal": "Something risky"}
    ctx["coach"] = {}
    ctx["token_cart"] = {}

    # Coach reads=[], so it gets everything
    assert coach.reads == [], "Coach must have reads=[] to receive all slots"

    phase = Phase(name="synthesis", emoji="\U0001f9e0", personas=[coach])
    run_phase(phase, ctx, "complex")

    # Verify coach received infosec slot with blocker verdict
    assert "infosec" in received_inputs, "Coach must receive infosec slot"
    assert received_inputs["infosec"]["verdict"] == "blocker"


# ---------------------------------------------------------------------------
# Test 3: Learner receives the full TurnContext
# ---------------------------------------------------------------------------

def test_learner_receives_all_slots(monkeypatch):
    """Learner's reads=[] means it receives ALL slots from TurnContext, not an empty dict."""
    learner = Learner()
    received_inputs: dict = {}

    def capture_run(inputs):
        received_inputs.update(inputs)
        return {"lessons": [], "corrections": []}

    monkeypatch.setattr(learner, "run", capture_run)

    ctx = TurnContext()
    ctx["strategist"] = {"plan": "Do X"}
    ctx["architect"] = {"proposal": "Build Y"}
    ctx["infosec"] = {"verdict": "clear"}
    ctx["coach"] = {"verdict": "ship"}

    assert learner.reads == [], "Learner must have reads=[] to receive all slots"

    phase = Phase(name="synthesis", emoji="\U0001f9e0", personas=[learner])
    run_phase(phase, ctx, "complex")

    # Learner should have received all 4 slots
    assert "strategist" in received_inputs
    assert "architect" in received_inputs
    assert "infosec" in received_inputs
    assert "coach" in received_inputs
    assert len(received_inputs) == 4
