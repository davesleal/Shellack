# Slack↔Terminal Bridge — Design Spec
**Date:** 2026-03-18
**Status:** Approved
**Author:** Dave Leal + Claude Code

---

## Overview

Build a bridge so Dave can respond to Claude Code prompts from Slack (any device) instead of switching to the terminal. Claude Code posts Block Kit button messages to the project's Slack channel when it needs input; clicking a button writes the answer to a named pipe that Claude Code reads as stdin.

---

## Goals

- Claude Code prompts appear as interactive button messages in the correct project channel
- Clicking a button on any device (phone, tablet, other machine) feeds the answer back to the running Claude Code session
- Multiple concurrent sessions work independently with no cross-contamination
- Designed to support additional input types (confirm, free-text) in future without rearchitecting
- Falls back to `#claude-code` when no project context is detected

---

## Architecture

```
claude-slack (wrapper script)
  └─ detects project from git remote → maps to primary_channel via orchestrator_config.py
  └─ creates session: UUID → /tmp/claude_bridge/<session_id>.json + named pipe
  └─ exports CLAUDE_BRIDGE_SESSION, CLAUDE_BRIDGE_CHANNEL env vars
  └─ starts `claude <args>` with stdin from named pipe
  └─ cleans up on exit (atexit + signal handlers)

Claude Code (in session)
  └─ when needing input: reads env vars, calls Slack MCP to post Block Kit message
     buttons carry value = "<session_id>|<answer_value>"

SlackClaw (always running)
  └─ @app.action("claude_bridge_input") handler:
       reads session_id|answer from button value
       looks up pipe path from /tmp/claude_bridge/<session_id>.json
       writes answer\n to named pipe → Claude stdin unblocks
       updates Slack message: greyed-out buttons + selected option shown
```

---

## Components

### 1. `claude-slack` (new script, `/usr/local/bin/claude-slack`)

Python script (~60 lines). Entry point replacing `claude` for bridge-enabled sessions.

**Responsibilities:**
- Detect current project from `git remote get-url origin` → match against `PROJECTS` in `orchestrator_config.py` via `github_repo` field
- Fall back to `#claude-code` (channel ID `C0AMEEP7EFL`) if no match
- Generate `session_id = str(uuid.uuid4())`
- Create `/tmp/claude_bridge/` dir if needed
- Create named pipe: `os.mkfifo(f"/tmp/claude_bridge/{session_id}")`
- Write session file: `/tmp/claude_bridge/{session_id}.json`:
  ```json
  {
    "pipe": "/tmp/claude_bridge/<session_id>",
    "channel_id": "<slack_channel_id>",
    "project_name": "<project name or 'Unknown'>"
  }
  ```
- Export env vars: `CLAUDE_BRIDGE_SESSION`, `CLAUDE_BRIDGE_CHANNEL`
- Register cleanup via `atexit` and `signal.signal(SIGTERM/SIGINT)`
- Start `claude` subprocess with all args passed through, stdin from open(pipe, 'r')
- On exit: remove pipe + session JSON

**Project detection:**
```python
remote = subprocess.check_output(["git", "remote", "get-url", "origin"]).decode().strip()
# Match against PROJECTS[key]["github_repo"] — normalize to "owner/repo" format
# e.g. git@github.com:davesleal/SlackClaw.git → davesleal/SlackClaw
```

**Fallback:** Any exception in detection (not a git repo, no remote, unknown repo) → silently use `#claude-code`.

---

### 2. `tools/slack_bridge.py` (new module)

Block Kit formatter. Keeps Slack message structure out of `bot_unified.py`.

```python
def format_bridge_blocks(
    question: str,
    options: list[str],
    session_id: str,
    input_type: str = "choice",  # "choice" | "confirm" (future: "text")
) -> list[dict]:
    """Return Block Kit blocks for a bridge input message."""
```

Each button's `value` = `"{session_id}|{option_value}"` and `action_id` = `"claude_bridge_input"`.

For `input_type="confirm"`: renders two buttons — "Yes" and "No".
For `input_type="choice"`: renders one button per option, up to Slack's limit of 5 per actions block (overflow to multiple rows if needed).

Returns a list of Block Kit block dicts ready to pass to `chat_postMessage(blocks=...)`.

---

### 3. `bot_unified.py` — new action handler

```python
@app.action("claude_bridge_input")
def handle_bridge_input(ack, body, action):
    ack()
    # parse value: "<session_id>|<answer>"
    # load /tmp/claude_bridge/<session_id>.json
    # write answer + "\n" to named pipe (non-blocking open with O_WRONLY | O_NONBLOCK)
    # update original message: replace buttons with "✅ You chose: <answer>"
```

