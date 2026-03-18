# Slack↔Terminal Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a named-pipe bridge so Dave can respond to Claude Code prompts via Slack Block Kit buttons on any device, instead of switching to the terminal.

**Architecture:** A `claude-slack` wrapper script creates a named pipe and a session file, then launches `claude` with the pipe as stdin. When Claude needs input, it posts a Block Kit message via Slack MCP; Dave clicks a button; the SlackClaw Bolt handler writes the answer to the pipe. Sessions are identified by UUID so concurrent sessions never cross-contaminate.

**Tech Stack:** Python 3.9+, Slack Bolt, `requests`, `fcntl`, `os` named pipes (POSIX), pytest + unittest.mock.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/slack_bridge.py` | Create | Block Kit formatter (`format_bridge_blocks`), project detector (`detect_channel_id`), session-start notifier (`post_session_start`) |
| `orchestrator_config.py` | Modify | Add `channel_id` field to every `CHANNEL_ROUTING` entry |
| `bot_unified.py` | Modify | Add `@app.action("claude_bridge_input")` handler; add `import json` |
| `CLAUDE.md` | Modify | Add Claude-Slack Bridge section so Claude Code knows to use Slack MCP when `CLAUDE_BRIDGE_SESSION` is set |
| `claude-slack` | Create | Wrapper script: session management, named pipe lifecycle, env export, subprocess launch |
| `SETUP_GUIDE.md` | Modify | Add installation + smoke-test steps |
| `tests/test_slack_bridge.py` | Create | Unit tests for `format_bridge_blocks`, `detect_channel_id`, `post_session_start` |
| `tests/test_claude_bridge_action.py` | Create | Integration tests for `handle_bridge_input` Bolt action |

---

## Task 1: `tools/slack_bridge.py` — Block Kit formatter and utilities

**Files:**
- Create: `tools/slack_bridge.py`
- Test: `tests/test_slack_bridge.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_slack_bridge.py`:

```python
import pytest
import sys
from unittest.mock import patch, MagicMock
import responses  # pip install responses


# ---------------------------------------------------------------------------
# format_bridge_blocks
# ---------------------------------------------------------------------------

def test_format_choice_returns_section_and_actions():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Which approach?", ["A", "B", "C"], "sess1")
    types = [b["type"] for b in blocks]
    assert "section" in types
    assert "actions" in types


def test_format_choice_button_values():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick one", ["X", "Y"], "abc")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    values = [btn["value"] for btn in actions_block["elements"]]
    assert "abc|X" in values
    assert "abc|Y" in values


def test_format_choice_action_ids():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick one", ["X", "Y"], "abc")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    for btn in actions_block["elements"]:
        assert btn["action_id"] == "claude_bridge_input"


def test_format_choice_splits_beyond_five_options():
    """6 options must produce two separate actions blocks (Slack limit is 5 per block)."""
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick", ["A", "B", "C", "D", "E", "F"], "s")
    actions_blocks = [b for b in blocks if b["type"] == "actions"]
    assert len(actions_blocks) == 2
    assert len(actions_blocks[0]["elements"]) == 5
    assert len(actions_blocks[1]["elements"]) == 1


def test_format_confirm_ignores_options():
    """input_type='confirm' always produces Yes/No regardless of options argument."""
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Are you sure?", ["Maybe", "Later"], "s", input_type="confirm")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    texts = [btn["text"]["text"] for btn in actions_block["elements"]]
    assert texts == ["Yes", "No"]


def test_format_confirm_button_values():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Confirm?", [], "s42", input_type="confirm")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    values = [btn["value"] for btn in actions_block["elements"]]
    assert "s42|yes" in values
    assert "s42|no" in values


# ---------------------------------------------------------------------------
# detect_channel_id
# ---------------------------------------------------------------------------

FAKE_PROJECTS = {
    "slackclaw": {
        "name": "SlackClaw",
        "primary_channel": "slackclaw-dev",
        "github_repo": "davesleal/SlackClaw",
    }
}

FAKE_ROUTING_OK = {
    "slackclaw-dev": {"mode": "dedicated", "channel_id": "C_SC"},
}

FAKE_ROUTING_MISSING = {
    "slackclaw-dev": {"mode": "dedicated"},  # no channel_id
}


def test_detect_known_repo_returns_channel_id():
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:davesleal/SlackClaw.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_OK):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C_SC"
    assert project_name == "SlackClaw"


