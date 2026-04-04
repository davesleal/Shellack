# Phased Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the flat post-hoc consultant model with a 9-phase cognitive pipeline using 25 personas + 4 infrastructure agents, with three-tier activation (simple/moderate/complex) and micro-loop revision support.

**Architecture:** Pipeline with shared typed dict. Each persona is a pure function: `(declared_input_slots) → named_output_slot`. Phases execute sequentially; within each phase, personas run sequentially. Micro-loops are conditional re-runs (max 1 retry) gated by complexity tier.

**Tech Stack:** Python 3.11+, Anthropic SDK (httpx), pytest, existing Shellack bot infrastructure.

**Spec:** `docs/superpowers/specs/2026-04-04-orchestrator-phases-design.md`

---

## File Structure

### New files (created)

| File | Responsibility |
|------|---------------|
| `tools/pipeline.py` | `TurnContext` TypedDict, `Phase` dataclass, `run_phase()`, `run_pipeline()`, micro-loop logic, tier routing |
| `tools/personas/__init__.py` | `Persona` base class, `PERSONA_REGISTRY` dict, `get_persona()` lookup |
| `tools/personas/strategist.py` | Phase 3: task decomposition |
| `tools/personas/researcher.py` | Phase 3: external doc lookup |
| `tools/personas/historian.py` | Phase 3: prior decision check |
| `tools/personas/architect.py` | Phase 4: structural proposal (migrated from consultants.py) |
| `tools/personas/specialist.py` | Phase 4: framework idiom validation |
| `tools/personas/data_scientist.py` | Phase 4: scale/query analysis |
| `tools/personas/empathizer.py` | Phase 4: user-facing friction detection |
| `tools/personas/connector.py` | Phase 4: cross-project pattern matching |
| `tools/personas/reuser.py` | Phase 4: registry-based duplication detection |
| `tools/personas/skeptic.py` | Phase 6: assumption challenge (replaces gut_check) |
| `tools/personas/devils_advocate.py` | Phase 6: strongest case against |
| `tools/personas/simplifier.py` | Phase 6: YAGNI enforcement |
| `tools/personas/prioritizer.py` | Phase 6: impact/effort ranking |
| `tools/personas/rogue.py` | Phase 7: stress testing |
| `tools/personas/hacker.py` | Phase 7: attack vector identification |
| `tools/personas/infosec.py` | Phase 7: defense prescription (migrated from consultants.py) |
| `tools/personas/inspector.py` | Phase 8: completeness check |
| `tools/personas/tester.py` | Phase 8: test strategy (migrated from consultants.py) |
| `tools/personas/visual_ux.py` | Phase 8: WCAG/a11y (migrated from consultants.py) |
| `tools/personas/learner.py` | Phase 9: lesson extraction |
| `tools/personas/coach.py` | Phase 9: ship/iterate/hold decision |
| `tools/personas/output_editor.py` | Phase 9: output polish (migrated from consultants.py) |
| `tools/personas/dreamer.py` | Phase 5: generative vision (later rollout) |
| `tools/personas/insights.py` | Phase 5: success measurement (later rollout) |
| `tools/personas/growth_coach.py` | Phase 5: AARRR funnel (later rollout) |
| `tests/test_pipeline.py` | Pipeline core tests |
| `tests/test_personas/` | One test file per persona |

### Modified files

| File | Changes |
|------|---------|
| `tools/agent_discussion.py` | Add 25 new emoji entries, add `add_phase_header()` method, phase-grouped `format()` |
| `bot_unified.py` | Replace inline consultant/gut-check logic with `run_pipeline()` call |

### Preserved (no changes)

`tools/token_cart.py`, `tools/thread_observer.py`, `tools/file_fetcher.py`, `tools/agent_manager.py`, `tools/registry.py`, `tools/thread_memory.py`, `tools/cost_tracker.py`

---

### Task 1: Pipeline Core — TurnContext, Persona Base, run_phase

**Files:**
- Create: `tools/pipeline.py`
- Create: `tools/personas/__init__.py`
- Create: `tests/test_pipeline.py`

- [ ] **Step 1: Write failing test for TurnContext and Persona base**

```python
# tests/test_pipeline.py
"""Tests for the cognitive pipeline core."""

import pytest
from tools.personas import Persona, PERSONA_REGISTRY
from tools.pipeline import TurnContext, run_phase, run_pipeline, Phase


class FakePersona(Persona):
    name = "fake"
    emoji = "🤖"
    model = "haiku"
    reads = ["observer"]
    system_prompt = "You are a test persona."
    max_tokens = 64

    def should_activate(self, complexity: str, turn_context: TurnContext) -> bool:
        return True

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        return f"Observer says: {inputs.get('observer', {}).get('summary', '')}"


class InactiveFakePersona(Persona):
    name = "inactive"
    emoji = "💤"
    model = "haiku"
    reads = ["observer"]
    system_prompt = "You are inactive."
    max_tokens = 64

    def should_activate(self, complexity: str, turn_context: TurnContext) -> bool:
        return False

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        return ""


# --- TurnContext ---


def test_turn_context_is_dict():
    ctx = TurnContext()
    assert isinstance(ctx, dict)


def test_turn_context_read_slot():
    ctx = TurnContext()
    ctx["observer"] = {"summary": "hello", "turn": 1}
    assert ctx["observer"]["summary"] == "hello"


def test_turn_context_write_slot():
    ctx = TurnContext()
    ctx["fake"] = {"result": "ok"}
    assert ctx["fake"]["result"] == "ok"


# --- Persona base ---


def test_persona_writes_equals_name():
    p = FakePersona()
    assert p.writes == "fake"


def test_persona_run_returns_dict(monkeypatch):
    """Persona.run() calls the API and returns parsed JSON."""
    import json

    fake_output = {"result": "ok"}
    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": json.dumps(fake_output)})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    p = FakePersona()
    monkeypatch.setattr(p, "_call_api", lambda system, user, model, max_tokens: mock_msg)

    result = p.run({"observer": {"summary": "test"}})
    assert result == fake_output


def test_persona_run_fallback_on_bad_json(monkeypatch):
    """If API returns non-JSON, persona wraps it in {raw: ...}."""
    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": "not json"})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    p = FakePersona()
    monkeypatch.setattr(p, "_call_api", lambda system, user, model, max_tokens: mock_msg)

    result = p.run({"observer": {"summary": "test"}})
    assert result == {"raw": "not json"}


# --- Phase execution ---


def test_run_phase_activates_persona(monkeypatch):
    """run_phase only runs personas whose should_activate returns True."""
    import json

    fake_output = {"result": "done"}
    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": json.dumps(fake_output)})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 5})(),
    })()

    active = FakePersona()
    inactive = InactiveFakePersona()
    monkeypatch.setattr(active, "_call_api", lambda s, u, m, mt: mock_msg)

    ctx = TurnContext()
    ctx["observer"] = {"summary": "test"}

    phase = Phase(name="test_phase", emoji="🧪", personas=[active, inactive])
    discussion_entries, cost = run_phase(phase, ctx, "moderate")

    assert "fake" in ctx
    assert ctx["fake"] == fake_output
    assert "inactive" not in ctx
    assert len(discussion_entries) == 1  # only active persona logged


def test_run_phase_empty_when_no_activation():
    """Phase with no activated personas produces no entries."""
    inactive = InactiveFakePersona()
    ctx = TurnContext()
    ctx["observer"] = {"summary": "test"}

    phase = Phase(name="test_phase", emoji="🧪", personas=[inactive])
    entries, cost = run_phase(phase, ctx, "simple")

    assert entries == []
    assert "inactive" not in ctx
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.pipeline'`

- [ ] **Step 3: Create Persona base class**

```python
# tools/personas/__init__.py
"""Cognitive persona base class and registry."""

from __future__ import annotations

import json
import logging
from typing import ClassVar

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_MODELS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(15.0)),
            max_retries=1,
        )
    return _client


PERSONA_REGISTRY: dict[str, type["Persona"]] = {}


def get_persona(name: str) -> "Persona":
    """Instantiate a persona by slot name."""
    cls = PERSONA_REGISTRY[name]
    return cls()


class Persona:
    """Base class for all cognitive personas.

    Subclasses MUST define: name, emoji, model, reads, system_prompt.
    Subclasses MUST implement: should_activate(), _build_user_content().
    """

    name: ClassVar[str]
    emoji: ClassVar[str]
    model: ClassVar[str]  # "haiku" or "sonnet"
    reads: ClassVar[list[str]]
    system_prompt: ClassVar[str]
    max_tokens: ClassVar[int] = 256

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name") and cls.name:
            PERSONA_REGISTRY[cls.name] = cls

    @property
    def writes(self) -> str:
        return self.name

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        """Override: return True if this persona should fire."""
        raise NotImplementedError

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        """Override: build the user message from declared input slots."""
        raise NotImplementedError

    def _call_api(self, system: str, user: str, model: str, max_tokens: int):
        """Call Anthropic API. Separated for testability."""
        client = _get_client()
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )

    def run(self, inputs: dict[str, dict]) -> dict:
        """Execute persona. Returns structured JSON dict."""
        user_content = self._build_user_content(inputs)
        model_id = _MODELS.get(self.model, _MODELS["haiku"])

        try:
            msg = self._call_api(self.system_prompt, user_content, model_id, self.max_tokens)
            text = msg.content[0].text.strip()
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                # Try to extract JSON from markdown code fence
                if "```json" in text:
                    json_block = text.split("```json")[1].split("```")[0].strip()
                    return json.loads(json_block)
                if text.startswith("{"):
                    # Might have trailing text after JSON
                    for end in range(len(text), 0, -1):
                        try:
                            return json.loads(text[:end])
                        except json.JSONDecodeError:
                            continue
                return {"raw": text}
        except Exception as exc:
            logger.warning(f"Persona {self.name} failed: {exc}")
            return {"error": str(exc)}

    def get_token_usage(self) -> tuple[int, int]:
        """Return (input_tokens, output_tokens) from last call. For cost tracking."""
        return (0, 0)  # override if needed
```

- [ ] **Step 4: Create pipeline module**

```python
# tools/pipeline.py
"""Cognitive pipeline — phased execution of personas with shared typed dict."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from tools.personas import Persona

logger = logging.getLogger(__name__)


class TurnContext(dict):
    """Shared typed dict for one turn. Each persona writes to its named slot."""
    pass


@dataclass
class Phase:
    """A group of personas that execute together."""
    name: str
    emoji: str
    personas: list[Persona] = field(default_factory=list)
    micro_loop: dict | None = None  # {"from": "skeptic", "to": "architect", "trigger_field": "verdict", "trigger_value": "reconsider"}


@dataclass
class TurnCostEntry:
    """Cost tracking for a single persona call."""
    persona: str
    input_tokens: int
    output_tokens: int
    model: str


def run_phase(
    phase: Phase,
    ctx: TurnContext,
    complexity: str,
) -> tuple[list[str], list[TurnCostEntry]]:
    """Execute a phase: run each persona that activates, write slots.

    Returns: (discussion_entries, cost_entries)
    """
    entries: list[str] = []
    costs: list[TurnCostEntry] = []

    for persona in phase.personas:
        if not persona.should_activate(complexity, ctx):
            continue

        # Gather only declared input slots
        inputs = {slot: ctx[slot] for slot in persona.reads if slot in ctx}

        result = persona.run(inputs)
        ctx[persona.writes] = result

        # Build discussion entry
        summary = _summarize_slot(persona.name, result)
        entries.append(f"{persona.emoji} {summary}")

        logger.info(f"Persona {persona.name} fired: {summary[:80]}")

    return entries, costs


def _summarize_slot(name: str, slot: dict) -> str:
    """One-line summary of a persona's output for the discussion log."""
    if "error" in slot:
        return f"{name}: error — {slot['error'][:60]}"
    if "raw" in slot:
        return f"{name}: {slot['raw'][:60]}"
    if "verdict" in slot:
        return f"{name}: {slot['verdict']}"
    if "summary" in slot:
        return f"{name}: {slot['summary'][:60]}"
    # Fallback: show first key
    first_key = next(iter(slot), None)
    if first_key:
        val = slot[first_key]
        if isinstance(val, str):
            return f"{name}: {val[:60]}"
        if isinstance(val, list):
            return f"{name}: {len(val)} items"
    return f"{name}: done"


