# Shellack Current State
**Last Updated:** YYYY-MM-DD
**Status:** _summary of current status_

---

## What's Running

### Shellack Bot
**Start Command:**
```bash
source venv/bin/activate && python bot_unified.py
```

**Monitoring:** _(list monitored projects from projects.yaml)_

### Configured Channels
```
#project-a-dev     → Project A agent
#project-b-dev     → Project B agent
#shellack-central  → Orchestrator
#code-review       → Peer review
```

---

## Key Config

**File:** `.env` (gitignored)
- `SESSION_BACKEND` — `api` or `max`
- `SESSION_MODEL` — default `claude-sonnet-4-6`
- `SHELLACK_BOT=1` — suppresses Slack MCP in claude subprocess

---

## Session Checkpoint — YYYY-MM-DD

### Fixes shipped
- _(list recent fixes)_

### Architecture now
- _(describe current architecture)_

---

## Open Items

- _(list known issues)_

---

## What's Next

- [ ] _(planned work)_

---

## Key Files

```
Shellack/
├── bot_unified.py
├── orchestrator_config.py
├── agents/
│   ├── agent_factory.py
│   ├── project_agent.py
│   └── sub_agents.py
├── tools/
│   ├── thinking_indicator.py
│   ├── slack_session.py
│   ├── session_backend.py
│   └── lifecycle.py
├── tests/
└── .env                        # credentials (SECRET)
```

## How to Resume

```bash
ps aux | grep bot_unified
source venv/bin/activate && python bot_unified.py
venv/bin/pytest -q
```
