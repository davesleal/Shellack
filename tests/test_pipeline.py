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
    run_phase_with_micro_loop,
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
    # _usage is metadata attached by run(); persona output fields are still present
    usage = result.pop("_usage")
    assert result == output
    assert usage == {"input_tokens": 10, "output_tokens": 5}


def test_persona_run_fallback_on_bad_json(monkeypatch):
    persona = PERSONA_REGISTRY["fake"]
    raw_text = "This is not JSON at all."

    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": raw_text})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    monkeypatch.setattr(persona, "_call_api", lambda *args, **kwargs: mock_msg)

    result = persona.run({})
    usage = result.pop("_usage")
    assert result == {"raw": raw_text}
    assert usage == {"input_tokens": 10, "output_tokens": 5}


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

    # Active persona writes to ctx — _usage must NOT leak into context slots
    assert ctx["fake"] == output
    assert "_usage" not in ctx["fake"]
    # Discussion has one entry
    assert len(discussion) == 1
    assert "fake" in discussion[0]
    # Cost entry emitted with real token values
    assert len(costs) == 1
    assert isinstance(costs[0], TurnCostEntry)
    assert costs[0].persona == "fake"
    assert costs[0].input_tokens == 10
    assert costs[0].output_tokens == 5


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


# ---------------------------------------------------------------------------
# run_phase_with_micro_loop tests
# ---------------------------------------------------------------------------

def _make_micro_loop_personas():
    """Create MockArchitect and MockSkeptic personas with controlled call sequences."""

    # Shared call counter
    call_log = {"architect": 0, "skeptic": 0}

    architect_outputs = [
        {"proposal": "v1"},
        {"proposal": "v2"},
    ]
    skeptic_outputs = [
        {"verdict": "reconsider", "revision_target": "architect"},
        {"verdict": "proceed"},
    ]

    class MockArchitect(Persona):
        name = "mock_architect"
        emoji = "🏗"
        model = "haiku"
        reads = ["observer"]
        system_prompt = "Architect."
        max_tokens = 64

        def should_activate(self, complexity, turn_context):
            return True

        def _build_user_content(self, inputs):
            return "build"

        def run(self, inputs):
            idx = call_log["architect"]
            call_log["architect"] += 1
            return architect_outputs[min(idx, len(architect_outputs) - 1)]

    class MockSkeptic(Persona):
        name = "mock_skeptic"
        emoji = "🤨"
        model = "haiku"
        reads = ["mock_architect"]
        system_prompt = "Skeptic."
        max_tokens = 64

        def should_activate(self, complexity, turn_context):
            return True

        def _build_user_content(self, inputs):
            return "challenge"

        def run(self, inputs):
            idx = call_log["skeptic"]
            call_log["skeptic"] += 1
            return skeptic_outputs[min(idx, len(skeptic_outputs) - 1)]

    return MockArchitect(), MockSkeptic(), call_log


def test_micro_loop_triggers_revision():
    """Skeptic returns 'reconsider'; architect re-runs (v2), skeptic re-runs and returns 'proceed'."""
    architect, skeptic, call_log = _make_micro_loop_personas()

    phase = Phase(
        name="test_challenge",
        emoji="🔥",
        personas=[architect, skeptic],
        micro_loop={
            "from": "mock_skeptic",
            "to": "mock_architect",
            "trigger_field": "verdict",
            "trigger_value": "reconsider",
        },
    )

    ctx = TurnContext()
    ctx["observer"] = {"summary": "some input"}

    discussion, costs = run_phase_with_micro_loop(phase, ctx, "complex")

    # Architect was re-run -> v2 in ctx
    assert ctx["mock_architect"] == {"proposal": "v2"}
    # Skeptic re-run -> proceed
    assert ctx["mock_skeptic"] == {"verdict": "proceed"}
    # 4 total calls: architect(1), skeptic(1), architect-revised(2), skeptic-re-run(2)
    assert call_log["architect"] == 2
    assert call_log["skeptic"] == 2
    # Discussion log has 4 entries: normal run (2) + revised + re-eval
    assert len(discussion) == 4
    assert any("revised" in e for e in discussion)
    assert any("re-eval" in e for e in discussion)


