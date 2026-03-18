# Slack Terminal Tunnel Design

## Goal

Turn Slack into a full bidirectional terminal for Claude — sessions triggered from Slack, output streamed to Slack threads, input via buttons or typed replies. No terminal required. Supports both Claude Max subscription and Anthropic API, switchable live via Slack command.

## Architecture

### Unified SessionBackend

All AI calls in SlackClaw (quick `@SlackClaw` replies and `run:` sessions) route through a single `SessionBackend` abstraction. Two implementations:

- **`MaxBackend`**: spawns `claude -p "<task>"` subprocess. Multi-turn via `claude --continue -p "<follow-up>"`. Captures `--output-format stream-json` stdout. Zero API cost — uses Claude Max subscription.
- **`APIBackend`**: uses `anthropic` SDK with `messages.stream()`. Manages conversation history in memory. Implements tool use loop. Costs API credits per token.

Backend configured via `SESSION_BACKEND=max|api` in `.env`. Switched live via `@SlackClaw set mode max|api` — no bot restart required.

### Components

**`tools/session_backend.py`** — `SessionBackend` abstract base, `MaxBackend`, `APIBackend`

**`tools/slack_session.py`** — `SlackSession`: owns one Slack thread lifecycle. Handles output buffering, input routing (buttons + typed replies), timeout warnings, cleanup.

**`tools/usage_tracker.py`** — Tracks token counts and estimated cost per month. Persisted in `usage.json`. Resets monthly.

**`tools/plugin_manager.py`** — Shells out to `claude plugin install/uninstall` and `claude mcp add/remove`. Manages SlackClaw extensions in `extensions/` with hot-reload.

**`bot_unified.py`** — Extended with: `run:` session trigger, `set mode/model` commands, `usage` command, `config` command, `plugins` command, `add/remove plugin/mcp/bot-plugin` commands, typed thread reply routing to active sessions.

---

## Trigger

`@SlackClaw run: <task>` in any project channel. Channel determines project context (existing `CHANNEL_ROUTING` lookup). Creates a `SlackSession` in that thread.

Existing `@SlackClaw <message>` behavior (quick reply via `ProjectAgent`) is unchanged.

---

## Session Lifecycle

### 1. Start
- `run:` prefix detected in `@app.event("app_mention")`
- `SlackSession` created, keyed by `thread_ts`
- 🔵 status posted to thread: "Starting session…"
- Backend spawned with task as initial prompt and project CLAUDE.md as system context

### 2. Output Chunking
Backend produces output continuously. `SlackSession` buffers and posts when:
- A tool call completes
- A paragraph break is detected
- 3 seconds pass with no new output (timeout flush)

If the gap since the last Slack message is <5s, the existing message is edited in-place. Otherwise a new message is posted. Prevents thread spam while keeping output readable.

### 3. Input — Two Paths

**Structured (Block Kit buttons):** Claude posts choices via Slack MCP. User clicks → `@app.action` handler feeds answer to backend via named pipe (existing bridge mechanism) or API conversation history append.

**Free-form (typed reply):** Any message posted to the thread while a `SlackSession` is active is intercepted in `@app.event("message")`. Routed to the active session as a user message. If no active session exists for that thread, falls back to normal behavior.

User can type `stop` or `cancel` at any time to terminate the session immediately.

### 4. Timeout Warnings
- **15 min idle** → thread message: "Session has been idle for 15 minutes. Still there?"
- **25 min idle** → thread message: "Session timing out in 5 minutes — reply or click to keep it alive"
- **30 min idle** → session paused, final message posted, cleanup

### 5. End
- Backend signals completion (process exit or stream end)
- Final output chunk posted
- ✅ status posted top-level to project channel (existing `LifecycleNotifier` pattern)
- If API mode: brief cost summary posted in thread ("This session used ~1.2M tokens, est. $3.60")
- `SlackSession` removed from active session map

---

## Onboarding

