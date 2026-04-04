# Shellack Current State
**Last Updated:** 2026-04-04
**Status:** Production-ready — 21-persona cognitive agent system, 467 tests green

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

## Session Checkpoint — 2026-04-01 (Genericization)

### What shipped
- **Config extraction** — `orchestrator_config.py` rewritten as YAML loader. All project defs moved to `projects.yaml` (gitignored). Ships `projects.example.yaml` with full commented schema.
- **Secret scanning** — `hooks/pre-commit` scans staged files for 12 secret patterns (Slack tokens, API keys, AWS, GitHub, private keys). Zero dependencies.
- **Personal refs stripped** — all tracked files use generic placeholders. No project names, channel IDs, bundle IDs, or personal identifiers in code, docs, tests, or scripts.
- **PROJECT_KNOWLEDGE removed** — agent reads `context` from config instead of hardcoded dict.
- **Triage fix** — `_DEFAULT` fallback evaluates `SESSION_MODEL` at call time, not import.
- **ThinkingIndicator** — fallback tests for `done()` failure paths.
- **Onboarding** — reads channel from `ONBOARDING_CHANNEL` env var or config, no hardcoded channel name.
- **YAML robustness** — warns on empty `projects` section and unrecognized top-level keys (catches typos).

### Architecture now
- `projects.yaml` → `orchestrator_config.py` (YAML loader) → module-level exports
- One `ProjectAgent` per channel, pre-warmed at startup
- Single-turn: `APIBackend` → `ThinkingIndicator` → gray attachment with response inline
- `run:` sessions: `MaxBackend` or `APIBackend` → `SlackSession` streaming
- No triage routing, no channel-level lifecycle posts, no peer-review auto-trigger

### GitHub issues closed
- #5 (multi-language support) — done via `projects.yaml`
- #8 (test suite) — 263 tests
- #11 (reverse chat) — core bot architecture
- #12 (Slack↔terminal bridge) — implemented

---

## Open Items

- [x] `conftest.py` for fresh-clone test support (davesleal/Shellack#13)
- [x] `CONTRIBUTING.md` with fork setup instructions
- [x] `<function_calls>` XML stripped from max-mode streaming (`_strip_tool_xml` in `slack_session.py`)
- [x] Personal refs stripped from `docs/superpowers/` (davesleal/Shellack#13 — closed)

---

## What's Next

- [x] Strip tool XML from SlackSession streaming chunks
- [x] Follow-ups from genericization (davesleal/Shellack#13 — closed)
- [x] Haiku Token Cart — full system implemented + wired (393 tests):
  - Token Cart Core (pre/post enrichment, handoff store)
  - Project Registry (.shellack/registry.md)
  - Cross-Thread Persistence (external handoffs)
  - Correction Feedback Loop (auto-update registry)
  - Cost Observability (per-turn spend in Churned block)
  - Gut Check Agent (sanity check before posting)
  - Inline Code Review (self-healing via post-call prompt)
  - Channel Agent Teams (infosec, architect, tester, output-editor, visual-ux consultants)
  - Agent Manager (complexity-based model selection)
  - Feature Configuration (runtime toggles via `@Shellack config`)
  - GitHub Discussions Journal — Sonnet polish + weekly threads, wired to session idle timeout
  - Session cleanup — 10min idle → journal finalized, session purged
- [x] Message UX redesign — `[think]/[reply]` tags, reasoning before reply, action buttons
- [x] Voice transcription — faster-whisper local transcription
- [x] Skill-aware agents — auto-detect stack, load relevant skills
- [x] File Fetcher + Thread Observer — agents read files and maintain thread context
- [x] Agent Discussion transparency — inter-agent chatter visible with emoji personas
- [x] Context Manifest — persistent `.shellack/context.md` that grows over time
- [x] Action buttons — numbered options as clickable Slack buttons
- [x] Startup context scan — STATE.md, git log, file structure, configs loaded on warmup
- [x] Thread continuation without @mention
- [x] TTL-based thread memory expiry (24h)
- [ ] 22-persona cognitive model — spec complete, 11 implemented, 11 to implement
- [ ] Self-research capability — auto-dispatch run: for context gaps (#22)
- [ ] Memory calibration agent (#21)
- [ ] Action buttons trigger run: sessions (#20)
- [ ] XML leak fix for cross-chunk boundaries in streaming
- [ ] Computer Use (#15), Visual UX screenshots (#16), Log Access (#17)
- [ ] Anthropic client consolidation (single global instance)
- [ ] Landing page: shellack.dev deployed on Cloudflare Workers
- [ ] LLM-driven agent transitions — mid-conversation routing (davesleal/Shellack#14, low priority)

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
│   ├── token_cart.py            # Haiku-powered context compaction
│   ├── registry.py              # .shellack/registry.md management
│   ├── thread_memory.py         # cross-thread persistence
│   ├── cost_tracker.py          # per-turn/thread cost tracking
│   ├── consultants.py           # infosec + architect consultants
│   ├── agent_manager.py         # complexity-based model selection
│   ├── github_journal.py        # GitHub Discussions journal posting
│   ├── journal_polisher.py      # Sonnet journal polish
│   ├── thinking_indicator.py
│   ├── slack_session.py
│   ├── session_backend.py
│   └── lifecycle.py
├── tests/                       # 218 tests
└── .env                         # credentials (SECRET)
```

## How to Resume

```bash
ps aux | grep bot_unified
source venv/bin/activate && python bot_unified.py
venv/bin/pytest -q
```

*Last session: 2026-04-01*