def test_micro_loop_does_not_trigger_on_moderate():
    """Micro-loop config is ignored for non-complex tiers."""
    architect, skeptic, call_log = _make_micro_loop_personas()

    phase = Phase(
        name="test_challenge_moderate",
        emoji="🔥",
        personas=[architect, skeptic],
        micro_loop={
            "from": "mock_skeptic",
            "to": "mock_architect",
            "trigger_field": "verdict",
            "trigger_value": "reconsider",
        },
    )

    ctx = TurnContext()
    ctx["observer"] = {"summary": "some input"}

    discussion, costs = run_phase_with_micro_loop(phase, ctx, "moderate")

    # Skeptic fired once with "reconsider" but architect was NOT re-run
    assert ctx["mock_architect"] == {"proposal": "v1"}
    assert ctx["mock_skeptic"] == {"verdict": "reconsider", "revision_target": "architect"}
    assert call_log["architect"] == 1
    assert call_log["skeptic"] == 1
    assert len(discussion) == 2


def test_underscore_metadata_passed_to_personas():
    """Underscore-prefixed keys like _project_path pass through to all personas."""
    persona = PERSONA_REGISTRY["fake"]
    received_inputs = {}

    original_run = persona.run

    def capture_run(inputs):
        received_inputs.update(inputs)
        return {"result": "ok"}

    persona.run = capture_run

    ctx = TurnContext()
    ctx["observer"] = {"summary": "test"}
    ctx["_project_path"] = "/some/path"

    phase = Phase(name="test_meta", emoji="📋", personas=[persona])
    run_phase(phase, ctx, "moderate")

    assert received_inputs.get("_project_path") == "/some/path"

    persona.run = original_run


def test_summarize_slot_toolkeeper_output():
    """_summarize_slot shows command count and output preview for Toolkeeper."""
    from tools.pipeline import _summarize_slot

    slot = {"needs_tools": True, "output": "$ cat file.py\ndef hello(): pass", "commands_run": ["cat file.py"]}
    result = _summarize_slot("toolkeeper", slot)
    assert "1 cmds" in result
    assert "cat file.py" in result

    slot_no_tools = {"needs_tools": False, "output": "", "commands_run": []}
    result = _summarize_slot("toolkeeper", slot_no_tools)
    assert "no tools needed" in result


def test_micro_loop_no_trigger_when_proceed():
    """Skeptic returns 'proceed' — no micro-loop fires, only 2 API calls total."""

    call_log = {"architect": 0, "skeptic": 0}

    class ProceedArchitect(Persona):
        name = "proceed_architect"
        emoji = "🏗"
        model = "haiku"
        reads = ["observer"]
        system_prompt = "Architect."
        max_tokens = 64

        def should_activate(self, complexity, turn_context):
            return True

        def _build_user_content(self, inputs):
            return "build"

        def run(self, inputs):
            call_log["architect"] += 1
            return {"proposal": "v1"}

    class ProceedSkeptic(Persona):
        name = "proceed_skeptic"
        emoji = "🤨"
        model = "haiku"
        reads = ["proceed_architect"]
        system_prompt = "Skeptic."
        max_tokens = 64

        def should_activate(self, complexity, turn_context):
            return True

        def _build_user_content(self, inputs):
            return "challenge"

        def run(self, inputs):
            call_log["skeptic"] += 1
            return {"verdict": "proceed"}

    phase = Phase(
        name="test_no_trigger",
        emoji="✅",
        personas=[ProceedArchitect(), ProceedSkeptic()],
        micro_loop={
            "from": "proceed_skeptic",
            "to": "proceed_architect",
            "trigger_field": "verdict",
            "trigger_value": "reconsider",
        },
    )

    ctx = TurnContext()
    ctx["observer"] = {"summary": "some input"}

    discussion, costs = run_phase_with_micro_loop(phase, ctx, "complex")

    assert call_log["architect"] == 1
    assert call_log["skeptic"] == 1
    assert len(discussion) == 2
    assert ctx["proceed_skeptic"] == {"verdict": "proceed"}
    assert not any("revised" in e for e in discussion)