def test_detect_unknown_repo_falls_back():
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:someone/other.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_OK):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "Unknown"


def test_detect_missing_channel_id_falls_back_with_warning(capsys):
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:davesleal/SlackClaw.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_MISSING):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "SlackClaw"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_detect_not_a_git_repo_falls_back():
    from tools.slack_bridge import detect_channel_id
    import subprocess
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "Unknown"


# ---------------------------------------------------------------------------
# post_session_start
# ---------------------------------------------------------------------------

@responses.activate
def test_post_session_start_success():
    import responses as rsps
    rsps.add(rsps.POST, "https://slack.com/api/chat.postMessage",
             json={"ok": True}, status=200)
    from tools.slack_bridge import post_session_start
    import os
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        post_session_start("C_SC", "SlackClaw")  # must not raise


@responses.activate
def test_post_session_start_logs_warning_on_slack_error(caplog):
    import responses as rsps, logging
    rsps.add(rsps.POST, "https://slack.com/api/chat.postMessage",
             json={"ok": False, "error": "channel_not_found"}, status=200)
    from tools.slack_bridge import post_session_start
    import os
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        with caplog.at_level(logging.WARNING):
            post_session_start("CBAD", "SlackClaw")
    assert "channel_not_found" in caplog.text
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/daveleal/Repos/SlackClaw && source venv/bin/activate
pip install responses  # if not already installed
pytest tests/test_slack_bridge.py -v 2>&1 | head -30
```

Expected: ImportError or ModuleNotFoundError for `tools.slack_bridge`.

- [ ] **Step 3: Implement `tools/slack_bridge.py`**

Create `tools/slack_bridge.py`:

```python
"""
SlackClaw — Slack↔Terminal Bridge utilities

Provides Block Kit formatting for interactive Claude Code input prompts,
project channel detection, and session-start notification.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys

import requests

from orchestrator_config import CHANNEL_ROUTING, PROJECTS

_FALLBACK_CHANNEL_ID = "C0AMEEP7EFL"  # #claude-code
_FALLBACK_PROJECT = "Unknown"

logger = logging.getLogger(__name__)


def format_bridge_blocks(
    question: str,
    options: list[str],
    session_id: str,
    input_type: str = "choice",
) -> list[dict]:
    """Return Block Kit blocks for a bridge input prompt.

    Each button's action_id is ``"claude_bridge_input"`` and its value is
    ``"{session_id}|{option_value}"``.  Options are split into rows of 5
    (Slack's limit per ``actions`` block).

    When ``input_type="confirm"``, ``options`` is ignored; the buttons are
    always "Yes" (value: "yes") and "No" (value: "no").
    When ``input_type="choice"``, each item in ``options`` becomes one button.
    """
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": question},
        }
    ]

    if input_type == "confirm":
        btn_options = [("Yes", "yes"), ("No", "no")]
    else:
        btn_options = [(opt, opt) for opt in options]

    # Split into rows of 5 (Slack limit per actions block)
    for i in range(0, max(len(btn_options), 1), 5):
        row = btn_options[i : i + 5]
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": label},
                        "value": f"{session_id}|{value}",
                        "action_id": "claude_bridge_input",
                    }
                    for label, value in row
                ],
            }
        )

    return blocks


def detect_channel_id() -> tuple[str, str]:
    """Return (channel_id, project_name) for the current git repo.

    Looks up the git remote URL, normalises it to ``owner/repo``, then
    matches against ``PROJECTS``.  Falls back to ``#claude-code`` for
    unknown repos or any error.  Logs a stderr warning when a project is
    recognised but its CHANNEL_ROUTING entry is missing ``channel_id``
    (misconfiguration that would cause silent wrong-channel routing).
    """
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        slug = re.sub(r"\.git$", "", remote)
        slug = re.sub(r"^git@github\.com:", "", slug)
        slug = re.sub(r"^https://github\.com/", "", slug)

        for _key, cfg in PROJECTS.items():
            if cfg.get("github_repo") == slug:
                primary = cfg.get("primary_channel", "")
                routing = CHANNEL_ROUTING.get(primary, {})
                channel_id = routing.get("channel_id", "")
                if channel_id:
                    return channel_id, cfg["name"]
                # Recognised project but channel_id not yet configured
                print(
                    f"[claude-slack] WARNING: project '{cfg['name']}' matched but "
                    f"CHANNEL_ROUTING['{primary}'] has no 'channel_id'. "
                    "Add channel_id to orchestrator_config.py. "
                    "Falling back to #claude-code.",
                    file=sys.stderr,
                )
                return _FALLBACK_CHANNEL_ID, cfg["name"]
    except Exception:
        pass
    return _FALLBACK_CHANNEL_ID, _FALLBACK_PROJECT


def post_session_start(channel_id: str, project_name: str) -> None:
    """Post a session-start message to Slack via direct API call.

    ``claude-slack`` is a standalone script with no Bolt App instance, so we
    call the Slack Web API directly.  Raises ``requests.HTTPError`` on HTTP
    failures.  Logs a warning (but does not raise) on Slack application-level
    errors (e.g. ``channel_not_found``).
    """
    import os
    token = os.environ["SLACK_BOT_TOKEN"]
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel": channel_id,
            "text": f"🟢 Claude Code session started — *{project_name}*",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        logger.warning("[claude-slack] post_session_start failed: %s", data.get("error"))
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_slack_bridge.py -v
```

Expected: 12 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/slack_bridge.py tests/test_slack_bridge.py
git commit -m "feat: add slack_bridge utility module with Block Kit formatter and project detector"
```

---

## Task 2: `orchestrator_config.py` — add `channel_id` to CHANNEL_ROUTING

**Files:**
- Modify: `orchestrator_config.py:79-113`

No new tests needed — this is pure data configuration. The lookup is already tested in Task 1.

- [ ] **Step 1: Look up the actual Slack channel IDs**

Run this in a Python shell (with venv active and `.env` loaded) or use the Slack MCP `slack_search_channels` tool to find each channel's ID:

```python
from slack_sdk import WebClient
import os
from dotenv import load_dotenv
load_dotenv()
client = WebClient(token=os.environ["SLACK_BOT_TOKEN"])
for name in ["dayist-dev", "nova-dev", "nudge-dev", "tiledock-dev",
             "atmos-dev", "sideplane-dev", "slackclaw-dev", "code-review"]:
    result = client.conversations_list(types="public_channel,private_channel", limit=200)
    channel = next((c for c in result["channels"] if c["name"] == name), None)
    if channel:
        print(f'"{name}": "{channel["id"]}",')
```

Note the IDs — you'll need them in the next step.

- [ ] **Step 2: Add `channel_id` to every CHANNEL_ROUTING entry**

In `orchestrator_config.py`, update `CHANNEL_ROUTING` to add `"channel_id"` to each entry. Replace the `C_PLACEHOLDER` values with the real IDs from Step 1:

```python
CHANNEL_ROUTING = {
    # iOS Project Channels
    "dayist-dev":   {"project": "dayist",     "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},
    "nova-dev":     {"project": "nova",        "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},
    "nudge-dev":    {"project": "nudge",       "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},

    # macOS Project Channels
    "tiledock-dev": {"project": "tiledock",    "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},
    "atmos-dev":    {"project": "atmosuniversal","mode": "dedicated",  "channel_id": "C_PLACEHOLDER"},
    "sideplane-dev":{"project": "sideplane",   "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},

    # Meta
    "slackclaw-dev":{"project": "slackclaw",   "mode": "dedicated",   "channel_id": "C_PLACEHOLDER"},

    # Special channels
    "slackclaw-central": {
        "mode": "orchestrator",
        "access": "all_projects",
        "channel_id": "C_PLACEHOLDER",
        "capabilities": [
            "update_claude_md",
            "set_global_rules",
            "cross_project_search",
            "coordinate_changes",
            "sync_standards"
        ]
    },

    "code-review": {
        "mode": "peer_review",
        "access": "all_projects",
        "channel_id": "C_PLACEHOLDER",
        "review_agents": ["code-quality", "security", "performance"],
        "approval_required": True,
        "auto_merge": False
    }
}
```

- [ ] **Step 3: Verify all tests still pass**

```bash
pytest tests/ -q
```

Expected: 12 passed (same as before — no new tests for config data).

- [ ] **Step 4: Commit**

```bash
git add orchestrator_config.py
git commit -m "feat: add channel_id to all CHANNEL_ROUTING entries for bridge project detection"
```

---

## Task 3: `bot_unified.py` — bridge action handler

**Files:**
- Modify: `bot_unified.py` (add `import json`, add action handler)
- Test: `tests/test_claude_bridge_action.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_claude_bridge_action.py`:

```python
"""
Tests for the claude_bridge_input Bolt action handler.

We test the handler logic directly — not through the full Bolt app stack —
by extracting it as a callable and passing mock ack/body/action/client args.
"""
import errno
import json
import os
import pytest
from unittest.mock import MagicMock, patch, call


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_handler():
    """Import the handler function after bot_unified is loaded."""
    # We import the module-level handler function, not the decorator.
    # The function is named handle_bridge_input in bot_unified.py.
    # We test it directly to avoid starting the full Bolt app.
    from bot_unified import handle_bridge_input
    return handle_bridge_input


def _body(channel="C1", user="U1", ts="123.456", value="sess1|AnswerA"):
    return {
        "channel": {"id": channel},
        "user": {"id": user},
        "message": {"ts": ts},
    }


def _action(value="sess1|AnswerA"):
    return {"value": value}


def _client():
    c = MagicMock()
    c.chat_postEphemeral = MagicMock()
    c.chat_update = MagicMock()
    return c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_handle_happy_path(tmp_path):
    """Pipe write succeeds → chat_update called with confirmation."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "test_pipe")
    os.mkfifo(pipe_path)
    # Open write-end to prevent ENXIO on the handler's open
    write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
    # Open read-end so we can read back what the handler writes
    read_fd = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)

    session_data = {"pipe": pipe_path}
    session_file = str(tmp_path / "sess1.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    body = _body(value="sess1|AnswerA")
    action = _action("sess1|AnswerA")

    with patch("bot_unified.open", create=True) as mock_open:
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.read = MagicMock(return_value=json.dumps(session_data))
        # Re-route the session file open to tmp_path
        real_open = open
        def patched_open(path, *args, **kwargs):
            if "claude_bridge" in path:
                return real_open(session_file, *args, **kwargs)
            return real_open(path, *args, **kwargs)
        with patch("builtins.open", side_effect=patched_open):
            handler(ack=ack, body=body, action=action, client=client)

    ack.assert_called_once()
    client.chat_update.assert_called_once()
    update_call = client.chat_update.call_args
    assert "✅" in update_call.kwargs.get("text", "") or "✅" in str(update_call)

    os.close(write_fd)
    os.close(read_fd)


def test_handle_malformed_value_is_ignored():
    """Values without '|' must be silently discarded after ack."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    handler(ack=ack, body=_body(), action={"value": "no-pipe-char"}, client=client)

    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
    client.chat_update.assert_not_called()


def test_handle_session_file_not_found(tmp_path):
    """Missing session file → ephemeral 'session expired' to user only."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in path:
            raise FileNotFoundError
        return open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        handler(ack=ack, body=_body(), action=_action("noexist|X"), client=client)

    ack.assert_called_once()
    client.chat_postEphemeral.assert_called_once()
    call_kwargs = client.chat_postEphemeral.call_args.kwargs
    assert call_kwargs["user"] == "U1"
    assert "expired" in call_kwargs["text"].lower()
    client.chat_update.assert_not_called()


def test_handle_pipe_enxio_shows_ephemeral_leaves_buttons(tmp_path):
    """ENXIO (no reader on pipe) → ephemeral error, chat_update NOT called."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "dead_pipe")
    os.mkfifo(pipe_path)
    session_data = {"pipe": pipe_path}
    session_file = str(tmp_path / "sess2.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in path:
            return open(session_file, *args, **kwargs)
        return open(path, *args, **kwargs)

    # Patch os.open to raise ENXIO (no reader)
    enxio = OSError(errno.ENXIO, "No such device or address")
    with patch("builtins.open", side_effect=patched_open), \
         patch("os.open", side_effect=enxio):
        handler(ack=ack, body=_body(), action=_action("sess2|X"), client=client)

    client.chat_postEphemeral.assert_called_once()
    client.chat_update.assert_not_called()


def test_handle_missing_message_ts_skips_chat_update(tmp_path):
    """When body has no 'message' key, pipe write succeeds but chat_update is skipped."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "pipe_nots")
    os.mkfifo(pipe_path)
    write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
    read_fd  = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)

    session_data = {"pipe": pipe_path}
    session_file = str(tmp_path / "sess3.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    body_no_ts = {"channel": {"id": "C1"}, "user": {"id": "U1"}}  # no "message" key

    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in path:
            return open(session_file, *args, **kwargs)
        return open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        handler(ack=ack, body=body_no_ts, action=_action("sess3|Y"), client=client)

    ack.assert_called_once()
    client.chat_update.assert_not_called()
    client.chat_postEphemeral.assert_not_called()

    os.close(write_fd)
    os.close(read_fd)


def test_handle_missing_channel_returns_early():
    """Body with no channel → early return, nothing posted."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    body_no_channel = {"user": {"id": "U1"}, "message": {"ts": "1.2"}}
    handler(ack=ack, body=body_no_channel, action=_action("s|X"), client=client)

    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
    client.chat_update.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_claude_bridge_action.py -v 2>&1 | head -20
```

Expected: ImportError (`cannot import name 'handle_bridge_input' from 'bot_unified'`).

- [ ] **Step 3: Add `import json` and the action handler to `bot_unified.py`**

Add `json` to the existing import block at the top of `bot_unified.py` (line 14, after `import os`):

```python
import json
```

Then add the handler after the existing handlers section (just before the `# STARTUP` section):

```python
# ============================================================================
# CLAUDE-SLACK BRIDGE HANDLER
# ============================================================================

@app.action("claude_bridge_input")
def handle_bridge_input(ack, body, action, client):
    """Handle button clicks from claude-slack Block Kit messages.

    Parses session_id and answer from the button value, writes the answer
    to the named pipe so Claude's stdin unblocks, then updates the Slack
    message to replace buttons with a confirmation.
    """
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
        return  # can't send ephemeral without both; already acked

    message_ts = body.get("message", {}).get("ts", "")
    # message_ts absent for modal/ephemeral actions — we still write to pipe
    # but skip the chat_update

    # Load session
    try:
        with open(session_file) as f:
            session = json.load(f)
    except FileNotFoundError:
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text="⚠️ Session expired — the terminal session may have ended.",
        )
        return
    except Exception as e:
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text=f"⚠️ Could not load session: {e}",
        )
        return

    # Write answer to named pipe
    pipe_path = session["pipe"]
    try:
        fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
        os.write(fd, (answer + "\n").encode())
        os.close(fd)
    except OSError as e:
        # ENXIO: no reader (claude-slack exited); EPIPE: broken pipe
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text=(
                f"⚠️ Could not reach terminal session — it may have exited. "
                f"({e.strerror})"
            ),
        )
        return  # leave buttons active so Dave can retry

    # Update message: replace buttons with confirmation
    if not message_ts:
        return
    client.chat_update(
        channel=channel,
        ts=message_ts,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *You chose:* {answer}"},
            }
        ],
        text=f"✅ You chose: {answer}",
    )
```

- [ ] **Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: all 28 + new tests pass. The bridge action tests that patch `builtins.open` and `os.open` may need minor fixture adjustments if the import path differs — fix by using the exact module path shown in the error (`bot_unified.open` vs `builtins.open`).

- [ ] **Step 5: Commit**

```bash
git add bot_unified.py tests/test_claude_bridge_action.py
git commit -m "feat: add claude_bridge_input Bolt action handler to bot_unified"
```

---

## Task 4: `CLAUDE.md` — add Claude-Slack Bridge instructions

**Files:**
- Modify: `CLAUDE.md`

No tests — this is instruction text consumed by Claude Code at session start.

- [ ] **Step 1: Append the bridge section to `CLAUDE.md`**

Add the following block at the end of `CLAUDE.md`:

```markdown
## Claude-Slack Bridge

When the environment variable `CLAUDE_BRIDGE_SESSION` is set (check with
Bash: `echo $CLAUDE_BRIDGE_SESSION`), you are running inside a Slack bridge
session. In this mode:

1. When you need input from Dave, use the Slack MCP (`slack_send_message`) to
   post to the channel ID in `$CLAUDE_BRIDGE_CHANNEL_ID`
2. Format the message using Block Kit with interactive buttons:
   - `action_id`: `claude_bridge_input`
   - `value`: `{CLAUDE_BRIDGE_SESSION}|{option_value}`
3. Then wait — Dave will click a button and the answer will arrive via stdin
   automatically
4. Do NOT ask for input via terminal (it will not be seen)

Helper: `tools/slack_bridge.py::format_bridge_blocks(question, options, session_id)`
returns the correct Block Kit JSON ready to pass to `slack_send_message`.
```

- [ ] **Step 2: Verify CLAUDE.md renders correctly**

```bash
grep -n "Claude-Slack Bridge" CLAUDE.md
```

Expected: line number printed showing the section header was added.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add Claude-Slack Bridge section to CLAUDE.md"
```

---

## Task 5: `claude-slack` wrapper script

**Files:**
- Create: `claude-slack` (repo root, executable)

No unit tests for the script itself — the underlying utilities (`detect_channel_id`, `post_session_start`, `format_bridge_blocks`) are already tested in Task 1. The script is validated by smoke test in Task 6.

- [ ] **Step 1: Create `claude-slack`**

Create `/Users/daveleal/Repos/SlackClaw/claude-slack`:

```python
#!/usr/bin/env python3
"""
claude-slack — Slack↔Terminal bridge wrapper for Claude Code.

Drop-in replacement for `claude`. Creates a named pipe session, exports
CLAUDE_BRIDGE_SESSION and CLAUDE_BRIDGE_CHANNEL_ID, and launches `claude`
with the pipe as stdin so Slack button clicks feed answers back automatically.
"""

from __future__ import annotations

import atexit
import fcntl
import json
import os
import signal
import subprocess
import sys
import uuid

# Add SlackClaw repo to path so orchestrator_config and tools are importable
sys.path.insert(0, "/Users/daveleal/Repos/SlackClaw")

from tools.slack_bridge import detect_channel_id, post_session_start

# ---------------------------------------------------------------------------
# Session setup
# ---------------------------------------------------------------------------

proc_handle = None  # initialised before signal handlers so SIGTERM is safe

session_id = str(uuid.uuid4())
session_dir = "/tmp/claude_bridge"
pipe_path = os.path.join(session_dir, session_id)
session_file = os.path.join(session_dir, f"{session_id}.json")

os.makedirs(session_dir, exist_ok=True)
os.mkfifo(pipe_path)

# Open write-end first (O_NONBLOCK) to unblock the read-end open below
write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
# Open read-end (O_NONBLOCK); succeeds immediately because write-end is open
read_fd = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)
# Clear O_NONBLOCK from read-end so subprocess stdin blocks normally
_flags = fcntl.fcntl(read_fd, fcntl.F_GETFL)
fcntl.fcntl(read_fd, fcntl.F_SETFL, _flags & ~os.O_NONBLOCK)

channel_id, project_name = detect_channel_id()

with open(session_file, "w") as f:
    json.dump(
        {"pipe": pipe_path, "channel_id": channel_id, "project_name": project_name},
        f,
    )

# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup() -> None:
    try:
        os.close(write_fd)
    except Exception:
        pass
    # read_fd ownership transferred to os.fdopen() → do not close by fd number
    for path in [pipe_path, session_file]:
        try:
            os.unlink(path)
        except Exception:
            pass


atexit.register(cleanup)


def _sigterm_handler(*_) -> None:
    # Forward SIGTERM to claude subprocess so it can save state, then clean up
    if proc_handle is not None:
        try:
            proc_handle.send_signal(signal.SIGTERM)
        except Exception:
            pass
    cleanup()
    sys.exit(0)


signal.signal(signal.SIGTERM, _sigterm_handler)

# ---------------------------------------------------------------------------
# Announce session to Slack
# ---------------------------------------------------------------------------

try:
    post_session_start(channel_id, project_name)
except Exception as e:
    print(f"[claude-slack] Could not post session-start to Slack: {e}", file=sys.stderr)

# ---------------------------------------------------------------------------
# Launch claude
# ---------------------------------------------------------------------------

env = os.environ.copy()
env["CLAUDE_BRIDGE_SESSION"] = session_id
env["CLAUDE_BRIDGE_CHANNEL_ID"] = channel_id

# os.fdopen transfers fd ownership; Popen dup2s it to stdin (fd 0).
# O_CLOEXEC is absent by default on macOS so write_fd is also inherited —
# this is intentional (write_fd in the child is the keep-alive copy).
proc_handle = subprocess.Popen(
    ["claude"] + sys.argv[1:],
    stdin=os.fdopen(read_fd, "rb"),
    env=env,
)
proc_handle.wait()
sys.exit(proc_handle.returncode)
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x /Users/daveleal/Repos/SlackClaw/claude-slack
```

- [ ] **Step 3: Symlink to `/usr/local/bin`**

```bash
ln -sf "$(pwd)/claude-slack" /usr/local/bin/claude-slack
```

- [ ] **Step 4: Commit**

```bash
git add claude-slack
git commit -m "feat: add claude-slack wrapper script for Slack terminal bridge"
```

---

## Task 6: Smoke test + `SETUP_GUIDE.md` installation steps

**Files:**
- Modify: `SETUP_GUIDE.md`

- [ ] **Step 1: Smoke test — session file created**

In a terminal, from a project directory with a configured `channel_id`:

```bash
CLAUDE_BRIDGE_TEST=1 /Users/daveleal/Repos/SlackClaw/claude-slack --version 2>&1 | head -5
ls /tmp/claude_bridge/
```

Expected: session JSON file appears, then disappears after process exits.

- [ ] **Step 2: Smoke test — fallback channel**

From `/tmp` (not a git repo):

```bash
cd /tmp && claude-slack --version 2>&1 | head -3
```

Expected: `[claude-slack] WARNING` NOT printed (unknown repo falls back silently to `#claude-code`). Session start message posted to `#claude-code`.

- [ ] **Step 3: Smoke test — end-to-end button click**

1. From `/Users/daveleal/Repos/SlackClaw`, run `claude-slack`
2. In a Claude session, run: `echo $CLAUDE_BRIDGE_SESSION`
3. Confirm non-empty UUID is printed
4. Use Slack MCP to post a Block Kit message with `format_bridge_blocks`
5. Click a button in Slack
6. Confirm the answer arrives in the Claude session's stdin

- [ ] **Step 4: Add installation section to `SETUP_GUIDE.md`**

Add the following after the existing Step 6 in `SETUP_GUIDE.md`:

```markdown
## Step 7: Install claude-slack Bridge (Optional)

The `claude-slack` script lets you respond to Claude Code prompts via Slack
buttons on any device, instead of switching to the terminal.

### Install

```bash
cd /Users/daveleal/Repos/SlackClaw
chmod +x claude-slack
ln -sf "$(pwd)/claude-slack" /usr/local/bin/claude-slack
```

### Usage — drop-in replacement for `claude`

```bash
claude-slack               # start new session
claude-slack --continue    # resume last session
claude-slack -p "do X"    # non-interactive prompt
```

### How it works

1. `claude-slack` detects the current project from the git remote URL and
   routes the session to the correct `#project-dev` channel.
2. A 🟢 session-start message is posted to that channel.
3. When Claude Code needs input, post a Block Kit message using
   `tools/slack_bridge.py::format_bridge_blocks` via the Slack MCP.
4. Dave clicks a button on any device → the answer feeds back to Claude's stdin.

### Prerequisite

`CHANNEL_ROUTING` in `orchestrator_config.py` must have `channel_id` filled
in for every project's `primary_channel` entry. Run Task 2 of the bridge
implementation plan if this hasn't been done yet.

### Smoke test

```bash
# From SlackClaw repo root:
claude-slack --version
# Expected: 🟢 session-start appears in #slackclaw-dev, script exits cleanly.
```
```

- [ ] **Step 5: Run full test suite one final time**

```bash
source venv/bin/activate && pytest tests/ -v
```

Expected: all tests pass.

- [ ] **Step 6: Final commit**

```bash
git add SETUP_GUIDE.md
git commit -m "docs: add claude-slack bridge installation and smoke test steps to SETUP_GUIDE"
```

---

## Verification Checklist (from spec)

After all tasks complete, verify:

- [ ] `claude-slack` in SlackClaw repo posts session-start to `#slackclaw-dev`
- [ ] `claude-slack` outside any known repo falls back to `#claude-code` silently
- [ ] Block Kit message appears with correct buttons when `format_bridge_blocks` is called
- [ ] Clicking a button feeds the answer to Claude's stdin
- [ ] Clicked message updates to show selection; buttons replaced with confirmation text
- [ ] Two concurrent `claude-slack` sessions route independently with no cross-contamination
- [ ] Stale button click (session ended) shows ephemeral error to Dave only, no crash
- [ ] ENXIO (no reader on pipe) shows ephemeral error, buttons stay active
- [ ] `claude-slack --continue` and other claude args pass through correctly
- [ ] All tests pass (`pytest tests/ -v`)
