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
- Falls back to `#claude-code` (ID: `C0AMEEP7EFL`) when no project context is detected

---

## Architecture

```
claude-slack (wrapper script)
  └─ detects project from git remote → maps to channel ID via orchestrator_config.py
  └─ creates session: UUID → /tmp/claude_bridge/<session_id>.json + named pipe
  └─ exports CLAUDE_BRIDGE_SESSION=<uuid>, CLAUDE_BRIDGE_CHANNEL_ID=<slack_channel_id>
  └─ holds pipe write-end open (keep-alive fd) to prevent EOF until session ends
  └─ starts `claude <args>` with stdin from pipe read-end (O_NONBLOCK)
  └─ cleans up on exit (SIGTERM handler + atexit)

Claude Code (in session)
  └─ detects CLAUDE_BRIDGE_SESSION is set (via Bash tool: echo $CLAUDE_BRIDGE_SESSION)
  └─ when needing input: uses Slack MCP to post Block Kit message with buttons
     buttons carry value = "<session_id>|<answer_value>"

Shellack (always running)
  └─ @app.action("claude_bridge_input") handler:
       parses session_id and answer from button value
       loads /tmp/claude_bridge/<session_id>.json → gets pipe path
       opens pipe write-end (O_WRONLY | O_NONBLOCK), writes answer + newline
       updates original Slack message: buttons replaced with "✅ You chose: <answer>"
       on error: chat_postEphemeral to Dave only
```

---

## Components

### 1. `claude-slack` (new script, `/usr/local/bin/claude-slack`)

Python script. Shebang: `#!/usr/bin/env python3`. Must be run from the same Python environment as Shellack (same venv) so `orchestrator_config` is importable.

**Responsibilities:**

**Project detection:**
```python
import re, subprocess

def detect_channel_id() -> tuple[str, str]:
    """Returns (channel_id, project_name). Falls back to #claude-code."""
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL
        ).decode().strip()
        # Normalise SSH and HTTPS remote URLs to "owner/repo"
        slug = re.sub(r"\.git$", "", remote)
        slug = re.sub(r"^git@github\.com:", "", slug)
        slug = re.sub(r"^https://github\.com/", "", slug)
        # Match against PROJECTS, then resolve channel ID via primary_channel
        from orchestrator_config import PROJECTS, CHANNEL_ROUTING
        for key, cfg in PROJECTS.items():
            if cfg.get("github_repo") == slug:
                primary = cfg.get("primary_channel", "")
                # Look up by primary_channel name — guaranteed one-to-one per project
                routing = CHANNEL_ROUTING.get(primary, {})
                channel_id = routing.get("channel_id", "")
                if channel_id:
                    return channel_id, cfg["name"]
                # Project matched but channel_id missing — misconfiguration, not unknown repo
                import sys as _sys
                print(
                    f"[claude-slack] WARNING: project '{cfg['name']}' matched but "
                    f"CHANNEL_ROUTING['{primary}'] has no 'channel_id'. "
                    "Add channel_id to orchestrator_config.py. Falling back to #claude-code.",
                    file=_sys.stderr,
                )
                return "C0AMEEP7EFL", cfg["name"]
    except Exception:
        pass
    return "C0AMEEP7EFL", "Unknown"  # fallback: #claude-code (not a known git repo)
```

**Constraint:** Each project must have exactly one entry in `CHANNEL_ROUTING` matching its `primary_channel`. The lookup uses `primary_channel` directly — not a scan of all routing entries — to guarantee deterministic results.

**Note:** `CHANNEL_ROUTING` entries must have a `channel_id` field added (see Modified Files). Only `"mode": "dedicated"` entries need `channel_id` for the bridge; other entries (`orchestrator`, `peer_review`) may include it for completeness.

**Named pipe — keep-alive write-end pattern:**

A named pipe `open(read)` blocks until a writer opens the other end. To prevent deadlock:

