"""
Tests for pipeline micro-loop logic, including dynamic target override.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas import PERSONA_REGISTRY, Persona
from tools.pipeline import Phase, TurnContext, run_phase_with_micro_loop


# ---------------------------------------------------------------------------
# Helpers: lightweight stub personas for testing
# ---------------------------------------------------------------------------

def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    return mock_msg


def _make_stub(name: str, output: dict) -> Persona:
    """Create a minimal persona stub that returns a fixed output dict.

    Uses a plain object with the Persona interface to avoid __init_subclass__
    registration side effects.
    """

    class _Stub:
        emoji = ""
        model = "haiku"
        reads: list[str] = []
        system_prompt = ""
        max_tokens = 64

        def __init__(self):
            self._name = name
            self._output = output

        @property
        def name(self):
            return self._name

        @property
        def writes(self) -> str:
            return self._name

        def should_activate(self, complexity: str, turn_context: dict) -> bool:
            return True

        def _build_user_content(self, inputs):
            return ""

        def run(self, inputs):
            return dict(self._output)

    return _Stub()  # type: ignore[return-value]


@pytest.fixture(autouse=True)
def _clean_registry():
    """Snapshot and restore PERSONA_REGISTRY around each test."""
    snapshot = dict(PERSONA_REGISTRY)
    yield
    PERSONA_REGISTRY.clear()
    PERSONA_REGISTRY.update(snapshot)


def _register(persona: _StubPersona):
    PERSONA_REGISTRY[persona.name] = persona


# ---------------------------------------------------------------------------
# Tests: dynamic_target_field micro-loop behaviour
# ---------------------------------------------------------------------------

class TestDynamicTargetMicroLoop:
    """Verify micro-loop routes to the persona named by revision_target."""

    def test_dynamic_target_override_routes_to_named_persona(self):
        """When revision_target names a valid persona, the loop re-runs that persona."""
        skeptic = _make_stub("skeptic", {
            "verdict": "reconsider",
            "revision_target": "specialist",
        })
        architect = _make_stub("architect", {"proposal": "v1"})
        specialist = _make_stub("specialist", {"detail": "revised"})

        _register(skeptic)
        _register(architect)
        _register(specialist)

        phase = Phase(
            name="challenge",
            emoji="",
            personas=[architect, skeptic],
            micro_loop={
                "from": "skeptic",
                "to": "architect",
                "trigger_field": "verdict",
                "trigger_value": "reconsider",
                "dynamic_target_field": "revision_target",
            },
        )

        ctx = TurnContext()
        discussion, costs = run_phase_with_micro_loop(phase, ctx, "complex")

        # The revised entry should be for specialist, not architect
        revised_entries = [e for e in discussion if "(revised)" in e]
        assert len(revised_entries) == 1
        assert "specialist" in revised_entries[0]

        # specialist slot should have been updated
        assert ctx["specialist"] == {"detail": "revised"}

    def test_falls_back_to_static_when_revision_target_missing(self):
        """When revision_target is absent, the loop falls back to the static 'to' persona."""
        skeptic = _make_stub("skeptic", {
            "verdict": "reconsider",
            # no revision_target key
        })
        architect = _make_stub("architect", {"proposal": "v1"})

        _register(skeptic)
        _register(architect)

        phase = Phase(
            name="challenge",
            emoji="",
            personas=[architect, skeptic],
            micro_loop={
                "from": "skeptic",
                "to": "architect",
                "trigger_field": "verdict",
                "trigger_value": "reconsider",
                "dynamic_target_field": "revision_target",
            },
        )

        ctx = TurnContext()
        discussion, _ = run_phase_with_micro_loop(phase, ctx, "complex")

        revised_entries = [e for e in discussion if "(revised)" in e]
        assert len(revised_entries) == 1
        assert "architect" in revised_entries[0]

    def test_falls_back_to_static_when_revision_target_unknown(self):
        """When revision_target names a persona not in registry, falls back to static 'to'."""
        skeptic = _make_stub("skeptic", {
            "verdict": "reconsider",
            "revision_target": "nonexistent_persona",
        })
        architect = _make_stub("architect", {"proposal": "v1"})

        _register(skeptic)
        _register(architect)

        phase = Phase(
            name="challenge",
            emoji="",
            personas=[architect, skeptic],
            micro_loop={
                "from": "skeptic",
                "to": "architect",
                "trigger_field": "verdict",
                "trigger_value": "reconsider",
                "dynamic_target_field": "revision_target",
            },
        )

        ctx = TurnContext()
        discussion, _ = run_phase_with_micro_loop(phase, ctx, "complex")

        revised_entries = [e for e in discussion if "(revised)" in e]
        assert len(revised_entries) == 1
        assert "architect" in revised_entries[0]

    def test_no_loop_when_verdict_is_not_reconsider(self):
        """Micro-loop does not fire when trigger value doesn't match."""
        skeptic = _make_stub("skeptic", {
            "verdict": "proceed",
            "revision_target": "specialist",
        })
        architect = _make_stub("architect", {"proposal": "v1"})

        _register(skeptic)
        _register(architect)

        phase = Phase(
            name="challenge",
            emoji="",
            personas=[architect, skeptic],
            micro_loop={
                "from": "skeptic",
                "to": "architect",
                "trigger_field": "verdict",
                "trigger_value": "reconsider",
                "dynamic_target_field": "revision_target",
            },
        )

        ctx = TurnContext()
        discussion, _ = run_phase_with_micro_loop(phase, ctx, "complex")

        revised_entries = [e for e in discussion if "(revised)" in e]
        assert len(revised_entries) == 0

    def test_no_loop_on_non_complex_tier(self):
        """Micro-loop only fires on complex tier."""
        skeptic = _make_stub("skeptic", {
            "verdict": "reconsider",
            "revision_target": "architect",
        })
        architect = _make_stub("architect", {"proposal": "v1"})

        _register(skeptic)
        _register(architect)

        phase = Phase(
            name="challenge",
            emoji="",
            personas=[architect, skeptic],
            micro_loop={
                "from": "skeptic",
                "to": "architect",
                "trigger_field": "verdict",
                "trigger_value": "reconsider",
                "dynamic_target_field": "revision_target",
            },
        )

        ctx = TurnContext()
        discussion, _ = run_phase_with_micro_loop(phase, ctx, "moderate")

        revised_entries = [e for e in discussion if "(revised)" in e]
        assert len(revised_entries) == 0
