# Slack Terminal Tunnel Design

## Goal

Turn Slack into a full bidirectional terminal for Claude — sessions triggered from Slack, output streamed to Slack threads, input via buttons or typed replies. No terminal required. Supports both Claude Max subscription and Anthropic API, switchable live via Slack command.

## Architecture

### Unified SessionBackend

All AI calls in SlackClaw (quick `@SlackClaw` replies and `run:` sessions) route through a single `SessionBackend` abstraction. Two implementations:

- **`MaxBackend`**: spawns a `claude` subprocess that stays alive for the entire session. Passes the initial prompt via stdin and reads `--output-format stream-json` from stdout. The subprocess remains running between turns — no `--continue` needed, because the process never exits until the session ends. **One subprocess per session.** Concurrent sessions each have their own isolated subprocess, eliminating any `--continue` collision risk.
- **`APIBackend`**: uses `anthropic` SDK with `messages.stream()`. Manages conversation history list in memory on `SlackSession`. Implements tool use loop. Costs API credits per token.

Backend configured via `SESSION_BACKEND=max|api` in `.env`. Switched live via `@SlackClaw set mode max|api` — no bot restart required.

### Components

**`tools/session_backend.py`** — `SessionBackend` abstract base, `MaxBackend`, `APIBackend`

**`tools/slack_session.py`** — `SlackSession`: owns one Slack thread lifecycle. Holds backend reference, `last_message_ts` (asyncio-locked), conversation history (API mode), idle timer. Handles output buffering, input dispatch, timeout warnings, cleanup.

**`tools/usage_tracker.py`** — Tracks token counts and estimated cost per month. Persisted in `usage.json`. Monthly reset checked on read (compare stored `reset_month` to current month).

**`tools/plugin_manager.py`** — Shells out to `claude plugin install/uninstall` and `claude mcp add/remove`. Manages SlackClaw extensions in `extensions/` with hot-reload.

**`bot_unified.py`** — Extended with: `run:` session trigger, unified `RUN_SESSIONS` dict (keyed by `thread_ts`) replacing the old `active_sessions` map, `set mode/model` commands, `usage` command, `config` command, `plugins` command, `add/remove plugin/mcp/bot-plugin` commands, typed thread reply routing to active sessions.

---

## Trigger

`@SlackClaw run: <task>` in any project channel. Channel determines project context (existing `CHANNEL_ROUTING` lookup). Creates a `SlackSession` in that thread.

Existing `@SlackClaw <message>` behavior (quick reply via `ProjectAgent`) is unchanged.

---

## Session Lifecycle

### 1. Start
- `run:` prefix detected in `@app.event("app_mention")`
- `SlackSession` created, stored in `RUN_SESSIONS[thread_ts]`
- 🔵 status posted to thread: "Starting session…"
- Backend spawned with task as initial prompt and project CLAUDE.md as system context

### 2. Output Chunking
Backend produces output continuously. `SlackSession` buffers and posts when:
- A tool call completes
- A paragraph break is detected
- 3 seconds pass with no new output (timeout flush)

**Edit-vs-new logic:** `SlackSession` tracks `last_message_ts` (the `ts` of the last message it posted). Protected by an `asyncio.Lock` to prevent races between concurrent output chunks. If the gap since `last_message_ts` was posted is <5s, `chat_update` edits it in-place. Otherwise `chat_postMessage` creates a new message and updates `last_message_ts`. This prevents thread spam while keeping output readable.

### 3. Input — Two Paths

**Structured (Block Kit buttons):** Claude posts choices via Slack MCP. User clicks → `@app.action("claude_bridge_input")` handler dispatches based on session type:
- `MaxBackend` session: writes answer to the subprocess's stdin pipe
- `APIBackend` session: appends answer as a `user` message to `SlackSession.history`, triggers next stream call

The action handler looks up `RUN_SESSIONS[thread_ts]` to determine which path to take. If no active session found, falls back to existing pipe-file behavior for `claude-slack` bridge sessions.

**Free-form (typed reply):** Thread replies intercepted in `@app.event("message")`. Handler checks `RUN_SESSIONS` for `thread_ts`. If found: routes message text to the session's backend (stdin write for Max, history append for API). If not found: falls back to existing behavior. **Note:** intercepts all thread replies in active sessions without requiring a bot mention — this is intentional for natural conversation flow. Bot must be in the channel to receive non-mention messages (requires `message.channels` scope, already granted).

User can type `stop` or `cancel` at any time to terminate the session immediately.

### 4. Timeout Warnings
Idle timer reset on every input received or output produced.
- **15 min idle** → thread message: "Session has been idle for 15 minutes. Still there?"
- **25 min idle** → thread message: "Session timing out in 5 minutes — reply or click to keep it alive"
- **30 min idle** → session paused, final message posted, cleanup

### 5. End
- Backend signals completion (subprocess exits or stream ends)
- Final output chunk posted
- ✅ status posted top-level to project channel (existing `LifecycleNotifier` pattern)
- If API mode: brief cost summary posted in thread ("This session used ~1.2M tokens, est. $3.60")
- `SlackSession` removed from `RUN_SESSIONS`

---

## Onboarding