```python
import fcntl, os, uuid, json, atexit, signal, subprocess, sys

proc_handle = None  # initialised here so SIGTERM handler can reference it safely

session_id = str(uuid.uuid4())
pipe_path = f"/tmp/claude_bridge/{session_id}"
os.makedirs("/tmp/claude_bridge", exist_ok=True)
os.mkfifo(pipe_path)

# Open write-end first (non-blocking) to unblock the read-end open below
write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
# Open read-end non-blocking (succeeds immediately because write-end is open)
read_fd  = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)
# Clear O_NONBLOCK from the read end so the subprocess's stdin blocks normally.
# (We only needed O_NONBLOCK to prevent this open() call from hanging; the
# write end being open was the real unlock. O_CLOEXEC is intentionally absent
# so both write_fd and read_fd are inherited by the child — required for stdin.)
_flags = fcntl.fcntl(read_fd, fcntl.F_GETFL)
fcntl.fcntl(read_fd, fcntl.F_SETFL, _flags & ~os.O_NONBLOCK)

channel_id, project_name = detect_channel_id()

# Write session file for Shellack to look up
session_file = f"/tmp/claude_bridge/{session_id}.json"
with open(session_file, "w") as f:
    json.dump({"pipe": pipe_path, "channel_id": channel_id,
               "project_name": project_name}, f)

def cleanup():
    try: os.close(write_fd)
    except: pass
    # read_fd ownership transferred to os.fdopen(); do not close by fd number —
    # Popen's dup2 already closed it; an os.close() here raises EBADF.
    for path in [pipe_path, session_file]:
        try: os.unlink(path)
        except: pass

atexit.register(cleanup)

def _sigterm_handler(*_):
    # Send SIGTERM to claude subprocess first so it can save state before cleanup
    if proc_handle is not None:
        try: proc_handle.send_signal(signal.SIGTERM)
        except: pass
    cleanup()
    sys.exit(0)

signal.signal(signal.SIGTERM, _sigterm_handler)
# Note: SIGKILL cannot be caught; stale files are harmless (handled on button click)

# Export env vars and launch claude
env = os.environ.copy()
env["CLAUDE_BRIDGE_SESSION"] = session_id
env["CLAUDE_BRIDGE_CHANNEL_ID"] = channel_id

# Post session-start message to Slack
# See tools/slack_bridge.py post_session_start()

# Note: os.open() does not set O_CLOEXEC on macOS by default, so both write_fd
# and read_fd are inherited by the child — intentional for stdin redirection.
# write_fd in the child is harmless: the parent still holds the keep-alive copy.
# We wrap read_fd in a file object so Popen's internal dup2-to-stdin + close_fds
# processing works correctly on all CPython versions.
proc_handle = None
proc = subprocess.Popen(
    ["claude"] + sys.argv[1:],
    stdin=os.fdopen(read_fd, "rb"),
    env=env,
)
proc_handle = proc
proc.wait()
sys.exit(proc.returncode)
```

---

### 2. `tools/slack_bridge.py` (new module)

Block Kit formatter and session utilities.

```python
def format_bridge_blocks(
    question: str,
    options: list[str],
    session_id: str,
    input_type: str = "choice",  # "choice" | "confirm" (future: "text")
) -> list[dict]:
    """
    Return Block Kit blocks for a bridge input message.
    Each button value = "{session_id}|{option_value}".
    Each button action_id = "claude_bridge_input".
    Options split into rows of 5 (Slack limit per actions block).
    Total blocks kept well under Slack's 50-block limit.

    When input_type="confirm", `options` is ignored; buttons are always
    "Yes" (value: "yes") and "No" (value: "no").
    When input_type="choice", each item in `options` becomes one button.
    """
```

For `input_type="confirm"`: two buttons — "Yes" (`yes`) and "No" (`no`). `options` is ignored.
For `input_type="choice"`: one button per option. If >5 options, splits into multiple `actions` blocks (5 per row).

```python
def post_session_start(channel_id: str, project_name: str):
    """Post session-start message via direct Slack API call.

    claude-slack is a standalone script with no Bolt App instance, so we call
    the Slack Web API directly using SLACK_BOT_TOKEN from the environment.
    """
    import logging, os, requests
    token = os.environ["SLACK_BOT_TOKEN"]
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel": channel_id,
            "text": f"🟢 Claude Code session started — *{project_name}*",
        },
    )
    resp.raise_for_status()  # surface HTTP-level failures
    data = resp.json()
    if not data.get("ok"):
        logging.warning("[claude-slack] post_session_start failed: %s", data.get("error"))
```

---

### 3. `bot_unified.py` — new action handler

