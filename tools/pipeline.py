"""
Pipeline core: TurnContext, Phase, run_phase, run_pipeline.

The pipeline routes a conversation turn through tiers of persona phases.
Each phase runs its personas, each persona reads declared input slots from
TurnContext and writes its output back.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from tools.personas import Persona, PERSONA_REGISTRY

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
}

_POST_HOC_PHASES: dict[str, list[str]] = {
    "simple": [],
    "moderate": [],
    "complex": [],
}


def _register_default_phases() -> None:
    """Register built-in phases. Called on import."""
    try:
        from tools.personas.toolkeeper import Toolkeeper

        register_phase(Phase(
            name="toolkeeper",
            emoji="\U0001f527",  # 🔧
            personas=[Toolkeeper()],
        ))

        # Toolkeeper runs before plan on moderate+ (gathers context)
        _TIER_PHASES["moderate"].insert(0, "toolkeeper")
        _TIER_PHASES["complex"].insert(0, "toolkeeper")
    except ImportError:
        pass

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

    try:
        from tools.personas.architect import Architect
        from tools.personas.specialist import Specialist
        from tools.personas.data_scientist import DataScientist
        from tools.personas.empathizer import Empathizer
        from tools.personas.connector import Connector
        from tools.personas.reuser import Reuser

        register_phase(Phase(
            name="design",
            emoji="\U0001f4d0",
            personas=[Architect(), Specialist(), DataScientist(), Empathizer(), Connector(), Reuser()],
            micro_loop={"from": "reuser", "to": "architect", "trigger_field": "verdict", "trigger_value": "duplicate"},
        ))

        # Wire design phase into tier routing
        _TIER_PHASES["moderate"].append("design")
        _TIER_PHASES["complex"].append("design")
    except ImportError:
        pass

    try:
        from tools.personas.dreamer import Dreamer
        from tools.personas.insights import Insights
        from tools.personas.growth_coach import GrowthCoach

        register_phase(Phase(
            name="vision",
            emoji="\U0001f52e",
            personas=[Dreamer(), Insights(), GrowthCoach()],
            micro_loop={"from": "insights", "to": "growth_coach", "trigger_field": "verdict", "trigger_value": "unmeasurable"},
        ))

        _TIER_PHASES["complex"].append("vision")
    except ImportError:
        pass

    try:
        from tools.personas.skeptic import Skeptic
        from tools.personas.devils_advocate import DevilsAdvocate
        from tools.personas.simplifier import Simplifier
        from tools.personas.prioritizer import Prioritizer

        register_phase(Phase(
            name="challenge",
            emoji="\U0001f928",
            personas=[Skeptic(), DevilsAdvocate(), Simplifier(), Prioritizer()],
            micro_loop={"from": "skeptic", "to": "architect", "trigger_field": "verdict", "trigger_value": "reconsider", "dynamic_target_field": "revision_target"},
        ))

        # Wire challenge phase into tier routing
        _TIER_PHASES["complex"].append("challenge")
        _POST_HOC_PHASES["moderate"].append("challenge")
    except ImportError:
        pass

    try:
        from tools.personas.rogue import Rogue
        from tools.personas.hacker import Hacker
        from tools.personas.infosec import Infosec

        register_phase(Phase(
            name="security",
            emoji="\U0001f6e1\ufe0f",
            personas=[Rogue(), Hacker(), Infosec()],
            micro_loop={"from": "infosec", "to": "architect", "trigger_field": "verdict", "trigger_value": "blocker"},
        ))

        # Security runs on complex only; moderate gets it via security_override in run_pipeline
        _TIER_PHASES["complex"].append("security")
    except ImportError:
        pass

    try:
        from tools.personas.inspector import Inspector
        from tools.personas.tester import Tester
        from tools.personas.visual_ux import VisualUX

        register_phase(Phase(
            name="quality",
            emoji="\u2705",
            personas=[Inspector(), Tester(), VisualUX()],
        ))

        # Quality runs on moderate and complex
        _TIER_PHASES["complex"].append("quality")
        _POST_HOC_PHASES["moderate"].append("quality")
    except ImportError:
        pass

    try:
        from tools.personas.learner import Learner
        from tools.personas.coach import Coach
        from tools.personas.output_editor import OutputEditor

        register_phase(Phase(
            name="synthesis",
            emoji="\U0001f9e0",
            personas=[Learner(), Coach(), OutputEditor()],
        ))

        # Synthesis runs post-hoc on complex only
        _POST_HOC_PHASES["complex"].append("synthesis")
    except ImportError:
        pass


_register_default_phases()


# ---------------------------------------------------------------------------
# Phase runner
# ---------------------------------------------------------------------------

def _summarize_slot(name: str, slot: object) -> str:
    """One-line summary of a slot value for the discussion log."""
    if isinstance(slot, dict):
        # Show verdict if present (most useful signal)
        if "verdict" in slot:
            return f"{slot['verdict']}"
        # Show raw content preview instead of just "{raw}"
        if "raw" in slot:
            preview = str(slot["raw"])[:60].replace("\n", " ")
            return f"{preview}"
        # Show error
        if "error" in slot:
            return f"error: {slot['error'][:50]}"
        # Fallback: show first meaningful value
        for key in ("summary", "proposal", "vision", "recommendation", "polished_output"):
            if key in slot:
                preview = str(slot[key])[:60].replace("\n", " ")
                return f"{preview}"
        # Last resort: show key names
        keys = list(slot.keys())[:3]
        return f"{{{', '.join(keys)}}}"
    if isinstance(slot, str):
        preview = slot[:60].replace("\n", " ")
        return f"{preview}"
    return f"{slot!r}"


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

        # Gather declared input slots.
        # Empty reads list means "read everything" (special case for synthesis personas).
        if persona.reads:
            inputs: dict[str, dict] = {slot: ctx[slot] for slot in persona.reads if slot in ctx}
        else:
            inputs = dict(ctx)

        # Call the persona
        try:
            result = persona.run(inputs)
        except Exception as exc:
            log.warning("%s %s raised %s: %s", persona.emoji, persona.name, type(exc).__name__, exc)
            result = {"error": str(exc)}

        # Extract usage metadata before writing to context
        usage = result.pop("_usage", {})

        # Write output to context
        ctx[persona.writes] = result

        # Build discussion entry
        entry = f"{persona.emoji} {persona.name}: {_summarize_slot(persona.writes, result)}"
        discussion.append(entry)

        # Record real token costs from the API response
        costs.append(TurnCostEntry(
            persona=persona.name,
            input_tokens=usage.get("input_tokens", 0),
            output_tokens=usage.get("output_tokens", 0),
            model=persona.model,
        ))

    return discussion, costs


# ---------------------------------------------------------------------------
# Micro-loop phase runner
# ---------------------------------------------------------------------------

def run_phase_with_micro_loop(
    phase: Phase,
    ctx: TurnContext,
    complexity: str,
) -> tuple[list[str], list[TurnCostEntry]]:
    """Execute a phase with optional micro-loop revision.

    If complexity is "complex" and phase has a micro_loop defined:
    1. Run all personas normally via run_phase()
    2. Check if the "from" persona's output triggers the loop
    3. If triggered, re-run the "to" persona with the flagging slot injected
    4. Re-run the "from" persona to re-evaluate
    5. Max 1 retry

    For non-complex tiers, identical to run_phase().
    """
    discussion, costs = run_phase(phase, ctx, complexity)

    if complexity != "complex" or not phase.micro_loop:
        return discussion, costs

    ml = phase.micro_loop
    from_slot = ml["from"]
    static_to = ml["to"]
    trigger_field = ml["trigger_field"]
    trigger_value = ml.get("trigger_value")  # None means "non-empty check"
    dynamic_target_field = ml.get("dynamic_target_field")

    # Check if trigger fires
    from_output = ctx.get(from_slot)
    if from_output is None:
        return discussion, costs

    field_value = from_output.get(trigger_field)
    if trigger_value is None:
        # Non-empty check (e.g. conflicts list has items)
        triggered = bool(field_value)
    else:
        triggered = field_value == trigger_value

    if not triggered:
        return discussion, costs

    # Resolve target: use dynamic field if configured and valid, else static
    to_slot = static_to
    if dynamic_target_field:
        dynamic_target = from_output.get(dynamic_target_field)
        if dynamic_target and dynamic_target in PERSONA_REGISTRY:
            to_slot = dynamic_target
        else:
            if dynamic_target:
                log.debug(
                    "micro_loop dynamic_target_field '%s' resolved to unknown persona '%s', falling back to '%s'",
                    dynamic_target_field, dynamic_target, static_to,
                )

    # Look up target persona from registry (may be in a different phase)
    if to_slot not in PERSONA_REGISTRY:
        log.warning("micro_loop target '%s' not found in PERSONA_REGISTRY", to_slot)
        return discussion, costs

    target_persona = PERSONA_REGISTRY[to_slot]

    # Re-run target persona with flagging slot injected
    if target_persona.reads:
        target_inputs: dict = {slot: ctx[slot] for slot in target_persona.reads if slot in ctx}
    else:
        target_inputs = dict(ctx)
    # Inject the flagging persona's output as extra context
    target_inputs[from_slot] = from_output

    try:
        target_result = target_persona.run(target_inputs)
    except Exception as exc:
        log.warning("%s %s (revised) raised %s: %s", target_persona.emoji, target_persona.name, type(exc).__name__, exc)
        target_result = {"error": str(exc)}

    target_usage = target_result.pop("_usage", {})
    ctx[target_persona.writes] = target_result
    entry = f"{target_persona.emoji} {target_persona.name} (revised): {_summarize_slot(target_persona.writes, target_result)}"
    discussion.append(entry)
    costs.append(TurnCostEntry(
        persona=f"{target_persona.name} (revised)",
        input_tokens=target_usage.get("input_tokens", 0),
        output_tokens=target_usage.get("output_tokens", 0),
        model=target_persona.model,
    ))

    # Re-run the "from" persona to re-evaluate
    source_persona: Persona | None = None
    for p in phase.personas:
        if p.name == from_slot:
            source_persona = p
            break
    if source_persona is None and from_slot in PERSONA_REGISTRY:
        source_persona = PERSONA_REGISTRY[from_slot]

    if source_persona is not None:
        if source_persona.reads:
            source_inputs: dict = {slot: ctx[slot] for slot in source_persona.reads if slot in ctx}
        else:
            source_inputs = dict(ctx)

        try:
            source_result = source_persona.run(source_inputs)
        except Exception as exc:
            log.warning("%s %s (re-eval) raised %s: %s", source_persona.emoji, source_persona.name, type(exc).__name__, exc)
            source_result = {"error": str(exc)}

        source_usage = source_result.pop("_usage", {})
        ctx[source_persona.writes] = source_result
        entry = f"{source_persona.emoji} {source_persona.name} (re-eval): {_summarize_slot(source_persona.writes, source_result)}"
        discussion.append(entry)
        costs.append(TurnCostEntry(
            persona=f"{source_persona.name} (re-eval)",
            input_tokens=source_usage.get("input_tokens", 0),
            output_tokens=source_usage.get("output_tokens", 0),
            model=source_persona.model,
        ))

    return discussion, costs


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline(
    ctx: TurnContext,
    complexity: str,
    pre_hoc: bool = True,
) -> tuple[list[tuple[str, list[str]]], list[TurnCostEntry]]:
    """
    Route to the correct phases based on complexity tier.

    Args:
        ctx: shared turn state
        complexity: one of "simple" | "moderate" | "complex"
        pre_hoc: if True, run cognitive phases; if False, run post-hoc phases

    Returns:
        (phase_results, costs) where phase_results is [(phase_name, entries)]
    """
    # Security override: check agent_manager slot
    security_override = ctx.get("agent_manager", {}).get("security_override", False)

    routing = _TIER_PHASES if pre_hoc else _POST_HOC_PHASES
    phase_names = list(routing.get(complexity, []))

    # Security override: if flagged on moderate, add security phase
    if security_override and "security" in PHASES and "security" not in phase_names:
        phase_names.append("security")

    phase_results: list[tuple[str, list[str]]] = []
    all_costs: list[TurnCostEntry] = []

    for phase_name in phase_names:
        if phase_name not in PHASES:
            log.warning("Phase '%s' referenced in routing but not registered", phase_name)
            continue
        phase = PHASES[phase_name]
        disc, costs = run_phase_with_micro_loop(phase, ctx, complexity)
        if disc:
            phase_results.append((phase_name, disc))
        all_costs.extend(costs)

    return phase_results, all_costs
