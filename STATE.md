# Shellack Current State
**Last Updated:** 2026-04-01
**Status:** Production-ready, genericized for open-source — 218 tests green

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
- #8 (test suite) — 218 tests
- #11 (reverse chat) — core bot architecture
- #12 (Slack↔terminal bridge) — implemented

---

## Open Items

- [ ] `conftest.py` for fresh-clone test support (davesleal/Shellack#13)
- [ ] `CONTRIBUTING.md` with fork setup instructions
- [ ] `<function_calls>` XML can still leak in max-mode streaming

---

## What's Next

- [ ] Strip tool XML from SlackSession streaming chunks
- [ ] Dedicated agent memory: rolling cross-thread context + Haiku auto-compaction
- [ ] Follow-ups from genericization (davesleal/Shellack#13)

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