```python
@app.action("claude_bridge_input")
def handle_bridge_input(ack, body, action, client):
    ack()

    raw_value = action.get("value", "")
    parts = raw_value.split("|", 1)
    if len(parts) != 2:
        return  # malformed, ignore

    session_id, answer = parts
    session_file = f"/tmp/claude_bridge/{session_id}.json"
    channel = body.get("channel", {}).get("id", "")
    user = body.get("user", {}).get("id", "")
    if not channel or not user:
        return  # can't send ephemeral without both; Bolt already acked
    message_ts = body.get("message", {}).get("ts", "")
    # message_ts may be absent for ephemeral/modal-triggered actions;
    # we still write to the pipe but skip chat_update in that case.

    # Load session
    try:
        with open(session_file) as f:
            session = json.load(f)
    except FileNotFoundError:
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text="⚠️ Session expired — the terminal session may have ended."
        )
        return
    except Exception as e:
        client.chat_postEphemeral(channel=channel, user=user,
                                   text=f"⚠️ Could not load session: {e}")
        return

    # Write answer to named pipe
    pipe_path = session["pipe"]
    try:
        fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, (answer + "\n").encode())
        os.close(fd)
    except OSError as e:
        # ENXIO: pipe exists but no reader (claude-slack exited after session file write)
        # EPIPE / other: broken pipe
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text=f"⚠️ Could not reach terminal session — it may have exited. ({e.strerror})"
        )
        return  # leave buttons active so Dave can retry or dismiss

    # Update message: replace buttons with confirmation text (buttons removed, not disabled —
    # Slack Block Kit has no native disabled state; replacement is the correct approach).
    if not message_ts:
        return  # no original message to update (e.g. triggered from modal)
    client.chat_update(
        channel=channel,
        ts=message_ts,
        blocks=[{
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"✅ *You chose:* {answer}"}
        }],
        text=f"✅ You chose: {answer}"
    )
```

Add `import os, json` at the top of `bot_unified.py`.

---

### 4. How Claude Code knows to use the bridge

When `CLAUDE_BRIDGE_SESSION` is set in the environment, Claude Code is running inside a `claude-slack` session. The following rule is added to `CLAUDE.md` (Shellack root) so it is loaded into every Claude Code session's system prompt:

```markdown
## Claude-Slack Bridge

When the environment variable `CLAUDE_BRIDGE_SESSION` is set (check with Bash: `echo $CLAUDE_BRIDGE_SESSION`), you are running inside a Slack bridge session. In this mode:

1. When you need input from Dave, use the Slack MCP (`slack_send_message`) to post to `$CLAUDE_BRIDGE_CHANNEL_ID`
2. Format the message using Block Kit with interactive buttons (action_id: `claude_bridge_input`, value: `{CLAUDE_BRIDGE_SESSION}|{option_value}`)
3. Then wait — Dave will click a button and the answer will arrive via stdin automatically
4. Do NOT ask for input via terminal (it will not be seen)

Helper: `tools/slack_bridge.py::format_bridge_blocks(question, options, session_id)` returns the correct Block Kit JSON.
```

---

## Modified Files

### `orchestrator_config.py` — add `channel_id` to CHANNEL_ROUTING entries

`claude-slack` needs to resolve a channel name to its Slack channel ID without a live API call. Add `"channel_id"` to each entry in `CHANNEL_ROUTING`:

```python
CHANNEL_ROUTING = {
    "dayist-dev":   {"project": "dayist",        "mode": "dedicated", "channel_id": "C..."},
    "nova-dev":     {"project": "nova",           "mode": "dedicated", "channel_id": "C..."},
    ...
    "slackclaw-dev":{"project": "slackclaw",      "mode": "dedicated", "channel_id": "C..."},
    "code-review":  {"project": None,             "mode": "peer_review","channel_id": "C..."},
}
```

Channel IDs are found via Slack app settings or `slack_search_channels`.

**⚠️ Prerequisite for bridge to function:** Every project's `primary_channel` entry in `CHANNEL_ROUTING` **must** have a `channel_id` field populated before `claude-slack` is used. If `channel_id` is missing for a recognized project, `detect_channel_id` will print a warning to stderr and fall back to `#claude-code` — the session will work but route to the wrong channel.

---

## Data Flow

### Happy path

