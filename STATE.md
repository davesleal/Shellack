# Shellack Current State
**Last Updated:** 2026-03-26
**Status:** Production-ready — noise reduced, agents pre-warmed, 182 tests green

---

## 🟢 What's Running

### Shellack Bot
**Location:** `~/Repos/SlackClaw`
**Start Command:**
```bash
cd ~/Repos/SlackClaw && source venv/bin/activate && python bot_unified.py
```

**Monitoring:** Dayist, TileDock, SidePlane (App Store Connect reviews)

### Configured Channels
```
#dayist-dev        → Dayist project agent
#tiledock-dev      → TileDock project agent
#atmos-dev         → Atmos Universal project agent
#sideplane-dev     → SidePlane project agent
#slackclaw-dev     → Shellack project agent
#slackclaw-central → Orchestrator
#code-review       → Peer review
```

---

## 🔧 Key Config

**File:** `.env` (gitignored)
- `SESSION_BACKEND` — `api` or `max`
- `SESSION_MODEL` — default `claude-sonnet-4-6`
- `SHELLACK_BOT=1` — suppresses Slack MCP in claude subprocess

---

## ✅ Session Checkpoint — 2026-03-26 (Bot polish)

### Fixes shipped
- **Triage removed entirely** — all requests use `SESSION_MODEL` directly. `classify` + `TriageResult` imports removed from `bot_unified.py`.
- **ThinkingIndicator deduplication** — `text=""` on all `chat_postMessage`/`chat_update` calls; only the colored attachment renders. No more plain-text duplicate above the bar.
- **Agent pre-warming** — `AgentFactory` caches by `channel_id` (not `thread_ts`). `warmup_all()` creates one agent per dedicated channel at startup. Zero delay on first message.
- **Lifecycle notifier refresh** — `handle()` recreates `_lifecycle` with current `thread_ts` so pre-warmed agents post to the right thread.
- **Code block formatting** — system prompt instructs agents: use triple-backtick fences with language tag, always close before resuming prose.
- **Unclosed fence safety** — `_md_to_mrkdwn` auto-closes dangling fences (odd ` ``` ` count) before splitting.
- **Test suite** — 182 tests (up from 161). New: `test_agent_factory.py` (7), `test_thinking_indicator.py` (5), `test_md_to_mrkdwn.py` (9).

### Architecture now
- One `ProjectAgent` per channel, created at startup
- Single-turn: `APIBackend` → `ThinkingIndicator` → gray attachment with response folded in
- `run:` sessions: `MaxBackend` or `APIBackend` → `SlackSession` streaming
- No triage, no channel-level lifecycle posts, no peer-review auto-trigger

---

## ⚠️ Open Items

- `<function_calls>` XML can still leak in max-mode `run:` streaming (SlackSession path has no XML stripping)

---

## 🔮 What's Next

- [ ] Strip tool XML from SlackSession streaming chunks
- [ ] Dedicated agent memory: rolling cross-thread context + Haiku auto-compaction

---

## 📂 Key Files

```
~/Repos/SlackClaw/
├── bot_unified.py
├── orchestrator_config.py
├── agents/
│   ├── agent_factory.py        # channel-keyed cache, warmup_all()
│   ├── project_agent.py        # per-channel agent
│   └── sub_agents.py
├── tools/
│   ├── thinking_indicator.py   # clay→gray animated Slack message
│   ├── slack_session.py        # streaming + _md_to_mrkdwn
│   ├── session_backend.py      # APIBackend / MaxBackend / quick_reply
│   └── lifecycle.py            # thread-only status posts
├── tests/                      # 182 tests
└── .env                        # credentials (SECRET)
```

## 🚀 How to Resume

```bash
ps aux | grep bot_unified
cd ~/Repos/SlackClaw && source venv/bin/activate && python bot_unified.py
venv/bin/pytest -q
```

*Last session: 2026-03-26*