# ---------------------------------------------------------------------------
# Phase definitions — populated as personas are implemented
# ---------------------------------------------------------------------------

PHASES: dict[str, Phase] = {}


def register_phase(phase: Phase) -> None:
    """Register a phase by name."""
    PHASES[phase.name] = phase


# ---------------------------------------------------------------------------
# Pipeline runner
# ---------------------------------------------------------------------------

# Phase execution order per tier
_TIER_PHASES: dict[str, list[str]] = {
    "simple": [],  # simple only runs infrastructure (not in PHASES)
    "moderate": ["plan", "design"],  # pre-hoc; challenge + quality added post-hoc
    "complex": ["plan", "design", "challenge", "security", "quality"],  # pre-hoc
}

_POST_HOC_PHASES: dict[str, list[str]] = {
    "simple": [],
    "moderate": ["challenge", "quality"],  # post-hoc review of response
    "complex": ["synthesis"],  # post agent call
}


def run_pipeline(
    ctx: TurnContext,
    complexity: str,
    pre_hoc: bool = True,
) -> tuple[list[tuple[str, list[str]]], list[TurnCostEntry]]:
    """Execute the cognitive pipeline for a complexity tier.

    Args:
        ctx: TurnContext with infrastructure slots already populated
        complexity: "simple", "moderate", or "complex"
        pre_hoc: True for phases before agent call, False for phases after

    Returns: ([(phase_name, entries)], all_costs)
    """
    if pre_hoc:
        phase_names = _TIER_PHASES.get(complexity, [])
    else:
        phase_names = _POST_HOC_PHASES.get(complexity, [])

    # Security override: if agent_manager flagged security, add security phase
    if pre_hoc and complexity == "moderate":
        am = ctx.get("agent_manager", {})
        if am.get("security_override"):
            if "security" not in phase_names:
                phase_names = list(phase_names) + ["security"]

    all_phase_results: list[tuple[str, list[str]]] = []
    all_costs: list[TurnCostEntry] = []

    for phase_name in phase_names:
        phase = PHASES.get(phase_name)
        if not phase:
            continue

        entries, costs = run_phase(phase, ctx, complexity)
        if entries:
            all_phase_results.append((phase_name, entries))
        all_costs.extend(costs)

    return all_phase_results, all_costs
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_pipeline.py -v`
Expected: All 8 tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/pipeline.py tools/personas/__init__.py tests/test_pipeline.py
git commit -m "feat: pipeline core — TurnContext, Persona base class, run_phase, run_pipeline"
```

---

### Task 2: Extend Agent Discussion for Phase-Grouped Output

**Files:**
- Modify: `tools/agent_discussion.py`
- Modify: `tests/test_agent_discussion.py`

- [ ] **Step 1: Write failing test for phase-grouped discussion**

```python
# Add to tests/test_agent_discussion.py

from tools.agent_discussion import DiscussionLog, AGENT_EMOJI


def test_add_phase_header():
    log = DiscussionLog()
    log.add_phase_header("plan", "🎯", "Plan & Research")
    log.add("strategist", "Tasks: [schema, RLS, tests]")
    result = log.format()
    assert "🎯 Plan & Research" in result
    assert "🎯 Tasks:" in result


def test_all_persona_emojis_registered():
    """Every persona in the spec has an emoji registered."""
    required = [
        "strategist", "researcher", "historian",
        "architect", "specialist", "data_scientist",
        "empathizer", "connector", "reuser",
        "skeptic", "devils_advocate", "simplifier", "prioritizer",
        "rogue", "hacker", "infosec",
        "inspector", "tester", "visual_ux",
        "learner", "coach", "output_editor",
        "dreamer", "insights", "growth_coach",
    ]
    for name in required:
        assert name in AGENT_EMOJI, f"Missing emoji for {name}"


def test_format_with_phases():
    log = DiscussionLog()
    log.add_phase_header("intake", "📨", "Intake")
    log.add("agent_manager", "Complexity: moderate")
    log.add("observer", "User asking about migration")
    log.add_phase_header("plan", "🎯", "Plan & Research")
    log.add("historian", "Prior migration had 3 commits")
    result = log.format()
    assert "📨 Intake" in result
    assert "🎯 Plan & Research" in result
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_agent_discussion.py -v`
Expected: FAIL — `AttributeError: 'DiscussionLog' has no attribute 'add_phase_header'` and missing emoji keys

- [ ] **Step 3: Update agent_discussion.py**

```python
# tools/agent_discussion.py
"""Agent discussion log — collects inter-agent chatter for transparency."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Agent emoji personas — infrastructure + 25 cognitive
AGENT_EMOJI = {
    # Infrastructure (always active)
    "observer": "\U0001f441\ufe0f",       # 👁️
    "file_fetcher": "\U0001f4c2",          # 📂
    "token_cart": "\U0001f6d2",            # 🛒
    "agent_manager": "\U0001f4cb",         # 📋
    # Phase 3: Plan & Research
    "strategist": "\U0001f3af",            # 🎯
    "researcher": "\U0001f310",            # 🌐
    "historian": "\U0001f4dc",             # 📜
    # Phase 4: Design & Propose
    "architect": "\U0001f4d0",             # 📐
    "specialist": "\U0001f9ec",            # 🧬
    "data_scientist": "\U0001f4ca",        # 📊
    "empathizer": "\U0001fac2",            # 🫂
    "connector": "\U0001f517",             # 🔗
    "reuser": "\u267b\ufe0f",             # ♻️
    # Phase 5: Vision & Measurement
    "dreamer": "\U0001f52e",               # 🔮
    "insights": "\U0001f4c9",              # 📉
    "growth_coach": "\U0001f4c8",          # 📈
    # Phase 6: Challenge
    "skeptic": "\U0001f928",               # 🤨
    "devils_advocate": "\U0001f479",       # 👹
    "simplifier": "\u2702\ufe0f",          # ✂️
    "prioritizer": "\u2696\ufe0f",         # ⚖️
    # Phase 7: Security
    "rogue": "\U0001f608",                 # 😈
    "hacker": "\U0001f3f4\u200d\u2620\ufe0f",  # 🏴‍☠️
    "infosec": "\U0001f6e1\ufe0f",         # 🛡️
    # Phase 8: Quality Gate
    "inspector": "\U0001f50d",             # 🔍
    "tester": "\U0001f9ea",                # 🧪
    "visual_ux": "\U0001f3a8",             # 🎨
    # Phase 9: Synthesis
    "learner": "\U0001f9e0",               # 🧠
    "coach": "\U0001f4aa",                 # 💪
    "output_editor": "\u270d\ufe0f",       # ✍️
    # Legacy (kept for backwards compat during migration)
    "gut_check": "\u2705",                 # ✅
    "correction": "\U0001f504",            # 🔄
}


class DiscussionLog:
    """Collects agent discussion entries for a single turn."""

    def __init__(self):
        self._entries: list[str] = []

    def add(self, agent: str, message: str) -> None:
        """Add a discussion entry. agent is a key from AGENT_EMOJI."""
        emoji = AGENT_EMOJI.get(agent, "\U0001f916")  # 🤖 fallback
        self._entries.append(f"{emoji} {message}")

    def add_phase_header(self, phase_id: str, emoji: str, label: str) -> None:
        """Add a phase separator header."""
        self._entries.append(f"\n{emoji} {label}")

    def add_phase_entries(self, phase_name: str, phase_emoji: str, entries: list[str]) -> None:
        """Add a full phase block: header + indented entries."""
        if not entries:
            return
        self.add_phase_header(phase_name, phase_emoji, phase_name.replace("_", " ").title())
        for entry in entries:
            self._entries.append(f"  {entry}")

    @property
    def entries(self) -> list[str]:
        return self._entries

    def format(self) -> str:
        """Format as a collapsible discussion block for Slack."""
        if not self._entries:
            return ""
        lines = "\n".join(self._entries)
        return f"\U0001f4ac Agent Discussion\n```\n{lines}\n```"

    def is_empty(self) -> bool:
        return len(self._entries) == 0
```

- [ ] **Step 4: Run tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_agent_discussion.py -v`
Expected: All tests PASS (old + new)

- [ ] **Step 5: Commit**

```bash
git add tools/agent_discussion.py tests/test_agent_discussion.py
git commit -m "feat: extend discussion log with phase headers and 25 persona emojis"
```

---

### Task 3: Phase 3 — Strategist, Historian, Researcher

**Files:**
- Create: `tools/personas/strategist.py`
- Create: `tools/personas/historian.py`
- Create: `tools/personas/researcher.py`
- Create: `tests/test_personas/__init__.py`
- Create: `tests/test_personas/test_strategist.py`
- Create: `tests/test_personas/test_historian.py`
- Create: `tests/test_personas/test_researcher.py`
- Modify: `tools/pipeline.py` (register plan phase)

- [ ] **Step 1: Write failing tests for Strategist**

```python
# tests/test_personas/__init__.py
# (empty)
```

```python
# tests/test_personas/test_strategist.py
"""Tests for the Strategist persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.strategist import Strategist
from tools.pipeline import TurnContext


@pytest.fixture
def strategist():
    return Strategist()


def test_strategist_metadata(strategist):
    assert strategist.name == "strategist"
    assert strategist.model == "haiku"
    assert strategist.writes == "strategist"
    assert "observer" in strategist.reads
    assert "token_cart" in strategist.reads


def test_strategist_activates_on_moderate(strategist):
    ctx = TurnContext()
    assert strategist.should_activate("moderate", ctx) is True
    assert strategist.should_activate("complex", ctx) is True
    assert strategist.should_activate("simple", ctx) is False


def test_strategist_run(strategist, monkeypatch):
    output = {"tasks": ["schema", "RLS"], "sequence": [1, 2], "dependencies": [], "estimated_complexity": "moderate"}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(strategist, "_call_api", lambda s, u, m, mt: mock_msg)

    result = strategist.run({
        "observer": {"summary": "User wants Phase 3 migration", "turn": 1},
        "token_cart": {"enriched_prompt": "migrate follows table", "handoff": ""},
    })
    assert result["tasks"] == ["schema", "RLS"]
    assert result["estimated_complexity"] == "moderate"


def test_strategist_builds_user_content(strategist):
    inputs = {
        "observer": {"summary": "User wants migration", "turn": 1},
        "token_cart": {"enriched_prompt": "migrate follows", "handoff": "prior work done"},
    }
    content = strategist._build_user_content(inputs)
    assert "User wants migration" in content
    assert "migrate follows" in content
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/test_strategist.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tools.personas.strategist'`

- [ ] **Step 3: Implement Strategist**

```python
# tools/personas/strategist.py
"""Strategist persona — task decomposition and sequencing."""

from tools.personas import Persona


class Strategist(Persona):
    name = "strategist"
    emoji = "\U0001f3af"  # 🎯
    model = "haiku"
    reads = ["observer", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Strategist — the team's planner. Given a task, decompose it into sequenced subtasks.

Your job:
1. DECOMPOSE: Break the task into concrete, ordered steps
2. SEQUENCE: Identify which steps depend on others
3. ESTIMATE: Is this simple, moderate, or complex?

Output ONLY valid JSON:
{"tasks": ["step1", "step2"], "sequence": [1, 2], "dependencies": [{"step": 2, "depends_on": 1}], "estimated_complexity": "moderate"}

Rules:
- Max 6 tasks. If more needed, group related work.
- Each task should be completable in one session.
- Name tasks concretely — "Create follows table with RLS" not "Set up database"."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        observer = inputs.get("observer", {})
        token_cart = inputs.get("token_cart", {})

        parts = []
        if observer.get("summary"):
            parts.append(f"## Thread Context\n{observer['summary']}")
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Task\n{token_cart['enriched_prompt']}")
        if token_cart.get("handoff"):
            parts.append(f"## Prior Work\n{token_cart['handoff'][:500]}")

        return "\n\n".join(parts) if parts else "No context available."
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/test_strategist.py -v`
Expected: All 4 tests PASS

- [ ] **Step 5: Write failing tests for Historian**

```python
# tests/test_personas/test_historian.py
"""Tests for the Historian persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.historian import Historian
from tools.pipeline import TurnContext