```
1. cd /Shellack && claude-slack
2. Wrapper: detects davesleal/Shellack → channel ID C_SLACKCLAW
3. Creates session abc123, pipe at /tmp/claude_bridge/abc123
4. Opens write-end fd (keep-alive), then read-end fd
5. Posts "🟢 Claude Code session started — Shellack" to #slackclaw-dev
6. Starts `claude` with stdin=read_fd, env includes CLAUDE_BRIDGE_SESSION=abc123,
   CLAUDE_BRIDGE_CHANNEL_ID=C_SLACKCLAW

7. Claude checks: echo $CLAUDE_BRIDGE_SESSION → abc123 (bridge mode active)
8. Claude needs input → calls format_bridge_blocks("Which approach?", ["A","B","C"], "abc123")
9. Posts Block Kit message to C_SLACKCLAW via Slack MCP
   button values: "abc123|A", "abc123|B", "abc123|C"

10. Dave clicks "B" on phone
11. Slack sends action payload to Shellack
12. handle_bridge_input: parses "abc123|B"
    reads /tmp/claude_bridge/abc123.json → pipe path
    opens pipe write-end (O_NONBLOCK), writes "B\n"
    updates Slack message: "✅ You chose: B"

13. Claude's stdin read unblocks, receives "B\n", continues
```

### Concurrent sessions

Two simultaneous `claude-slack` sessions (e.g. Shellack + Dayist) each get unique session IDs. Button values carry the session ID, so each click writes to the correct pipe. No shared state between sessions.

---

## Error Cases

| Scenario | Handling |
|----------|----------|
| Not a git repo / unknown remote | Silently fall back to `#claude-code` (C0AMEEP7EFL) |
| Session file missing on button click | `chat_postEphemeral` "Session expired" to Dave only; no crash |
| Pipe exists but no reader (ENXIO — claude-slack exited after session file write) | `chat_postEphemeral` error; buttons stay active for retry |
| Other pipe write failure (EPIPE, permission) | `chat_postEphemeral` error; buttons stay active |
| `claude-slack` killed via SIGTERM | SIGTERM handler cleans up pipe + session file |
| `claude-slack` killed via SIGKILL | Stale files remain; harmless — "session expired" on next button click |
| >5 options | `format_bridge_blocks` splits into multiple actions rows (5 per row); total blocks stay well under Slack's 50-block limit |
| Dave never clicks (async timeout) | Known limitation — Claude Code blocks indefinitely on pipe read. Acceptable for MVP; future work: close write-end after N minutes to send EOF |

---

## Input Type System

`format_bridge_blocks` accepts `input_type` to support future expansion:

| Type | Status | Implementation |
|------|--------|----------------|
| `choice` | ✅ MVP | Inline buttons, one per option |
| `confirm` | ✅ MVP | "Yes" / "No" buttons |
| `text` | Future | Slack modal (`views.open`) + `@app.view("claude_bridge_text")` handler |

Adding `text` input later requires only a new branch in `format_bridge_blocks` and a new view handler — no changes to the pipe/session architecture.

---

## Files

| File | Action | Responsibility |
|------|--------|---------------|
| `claude-slack` | Create | Wrapper script — session, pipe, project detection |
| `tools/slack_bridge.py` | Create | Block Kit formatter with input type system |
| `orchestrator_config.py` | Modify | Add `channel_id` to all CHANNEL_ROUTING entries |
| `CLAUDE.md` | Modify | Add bridge instructions for Claude Code sessions |
| `bot_unified.py` | Modify | Add `@app.action("claude_bridge_input")` handler |
| `tests/test_slack_bridge.py` | Create | Unit tests for formatter + project detection |
| `tests/test_claude_bridge_action.py` | Create | Integration tests for action handler |
| `SETUP_GUIDE.md` | Modify | Add installation + smoke test steps |

---

## Environment Variables

`SLACK_BOT_TOKEN` is already required by Shellack (no change).

Two new **runtime** vars set by the wrapper — no user configuration required:

| Var | Set by | Purpose |
|-----|--------|---------|
| `CLAUDE_BRIDGE_SESSION` | `claude-slack` | Session UUID; identifies pipe + session file |
| `CLAUDE_BRIDGE_CHANNEL_ID` | `claude-slack` | Slack channel ID for posting prompts |

---

## Installation

```bash
# Shebang in claude-slack: #!/usr/bin/env python3
# Must use same Python/venv as Shellack so orchestrator_config is importable

chmod +x claude-slack
ln -sf "$(pwd)/claude-slack" /usr/local/bin/claude-slack

# Usage — drop-in replacement for `claude`
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
- [ ] Clicked message updates to show selection; buttons replaced with confirmation text
- [ ] Two concurrent sessions route independently with no cross-contamination
- [ ] Stale button click (session ended) shows ephemeral error to Dave only, no crash
- [ ] ENXIO (no reader on pipe) shows ephemeral error, buttons stay active
- [ ] `claude-slack --continue` and other claude args pass through correctly
- [ ] All unit + integration tests pass
