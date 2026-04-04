"""
Pipeline core: TurnContext, Phase, run_phase, run_pipeline.

The pipeline routes a conversation turn through tiers of persona phases.
Each phase runs its personas, each persona reads declared input slots from
TurnContext and writes its output back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tools.personas import Persona

log = logging.getLogger(__name__)


class TurnContext(dict):
    """Shared typed state for a single conversation turn."""


@dataclass
class TurnCostEntry:
    persona: str
    input_tokens: int
    output_tokens: int
    model: str


@dataclass
class Phase:
    name: str
    emoji: str
    personas: list[Persona]
    micro_loop: dict | None = None


# ---------------------------------------------------------------------------
# Phase registry
# ---------------------------------------------------------------------------

PHASES: dict[str, Phase] = {}


def register_phase(phase: Phase) -> None:
    PHASES[phase.name] = phase


# Tier routing tables — populated by _register_default_phases()
_TIER_PHASES: dict[str, list[str]] = {
    "simple": [],
    "moderate": [],
    "complex": [],
    "deep": [],
}

_POST_HOC_PHASES: dict[str, list[str]] = {
    "simple": [],
    "moderate": [],
    "complex": [],
    "deep": [],
}


def _register_default_phases() -> None:
    """Register built-in phases. Called on import."""
    try:
        from tools.personas.strategist import Strategist
        from tools.personas.historian import Historian
        from tools.personas.researcher import Researcher

        register_phase(Phase(
            name="plan",
            emoji="\U0001f3af",
            personas=[Strategist(), Historian(), Researcher()],
            micro_loop={"from": "historian", "to": "strategist", "trigger_field": "conflicts"},
        ))

        # Wire plan phase into tier routing
        _TIER_PHASES["moderate"].append("plan")
        _TIER_PHASES["complex"].append("plan")
    except ImportError:
        pass


_register_default_phases()


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------

def _summarize_slot(name: str, slot: object) -> str:
    """One-line summary of a slot value for the discussion log."""
    if isinstance(slot, dict):
        keys = list(slot.keys())[:3]
        return f"{name}: {{{', '.join(keys)}{'...' if len(slot) > 3 else ''}}}"
    if isinstance(slot, str):
        preview = slot[:60].replace("\n", " ")
        return f"{name}: \"{preview}{'...' if len(slot) > 60 else ''}\""
    return f"{name}: {slot!r}"


def run_phase(
    phase: Phase,
    ctx: TurnContext,
    complexity: str,
) -> tuple[list[str], list[TurnCostEntry]]:
    """
    Run all personas in a phase against the current TurnContext.

    Returns:
        discussion: list of one-line log entries
        costs: list of TurnCostEntry for token accounting
    """
    discussion: list[str] = []
    costs: list[TurnCostEntry] = []

    for persona in phase.personas:
        if not persona.should_activate(complexity, ctx):
            log.debug("%s %s skipped (should_activate=False)", persona.emoji, persona.name)
            continue

        # Gather declared input slots
        inputs: dict[str, dict] = {}
        for slot_name in persona.reads:
            if slot_name in ctx:
                inputs[slot_name] = ctx[slot_name]

        # Call the persona
        try:
            result = persona.run(inputs)
        except Exception as exc:
            log.warning("%s %s raised %s: %s", persona.emoji, persona.name, type(exc).__name__, exc)
            result = {"error": str(exc)}

        # Write output to context
        ctx[persona.writes] = result

        # Build discussion entry
        entry = f"{persona.emoji} {persona.name}: {_summarize_slot(persona.writes, result)}"
        discussion.append(entry)

        # Record cost if the persona exposes usage (via run returning a result with __usage__)
        # Real cost tracking happens via _call_api; here we emit a zero-cost entry as a placeholder
        # unless the persona's last API call stored usage on ctx.
        costs.append(TurnCostEntry(
            persona=persona.name,
            input_tokens=0,
            output_tokens=0,
            model=persona.model,
        ))

    return discussion, costs


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    ctx: TurnContext,
    complexity: str,
    pre_hoc: bool = True,
) -> tuple[list[str], list[TurnCostEntry]]:
    """
    Route to the correct phases based on complexity tier.

    Args:
        ctx: shared turn state
        complexity: one of "simple" | "moderate" | "complex" | "deep"
        pre_hoc: if True, run cognitive phases; if False, run post-hoc phases

    Returns:
        (discussion, costs) aggregated across all phases
    """
    # Security override: always run security phase if flagged
    security_flagged = ctx.get("security_flagged", False)

    routing = _TIER_PHASES if pre_hoc else _POST_HOC_PHASES
    phase_names = routing.get(complexity, [])

    all_discussion: list[str] = []
    all_costs: list[TurnCostEntry] = []

    for phase_name in phase_names:
        if phase_name not in PHASES:
            log.warning("Phase '%s' referenced in routing but not registered", phase_name)
            continue
        phase = PHASES[phase_name]
        disc, costs = run_phase(phase, ctx, complexity)
        all_discussion.extend(disc)
        all_costs.extend(costs)

    # Security override: if flagged, ensure security phase runs (if registered)
    if security_flagged and "security" in PHASES and "security" not in phase_names:
        disc, costs = run_phase(PHASES["security"], ctx, complexity)
        all_discussion.extend(disc)
        all_costs.extend(costs)

    return all_discussion, all_costs