**Error handling:**
- Session file missing → `client.chat_postEphemeral(text="⚠️ Session expired — the terminal session may have ended.")` visible only to Dave, no pipe write, no crash
- Pipe write fails (broken pipe, permission) → ephemeral error, buttons remain active so Dave can retry
- JSON parse error → ephemeral error, log

---

## Data Flow

### Happy path

```
1. cd /SlackClaw && claude-slack
2. Wrapper: detects davesleal/SlackClaw → channel slackclaw-dev
3. Creates session abc123, pipe at /tmp/claude_bridge/abc123
4. Posts "🟢 Claude Code session started — SlackClaw" to #slackclaw-dev
5. Starts claude reading from pipe

6. Claude needs input
7. Reads $CLAUDE_BRIDGE_SESSION (abc123), $CLAUDE_BRIDGE_CHANNEL (slackclaw-dev)
8. Posts Block Kit message with buttons to #slackclaw-dev
   button values: "abc123|1", "abc123|2", "abc123|3"

9. Dave clicks "Option 2" on phone
10. Slack sends action payload to SlackClaw
11. SlackClaw: reads "abc123|2", opens /tmp/claude_bridge/abc123.json, gets pipe path
12. Writes "2\n" to pipe
13. Updates Slack message: "✅ You chose: Option 2"

14. Claude's stdin unblocks, reads "2", continues
```

### Concurrent sessions

Two simultaneous `claude-slack` sessions (e.g. SlackClaw + Dayist) each get unique session IDs. Button values carry the session ID, so each click writes to the correct pipe. No shared state between sessions.

---

## Error Cases

| Scenario | Handling |
|----------|----------|
| Not a git repo / unknown remote | Silently fall back to `#claude-code` |
| Session file missing on button click | Ephemeral "Session expired" to Dave; no crash |
| Pipe write failure | Ephemeral error to Dave; buttons stay active for retry |
| `claude-slack` killed ungracefully | `atexit` + `SIGTERM` handler cleans up; stale files are harmless |
| Slack action delivery failure | Standard Slack retry; idempotent pipe write is safe |
| >5 options (Slack button limit) | `format_bridge_blocks` splits into multiple action rows (max 5 buttons each) |

---

## Input Type System

`format_bridge_blocks` accepts `input_type` to support future expansion:

| Type | Current | Implementation |
|------|---------|----------------|
| `choice` | ✅ MVP | Inline buttons, one per option |
| `confirm` | ✅ MVP | "Yes" / "No" buttons |
| `text` | Future | Slack modal (popup form) via `views.open` |

Adding `text` input later requires only a new branch in `format_bridge_blocks` and a `@app.view("claude_bridge_text")` handler — no changes to the pipe/session architecture.

---

## Files

| File | Action | Responsibility |
|------|--------|---------------|
| `claude-slack` | Create | Wrapper script — session, pipe, project detection |
| `tools/slack_bridge.py` | Create | Block Kit formatter with input type system |
| `bot_unified.py` | Modify | Add `@app.action("claude_bridge_input")` handler |
| `tests/test_slack_bridge.py` | Create | Unit tests for formatter + project detection |
| `tests/test_claude_bridge_action.py` | Create | Integration tests for action handler |
| `SETUP_GUIDE.md` | Modify | Add smoke test + installation steps |

---

## Environment

No new env vars required. Uses existing:
- `SLACK_BOT_TOKEN` — SlackClaw posts session start message and updates button messages
- `CLAUDE_BRIDGE_SESSION`, `CLAUDE_BRIDGE_CHANNEL` — set by wrapper, read by Claude Code

---

## Installation

```bash
# Make executable and available globally
chmod +x claude-slack
ln -sf $(pwd)/claude-slack /usr/local/bin/claude-slack

# Usage (drop-in replacement for `claude`)
claude-slack
claude-slack --continue
claude-slack -p "do the thing"
```

---

## Success Criteria

- [ ] `claude-slack` in a known repo posts session-start message to correct project channel
- [ ] `claude-slack` outside any known repo falls back to `#claude-code`
- [ ] Block Kit message appears with correct buttons when Claude needs input
- [ ] Clicking a button on any device feeds the answer to Claude's stdin
- [ ] Clicked message updates to show selection; buttons disabled
- [ ] Two concurrent sessions route independently with no cross-contamination
- [ ] Stale button click (session ended) shows ephemeral error, no crash
- [ ] `claude-slack --continue` and other claude args pass through correctly
- [ ] All unit + integration tests pass