Triggered once on first `python bot_unified.py` — detected by absence of `SESSION_BACKEND` in `.env`.

Posts to `#slackclaw-dev` with two Block Kit buttons:
- **Claude Max subscription** — sets `SESSION_BACKEND=max`
- **Anthropic API key** — sets `SESSION_BACKEND=api`, then posts model selection buttons

Model selection (API mode only):
- **Opus 4.6** — most capable, ~$15/Mtok
- **Sonnet 4.6** (recommended) — fast + smart, ~$3/Mtok
- **Haiku 4.5** — cheapest, ~$0.25/Mtok

Sets `SESSION_MODEL=claude-sonnet-4-6` (or chosen model) in `.env`. Confirmation posted. Never repeats unless user runs `@SlackClaw set mode <x>` to change.

---

## Config Commands

All persist to `.env` immediately. No bot restart required.

| Command | Effect |
|---------|--------|
| `@SlackClaw set mode max` | Switch to Max subscription backend |
| `@SlackClaw set mode api` | Switch to API backend |
| `@SlackClaw set model opus` | Set model to claude-opus-4-6 (API mode) |
| `@SlackClaw set model sonnet` | Set model to claude-sonnet-4-6 (API mode) |
| `@SlackClaw set model haiku` | Set model to claude-haiku-4-5 (API mode) |
| `@SlackClaw usage` | Show current month stats and estimated cost |
| `@SlackClaw config` | Show all current settings |

---

## Plugin & MCP Management

Three namespaces under one interface:

### Claude Code Plugins
`@SlackClaw add plugin <name>` → shells out to `claude plugin install <name>`
`@SlackClaw remove plugin <name>` → shells out to `claude plugin uninstall <name>`

### MCP Servers
`@SlackClaw add mcp <name> <command>` → shells out to `claude mcp add <name> <command>`, updates `~/.claude/settings.json`
`@SlackClaw remove mcp <name>` → shells out to `claude mcp remove <name>`

### SlackClaw Extensions
`@SlackClaw add bot-plugin <name>` → downloads to `extensions/<name>/`, hot-reloaded immediately
`@SlackClaw remove bot-plugin <name>` → removes from `extensions/`, unloaded immediately

`@SlackClaw plugins` → lists all installed plugins, MCPs, and bot extensions with status.

Plugin/MCP changes take effect on the next `run:` session. Bot extensions hot-reload with no restart.

---

## Usage Tracking

`usage.json` in SlackClaw root. Updated after every session and quick reply. Resets on the first of each month.

Tracked fields:
- `session_count` — number of `run:` sessions
- `mention_count` — number of quick `@SlackClaw` replies
- `tokens_in` / `tokens_out` — API mode only
- `estimated_cost` — API mode only, calculated from model pricing
- `mode` — max or api
- `model` — current model

Max mode shows session/mention counts with $0.00 cost. API mode shows full token breakdown.

---

## Implementation Phases

This feature is best delivered in three phases:

**Phase 1 — Session tunnel core**
`SessionBackend` abstraction, `MaxBackend`, `APIBackend`, `SlackSession` lifecycle, `run:` trigger, output chunking, typed reply routing, timeout warnings. This is the minimum viable tunnel.

**Phase 2 — Config & onboarding**
Onboarding flow, `set mode/model` commands, `usage` command, `config` command, `usage_tracker.py`.

**Phase 3 — Plugin management**
`plugin_manager.py`, `plugins` command, `add/remove plugin/mcp/bot-plugin` commands, `extensions/` hot-reload system.

---

## Error Handling

- Backend process crash → `❌ Session ended unexpectedly` posted in thread, session cleaned up
- Slack API error during output post → retry once, then log and continue (don't crash session)
- MCP/plugin install failure → error message posted ephemerally to Dave only
- Typed reply with no active session → falls back to normal `@SlackClaw` behavior silently
- `set mode max` with no `claude` CLI found → ephemeral error: "claude CLI not found. Install Claude Code first."
