"""
Tests for pipeline core: TurnContext, Persona base class, run_phase, run_pipeline.
"""

import json
import pytest

from tools.personas import Persona, PERSONA_REGISTRY
from tools.pipeline import (
    TurnContext,
    Phase,
    TurnCostEntry,
    run_phase,
    run_pipeline,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class FakePersona(Persona):
    name = "fake"
    emoji = "🤖"
    model = "haiku"
    reads = ["observer"]
    system_prompt = "You are a test persona."
    max_tokens = 64

    def should_activate(self, complexity, turn_context):
        return True

    def _build_user_content(self, inputs):
        return f"Observer says: {inputs.get('observer', {}).get('summary', '')}"


class InactiveFakePersona(Persona):
    name = "inactive"
    emoji = "💤"
    model = "haiku"
    reads = ["observer"]
    system_prompt = "You are inactive."
    max_tokens = 64

    def should_activate(self, complexity, turn_context):
        return False

    def _build_user_content(self, inputs):
        return ""


# ---------------------------------------------------------------------------
# TurnContext tests
# ---------------------------------------------------------------------------

def test_turn_context_is_dict():
    ctx = TurnContext()
    assert isinstance(ctx, dict)


def test_turn_context_read_slot():
    ctx = TurnContext()
    ctx["observer"] = {"summary": "hello"}
    assert ctx["observer"]["summary"] == "hello"


def test_turn_context_write_slot():
    ctx = TurnContext()
    ctx["fake"] = {"confidence": 0.9}
    assert ctx["fake"] == {"confidence": 0.9}


# ---------------------------------------------------------------------------
# Persona tests
# ---------------------------------------------------------------------------

def test_persona_writes_equals_name():
    persona = PERSONA_REGISTRY["fake"]
    assert persona.writes == "fake"


def test_persona_run_returns_dict(monkeypatch):
    persona = PERSONA_REGISTRY["fake"]
    output = {"confidence": 0.9, "label": "positive"}

    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": json.dumps(output)})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    monkeypatch.setattr(persona, "_call_api", lambda *args, **kwargs: mock_msg)

    result = persona.run({"observer": {"summary": "test"}})
    assert result == output


def test_persona_run_fallback_on_bad_json(monkeypatch):
    persona = PERSONA_REGISTRY["fake"]
    raw_text = "This is not JSON at all."

    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": raw_text})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    monkeypatch.setattr(persona, "_call_api", lambda *args, **kwargs: mock_msg)

    result = persona.run({})
    assert result == {"raw": raw_text}


# ---------------------------------------------------------------------------
# run_phase tests
# ---------------------------------------------------------------------------

def test_run_phase_activates_persona(monkeypatch):
    persona = PERSONA_REGISTRY["fake"]
    output = {"summary": "all good"}

    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": json.dumps(output)})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    monkeypatch.setattr(persona, "_call_api", lambda *args, **kwargs: mock_msg)

    ctx = TurnContext()
    ctx["observer"] = {"summary": "some input"}

    phase = Phase(name="test_phase", emoji="🧪", personas=[persona])
    discussion, costs = run_phase(phase, ctx, "moderate")

    # Active persona writes to ctx
    assert ctx["fake"] == output
    # Discussion has one entry
    assert len(discussion) == 1
    assert "fake" in discussion[0]
    # Cost entry emitted
    assert len(costs) == 1
    assert isinstance(costs[0], TurnCostEntry)
    assert costs[0].persona == "fake"


def test_run_phase_empty_when_no_activation():
    inactive = PERSONA_REGISTRY["inactive"]

    ctx = TurnContext()
    ctx["observer"] = {"summary": "some input"}

    phase = Phase(name="test_phase_inactive", emoji="💤", personas=[inactive])
    discussion, costs = run_phase(phase, ctx, "simple")

    assert discussion == []
    assert costs == []
    assert "inactive" not in ctx


# ---------------------------------------------------------------------------
# run_pipeline tests
# ---------------------------------------------------------------------------

def test_run_pipeline_simple_runs_no_phases():
    """Simple tier has no cognitive phases registered — pipeline returns empty."""
    ctx = TurnContext()
    ctx["observer"] = {"summary": "hi"}

    discussion, costs = run_pipeline(ctx, "simple", pre_hoc=True)

    assert discussion == []
    assert costs == []