**Detection:** Absence of `ONBOARDING_COMPLETE=true` in `.env`. This is a dedicated flag — not inferred from other key presence. A fresh clone with no `.env` will have `ONBOARDING_COMPLETE` absent; so will a partial `.env` from a previous incomplete setup.

**Startup behavior:** Bot starts fully before posting onboarding. Onboarding message is posted to `#slackclaw-dev` immediately after the Slack socket connection is established. The bot does NOT gate startup on the onboarding response — it continues running normally and handles the button click asynchronously when the user responds.

Posts to `#slackclaw-dev` with two Block Kit buttons:
- **Claude Max subscription** — sets `SESSION_BACKEND=max`, `ONBOARDING_COMPLETE=true` in `.env`
- **Anthropic API key** — sets `SESSION_BACKEND=api`, then posts model selection buttons

Model selection (API mode only):
- **Opus 4.6** — most capable, ~$15/Mtok
- **Sonnet 4.6** (recommended) — fast + smart, ~$3/Mtok
- **Haiku 4.5** — cheapest, ~$0.25/Mtok

Sets `SESSION_MODEL=claude-sonnet-4-6` (or chosen model) and `ONBOARDING_COMPLETE=true` in `.env`. Confirmation posted. Never repeats.

---

## Config Commands

All persist to `.env` immediately. No bot restart required.

| Command | Effect |
|---------|--------|
| `@SlackClaw set mode max` | Switch to Max subscription backend |
| `@SlackClaw set mode api` | Switch to API backend |
| `@SlackClaw set model opus` | Set model to claude-opus-4-6 (API mode) |
| `@SlackClaw set model sonnet` | Set model to claude-sonnet-4-6 (API mode) |
| `@SlackClaw set model haiku` | Set model to claude-haiku-4-5-20251001 (API mode) |
| `@SlackClaw usage` | Show current month stats and estimated cost |
| `@SlackClaw config` | Show all current settings |

---

## Plugin & MCP Management

Three namespaces under one interface:

### Claude Code Plugins
`@SlackClaw add plugin <name>` → shells out to `claude plugin install <name>`
`@SlackClaw remove plugin <name>` → shells out to `claude plugin uninstall <name>`

Note: `claude plugin` is the stable public CLI surface for Claude Code extensions.

### MCP Servers
`@SlackClaw add mcp <name> <command>` → shells out to `claude mcp add <name> <command>`, updates `~/.claude/settings.json`
`@SlackClaw remove mcp <name>` → shells out to `claude mcp remove <name>`

### SlackClaw Extensions
`@SlackClaw add bot-plugin <name>` → clones from `https://github.com/SlackClaw-plugins/<name>` into `extensions/<name>/`, imports and registers the extension module immediately (hot-reload via `importlib`). For MVP, only official `SlackClaw-plugins` GitHub org is supported as the registry. Full URL override supported: `@SlackClaw add bot-plugin https://github.com/user/repo`.
`@SlackClaw remove bot-plugin <name>` → unregisters module, deletes `extensions/<name>/`

`@SlackClaw plugins` → lists all installed plugins, MCPs, and bot extensions with status.

Plugin/MCP changes take effect on the next `run:` session. Bot extensions hot-reload immediately.

---

## Usage Tracking

`usage.json` in SlackClaw root. Updated after every session and quick reply. Monthly reset: on read, compare `reset_month` field (format: `"YYYY-MM"`) to current month — if different, zero counters and update `reset_month`. No cron required.

Tracked fields:
- `reset_month` — `"YYYY-MM"` of last reset
- `session_count` — number of `run:` sessions
- `mention_count` — number of quick `@SlackClaw` replies
- `tokens_in` / `tokens_out` — API mode only
- `estimated_cost` — API mode only, calculated from model pricing
- `mode` — max or api
- `model` — current model

Max mode shows session/mention counts with $0.00 cost. API mode shows full token breakdown.

---

## Implementation Phases

**Phase 1 — Session tunnel core**
`SessionBackend` abstraction, `MaxBackend` (long-lived subprocess), `APIBackend`, `SlackSession` lifecycle, `run:` trigger, `RUN_SESSIONS` dict, output chunking with asyncio-locked `last_message_ts`, typed reply routing, action handler dispatch, timeout warnings. Minimum viable tunnel.

**Phase 2 — Config & onboarding**
Onboarding flow (`ONBOARDING_COMPLETE` flag), `set mode/model` commands, `usage` command, `config` command, `usage_tracker.py` with check-on-read monthly reset.

**Phase 3 — Plugin management**
`plugin_manager.py`, `plugins` command, `add/remove plugin/mcp/bot-plugin` commands, `extensions/` hot-reload via `importlib`, GitHub org registry for bot-plugins.

---

## Error Handling

- Backend process crash → `❌ Session ended unexpectedly` posted in thread, session removed from `RUN_SESSIONS`
- Slack API error during output post → retry once, then log and continue (don't crash session)
- MCP/plugin install failure → error message posted ephemerally to the triggering user only
- Typed reply with no active session → falls back to normal `@SlackClaw` behavior silently
- `set mode max` with no `claude` CLI found → ephemeral error: "claude CLI not found. Install Claude Code first."
- `add bot-plugin` from unknown org → ephemeral error with instructions to use full GitHub URL
