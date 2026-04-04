# Phased Orchestrator — 25 Cognitive Personas + 4 Infrastructure Agents

> **Date:** 2026-04-04
> **Status:** Approved
> **Supersedes:** `2026-04-04-cognitive-personas.md` (flat roster without phases)
> **Viz Reference:** `docs/viz/orchestrator-flow.jsx`

## Goal

Replace the flat post-hoc consultant model with a phased cognitive pipeline where personas shape the agent's response **before** it ships. The pipeline uses a shared typed dict with named slots — personas are pure functions that read declared inputs and write structured JSON to their named output slot. Micro-loops (intra-turn revisions) are the cost lever that distinguishes moderate from complex tasks.

## Architecture

### Communication Model: Pipeline with Shared Typed Dict

```python
# TurnContext — the shared state for one turn
turn_context: dict[str, dict] = {
    "agent_manager": {"complexity": "moderate", "model": "claude-sonnet-4-6"},
    "observer": {"summary": "...", "turn": 3, "decisions": [], "open_questions": []},
    "token_cart": {"enriched_prompt": "...", "handoff": "...", "registry": "..."},
    "strategist": {"tasks": [...], "sequence": [...], "dependencies": [...]},
    "architect": {"proposal": "...", "data_model": "...", "api_surface": "..."},
    "skeptic": {"assumptions": [...], "verdict": "proceed", "revision_target": None},
    # ... each persona writes to its named slot
}
```

**Rules:**
- Each persona declares `reads: list[str]` (input slot names) and `writes: str` (output slot name)
- Personas receive ONLY their declared input slots, not the full dict — saves tokens
- Output is structured JSON (80-200 tokens), not prose
- The pipeline is a for-loop over phases with the shared dict
- Micro-loops are a conditional re-run when an output slot contains a `revision_target`

### Three-Tier Activation

The Agent Manager classifies complexity. The classification determines which phases fire and whether micro-loops are enabled.

| Tier | Classification | Phases | Micro-Loops | Personas | Est. Cost |
|------|---------------|--------|-------------|----------|-----------|
| **Simple** | Explain, rename, format, greeting | 1-2 (Intake + Enrich) + agent call + gut check | None | 3-4 | ~$0.002 |
| **Moderate** | Bug fix, new feature (1-2 files), tests | 1-2 + lightweight Plan/Design + agent call + post-hoc Challenge/Quality + conditional Security | None (advisory only) | 8-10 | ~$0.005 |
| **Complex** | Refactor, architecture, multi-file, security-sensitive | Full 9-phase pipeline before agent call | Enabled (max 1 retry each) | 14-20 | ~$0.008-0.014 |

**Key insight:** The cost lever is micro-loops, not persona count. Moderate gets the same personas as complex but in advisory mode (post-hoc, no revision loops). Complex enables pre-hoc revision where Skeptic can send Architect back to revise.

**Security override:** If triage detects auth/input/crypto keywords in a moderate task, the Security phase fires regardless of complexity tier.

### Phase Execution Model

```
Simple:   [Intake] → [Enrich] → AGENT CALL → [Gut Check] → POST
Moderate: [Intake] → [Enrich] → [Plan*] → [Design*] → AGENT CALL → [Challenge†] → [Quality†] → [Security‡] → POST
Complex:  [Intake] → [Enrich] → [Plan] → [Design] → [Vision§] → [Challenge] → [Security] → [Quality] → AGENT CALL → [Synthesis] → POST

* lightweight: fewer personas, no micro-loops
† post-hoc: reviews the response, doesn't shape it
‡ conditional: only if auth/input/crypto detected
§ Vision group ships in later rollout phase
```

## Roster

### Infrastructure Agents (Always Active, unnumbered)

These are not cognitive personas — they are infrastructure that runs on every turn regardless of complexity.

| Agent | Emoji | Model | Output Contract |
|-------|-------|-------|-----------------|
| **Agent Manager** | 📋 | Haiku | `{complexity: "simple"|"moderate"|"complex", model: str, security_override: bool}` |
| **Observer** | 👁️ | Haiku | `{summary: str, turn: int, decisions: list, open_questions: list, files_mentioned: list}` |
| **Token Cart** | 🛒 | Haiku | `{enriched_prompt: str, handoff: str, registry: str, file_context: str}` |
| **File Fetcher** | 📂 | Haiku | `{files_loaded: list[str], content: dict[str, str]}` |