@pytest.fixture
def historian():
    return Historian()


def test_historian_metadata(historian):
    assert historian.name == "historian"
    assert historian.model == "haiku"
    assert "observer" in historian.reads
    assert "token_cart" in historian.reads


def test_historian_activates_on_moderate(historian):
    ctx = TurnContext()
    assert historian.should_activate("moderate", ctx) is True
    assert historian.should_activate("complex", ctx) is True
    assert historian.should_activate("simple", ctx) is False


def test_historian_run(historian, monkeypatch):
    output = {"prior_decisions": ["Used RLS for auth"], "conflicts": [], "lessons": ["Phase 2 took 3 commits"]}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=40, output_tokens=25)
    monkeypatch.setattr(historian, "_call_api", lambda s, u, m, mt: mock_msg)

    result = historian.run({
        "observer": {"summary": "migration task", "turn": 1},
        "token_cart": {"handoff": "Phase 2 complete", "registry": "| RLS | auth pattern |"},
    })
    assert result["conflicts"] == []
    assert "Phase 2" in result["lessons"][0]
```

- [ ] **Step 6: Implement Historian**

```python
# tools/personas/historian.py
"""Historian persona — checks prior decisions and learned lessons."""

from tools.personas import Persona


class Historian(Persona):
    name = "historian"
    emoji = "\U0001f4dc"  # 📜
    model = "haiku"
    reads = ["observer", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Historian — the team's memory. Check whether the current task conflicts with prior decisions or repeats past mistakes.

Your job:
1. RECALL: What prior decisions are relevant to this task?
2. DETECT: Does the proposed approach conflict with anything we decided before?
3. LEARN: What lessons from past work apply here?

Output ONLY valid JSON:
{"prior_decisions": ["decision1"], "conflicts": [{"decision": "use RLS", "conflict_with": "proposed app-level auth"}], "lessons": ["lesson1"]}

Rules:
- Only report ACTUAL conflicts, not hypothetical ones
- If no conflicts, return empty conflicts array
- Draw from handoff context, registry, and thread memory
- Be specific — name the prior decision and what conflicts with it"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        observer = inputs.get("observer", {})
        token_cart = inputs.get("token_cart", {})

        parts = []
        if observer.get("summary"):
            parts.append(f"## Current Task\n{observer['summary']}")
        if token_cart.get("handoff"):
            parts.append(f"## Prior Handoff\n{token_cart['handoff'][:800]}")
        if token_cart.get("registry"):
            parts.append(f"## Project Registry\n{token_cart['registry'][:500]}")

        return "\n\n".join(parts) if parts else "No prior context available."
```

- [ ] **Step 7: Run Historian tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/test_historian.py -v`
Expected: All 3 tests PASS

- [ ] **Step 8: Write failing tests for Researcher**

```python
# tests/test_personas/test_researcher.py
"""Tests for the Researcher persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.researcher import Researcher
from tools.pipeline import TurnContext


@pytest.fixture
def researcher():
    return Researcher()


def test_researcher_metadata(researcher):
    assert researcher.name == "researcher"
    assert researcher.model == "sonnet"
    assert "observer" in researcher.reads
    assert "strategist" in researcher.reads


def test_researcher_activates_only_on_complex(researcher):
    ctx = TurnContext()
    assert researcher.should_activate("complex", ctx) is True
    assert researcher.should_activate("moderate", ctx) is False
    assert researcher.should_activate("simple", ctx) is False


def test_researcher_run(researcher, monkeypatch):
    output = {"findings": [{"source": "Supabase docs", "summary": "RLS uses policies", "relevance": "high"}], "apis_referenced": ["supabase.rls"]}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=60, output_tokens=40)
    monkeypatch.setattr(researcher, "_call_api", lambda s, u, m, mt: mock_msg)

    result = researcher.run({
        "observer": {"summary": "Supabase migration"},
        "strategist": {"tasks": ["Create RLS policies"], "sequence": [1]},
    })
    assert len(result["findings"]) == 1
    assert result["findings"][0]["source"] == "Supabase docs"
```

- [ ] **Step 9: Implement Researcher**

```python
# tools/personas/researcher.py
"""Researcher persona — fetches external docs and best practices."""

from tools.personas import Persona


class Researcher(Persona):
    name = "researcher"
    emoji = "\U0001f310"  # 🌐
    model = "sonnet"
    reads = ["observer", "strategist"]
    max_tokens = 512
    system_prompt = """You are the Researcher — the team's external knowledge source. When the task references external APIs, libraries, or frameworks, provide accurate, current information.

Your job:
1. IDENTIFY: What external knowledge does this task need?
2. RETRIEVE: What do the docs/best practices say?
3. SUMMARIZE: Concise, actionable findings

Output ONLY valid JSON:
{"findings": [{"source": "doc name", "summary": "key info", "relevance": "high|medium|low"}], "apis_referenced": ["api.name"]}

Rules:
- Only research what the task actually needs — no tangential exploration
- Cite specific sources (doc pages, API references)
- If no external knowledge is needed, return empty findings array
- Prefer official docs over blog posts"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        observer = inputs.get("observer", {})
        strategist = inputs.get("strategist", {})

        parts = []
        if observer.get("summary"):
            parts.append(f"## Task Context\n{observer['summary']}")
        if strategist.get("tasks"):
            task_list = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{task_list}")

        return "\n\n".join(parts) if parts else "No context available."
```

- [ ] **Step 10: Register Phase 3 in pipeline**

```python
# Add to bottom of tools/pipeline.py, after the run_pipeline function:

def _register_default_phases():
    """Register built-in phases. Called on import."""
    try:
        from tools.personas.strategist import Strategist
        from tools.personas.historian import Historian
        from tools.personas.researcher import Researcher

        register_phase(Phase(
            name="plan",
            emoji="\U0001f3af",  # 🎯
            personas=[Strategist(), Historian(), Researcher()],
            micro_loop={"from": "historian", "to": "strategist", "trigger_field": "conflicts"},
        ))
    except ImportError:
        pass  # personas not yet implemented


_register_default_phases()
```

- [ ] **Step 11: Run all Phase 3 tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 12: Commit**

```bash
git add tools/personas/strategist.py tools/personas/historian.py tools/personas/researcher.py \
    tests/test_personas/__init__.py tests/test_personas/test_strategist.py \
    tests/test_personas/test_historian.py tests/test_personas/test_researcher.py \
    tools/pipeline.py
git commit -m "feat: Phase 3 personas — Strategist, Historian, Researcher"
```

---

### Task 4: Phase 4 — Architect, Specialist, Data Scientist, Empathizer, Connector, Reuser

**Files:**
- Create: `tools/personas/architect.py`
- Create: `tools/personas/specialist.py`
- Create: `tools/personas/data_scientist.py`
- Create: `tools/personas/empathizer.py`
- Create: `tools/personas/connector.py`
- Create: `tools/personas/reuser.py`
- Create: `tests/test_personas/test_architect.py`
- Create: `tests/test_personas/test_design_phase.py`
- Modify: `tools/pipeline.py` (register design phase)

- [ ] **Step 1: Write failing tests for Architect (migrated from consultants.py)**

```python
# tests/test_personas/test_architect.py
"""Tests for the Architect persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.architect import Architect
from tools.pipeline import TurnContext


@pytest.fixture
def architect():
    return Architect()


def test_architect_metadata(architect):
    assert architect.name == "architect"
    assert architect.model == "sonnet"
    assert "strategist" in architect.reads
    assert "historian" in architect.reads
    assert "token_cart" in architect.reads


def test_architect_activates_moderate_and_complex(architect):
    ctx = TurnContext()
    assert architect.should_activate("moderate", ctx) is True
    assert architect.should_activate("complex", ctx) is True
    assert architect.should_activate("simple", ctx) is False


def test_architect_run(architect, monkeypatch):
    output = {
        "proposal": "Add follows table with FK to supabase_users",
        "data_model": "follows(id, follower_id, following_id, created_at)",
        "api_surface": "followUser(), unfollowUser(), getFollowers()",
        "files_affected": ["supabase/migrations/003.sql", "src/services/followService.ts"],
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=80, output_tokens=60)
    monkeypatch.setattr(architect, "_call_api", lambda s, u, m, mt: mock_msg)

    result = architect.run({
        "strategist": {"tasks": ["Create follows table"], "sequence": [1]},
        "historian": {"prior_decisions": ["Use RLS"], "conflicts": []},
        "token_cart": {"enriched_prompt": "migrate follows", "registry": ""},
    })
    assert "follows" in result["proposal"]
    assert len(result["files_affected"]) == 2
```

- [ ] **Step 2: Implement all Phase 4 personas**

```python
# tools/personas/architect.py
"""Architect persona — structural proposals."""

from tools.personas import Persona


class Architect(Persona):
    name = "architect"
    emoji = "\U0001f4d0"  # 📐
    model = "sonnet"
    reads = ["strategist", "historian", "token_cart"]
    max_tokens = 512
    system_prompt = """You are the Architect — the team's structural designer. Propose how to build what the Strategist planned.

Your job:
1. PROPOSE: Structure, data models, API surface
2. DECOMPOSE: Which files need to change
3. JUSTIFY: Why this structure over alternatives

Output ONLY valid JSON:
{"proposal": "one-paragraph description", "data_model": "schema description", "api_surface": "key functions/endpoints", "files_affected": ["path/to/file.ext"]}

Rules:
- Respect prior decisions from the Historian
- Follow existing patterns in the codebase (from registry/handoff)
- Prefer simplicity — the Simplifier will challenge overengineering
- Name specific files and functions, not abstract concepts"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        strategist = inputs.get("strategist", {})
        historian = inputs.get("historian", {})
        token_cart = inputs.get("token_cart", {})

        parts = []
        if strategist.get("tasks"):
            task_list = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{task_list}")
        if historian.get("prior_decisions"):
            decisions = "\n".join(f"- {d}" for d in historian["prior_decisions"])
            parts.append(f"## Prior Decisions (MUST respect)\n{decisions}")
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Task Detail\n{token_cart['enriched_prompt'][:500]}")
        if token_cart.get("registry"):
            parts.append(f"## Registry\n{token_cart['registry'][:500]}")

        return "\n\n".join(parts) if parts else "No context available."
```

```python
# tools/personas/specialist.py
"""Specialist persona — language/framework idiom validation."""

from tools.personas import Persona


class Specialist(Persona):
    name = "specialist"
    emoji = "\U0001f9ec"  # 🧬
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Specialist — the team's idiom enforcer. Check the Architect's proposal for framework-specific anti-patterns.

Output ONLY valid JSON:
{"idiom_violations": [{"pattern": "what's wrong", "fix": "how to fix", "framework": "which framework"}], "verdict": "idiomatic"|"fixable"|"wrong"}

Rules:
- Only flag actual idiom violations, not style preferences
- Be framework-specific: Swift has different rules than Python, React different from Vue
- "idiomatic" = no issues. "fixable" = minor issues. "wrong" = fundamentally misusing the framework"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        token_cart = inputs.get("token_cart", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("api_surface"):
            parts.append(f"## API\n{architect['api_surface']}")
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Context\n{token_cart['enriched_prompt'][:300]}")
        return "\n\n".join(parts) if parts else "No proposal to review."
```

```python
# tools/personas/data_scientist.py
"""Data Scientist persona — scale and query pattern analysis."""

from tools.personas import Persona


class DataScientist(Persona):
    name = "data_scientist"
    emoji = "\U0001f4ca"  # 📊
    model = "haiku"
    reads = ["architect"]
    max_tokens = 256
    system_prompt = """You are the Data Scientist — the team's scale analyst. Check the Architect's data model for scale issues.

Output ONLY valid JSON:
{"scale_concerns": ["concern1"], "query_patterns": ["pattern1"], "index_suggestions": ["index1"], "verdict": "scalable"|"review"|"blocker"}

Rules:
- Focus on data access patterns, not business logic
- Flag N+1 queries, missing indexes, unbounded queries
- "scalable" = no issues. "review" = potential issues at scale. "blocker" = will fail under load"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        return "\n\n".join(parts) if parts else "No data model to review."
```

```python
# tools/personas/empathizer.py
"""Empathizer persona — end-user perspective."""

from tools.personas import Persona


class Empathizer(Persona):
    name = "empathizer"
    emoji = "\U0001fac2"  # 🫂
    model = "haiku"
    reads = ["architect", "observer"]
    max_tokens = 256
    system_prompt = """You are the Empathizer — the team's user advocate. How does the person USING this feature feel?

Output ONLY valid JSON:
{"friction_points": [{"element": "what", "issue": "why it's friction", "suggestion": "how to fix"}], "verdict": "smooth"|"rough"|"blocking"}

Rules:
- Think from the end user's perspective, not the developer's
- "smooth" = intuitive. "rough" = confusing but usable. "blocking" = users will abandon
- Focus on the most impactful friction, not nitpicks"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        observer = inputs.get("observer", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("api_surface"):
            parts.append(f"## User-Facing API\n{architect['api_surface']}")
        if observer.get("summary"):
            parts.append(f"## Context\n{observer['summary']}")
        return "\n\n".join(parts) if parts else "No proposal to review."
```

```python
# tools/personas/connector.py
"""Connector persona — cross-project pattern recognition."""

from tools.personas import Persona


class Connector(Persona):
    name = "connector"
    emoji = "\U0001f517"  # 🔗
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Connector — the team's pattern matcher. Identify similar patterns across projects.

Output ONLY valid JSON:
{"similar_patterns": [{"project": "name", "pattern": "description", "relevance": "high|medium|low"}], "reuse_opportunities": ["opportunity"]}

Rules:
- Only flag patterns you can point to in the registry or handoff
- "This is similar to how we solved X" is valuable. "Maybe check Y" is not.
- If no cross-project patterns found, return empty arrays"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        token_cart = inputs.get("token_cart", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if token_cart.get("registry"):
            parts.append(f"## Registry\n{token_cart['registry'][:600]}")
        return "\n\n".join(parts) if parts else "No proposal to review."
```

```python
# tools/personas/reuser.py
"""Reuser persona — registry-based duplication detection."""

from tools.personas import Persona


class Reuser(Persona):
    name = "reuser"
    emoji = "\u267b\ufe0f"  # ♻️
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Reuser — the team's DRY enforcer. Check if the proposal creates something that already exists or uses a library inconsistently.

Output ONLY valid JSON:
{"existing_components": [{"name": "component", "path": "file/path", "match_score": 0.9}], "lib_consistency": [{"adopted": "lib we use", "proposed": "lib they want", "fix": "use adopted lib"}], "verdict": "clean"|"duplicate"|"inconsistent"}

Rules:
- Check the registry for existing components that match
- Check if adopted libraries are being bypassed (e.g., using fetch when SWR is adopted)
- "clean" = no duplication. "duplicate" = existing component found. "inconsistent" = wrong lib used
- If verdict is "duplicate", the Architect MUST be re-run with your findings (micro-loop)"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        token_cart = inputs.get("token_cart", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("files_affected"):
            files = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files\n{files}")
        if token_cart.get("registry"):
            parts.append(f"## Registry (check for existing components)\n{token_cart['registry'][:600]}")
        return "\n\n".join(parts) if parts else "No proposal to review."
```

- [ ] **Step 3: Write integration test for design phase**

```python
# tests/test_personas/test_design_phase.py
"""Integration test for the Design phase — verifies moderate subset and complex full set."""

import json
import pytest
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.architect import Architect
from tools.personas.specialist import Specialist
from tools.personas.data_scientist import DataScientist
from tools.personas.empathizer import Empathizer
from tools.personas.connector import Connector
from tools.personas.reuser import Reuser


def _mock_api(persona, output):
    """Monkeypatch _call_api on a persona to return canned output."""
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_moderate_design_only_3_personas():
    """On moderate, only Architect + Specialist + Reuser fire."""
    personas = [Architect(), Specialist(), DataScientist(), Empathizer(), Connector(), Reuser()]
    for p in personas:
        _mock_api(p, {"verdict": "ok"})

    ctx = TurnContext()
    ctx["strategist"] = {"tasks": ["add table"], "sequence": [1]}
    ctx["historian"] = {"prior_decisions": [], "conflicts": []}
    ctx["token_cart"] = {"enriched_prompt": "test", "registry": "", "handoff": ""}
    ctx["observer"] = {"summary": "test"}

    phase = Phase(name="design", emoji="📐", personas=personas)
    entries, _ = run_phase(phase, ctx, "moderate")

    activated = [p.name for p in personas if p.name in ctx]
    assert "architect" in activated
    assert "specialist" in activated
    assert "reuser" in activated
    assert "data_scientist" not in activated
    assert "empathizer" not in activated
    assert "connector" not in activated


def test_complex_design_all_6_personas():
    """On complex, all 6 personas fire."""
    personas = [Architect(), Specialist(), DataScientist(), Empathizer(), Connector(), Reuser()]
    for p in personas:
        _mock_api(p, {"verdict": "ok"})

    ctx = TurnContext()
    ctx["strategist"] = {"tasks": ["refactor auth"], "sequence": [1]}
    ctx["historian"] = {"prior_decisions": [], "conflicts": []}
    ctx["token_cart"] = {"enriched_prompt": "refactor", "registry": "| Modal | ui/modal.tsx |"}
    ctx["observer"] = {"summary": "refactor auth module"}

    phase = Phase(name="design", emoji="📐", personas=personas)
    entries, _ = run_phase(phase, ctx, "complex")

    activated = [p.name for p in personas if p.name in ctx]
    assert len(activated) == 6
```

- [ ] **Step 4: Register design phase in pipeline.py**

Add to `_register_default_phases()` in `tools/pipeline.py`:

```python
    try:
        from tools.personas.architect import Architect
        from tools.personas.specialist import Specialist
        from tools.personas.data_scientist import DataScientist
        from tools.personas.empathizer import Empathizer
        from tools.personas.connector import Connector
        from tools.personas.reuser import Reuser

        register_phase(Phase(
            name="design",
            emoji="\U0001f4d0",  # 📐
            personas=[Architect(), Specialist(), DataScientist(), Empathizer(), Connector(), Reuser()],
            micro_loop={"from": "reuser", "to": "architect", "trigger_field": "verdict", "trigger_value": "duplicate"},
        ))
    except ImportError:
        pass
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/personas/architect.py tools/personas/specialist.py tools/personas/data_scientist.py \
    tools/personas/empathizer.py tools/personas/connector.py tools/personas/reuser.py \
    tests/test_personas/test_architect.py tests/test_personas/test_design_phase.py \
    tools/pipeline.py
git commit -m "feat: Phase 4 personas — Architect, Specialist, DataScientist, Empathizer, Connector, Reuser"
```

---

### Task 5: Phase 6 — Skeptic, Devil's Advocate, Simplifier, Prioritizer

**Files:**
- Create: `tools/personas/skeptic.py`
- Create: `tools/personas/devils_advocate.py`
- Create: `tools/personas/simplifier.py`
- Create: `tools/personas/prioritizer.py`
- Create: `tests/test_personas/test_skeptic.py`
- Create: `tests/test_personas/test_challenge_phase.py`
- Modify: `tools/pipeline.py` (register challenge phase)

- [ ] **Step 1: Write failing test for Skeptic**

```python
# tests/test_personas/test_skeptic.py
"""Tests for the Skeptic persona."""

import json
import pytest
from unittest.mock import MagicMock
from tools.personas.skeptic import Skeptic
from tools.pipeline import TurnContext


@pytest.fixture
def skeptic():
    return Skeptic()


def test_skeptic_metadata(skeptic):
    assert skeptic.name == "skeptic"
    assert skeptic.model == "haiku"
    assert "architect" in skeptic.reads
    assert "strategist" in skeptic.reads


def test_skeptic_activates_moderate_and_complex(skeptic):
    ctx = TurnContext()
    assert skeptic.should_activate("moderate", ctx) is True
    assert skeptic.should_activate("complex", ctx) is True
    assert skeptic.should_activate("simple", ctx) is False


def test_skeptic_proceed_verdict(skeptic, monkeypatch):
    output = {"assumptions": [], "verdict": "proceed", "revision_target": None}
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(skeptic, "_call_api", lambda s, u, m, mt: mock_msg)

    result = skeptic.run({
        "architect": {"proposal": "Add follows table"},
        "strategist": {"tasks": ["schema"]},
    })
    assert result["verdict"] == "proceed"
    assert result["revision_target"] is None


def test_skeptic_reconsider_verdict(skeptic, monkeypatch):
    output = {
        "assumptions": [{"claim": "unique constraint sufficient", "evidence": "none given", "risk": "race condition"}],
        "verdict": "reconsider",
        "revision_target": "architect",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(skeptic, "_call_api", lambda s, u, m, mt: mock_msg)

    result = skeptic.run({
        "architect": {"proposal": "Add follows table with unique constraint"},
        "strategist": {"tasks": ["schema"]},
    })
    assert result["verdict"] == "reconsider"
    assert result["revision_target"] == "architect"
    assert len(result["assumptions"]) == 1
```

- [ ] **Step 2: Implement all Phase 6 personas**

```python
# tools/personas/skeptic.py
"""Skeptic persona — challenges assumptions."""

from tools.personas import Persona


class Skeptic(Persona):
    name = "skeptic"
    emoji = "\U0001f928"  # 🤨
    model = "haiku"
    reads = ["architect", "strategist"]
    max_tokens = 256
    system_prompt = """You are the Skeptic — the team's assumption checker. Challenge unstated assumptions in the proposal.

Output ONLY valid JSON:
{"assumptions": [{"claim": "what's assumed", "evidence": "what evidence supports it", "risk": "what happens if wrong"}], "verdict": "proceed"|"reconsider"|"block", "revision_target": null|"architect"}

Rules:
- Only flag assumptions that could actually cause problems if wrong
- "proceed" = assumptions are reasonable. "reconsider" = risky assumptions need addressing. "block" = fatal assumption
- Set revision_target to "architect" if the Architect should revise the proposal
- Don't challenge obvious truths or well-established patterns
- Max 3 assumptions — focus on the riskiest"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        strategist = inputs.get("strategist", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal to Challenge\n{architect['proposal']}")
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if strategist.get("tasks"):
            task_list = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{task_list}")
        return "\n\n".join(parts) if parts else "No proposal to challenge."
```

```python
# tools/personas/devils_advocate.py
"""Devil's Advocate persona — argues the opposite."""

from tools.personas import Persona


class DevilsAdvocate(Persona):
    name = "devils_advocate"
    emoji = "\U0001f479"  # 👹
    model = "haiku"
    reads = ["architect", "strategist"]
    max_tokens = 256
    system_prompt = """You are the Devil's Advocate — build the strongest case AGAINST the current proposal.

Output ONLY valid JSON:
{"counter_argument": "the best case against", "alternative": "what we'd do instead", "verdict": "proceed"|"has_merit"|"stop"}

Rules:
- This is a stress test, not obstruction. Build the STRONGEST possible counter-argument.
- "proceed" = the proposal survives scrutiny. "has_merit" = counter-argument is worth considering. "stop" = the counter-argument is stronger than the proposal.
- Always propose an alternative, even if you think the proposal should proceed.
- Be specific — "what if we didn't build this at all?" is only valid if you can explain why."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        strategist = inputs.get("strategist", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if strategist.get("tasks"):
            task_list = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Plan\n{task_list}")
        return "\n\n".join(parts) if parts else "No proposal to challenge."
```

```python
# tools/personas/simplifier.py
"""Simplifier persona — YAGNI enforcement."""

from tools.personas import Persona


class Simplifier(Persona):
    name = "simplifier"
    emoji = "\u2702\ufe0f"  # ✂️
    model = "haiku"
    reads = ["architect"]
    max_tokens = 256
    system_prompt = """You are the Simplifier — the team's YAGNI enforcer. Can we do this in half the code?

Output ONLY valid JSON:
{"simplifications": [{"current": "what's proposed", "proposed": "simpler alternative", "savings": "what we save"}], "verdict": "minimal"|"reducible"|"overengineered"}

Rules:
- "minimal" = already as simple as possible. "reducible" = could be simpler. "overengineered" = way more than needed.
- Three similar lines > a premature abstraction.
- Only suggest simplifications that preserve ALL functionality.
- Max 3 simplifications."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("files_affected"):
            parts.append(f"## Files: {len(architect['files_affected'])}")
        return "\n\n".join(parts) if parts else "No proposal to simplify."
```

```python
# tools/personas/prioritizer.py
"""Prioritizer persona — impact/effort ranking."""

from tools.personas import Persona


class Prioritizer(Persona):
    name = "prioritizer"
    emoji = "\u2696\ufe0f"  # ⚖️
    model = "haiku"
    reads = ["strategist", "skeptic"]
    max_tokens = 256
    system_prompt = """You are the Prioritizer — the team's tiebreaker. When multiple options survive, rank them by impact-to-effort ratio.

Output ONLY valid JSON:
{"ranked_options": [{"option": "name", "impact": "high|medium|low", "effort": "high|medium|low", "score": 0.8}], "recommendation": "what to do first and why"}

Rules:
- Score = impact / effort (high impact + low effort = best)
- If only one option, still score it — is it worth doing at all?
- Consider the Skeptic's assumptions when ranking — risky assumptions lower the score
- Be decisive — pick one recommendation"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        strategist = inputs.get("strategist", {})
        skeptic = inputs.get("skeptic", {})
        parts = []
        if strategist.get("tasks"):
            task_list = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Options/Tasks\n{task_list}")
        if skeptic.get("assumptions"):
            assumptions = "\n".join(f"- {a['claim']}: {a['risk']}" for a in skeptic["assumptions"])
            parts.append(f"## Risk Factors\n{assumptions}")
        return "\n\n".join(parts) if parts else "No options to rank."
```

- [ ] **Step 3: Register challenge phase in pipeline.py**

Add to `_register_default_phases()`:

```python
    try:
        from tools.personas.skeptic import Skeptic
        from tools.personas.devils_advocate import DevilsAdvocate
        from tools.personas.simplifier import Simplifier
        from tools.personas.prioritizer import Prioritizer

        register_phase(Phase(
            name="challenge",
            emoji="\U0001f928",  # 🤨
            personas=[Skeptic(), DevilsAdvocate(), Simplifier(), Prioritizer()],
            micro_loop={"from": "skeptic", "to": "architect", "trigger_field": "verdict", "trigger_value": "reconsider"},
        ))
    except ImportError:
        pass
```

- [ ] **Step 4: Write challenge phase integration test**

```python
# tests/test_personas/test_challenge_phase.py
"""Integration test for the Challenge phase."""

import json
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.skeptic import Skeptic
from tools.personas.devils_advocate import DevilsAdvocate
from tools.personas.simplifier import Simplifier
from tools.personas.prioritizer import Prioritizer


def _mock_api(persona, output):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_moderate_challenge_skeptic_and_prioritizer_only():
    """On moderate, only Skeptic + Prioritizer fire (post-hoc advisory)."""
    personas = [Skeptic(), DevilsAdvocate(), Simplifier(), Prioritizer()]
    for p in personas:
        _mock_api(p, {"verdict": "proceed"})

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "add table"}
    ctx["strategist"] = {"tasks": ["schema"]}

    phase = Phase(name="challenge", emoji="🤨", personas=personas)
    run_phase(phase, ctx, "moderate")

    assert "skeptic" in ctx
    assert "prioritizer" in ctx
    assert "devils_advocate" not in ctx
    assert "simplifier" not in ctx
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/personas/skeptic.py tools/personas/devils_advocate.py \
    tools/personas/simplifier.py tools/personas/prioritizer.py \
    tests/test_personas/test_skeptic.py tests/test_personas/test_challenge_phase.py \
    tools/pipeline.py
git commit -m "feat: Phase 6 personas — Skeptic, Devil's Advocate, Simplifier, Prioritizer"
```

---

### Task 6: Phase 7-8 — Security + Quality Gate

**Files:**
- Create: `tools/personas/rogue.py`
- Create: `tools/personas/hacker.py`
- Create: `tools/personas/infosec.py`
- Create: `tools/personas/inspector.py`
- Create: `tools/personas/tester.py`
- Create: `tools/personas/visual_ux.py`
- Create: `tests/test_personas/test_security_phase.py`
- Create: `tests/test_personas/test_quality_phase.py`
- Modify: `tools/pipeline.py` (register security + quality phases)

- [ ] **Step 1: Implement Security personas (Rogue, Hacker, Infosec)**

```python
# tools/personas/rogue.py
"""Rogue persona — stress testing scenarios."""

from tools.personas import Persona


class Rogue(Persona):
    name = "rogue"
    emoji = "\U0001f608"  # 😈
    model = "haiku"
    reads = ["architect"]
    max_tokens = 256
    system_prompt = """You are the Rogue — the team's chaos engineer. What breaks under stress?

Output ONLY valid JSON:
{"stress_scenarios": [{"scenario": "what happens", "impact": "how bad", "likelihood": "high|medium|low"}], "verdict": "resilient"|"fragile"|"breaks"}

Rules:
- Think: 10x concurrent users, 50MB payloads, race conditions, network partitions
- Focus on scenarios that are plausible, not theoretical
- Max 3 scenarios — the scariest ones"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity == "complex":
            return True
        if complexity == "moderate":
            am = turn_context.get("agent_manager", {})
            return am.get("security_override", False)
        return False

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if architect.get("api_surface"):
            parts.append(f"## API\n{architect['api_surface']}")
        return "\n\n".join(parts) if parts else "No proposal to stress test."
```

```python
# tools/personas/hacker.py
"""Hacker persona — attack vector identification."""

from tools.personas import Persona


class Hacker(Persona):
    name = "hacker"
    emoji = "\U0001f3f4\u200d\u2620\ufe0f"  # 🏴‍☠️
    model = "haiku"
    reads = ["architect"]
    max_tokens = 256
    system_prompt = """You are the Hacker — the team's red teamer. How would a bad actor exploit this?

Output ONLY valid JSON:
{"attack_vectors": [{"vector": "attack name", "severity": "critical|high|medium|low", "exploitability": "easy|moderate|hard"}], "verdict": "secure"|"vulnerable"|"critical"}

Rules:
- Think: injection, privilege escalation, data exfiltration, rate limit bypass, IDOR
- Focus on the proposal's specific attack surface, not generic security advice
- "critical" = must fix before shipping. "vulnerable" = should fix. "secure" = no vectors found
- Max 3 vectors — the most exploitable ones"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity == "complex":
            return True
        if complexity == "moderate":
            am = turn_context.get("agent_manager", {})
            return am.get("security_override", False)
        return False

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        return "\n\n".join(parts) if parts else "No proposal to attack."
```

```python
# tools/personas/infosec.py
"""Infosec persona — defense prescription."""

from tools.personas import Persona


class Infosec(Persona):
    name = "infosec"
    emoji = "\U0001f6e1\ufe0f"  # 🛡️
    model = "sonnet"
    reads = ["architect", "rogue", "hacker"]
    max_tokens = 512
    system_prompt = """You are Infosec — the team's defensive security expert. For every threat found by Rogue and Hacker, prescribe a defense.

Output ONLY valid JSON:
{"mitigations": [{"threat": "what's the threat", "defense": "how to defend", "priority": "critical|high|medium"}], "verdict": "clear"|"mitigable"|"blocker"}

Rules:
- Every threat from Rogue and Hacker must have a corresponding mitigation
- "blocker" means the design MUST change — this triggers a micro-loop back to Architect
- "blocker" cannot be overridden — it's a hard gate
- Prefer platform-native security (RLS, CORS headers, CSP) over application-level checks
- Be specific — name the exact defense mechanism"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity == "complex":
            return True
        if complexity == "moderate":
            am = turn_context.get("agent_manager", {})
            return am.get("security_override", False)
        return False

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        rogue = inputs.get("rogue", {})
        hacker = inputs.get("hacker", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if rogue.get("stress_scenarios"):
            scenarios = "\n".join(f"- {s['scenario']} ({s['impact']})" for s in rogue["stress_scenarios"])
            parts.append(f"## Stress Scenarios (Rogue)\n{scenarios}")
        if hacker.get("attack_vectors"):
            vectors = "\n".join(f"- {v['vector']} ({v['severity']})" for v in hacker["attack_vectors"])
            parts.append(f"## Attack Vectors (Hacker)\n{vectors}")
        return "\n\n".join(parts) if parts else "No threats to mitigate."
```

- [ ] **Step 2: Implement Quality personas (Inspector, Tester, Visual UX)**

```python
# tools/personas/inspector.py
"""Inspector persona — completeness check."""

from tools.personas import Persona


class Inspector(Persona):
    name = "inspector"
    emoji = "\U0001f50d"  # 🔍
    model = "haiku"
    reads = ["architect"]
    max_tokens = 256
    system_prompt = """You are the Inspector — the team's completeness checker. Find gaps: edge cases, missing returns, unclosed resources, unhandled errors.

Output ONLY valid JSON:
{"gaps": [{"type": "edge_case|missing_return|resource_leak|error_handling", "location": "where", "severity": "critical|medium|low"}], "verdict": "complete"|"gaps"|"incomplete"}

Rules:
- Focus on gaps that cause bugs, not style issues
- "complete" = no gaps. "gaps" = fixable issues. "incomplete" = major pieces missing
- Max 5 gaps — the most impactful ones
- Be specific — name the exact location and what's missing"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if architect.get("api_surface"):
            parts.append(f"## API\n{architect['api_surface']}")
        return "\n\n".join(parts) if parts else "No proposal to inspect."
```

```python
# tools/personas/tester.py
"""Tester persona — test strategy generation."""

from tools.personas import Persona


class Tester(Persona):
    name = "tester"
    emoji = "\U0001f9ea"  # 🧪
    model = "sonnet"
    reads = ["architect", "inspector"]
    max_tokens = 512
    system_prompt = """You are the Tester — the team's test strategist. Generate test cases from the Inspector's gaps and the Architect's proposal.

Output ONLY valid JSON:
{"test_cases": [{"name": "test_name", "type": "unit|integration|e2e", "assertion": "what to assert"}], "coverage_gaps": ["what's not covered"], "verdict": "covered"|"gaps"|"untested"}

Rules:
- Every gap from Inspector should have a corresponding test case
- Prefer unit tests over integration tests
- Name tests specifically — "test_self_follow_blocked" not "test_follows"
- Include the assertion — what exactly should the test check?
- Max 6 test cases"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        inspector = inputs.get("inspector", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if inspector.get("gaps"):
            gaps = "\n".join(f"- [{g['type']}] {g['location']} ({g['severity']})" for g in inspector["gaps"])
            parts.append(f"## Gaps Found by Inspector\n{gaps}")
        return "\n\n".join(parts) if parts else "No proposal to test."
```

```python
# tools/personas/visual_ux.py
"""Visual UX persona — WCAG/accessibility compliance."""

from tools.personas import Persona


class VisualUX(Persona):
    name = "visual_ux"
    emoji = "\U0001f3a8"  # 🎨
    model = "sonnet"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """You are Visual UX — the team's accessibility and design guardian.

Check WCAG 2.x:
- Color contrast (4.5:1 text, 3:1 large)
- Touch targets (44pt iOS, 48dp Android, 44px web)
- Text alternatives for images/icons
- Keyboard/VoiceOver navigability
- Dynamic type support
- Reduced motion preference

Check UX laws:
- Fitts's, Hick's, Miller's, Jakob's, Proximity

Output ONLY valid JSON:
{"a11y_issues": [{"element": "what", "violation": "which rule", "fix": "how to fix"}], "ux_issues": [{"element": "what", "issue": "description"}], "verdict": "accessible"|"fixable"|"blocker"}

Rules:
- "blocker" = WCAG AA failure. This BLOCKS shipping. Cannot be overridden.
- Only fire on proposals that touch UI code
- Max 4 issues"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity not in ("moderate", "complex"):
            return False
        architect = turn_context.get("architect", {})
        files = architect.get("files_affected", [])
        ui_extensions = (".tsx", ".jsx", ".vue", ".svelte", ".swift", ".css", ".html")
        return any(f.endswith(ext) for f in files for ext in ui_extensions)

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if architect.get("files_affected"):
            ui_files = [f for f in architect["files_affected"] if any(f.endswith(e) for e in (".tsx", ".jsx", ".vue", ".svelte", ".swift", ".css", ".html"))]
            if ui_files:
                parts.append(f"## UI Files\n{chr(10).join(f'- {f}' for f in ui_files)}")
        return "\n\n".join(parts) if parts else "No UI to review."
```

- [ ] **Step 3: Register security + quality phases in pipeline.py**

Add to `_register_default_phases()`:

```python
    try:
        from tools.personas.rogue import Rogue
        from tools.personas.hacker import Hacker
        from tools.personas.infosec import Infosec

        register_phase(Phase(
            name="security",
            emoji="\U0001f6e1\ufe0f",  # 🛡️
            personas=[Rogue(), Hacker(), Infosec()],
            micro_loop={"from": "infosec", "to": "architect", "trigger_field": "verdict", "trigger_value": "blocker"},
        ))
    except ImportError:
        pass

    try:
        from tools.personas.inspector import Inspector
        from tools.personas.tester import Tester
        from tools.personas.visual_ux import VisualUX

        register_phase(Phase(
            name="quality",
            emoji="\u2705",  # ✅
            personas=[Inspector(), Tester(), VisualUX()],
        ))
    except ImportError:
        pass
```

- [ ] **Step 4: Write security and quality integration tests**

```python
# tests/test_personas/test_security_phase.py
"""Integration test for the Security phase."""

import json
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.rogue import Rogue
from tools.personas.hacker import Hacker
from tools.personas.infosec import Infosec


def _mock_api(persona, output):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_security_fires_on_complex():
    personas = [Rogue(), Hacker(), Infosec()]
    for p in personas:
        _mock_api(p, {"verdict": "secure"})

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "add auth flow", "api_surface": "login()"}

    phase = Phase(name="security", emoji="🛡️", personas=personas)
    run_phase(phase, ctx, "complex")

    assert "rogue" in ctx
    assert "hacker" in ctx
    assert "infosec" in ctx


def test_security_conditional_on_moderate():
    """Security only fires on moderate if security_override is set."""
    personas = [Rogue(), Hacker(), Infosec()]
    for p in personas:
        _mock_api(p, {"verdict": "secure"})

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "add auth"}
    ctx["agent_manager"] = {"security_override": False}

    phase = Phase(name="security", emoji="🛡️", personas=personas)
    run_phase(phase, ctx, "moderate")
    assert "rogue" not in ctx

    ctx["agent_manager"]["security_override"] = True
    run_phase(phase, ctx, "moderate")
    assert "rogue" in ctx
```

```python
# tests/test_personas/test_quality_phase.py
"""Integration test for the Quality Gate phase."""

import json
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.inspector import Inspector
from tools.personas.tester import Tester
from tools.personas.visual_ux import VisualUX


def _mock_api(persona, output):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_visual_ux_only_activates_on_ui_files():
    vux = VisualUX()
    _mock_api(vux, {"verdict": "accessible"})

    ctx_ui = TurnContext()
    ctx_ui["architect"] = {"proposal": "add modal", "files_affected": ["src/Modal.tsx"]}
    assert vux.should_activate("moderate", ctx_ui) is True

    ctx_backend = TurnContext()
    ctx_backend["architect"] = {"proposal": "add endpoint", "files_affected": ["api/routes.py"]}
    assert vux.should_activate("moderate", ctx_backend) is False


def test_quality_gate_inspector_feeds_tester():
    inspector = Inspector()
    tester = Tester()
    _mock_api(inspector, {"gaps": [{"type": "edge_case", "location": "self-follow", "severity": "medium"}], "verdict": "gaps"})
    _mock_api(tester, {"test_cases": [{"name": "test_self_follow", "type": "unit", "assertion": "self-follow rejected"}], "coverage_gaps": [], "verdict": "covered"})

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "add follows table"}

    phase = Phase(name="quality", emoji="✅", personas=[inspector, tester])
    run_phase(phase, ctx, "moderate")

    assert ctx["inspector"]["verdict"] == "gaps"
    assert len(ctx["tester"]["test_cases"]) == 1
```

- [ ] **Step 5: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/personas/rogue.py tools/personas/hacker.py tools/personas/infosec.py \
    tools/personas/inspector.py tools/personas/tester.py tools/personas/visual_ux.py \
    tests/test_personas/test_security_phase.py tests/test_personas/test_quality_phase.py \
    tools/pipeline.py
git commit -m "feat: Phase 7-8 personas — Rogue, Hacker, Infosec, Inspector, Tester, VisualUX"
```

---

### Task 7: Phase 9 — Learner, Coach, Output Editor

**Files:**
- Create: `tools/personas/learner.py`
- Create: `tools/personas/coach.py`
- Create: `tools/personas/output_editor.py`
- Create: `tests/test_personas/test_synthesis_phase.py`
- Modify: `tools/pipeline.py` (register synthesis phase)

- [ ] **Step 1: Implement Synthesis personas**

```python
# tools/personas/learner.py
"""Learner persona — lesson extraction from turn."""

from tools.personas import Persona


class Learner(Persona):
    name = "learner"
    emoji = "\U0001f9e0"  # 🧠
    model = "haiku"
    reads = []  # reads ALL slots — special case handled in pipeline
    max_tokens = 256
    system_prompt = """You are the Learner — the team's knowledge extractor. Observe the full inter-persona discussion and extract lessons.

Output ONLY valid JSON:
{"lessons": [{"pattern": "what happened", "insight": "what we learned", "persistence": "thread"|"project"|"permanent"}], "corrections": ["correction1"]}

Persistence levels:
- "thread" = useful for this thread only → written to thread-memory
- "project" = useful across threads → written to registry
- "permanent" = structural rule → triggers CLAUDE.md update

Rules:
- Only extract non-obvious lessons. "We used RLS" is not a lesson. "RLS was chosen over app-level auth because of compliance requirements" is a lesson.
- Corrections are things the operator corrected mid-turn
- Max 3 lessons per turn"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        # Learner receives ALL slots — summarize them
        parts = []
        for slot_name, slot_data in inputs.items():
            if isinstance(slot_data, dict):
                verdict = slot_data.get("verdict", "")
                summary = verdict or str(slot_data)[:100]
                parts.append(f"- {slot_name}: {summary}")
        return f"## Full Turn Summary\n" + "\n".join(parts) if parts else "Empty turn."
```

```python
# tools/personas/coach.py
"""Coach persona — final ship/iterate/hold decision."""

from tools.personas import Persona


class Coach(Persona):
    name = "coach"
    emoji = "\U0001f4aa"  # 💪
    model = "haiku"
    reads = []  # reads ALL slots — special case handled in pipeline
    max_tokens = 128
    system_prompt = """You are the Coach — the team's confidence voice. Read everything and make the final call.

Output ONLY valid JSON:
{"verdict": "ship"|"iterate"|"hold", "confidence": 0.85, "reasoning": "one sentence"}

Rules:
- "ship" = everything looks good, send it. confidence > 0.7
- "iterate" = good direction but needs another pass. 0.4 < confidence < 0.7
- "hold" = something is wrong, don't send. confidence < 0.4
- If any persona returned "blocker", you MUST return "hold"
- Be decisive. Your job is to end deliberation, not extend it."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        blockers = []
        verdicts = []
        for slot_name, slot_data in inputs.items():
            if isinstance(slot_data, dict):
                v = slot_data.get("verdict", "")
                if v:
                    verdicts.append(f"- {slot_name}: {v}")
                if v in ("blocker", "block", "critical"):
                    blockers.append(slot_name)

        parts = [f"## Verdicts\n" + "\n".join(verdicts)]
        if blockers:
            parts.append(f"## BLOCKERS: {', '.join(blockers)}")
        return "\n\n".join(parts)
```

```python
# tools/personas/output_editor.py
"""Output Editor persona — polishes final output."""

from tools.personas import Persona


class OutputEditor(Persona):
    name = "output_editor"
    emoji = "\u270d\ufe0f"  # ✍️
    model = "sonnet"
    reads = ["coach", "token_cart"]
    max_tokens = 512
    system_prompt = """You are the Output Editor — the team's polish pass. Take the response and clean it for the target medium.

Output ONLY valid JSON:
{"polished_output": "the cleaned text", "format": "slack"|"github"|"docs"}

Rules:
- For Slack: use mrkdwn (bold, code blocks, bullet lists). No HTML.
- For GitHub: use proper markdown with headers and code fences.
- For docs: clean prose with headers.
- Don't change the substance — only improve clarity, formatting, and conciseness.
- If the response is already clean, return it unchanged."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        coach = inputs.get("coach", {})
        token_cart = inputs.get("token_cart", {})
        parts = []
        if coach.get("verdict"):
            parts.append(f"## Coach Verdict: {coach['verdict']}")
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Original Task\n{token_cart['enriched_prompt'][:300]}")
        return "\n\n".join(parts) if parts else "Nothing to polish."
```

- [ ] **Step 2: Register synthesis phase, write tests**

Add to `_register_default_phases()` in `tools/pipeline.py`:

```python
    try:
        from tools.personas.learner import Learner
        from tools.personas.coach import Coach
        from tools.personas.output_editor import OutputEditor

        register_phase(Phase(
            name="synthesis",
            emoji="\U0001f9e0",  # 🧠
            personas=[Learner(), Coach(), OutputEditor()],
        ))
    except ImportError:
        pass
```

```python
# tests/test_personas/test_synthesis_phase.py
"""Integration test for the Synthesis phase."""

import json
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.learner import Learner
from tools.personas.coach import Coach
from tools.personas.output_editor import OutputEditor


def _mock_api(persona, output):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_synthesis_only_on_complex():
    learner = Learner()
    coach = Coach()
    editor = OutputEditor()
    for p in [learner, coach, editor]:
        _mock_api(p, {"verdict": "ship"})

    ctx = TurnContext()
    ctx["token_cart"] = {"enriched_prompt": "test"}

    phase = Phase(name="synthesis", emoji="🧠", personas=[learner, coach, editor])
    run_phase(phase, ctx, "moderate")
    assert "learner" not in ctx  # doesn't fire on moderate

    run_phase(phase, ctx, "complex")
    assert "learner" in ctx  # fires on complex


def test_coach_detects_blocker():
    coach = Coach()
    _mock_api(coach, {"verdict": "hold", "confidence": 0.2, "reasoning": "Infosec blocker"})

    ctx = TurnContext()
    ctx["infosec"] = {"verdict": "blocker"}
    ctx["token_cart"] = {"enriched_prompt": "test"}

    result = coach.run(ctx)
    assert result["verdict"] == "hold"
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add tools/personas/learner.py tools/personas/coach.py tools/personas/output_editor.py \
    tests/test_personas/test_synthesis_phase.py tools/pipeline.py
git commit -m "feat: Phase 9 personas — Learner, Coach, Output Editor"
```

---

### Task 8: Wire Pipeline into bot_unified.py

**Files:**
- Modify: `bot_unified.py`
- Modify: `tests/test_pipeline.py` (add tier routing integration tests)

- [ ] **Step 1: Write integration test for tier routing**

```python
# Add to tests/test_pipeline.py

def test_run_pipeline_simple_runs_no_phases():
    """Simple tier runs no cognitive phases (only infrastructure, handled separately)."""
    ctx = TurnContext()
    ctx["agent_manager"] = {"complexity": "simple", "model": "haiku", "security_override": False}
    ctx["observer"] = {"summary": "hello", "turn": 1}
    ctx["token_cart"] = {"enriched_prompt": "hello", "handoff": ""}

    results, costs = run_pipeline(ctx, "simple", pre_hoc=True)
    assert results == []


def test_run_pipeline_moderate_runs_plan_and_design():
    """Moderate pre-hoc runs plan + design phases."""
    from tools.pipeline import PHASES

    # Only test if phases are registered
    if "plan" not in PHASES or "design" not in PHASES:
        pytest.skip("Phases not registered yet")

    ctx = TurnContext()
    ctx["agent_manager"] = {"complexity": "moderate", "model": "sonnet", "security_override": False}
    ctx["observer"] = {"summary": "fix bug", "turn": 1}
    ctx["token_cart"] = {"enriched_prompt": "fix login bug", "handoff": "", "registry": ""}

    # We can't run the full pipeline without mocking — just verify phase selection
    from tools.pipeline import _TIER_PHASES
    assert "plan" in _TIER_PHASES["moderate"]
    assert "design" in _TIER_PHASES["moderate"]
    assert "challenge" not in _TIER_PHASES["moderate"]  # challenge is post-hoc for moderate
```

- [ ] **Step 2: Replace inline consultant/gut-check logic in bot_unified.py**

In `bot_unified.py`, find the section from "8b. Gut check" through "8c. Consultant dispatch" (approximately lines 446-483) and replace with the pipeline call. The key changes:

1. Before the agent call: run `run_pipeline(ctx, complexity, pre_hoc=True)` for moderate+ tasks
2. After the agent call: run `run_pipeline(ctx, complexity, pre_hoc=False)` for post-hoc phases
3. Replace the inline `discussion.add()` calls with `discussion.add_phase_entries()` from pipeline results

```python
# In bot_unified.py, replace the gut_check + consultant blocks with:

    # 8b. Run post-hoc cognitive pipeline (replaces gut check + consultants)
    use_pipeline = project.get("features", {}).get("pipeline", True)
    if use_pipeline and use_token_cart:
        try:
            from tools.pipeline import TurnContext, run_pipeline

            # Build TurnContext from session state
            turn_ctx = TurnContext()
            turn_ctx["agent_manager"] = {
                "complexity": complexity if use_agent_manager else "moderate",
                "model": model,
                "security_override": _has_security_keywords(prompt),
            }
            turn_ctx["observer"] = {
                "summary": observer.context if observer else prompt[:200],
                "turn": session.get("turn_count", 1),
            }
            turn_ctx["token_cart"] = {
                "enriched_prompt": enriched_context if isinstance(enriched_context, str) else prompt,
                "handoff": session.get("handoff", "") or "",
                "registry": registry_content or "",
            }
            # For post-hoc: inject the agent's response as the "architect" slot
            # (post-hoc personas read the response AS IF it were an architect proposal)
            turn_ctx["architect"] = {
                "proposal": response[:2000],
                "data_model": "",
                "api_surface": "",
                "files_affected": [],
            }
            turn_ctx["strategist"] = {"tasks": [], "sequence": []}
            turn_ctx["historian"] = {"prior_decisions": [], "conflicts": []}

            # Run post-hoc phases
            current_complexity = complexity if use_agent_manager else "moderate"
            phase_results, _ = run_pipeline(turn_ctx, current_complexity, pre_hoc=False)

            for phase_name, entries in phase_results:
                phase_emoji = {"challenge": "🤨", "quality": "✅", "security": "🛡️", "synthesis": "🧠"}.get(phase_name, "📋")
                discussion.add_phase_entries(phase_name, phase_emoji, entries)

            # Check for blocker verdicts
            for slot_name in ("infosec", "visual_ux"):
                slot = turn_ctx.get(slot_name, {})
                if slot.get("verdict") == "blocker":
                    response += f"\n\n🔴 **{slot_name.upper()} BLOCKER:** Response held for review."

            # Append consultant-style findings to response
            for slot_name in ("skeptic", "inspector", "tester"):
                slot = turn_ctx.get(slot_name, {})
                if slot.get("verdict") not in (None, "proceed", "complete", "covered", "accessible"):
                    summary = _summarize_persona_finding(slot_name, slot)
                    if summary:
                        response += f"\n\n{summary}"

        except Exception:
            pass  # never block on pipeline
```

Add the helper function:

```python
def _has_security_keywords(prompt: str) -> bool:
    """Check if prompt contains auth/input/crypto keywords for security override."""
    import re
    patterns = [r"\bauth\b", r"\blogin\b", r"\btoken\b", r"\bcrypto\b", r"\bpassword\b", r"\bsession\b", r"\binjection\b"]
    lower = prompt.lower()
    return any(re.search(p, lower) for p in patterns)


def _summarize_persona_finding(slot_name: str, slot: dict) -> str:
    """Format a persona's findings for appending to the response."""
    verdict = slot.get("verdict", "")
    if slot_name == "skeptic" and verdict == "reconsider":
        assumptions = slot.get("assumptions", [])
        if assumptions:
            items = "\n".join(f"- {a.get('claim', '')}: {a.get('risk', '')}" for a in assumptions[:3])
            return f"🤨 *Skeptic:*\n{items}"
    if slot_name == "inspector" and verdict == "gaps":
        gaps = slot.get("gaps", [])
        if gaps:
            items = "\n".join(f"- {g.get('location', '')}: {g.get('type', '')}" for g in gaps[:3])
            return f"🔍 *Inspector:*\n{items}"
    return ""
```

- [ ] **Step 3: Keep backward compatibility — feature gate**

The pipeline is gated behind `project.features.pipeline` (default `True`). When `False`, the old gut-check + consultant logic runs. This allows gradual rollout.

Add `"pipeline"` to the feature gate list in `bot_unified.py`:

```python
# Add to the FEATURE_GATES list (around line 901):
    "pipeline",
```

- [ ] **Step 4: Run full test suite**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest -q`
Expected: All tests PASS (existing + new)

- [ ] **Step 5: Commit**

```bash
git add bot_unified.py tests/test_pipeline.py
git commit -m "feat: wire cognitive pipeline into bot_unified.py with feature gate"
```

---

### Task 9: Phase 5 — Dreamer, Insights, Growth Coach (Later Rollout)

**Files:**
- Create: `tools/personas/dreamer.py`
- Create: `tools/personas/insights.py`
- Create: `tools/personas/growth_coach.py`
- Create: `tests/test_personas/test_vision_phase.py`
- Modify: `tools/pipeline.py` (register vision phase)

- [ ] **Step 1: Implement Vision personas**

```python
# tools/personas/dreamer.py
"""Dreamer persona — generative visionary."""

from tools.personas import Persona


class Dreamer(Persona):
    name = "dreamer"
    emoji = "\U0001f52e"  # 🔮
    model = "sonnet"
    reads = ["architect", "token_cart"]
    max_tokens = 256
    system_prompt = """You are the Dreamer — the team's visionary. While others validate and defend, you imagine what's possible.

Your job:
1. EXTRAPOLATE: "This utility could become a shared package"
2. CONNECT: "This pattern is what Notion did before they became a platform"
3. INSPIRE: "If we built this as a plugin, the community could extend it"
4. GROUND: Always tie vision to a concrete next step

NOT a license to scope-creep. Your visions are SEEDS for future work, not additions to the current task.

Output ONLY valid JSON:
{"vision": "one-paragraph vision", "next_step": "concrete action", "platform_potential": "what this could become", "time_horizon": "sprint"|"quarter"|"long_term"}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        token_cart = inputs.get("token_cart", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Context\n{token_cart['enriched_prompt'][:300]}")
        return "\n\n".join(parts) if parts else "No proposal to dream about."
```

```python
# tools/personas/insights.py
"""Insights persona — success measurement."""

from tools.personas import Persona


class Insights(Persona):
    name = "insights"
    emoji = "\U0001f4c9"  # 📉
    model = "haiku"
    reads = ["architect", "dreamer"]
    max_tokens = 256
    system_prompt = """You are Insights — the team's measurement conscience. Every feature ships with success criteria or it doesn't ship.

Your job:
1. DEFINE: What does success look like? (metric, threshold, timeframe)
2. INSTRUMENT: What events/logs/analytics need to be added?
3. BASELINE: What's the current state we're comparing against?
4. CHALLENGE: If no one can define success, should we build this?

Output ONLY valid JSON:
{"success_criteria": ["criterion1"], "metrics": ["metric1"], "instrumentation": ["event1"], "verdict": "measurable"|"needs_definition"|"unmeasurable"}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        dreamer = inputs.get("dreamer", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if dreamer.get("vision"):
            parts.append(f"## Dreamer's Vision\n{dreamer['vision']}")
        return "\n\n".join(parts) if parts else "No proposal to measure."
```

```python
# tools/personas/growth_coach.py
"""Growth Coach persona — AARRR funnel evaluation."""

from tools.personas import Persona


class GrowthCoach(Persona):
    name = "growth_coach"
    emoji = "\U0001f4c8"  # 📈
    model = "haiku"
    reads = ["architect", "insights"]
    max_tokens = 256
    system_prompt = """You are the Growth Coach — the team's funnel thinker. Evaluate through AARRR: Acquisition, Activation, Retention, Referral, Revenue.

Output ONLY valid JSON:
{"funnel_impact": "which AARRR stage", "conversion_risk": "could this hurt conversion?", "ab_test_opportunity": "is this A/B testable?", "verdict": "ship"|"measure_first"|"reconsider"}

Rules:
- Be specific about which funnel stage this affects
- Flag if a feature adds friction to critical paths (onboarding, checkout)
- NOT a license to add growth hacks — ensure features serve users AND the business"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        architect = inputs.get("architect", {})
        insights = inputs.get("insights", {})
        parts = []
        if architect.get("proposal"):
            parts.append(f"## Proposal\n{architect['proposal']}")
        if insights.get("success_criteria"):
            criteria = "\n".join(f"- {c}" for c in insights["success_criteria"])
            parts.append(f"## Success Criteria\n{criteria}")
        if insights.get("verdict"):
            parts.append(f"## Measurability: {insights['verdict']}")
        return "\n\n".join(parts) if parts else "No proposal to evaluate."
```

- [ ] **Step 2: Register vision phase, add to tier routing**

Add to `_register_default_phases()` in `tools/pipeline.py`:

```python
    try:
        from tools.personas.dreamer import Dreamer
        from tools.personas.insights import Insights
        from tools.personas.growth_coach import GrowthCoach

        register_phase(Phase(
            name="vision",
            emoji="\U0001f52e",  # 🔮
            personas=[Dreamer(), Insights(), GrowthCoach()],
            micro_loop={"from": "insights", "to": "growth_coach", "trigger_field": "verdict", "trigger_value": "unmeasurable"},
        ))
    except ImportError:
        pass
```

Update `_TIER_PHASES` in `tools/pipeline.py`:

```python
_TIER_PHASES: dict[str, list[str]] = {
    "simple": [],
    "moderate": ["plan", "design"],
    "complex": ["plan", "design", "vision", "challenge", "security", "quality"],
}
```

- [ ] **Step 3: Write vision phase test**

```python
# tests/test_personas/test_vision_phase.py
"""Integration test for the Vision phase."""

import json
from unittest.mock import MagicMock
from tools.pipeline import TurnContext, Phase, run_phase
from tools.personas.dreamer import Dreamer
from tools.personas.insights import Insights
from tools.personas.growth_coach import GrowthCoach


def _mock_api(persona, output):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=10)
    persona._call_api = lambda s, u, m, mt: mock_msg


def test_vision_only_on_complex():
    personas = [Dreamer(), Insights(), GrowthCoach()]
    for p in personas:
        _mock_api(p, {"verdict": "ship"})

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "new feature"}
    ctx["token_cart"] = {"enriched_prompt": "test"}

    phase = Phase(name="vision", emoji="🔮", personas=personas)
    run_phase(phase, ctx, "moderate")
    assert "dreamer" not in ctx

    run_phase(phase, ctx, "complex")
    assert "dreamer" in ctx
    assert "insights" in ctx
    assert "growth_coach" in ctx
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_personas/ tests/test_pipeline.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/personas/dreamer.py tools/personas/insights.py tools/personas/growth_coach.py \
    tests/test_personas/test_vision_phase.py tools/pipeline.py
git commit -m "feat: Phase 5 personas — Dreamer, Insights, Growth Coach"
```

---

### Task 10: Micro-Loop Revision Logic

**Files:**
- Modify: `tools/pipeline.py` (add `run_phase_with_micro_loop`)
- Modify: `tests/test_pipeline.py` (add micro-loop tests)

- [ ] **Step 1: Write failing micro-loop tests**

```python
# Add to tests/test_pipeline.py

def test_micro_loop_triggers_revision(monkeypatch):
    """When a persona flags revision_target, the target re-runs once."""
    import json

    class MockArchitect(Persona):
        name = "architect"
        emoji = "📐"
        model = "sonnet"
        reads = ["token_cart"]
        system_prompt = "test"
        call_count = 0

        def should_activate(self, complexity, ctx):
            return True

        def _build_user_content(self, inputs):
            return "test"

    class MockSkeptic(Persona):
        name = "skeptic"
        emoji = "🤨"
        model = "haiku"
        reads = ["architect"]
        system_prompt = "test"

        def should_activate(self, complexity, ctx):
            return True

        def _build_user_content(self, inputs):
            return "test"

    architect = MockArchitect()
    skeptic = MockSkeptic()

    # First architect call returns initial proposal
    # Skeptic returns reconsider → revision_target = architect
    # Second architect call returns revised proposal
    # Skeptic re-checks and returns proceed

    call_sequence = [
        json.dumps({"proposal": "v1", "data_model": "", "api_surface": "", "files_affected": []}),
        json.dumps({"assumptions": [{"claim": "test", "evidence": "none", "risk": "high"}], "verdict": "reconsider", "revision_target": "architect"}),
        json.dumps({"proposal": "v2 (revised)", "data_model": "", "api_surface": "", "files_affected": []}),
        json.dumps({"assumptions": [], "verdict": "proceed", "revision_target": None}),
    ]
    call_idx = [0]

    def mock_call(system, user, model, max_tokens):
        idx = call_idx[0]
        call_idx[0] += 1
        mock_msg = type("Msg", (), {
            "content": [type("Block", (), {"text": call_sequence[idx]})()],
            "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 10})(),
        })()
        return mock_msg

    monkeypatch.setattr(architect, "_call_api", mock_call)
    monkeypatch.setattr(skeptic, "_call_api", mock_call)

    ctx = TurnContext()
    ctx["token_cart"] = {"enriched_prompt": "test"}

    phase = Phase(
        name="test_phase",
        emoji="🧪",
        personas=[architect, skeptic],
        micro_loop={"from": "skeptic", "to": "architect", "trigger_field": "verdict", "trigger_value": "reconsider"},
    )

    from tools.pipeline import run_phase_with_micro_loop
    entries, costs = run_phase_with_micro_loop(phase, ctx, "complex")

    # Architect should have been revised (v2)
    assert "v2" in ctx["architect"]["proposal"]
    # Skeptic should have re-evaluated to proceed
    assert ctx["skeptic"]["verdict"] == "proceed"
    # Should have 4 entries (2 calls each for architect and skeptic)
    assert call_idx[0] == 4


def test_micro_loop_does_not_trigger_on_moderate():
    """Micro-loops are disabled for moderate tier."""
    import json

    class MockSkeptic(Persona):
        name = "skeptic"
        emoji = "🤨"
        model = "haiku"
        reads = ["architect"]
        system_prompt = "test"

        def should_activate(self, complexity, ctx):
            return True

        def _build_user_content(self, inputs):
            return "test"

    skeptic = MockSkeptic()

    # Skeptic returns reconsider, but on moderate, no revision loop
    mock_msg = type("Msg", (), {
        "content": [type("Block", (), {"text": json.dumps({"assumptions": [], "verdict": "reconsider", "revision_target": "architect"})})()],
        "usage": type("Usage", (), {"input_tokens": 10, "output_tokens": 10})(),
    })()
    monkeypatch_attr = lambda s, u, m, mt: mock_msg

    skeptic._call_api = monkeypatch_attr

    ctx = TurnContext()
    ctx["architect"] = {"proposal": "v1"}

    phase = Phase(
        name="challenge",
        emoji="🤨",
        personas=[skeptic],
        micro_loop={"from": "skeptic", "to": "architect", "trigger_field": "verdict", "trigger_value": "reconsider"},
    )

    from tools.pipeline import run_phase_with_micro_loop
    entries, costs = run_phase_with_micro_loop(phase, ctx, "moderate")

    # Skeptic fired but no revision loop
    assert ctx["skeptic"]["verdict"] == "reconsider"
    # Architect NOT re-run (still v1)
    assert ctx["architect"]["proposal"] == "v1"
```

- [ ] **Step 2: Implement run_phase_with_micro_loop in pipeline.py**

```python
# Add to tools/pipeline.py

def run_phase_with_micro_loop(
    phase: Phase,
    ctx: TurnContext,
    complexity: str,
) -> tuple[list[str], list[TurnCostEntry]]:
    """Execute a phase with optional micro-loop revision.

    If complexity is "complex" and a micro-loop is defined:
    1. Run all personas normally
    2. Check if the "from" persona's output triggers the loop
    3. If triggered, re-run the "to" persona with the flag injected
    4. Re-run the "from" persona to re-evaluate
    5. Max 1 retry — if still flagged, proceed anyway

    For non-complex tiers, this is identical to run_phase().
    """
    entries, costs = run_phase(phase, ctx, complexity)

    # Micro-loops only on complex
    if complexity != "complex" or not phase.micro_loop:
        return entries, costs

    ml = phase.micro_loop
    from_slot = ctx.get(ml["from"], {})
    trigger_field = ml.get("trigger_field", "verdict")
    trigger_value = ml.get("trigger_value")

    if from_slot.get(trigger_field) != trigger_value:
        return entries, costs  # no revision needed

    logger.info(f"Micro-loop triggered: {ml['from']} → {ml['to']} (field={trigger_field}, value={trigger_value})")

    # Find the target and source personas
    target_persona = None
    source_persona = None
    for p in phase.personas:
        if p.name == ml["to"]:
            target_persona = p
        if p.name == ml["from"]:
            source_persona = p

    if not target_persona:
        # Target might be in a different phase (e.g., Skeptic → Architect)
        from tools.personas import PERSONA_REGISTRY
        target_cls = PERSONA_REGISTRY.get(ml["to"])
        if target_cls:
            target_persona = target_cls()

    if not target_persona or not source_persona:
        logger.warning(f"Micro-loop: could not find target={ml['to']} or source={ml['from']}")
        return entries, costs

    # Re-run target with the flagging slot injected
    target_inputs = {slot: ctx[slot] for slot in target_persona.reads if slot in ctx}
    target_inputs[ml["from"]] = from_slot  # inject the flag
    revised = target_persona.run(target_inputs)
    ctx[target_persona.writes] = revised
    entries.append(f"{target_persona.emoji} (revised) {_summarize_slot(target_persona.name, revised)}")

    # Re-run source to re-evaluate
    source_inputs = {slot: ctx[slot] for slot in source_persona.reads if slot in ctx}
    re_eval = source_persona.run(source_inputs)
    ctx[source_persona.writes] = re_eval
    entries.append(f"{source_persona.emoji} (re-eval) {_summarize_slot(source_persona.name, re_eval)}")

    return entries, costs
```

- [ ] **Step 3: Update run_pipeline to use run_phase_with_micro_loop**

In `run_pipeline()`, replace the `run_phase()` call:

```python
        entries, costs = run_phase_with_micro_loop(phase, ctx, complexity)
```

- [ ] **Step 4: Run all tests**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest tests/test_pipeline.py tests/test_personas/ -v`
Expected: All tests PASS

- [ ] **Step 5: Run full suite to verify no regressions**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add tools/pipeline.py tests/test_pipeline.py
git commit -m "feat: micro-loop revision logic — intra-turn Skeptic→Architect→Skeptic loops"
```

---

### Task 11: Final — Run Full Suite, Update STATE.md

**Files:**
- Modify: `STATE.md`
- Modify: `docs/JOURNAL.md`

- [ ] **Step 1: Run full test suite**

Run: `cd /Users/daveleal/Repos/SlackClaw && venv/bin/pytest -q`
Expected: All tests PASS (existing 467 + new pipeline/persona tests)

- [ ] **Step 2: Update STATE.md**

Update the "What's Next" section — mark the 22-persona item as done, add the phased orchestrator status:

```markdown
- [x] 25-persona cognitive pipeline — 9 phases, 3-tier activation, micro-loop revision
```

- [ ] **Step 3: Append JOURNAL.md entry**

```markdown
## 2026-04-04 — Phased Orchestrator: 25 Personas Across 9 Phases

Replaced the flat post-hoc consultant model with a phased cognitive pipeline.
The key insight was that micro-loops — not persona count — are the cost lever.
Simple tasks fire 3-4 personas (~$0.002). Moderate gets 8-10 with advisory-only
review (~$0.005). Complex gets the full 9-phase pipeline with intra-turn revision
loops where the Skeptic can send the Architect back to revise (~$0.008-0.014).

The communication model is a shared typed dict with named slots. Each persona is
a pure function: declared inputs → structured JSON output. No pub/sub, no message
bus — just a for-loop with a dict. Micro-loops are a conditional re-run (max 1
retry) gated by the complexity tier.

The hardest design decision was where to place the agent call relative to the
phases. Simple: agent runs immediately. Moderate: Plan + Design pre-hoc, then
agent, then Challenge + Quality post-hoc. Complex: full pipeline pre-hoc shapes
the context before the agent ever sees it.
```

- [ ] **Step 4: Commit**

```bash
git add STATE.md docs/JOURNAL.md
git commit -m "docs: update STATE.md and journal for phased orchestrator"
```
