# Shellack Current State
**Last Updated:** 2026-04-05
**Status:** Production — 25-persona phased cognitive pipeline + self-research, 715 tests green

---

## What's Running

### Shellack Bot
**Start Command:**
```bash
source venv/bin/activate && python bot_unified.py
```

**Config:** `projects.yaml` (gitignored) — see `projects.example.yaml` for schema

### Configured Channels
Loaded from `projects.yaml` at startup. Validated with `validate_config()`.

---

## Key Config

**File:** `.env` (gitignored)
- `SESSION_BACKEND` — `api` or `max`
- `SESSION_MODEL` — default `claude-sonnet-4-6`
- `SHELLACK_BOT=1` — suppresses Slack MCP in claude subprocess

**File:** `projects.yaml` (gitignored)
- All project definitions, channel routing, coding standards
- Env var overrides: `{PROJECT}_PROJECT_PATH`, `{PROJECT}_BUNDLE_ID`
- `SHELLACK_CONFIG` overrides config file path

---

## Session Checkpoint — 2026-04-05 (Pipeline Quality + Self-Research)

### What shipped
- **Self-research auto-dispatch** — `tools/self_research.py` runs a Haiku-driven loop (up to 5 steps) to investigate codebase questions. Iteratively runs safe read-only commands, accumulates findings, injects into enriched context. Fires automatically on moderate+ when Toolkeeper doesn't gather output.
- **Toolkeeper persona** — `tools/personas/toolkeeper.py` auto-executes safe read-only commands (cat, grep, git log, etc.) to gather context before the main agent call. Safety-hardened with shell injection blocking ($(), backticks, process substitution, eval, exec).
- **Agent-manager enabled by default** — 3-tier Haiku classification (simple/moderate/complex) now runs on every message. Simple questions skip pipeline entirely (~14s), moderate gets pipeline + self-research (~75s), complex gets full 9-phase pipeline (~3min).
- **Cost tracking** — real token counts extracted from Anthropic API responses, wired through pipeline and micro-loops via `_usage` metadata pattern.
- **Skeptic dynamic targeting** — micro-loop `revision_target` field allows Skeptic to route revisions to any persona, not just the static `to` target.
- **Discussion log improvements** — `_summarize_slot` shows meaningful previews (verdict, command count, findings) instead of dict keys. Persona JSON fences stripped in base class.
- **Markdown→mrkdwn tables** — `_convert_tables()` wraps markdown tables in code blocks for Slack rendering.
- **14 per-persona unit tests** — Connector, DataScientist, Empathizer, Dreamer, GrowthCoach, Insights, Inspector, Tester, VisualUX, Rogue, Hacker, Prioritizer, Simplifier, DevilsAdvocate.
- **Classification prompt tuning** — "uptime?" → simple (14s), "how does triage work?" → moderate (reads source), "trace lifecycle" → complex (full pipeline).
- **Pipeline metadata passthrough** — underscore-prefixed keys (e.g. `_project_path`) pass through to all personas regardless of `reads` declaration.

### Bugs fixed
- Toolkeeper `_project_path` was filtered by reads list → always ran in cwd instead of project dir
- Self-research trigger was inverted (fired when Toolkeeper said "no tools needed" = wrong direction)
- Toolkeeper `run()` override silently dropped `_usage` → cost always 0
- Agent-manager was opt-in (default OFF) → everything defaulted to moderate
- Enriched context fed to Toolkeeper made Haiku think it already had enough info
- Shell injection vectors: `$()`, backticks, `<()`, `system()`, `sed -i`, `eval`, `exec`, `source`, pipe to sh/bash
- `_StubPersona` undefined type annotation in test
- Unused `field` import in pipeline.py
- Persona JSON wrapped in markdown fences → `{"raw": text}` fallback → bad discussion display

### Architecture now
- `projects.yaml` → `orchestrator_config.py` (YAML loader) → module-level exports
- One `ProjectAgent` per channel, pre-warmed at startup
- **3-tier classification**: `agent_manager.py` → Haiku classifies → simple/moderate/complex
- **Pipeline**: `pipeline.py` → 25 personas across 9 phases, tier-gated activation
- **Self-research**: `self_research.py` → iterative Haiku loop for codebase investigation
- **Toolkeeper**: auto-executes safe commands, hardened safety whitelist
- Single-turn: `APIBackend` → `ThinkingIndicator` → gray attachment with response inline
- `run:` sessions: `MaxBackend` or `APIBackend` → `SlackSession` streaming

---

## Open Items

- [x] Self-research capability — auto-dispatch for context gaps (#22)
- [ ] Memory calibration agent (#21)
- [ ] Action buttons trigger run: sessions (#20)
- [ ] XML leak fix for cross-chunk boundaries in streaming
- [ ] Computer Use (#15), Visual UX screenshots (#16), Log Access (#17)
- [ ] Anthropic client consolidation (single global instance)
- [ ] Landing page: shellack.dev deployed on Cloudflare Workers
- [ ] LLM-driven agent transitions — mid-conversation routing (davesleal/Shellack#14, low priority)
- [ ] Parallel-within-phase execution (stretch goal for latency)

---

## Key Files

```
Shellack/
├── bot_unified.py
├── orchestrator_config.py       # YAML loader
├── projects.yaml                # YOUR config (gitignored)
├── projects.example.yaml        # template for forks
├── hooks/pre-commit             # secret scanning
├── agents/
│   ├── agent_factory.py
│   ├── project_agent.py
│   └── sub_agents.py
├── tools/
│   ├── pipeline.py              # TurnContext, Phase, run_pipeline orchestration
│   ├── self_research.py         # Multi-step Haiku codebase investigation
│   ├── personas/                # 25 cognitive personas (one file each)
│   │   ├── __init__.py          # Persona base class + registry + fence stripping
│   │   ├── toolkeeper.py        # Auto-execute safe commands for context
│   │   ├── strategist.py        # Phase 3: task decomposition
│   │   ├── historian.py         # Phase 3: prior decisions
│   │   ├── architect.py         # Phase 4: structural proposals
│   │   ├── skeptic.py           # Phase 6: assumption challenge
│   │   ├── infosec.py           # Phase 7: defensive security
│   │   ├── inspector.py         # Phase 8: completeness check
│   │   ├── learner.py           # Phase 9: lesson extraction
│   │   └── ... (25 total)
│   ├── token_cart.py            # Haiku-powered context compaction
│   ├── triage.py                # Complexity classification (unused — agent_manager used instead)
│   ├── agent_manager.py         # Haiku classifier + model selection (enabled by default)
│   ├── agent_discussion.py      # Phase-grouped discussion log with emoji personas
│   ├── registry.py              # .shellack/registry.md management
│   ├── thread_memory.py         # Cross-thread persistence (24h TTL)
│   ├── cost_tracker.py          # Per-turn/thread cost tracking
│   ├── slack_session.py         # Streaming + _md_to_mrkdwn + table conversion
│   ├── session_backend.py
│   ├── thinking_indicator.py
│   └── lifecycle.py
├── tests/                       # 715 tests
└── .env                         # credentials (SECRET)
```

## How to Resume

```bash
ps aux | grep bot_unified
source venv/bin/activate && python bot_unified.py
venv/bin/pytest -q
```

*Last session: 2026-04-05*