### Phase 3: Plan & Research (Moderate+ pre-hoc)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 1 | **Strategist** | 🎯 | Haiku | observer, token_cart, historian* | `{tasks: list, sequence: list, dependencies: list, estimated_complexity: str}` |
| 2 | **Researcher** | 🌐 | Sonnet | observer, strategist | `{findings: list[{source, summary, relevance}], apis_referenced: list}` |
| 3 | **Historian** | 📜 | Haiku | observer, token_cart | `{prior_decisions: list, conflicts: list[{decision, conflict_with}], lessons: list}` |

*Strategist normally reads observer + token_cart. During a micro-loop re-run, historian is appended to its inputs.

**Micro-loop (complex only):** If `historian.conflicts` is non-empty, re-run Strategist with `historian.conflicts` injected into its inputs (historian slot temporarily added to Strategist's reads). Max 1 retry.

### Phase 4: Design & Propose (Moderate+ pre-hoc)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 4 | **Architect** | 📐 | Sonnet | strategist, historian, token_cart | `{proposal: str, data_model: str, api_surface: str, files_affected: list}` |
| 5 | **Specialist** | 🧬 | Haiku | architect, token_cart | `{idiom_violations: list[{pattern, fix, framework}], verdict: "idiomatic"|"fixable"|"wrong"}` |
| 6 | **Data Scientist** | 📊 | Haiku | architect | `{scale_concerns: list, query_patterns: list, index_suggestions: list, verdict: "scalable"|"review"|"blocker"}` |
| 7 | **Empathizer** | 🫂 | Haiku | architect, observer | `{friction_points: list[{element, issue, suggestion}], verdict: "smooth"|"rough"|"blocking"}` |
| 8 | **Connector** | 🔗 | Haiku | architect, token_cart | `{similar_patterns: list[{project, pattern, relevance}], reuse_opportunities: list}` |
| 9 | **Reuser** | ♻️ | Haiku | architect, token_cart | `{existing_components: list[{name, path, match_score}], lib_consistency: list[{adopted, proposed, fix}], verdict: "clean"|"duplicate"|"inconsistent"}` |

**Moderate subset:** Only Architect + Specialist + Reuser fire (3 of 6). No micro-loop.

**Micro-loop (complex only):** If `reuser.verdict == "duplicate"`, re-run Architect with `reuser.existing_components` injected. Max 1 retry.

### Phase 5: Vision & Measurement (Complex only, later rollout, pre-hoc)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 10 | **Dreamer** | 🔮 | Sonnet | architect, token_cart | `{vision: str, next_step: str, platform_potential: str, time_horizon: "sprint"|"quarter"|"long_term"}` |
| 11 | **Insights** | 📉 | Haiku | architect, dreamer | `{success_criteria: list, metrics: list, instrumentation: list, verdict: "measurable"|"needs_definition"|"unmeasurable"}` |
| 12 | **Growth Coach** | 📈 | Haiku | architect, insights | `{funnel_impact: str, conversion_risk: str, ab_test_opportunity: str, verdict: "ship"|"measure_first"|"reconsider"}` |

**Micro-loop:** If `insights.verdict == "unmeasurable"`, re-run Growth Coach with flag. Max 1 retry.

### Phase 6: Challenge (Moderate: post-hoc advisory / Complex: pre-hoc with revision)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 13 | **Skeptic** | 🤨 | Haiku | architect, strategist | `{assumptions: list[{claim, evidence, risk}], verdict: "proceed"|"reconsider"|"block", revision_target: str|null}` |
| 14 | **Devil's Advocate** | 👹 | Haiku | architect, strategist | `{counter_argument: str, alternative: str, verdict: "proceed"|"has_merit"|"stop"}` |
| 15 | **Simplifier** | ✂️ | Haiku | architect | `{simplifications: list[{current, proposed, savings}], verdict: "minimal"|"reducible"|"overengineered"}` |
| 16 | **Prioritizer** | ⚖️ | Haiku | strategist, skeptic | `{ranked_options: list[{option, impact, effort, score}], recommendation: str}` |

**Moderate:** Skeptic + Prioritizer, post-hoc (reviews response, no revision loop). Prioritizer provides tiebreaker if multiple options survive from Design.

**Complex micro-loop:** If `skeptic.verdict == "reconsider"` and `skeptic.revision_target == "architect"`, re-run Architect with `skeptic.assumptions` injected, then re-run Skeptic. Max 1 retry.

### Phase 7: Security (Moderate: conditional post-hoc / Complex: always, pre-hoc)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 17 | **Rogue** | 😈 | Haiku | architect | `{stress_scenarios: list[{scenario, impact, likelihood}], verdict: "resilient"|"fragile"|"breaks"}` |
| 18 | **Hacker** | 🏴‍☠️ | Haiku | architect | `{attack_vectors: list[{vector, severity, exploitability}], verdict: "secure"|"vulnerable"|"critical"}` |
| 19 | **Infosec** | 🛡️ | Sonnet | architect, rogue, hacker | `{mitigations: list[{threat, defense, priority}], verdict: "clear"|"mitigable"|"blocker"}` |

**Moderate:** Only fires if triage detects auth/input/crypto keywords. Post-hoc (reviews response).

**Complex micro-loop:** If `infosec.verdict == "blocker"`, re-run Architect with `infosec.mitigations` injected. Max 1 retry. This is non-negotiable — blockers cannot be overridden.

### Phase 8: Quality Gate (Moderate+: post-hoc / Complex: pre-hoc)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 20 | **Inspector** | 🔍 | Haiku | architect | `{gaps: list[{type, location, severity}], verdict: "complete"|"gaps"|"incomplete"}` |
| 21 | **Tester** | 🧪 | Sonnet | architect, inspector | `{test_cases: list[{name, type, assertion}], coverage_gaps: list, verdict: "covered"|"gaps"|"untested"}` |
| 22 | **Visual UX** | 🎨 | Sonnet | architect | `{a11y_issues: list[{element, violation, fix}], ux_issues: list, verdict: "accessible"|"fixable"|"blocker"}` |

**Micro-loop (complex only):** `inspector.gaps` feeds directly into `tester.test_cases`. Inspector and Tester run sequentially within this phase. Visual UX runs in parallel with Inspector.

**Blocking gate:** If `visual_ux.verdict == "blocker"`, the response is held. This is absolute — WCAG AA failures cannot be shipped.

### Phase 9: Synthesis (Complex only, post agent call)

| # | Persona | Emoji | Model | Reads | Output Contract |
|---|---------|-------|-------|-------|-----------------|
| 23 | **Learner** | 🧠 | Haiku | _all slots_ | `{lessons: list[{pattern, insight, persistence: "thread"|"project"|"permanent"}], corrections: list}` |
| 24 | **Coach** | 💪 | Haiku | _all slots_ | `{verdict: "ship"|"iterate"|"hold", confidence: float, reasoning: str}` |
| 25 | **Output Editor** | ✍️ | Sonnet | coach, token_cart | `{polished_output: str, format: "slack"|"github"|"docs"}` |

**Learner feedback loops:**
- `persistence == "thread"` → writes to `.shellack/thread-memory/{project_key}.md`
- `persistence == "project"` → writes to `.shellack/registry.md` via correction loop
- `persistence == "permanent"` → triggers Self-Improver to update `CLAUDE.md`

## Seven Self-Healing Feedback Loops

| # | Loop | Path | Speed | Description |
|---|------|------|-------|-------------|
| 1 | **Intra-turn revision** | Skeptic → Architect → Skeptic | Immediate | Assumption flagged and addressed within the same turn |
| 2 | **Registry enforcement** | Reuser → Architect → revised proposal | Immediate | Existing component found before new one is created |
| 3 | **Security blocker** | Infosec → Architect → redesign → Infosec | Immediate | Critical vulnerability blocks shipping. Non-negotiable |
| 4 | **Correction capture** | Operator corrects → Token Cart → Registry + Learner | Next interaction | Operator correction persists across all future threads |
| 5 | **Lesson extraction** | Learner → thread-memory → Historian | Next turn/thread | Learner writes lessons, Historian retrieves them |
| 6 | **Persona evolution** | Learner → persona-tuning.md → adjusted prompts | Next invocation | Repeated mistakes adjust persona system prompts |
| 7 | **CLAUDE.md rule** | Learner → Self-Improver → CLAUDE.md → all agents | Permanent | Structural lesson becomes a permanent project rule |

## Integration Map

### Existing Systems Preserved

| System | File | Role in New Architecture |
|--------|------|------------------------|
| Token Cart | `tools/token_cart.py` | Phase 2 — becomes the `token_cart` slot writer. `pre_call`, `post_call`, `gut_check` preserved |
| Thread Observer | `tools/thread_observer.py` | Phase 1 — becomes the `observer` slot writer. `observe`, `identify_needed_files` preserved |
| File Fetcher | `tools/file_fetcher.py` | Phase 2 — becomes the `file_fetcher` slot writer |
| Agent Manager | `tools/agent_manager.py` | Phase 1 — `classify_complexity` becomes the activation gate |
| Consultants | `tools/consultants.py` | **Replaced.** Individual personas move to `tools/personas/`. `detect_triggers` logic moves to phase activation |
| Agent Discussion | `tools/agent_discussion.py` | **Extended.** `AGENT_EMOJI` grows to 25 cognitive + 4 infrastructure entries. `DiscussionLog` now reads from slot outputs |
| Cost Tracker | `tools/cost_tracker.py` | Unchanged. Each persona call gets tracked |
| Registry | `tools/registry.py` | Unchanged. Read by Token Cart, written by Learner |
| Thread Memory | `tools/thread_memory.py` | Unchanged. Read by Historian, written by Learner |

### New Files

| File | Purpose |
|------|---------|
| `tools/pipeline.py` | `TurnContext` (typed dict), `run_phase`, `run_pipeline`, micro-loop logic |
| `tools/personas/__init__.py` | Persona base class, registry of all personas |
| `tools/personas/strategist.py` | Phase 3: Strategist persona |
| `tools/personas/researcher.py` | Phase 3: Researcher persona |
| `tools/personas/historian.py` | Phase 3: Historian persona |
| `tools/personas/architect.py` | Phase 4: Architect persona (migrated from consultants.py) |
| `tools/personas/specialist.py` | Phase 4: Specialist persona |
| `tools/personas/data_scientist.py` | Phase 4: Data Scientist persona |
| `tools/personas/empathizer.py` | Phase 4: Empathizer persona |
| `tools/personas/connector.py` | Phase 4: Connector persona |
| `tools/personas/reuser.py` | Phase 4: Reuser persona |
| `tools/personas/dreamer.py` | Phase 5: Dreamer persona (later rollout) |
| `tools/personas/insights.py` | Phase 5: Insights persona (later rollout) |
| `tools/personas/growth_coach.py` | Phase 5: Growth Coach persona (later rollout) |
| `tools/personas/skeptic.py` | Phase 6: Skeptic persona (replaces gut check) |
| `tools/personas/devils_advocate.py` | Phase 6: Devil's Advocate persona |
| `tools/personas/simplifier.py` | Phase 6: Simplifier persona |
| `tools/personas/prioritizer.py` | Phase 6: Prioritizer persona |
| `tools/personas/rogue.py` | Phase 7: Rogue persona |
| `tools/personas/hacker.py` | Phase 7: Hacker persona |
| `tools/personas/infosec.py` | Phase 7: Infosec persona (migrated from consultants.py) |
| `tools/personas/inspector.py` | Phase 8: Inspector persona |
| `tools/personas/tester.py` | Phase 8: Tester persona (migrated from consultants.py) |
| `tools/personas/visual_ux.py` | Phase 8: Visual UX persona (migrated from consultants.py) |
| `tools/personas/learner.py` | Phase 9: Learner persona |
| `tools/personas/coach.py` | Phase 9: Coach persona |
| `tools/personas/output_editor.py` | Phase 9: Output Editor persona (migrated from consultants.py) |

### Persona Base Class

```python
class Persona:
    """Base class for all cognitive personas."""
    name: str           # slot name in TurnContext
    emoji: str          # for discussion log
    model: str          # "haiku" or "sonnet"
    reads: list[str]    # declared input slot names
    writes: str         # output slot name (== self.name)
    system_prompt: str  # persona-specific system prompt
    max_tokens: int     # output cap (default 256)

    def run(self, inputs: dict[str, dict]) -> dict:
        """Execute persona. Receives only declared input slots.
        Returns structured JSON dict to write into self.writes slot."""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        """Whether this persona should fire on this turn.
        Checked by the pipeline runner."""
```

### Pipeline Runner

```python
def run_pipeline(
    prompt: str,
    session: dict,
    project: dict,
    complexity: str,  # from Agent Manager
) -> TurnContext:
    """Execute the cognitive pipeline based on complexity tier.

    Simple:   phases 1-2 only
    Moderate: phases 1-4 (lightweight) + 6-8 (post-hoc)
    Complex:  phases 1-9 (full, with micro-loops)
    """
```

## Phase-by-Phase Rollout Plan

Each phase ships independently. Tests for each phase are written and passing before the next begins.

| Order | Phase | What Ships | Depends On |
|-------|-------|-----------|------------|
| 1 | **Pipeline Core** | `TurnContext`, `Persona` base class, `run_phase`, `run_pipeline` scaffold, discussion log integration | Nothing — foundational |
| 2 | **Phase 1-2 Migration** | Migrate Observer, Token Cart, File Fetcher, Agent Manager to persona interface. Wire pipeline into `bot_unified.py`. Simple tier works | Pipeline Core |
| 3 | **Phase 3: Plan & Research** | Strategist, Historian, Researcher. Moderate tier gets lightweight Plan | Phase 1-2 |
| 4 | **Phase 4: Design & Propose** | Architect (migrate), Specialist, Data Scientist, Empathizer, Connector, Reuser. Moderate tier gets lightweight Design | Phase 3 |
| 5 | **Phase 6: Challenge** | Skeptic (replaces gut check), Devil's Advocate, Simplifier, Prioritizer. Moderate tier gets post-hoc Skeptic | Phase 4 |
| 6 | **Phase 7-8: Security + Quality** | Rogue, Hacker, Infosec (migrate), Inspector, Tester (migrate), Visual UX (migrate). Security conditional on moderate | Phase 5 |
| 7 | **Phase 9: Synthesis** | Learner, Coach, Output Editor (migrate). Full complex tier operational | Phase 6 |
| 8 | **Phase 5: Vision** | Dreamer, Insights, Growth Coach. Last because it's generative, not defensive | Phase 7 |
| 9 | **Micro-Loops** | Enable revision loops for complex tier. All 7 self-healing loops operational | Phase 8 |

## Discussion Log Evolution

The Agent Discussion block in Slack grows from flat entries to phase-grouped output:

```
💬 Agent Discussion
📨 Intake
  📋 Complexity: moderate → claude-sonnet-4-6
  👁️ User asking about Phase 3 migration

🛒 Context
  🛒 Enriched with handoff + 2 files
  📂 Loaded followService.ts, likeService.ts

🎯 Plan
  📜 Prior migration (Phase 2) had 3 commits, no rollback
  🎯 Tasks: [schema, RLS, service layer, tests]

📐 Design
  📐 3 tables: follows, post_likes, reposts
  🧬 Supabase: use RLS, not app-level auth
  ♻️ supabase_users table already exists — reuse

🤨 Challenge (advisory)
  🤨 Schema looks solid. No assumptions flagged.

✅ Quality
  🔍 Edge case: self-follow not prevented
  🧪 Test case added: test_self_follow_blocked

💪 SHIP
```

## Cost Model

| Tier | Haiku Calls | Sonnet Calls | Total Est. |
|------|------------|-------------|------------|
| Simple | 3-4 | 0 | ~$0.002 |
| Moderate | 6-8 | 1-2 | ~$0.005 |
| Complex | 12-16 | 3-5 | ~$0.008-0.014 |
| Complex + Vision | 14-18 | 5-7 | ~$0.010-0.018 |

Pricing basis: Haiku ~$0.0005/call, Sonnet ~$0.005/call (estimated at 200-token input + 150-token output per persona).

## Testing Strategy

Each persona gets:
1. **Unit test:** Given these input slots, does it produce correct output contract?
2. **Activation test:** Given this complexity + context, does `should_activate` return correctly?
3. **Integration test:** Does the phase run correctly with real slot data?

Pipeline gets:
1. **Tier routing test:** Simple/moderate/complex prompts route to correct phase sets
2. **Micro-loop test:** Revision triggers cause exactly 1 retry, then proceed
3. **Latency test:** Each tier completes within budget (simple <2s, moderate <5s, complex <18s; stretch goal <12s once parallel-within-phase lands)
4. **Cost test:** Token count per tier stays within estimates

## Non-Goals

- **No parallel API calls within a phase** — sequential for now. Parallel is an optimization for later.
- **No dynamic persona loading** — all personas are statically registered. Dynamic loading adds complexity without clear benefit.
- **No persona-to-persona direct messaging** — all communication goes through the shared dict. No pub/sub.
- **No persistence of TurnContext** — it lives for one turn only. Learner extracts what should persist.
