# Slack Terminal Tunnel — Phase 2: Config & Onboarding

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add live config commands (`set mode/model`, `usage`, `config`), first-run onboarding via Block Kit buttons, and usage tracking persisted to `usage.json`.

**Architecture:** `UsageTracker` handles file-backed monthly-reset counters. `ConfigWriter` handles atomic `.env` updates that take effect immediately via `os.environ`. Config commands are dispatched from `handle_mention` before existing routing. Onboarding is posted once on startup to `#slackclaw-dev` via Block Kit buttons; each button is handled by its own `@app.action` handler.

**Tech Stack:** Python 3.9+, Slack Bolt (sync/threading), `json`, `re`, `threading.Lock`, Block Kit

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `tools/usage_tracker.py` | Create | `UsageTracker`: file-backed monthly counters, format helpers |
| `tools/config_writer.py` | Create | `set_env_var`: update `.env` + `os.environ` live |
| `bot_unified.py` | Modify | `usage_tracker` instance, config commands, onboarding flow, usage integration |
| `tests/test_usage_tracker.py` | Create | `UsageTracker` unit tests |
| `tests/test_config_writer.py` | Create | `set_env_var` unit tests |
| `tests/test_bot_config_commands.py` | Create | Config command integration tests |
| `tests/test_onboarding.py` | Create | Onboarding flow tests |
| `.env.example` | Modify | Document `SESSION_BACKEND`, `SESSION_MODEL`, `ONBOARDING_COMPLETE` |

---

## Task 1: `UsageTracker`

**Files:**
- Create: `tools/usage_tracker.py`
- Create: `tests/test_usage_tracker.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_usage_tracker.py
import json
import os
import pytest


def test_record_session_increments_count(tmp_path):
    from tools.usage_tracker import UsageTracker
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("api", "claude-sonnet-4-6")
    assert tracker.get_stats()["session_count"] == 1


def test_record_mention_increments_count(tmp_path):
    from tools.usage_tracker import UsageTracker
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_mention("api", "claude-sonnet-4-6")
    assert tracker.get_stats()["mention_count"] == 1


def test_api_session_accumulates_tokens_and_cost(tmp_path):
    from tools.usage_tracker import UsageTracker
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("api", "claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=100_000)
    stats = tracker.get_stats()
    assert stats["tokens_in"] == 1_000_000
    assert stats["tokens_out"] == 100_000
    # sonnet: $3/Mtok in, $15/Mtok out → $3.00 + $1.50 = $4.50
    assert abs(stats["estimated_cost"] - 4.50) < 0.01


def test_max_session_does_not_record_tokens(tmp_path):
    from tools.usage_tracker import UsageTracker
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("max", "claude-sonnet-4-6", tokens_in=500_000, tokens_out=50_000)
    stats = tracker.get_stats()
    assert stats["tokens_in"] == 0
    assert stats["estimated_cost"] == 0.0


def test_monthly_reset_on_stale_month(tmp_path):
    from tools.usage_tracker import UsageTracker
    path = str(tmp_path / "usage.json")
    # Write stale state from previous month
    stale = {
        "reset_month": "2020-01",
        "session_count": 99,
        "mention_count": 50,
        "tokens_in": 1000,
        "tokens_out": 500,
        "estimated_cost": 5.0,
        "mode": "api",
        "model": "claude-sonnet-4-6",
    }
    with open(path, "w") as f:
        json.dump(stale, f)
    tracker = UsageTracker(path=path)
    stats = tracker.get_stats()
    assert stats["session_count"] == 0
    assert stats["tokens_in"] == 0
    assert stats["estimated_cost"] == 0.0


def test_format_usage_message_api_mode(tmp_path, monkeypatch):
    from tools.usage_tracker import UsageTracker
    monkeypatch.setenv("SESSION_BACKEND", "api")
    monkeypatch.setenv("SESSION_MODEL", "claude-sonnet-4-6")
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("api", "claude-sonnet-4-6", tokens_in=500_000, tokens_out=100_000)
    msg = tracker.format_usage_message()
    assert "Anthropic API" in msg
    assert "claude-sonnet-4-6" in msg
    assert "500,000" in msg


def test_format_usage_message_max_mode(tmp_path, monkeypatch):
    from tools.usage_tracker import UsageTracker
    monkeypatch.setenv("SESSION_BACKEND", "max")
    monkeypatch.setenv("SESSION_MODEL", "claude-sonnet-4-6")
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("max", "claude-sonnet-4-6")
    msg = tracker.format_usage_message()
    assert "Claude Max" in msg
    assert "$0.00" in msg
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /Users/daveleal/Repos/Shellack
source venv/bin/activate
pytest tests/test_usage_tracker.py -v 2>&1 | head -15
```

Expected: `ModuleNotFoundError` — `usage_tracker` doesn't exist yet.

- [ ] **Step 3: Implement `UsageTracker`**

```python
# tools/usage_tracker.py
"""
UsageTracker — tracks Shellack session/mention counts and API token usage.

Persists to usage.json in the Shellack root. Monthly reset: on every read,
compare the stored reset_month to the current month — if different, zero all
counters and update reset_month. No cron required.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict

_DEFAULT_STATE: Dict[str, Any] = {
    "reset_month": "",
    "session_count": 0,
    "mention_count": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "estimated_cost": 0.0,
    "mode": "api",
    "model": "claude-sonnet-4-6",
}

# Cost per million tokens: (input_price, output_price)
_MODEL_PRICING: Dict[str, tuple] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}

USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "usage.json")


class UsageTracker:
    def __init__(self, path: str = USAGE_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _current_month(self) -> str:
        return datetime.now().strftime("%Y-%m")

    def _load(self) -> Dict[str, Any]:
        """Load state from file, applying a monthly reset if needed."""
        try:
            with open(self._path) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            state = dict(_DEFAULT_STATE)

        if state.get("reset_month") != self._current_month():
            state = dict(_DEFAULT_STATE)
            state["reset_month"] = self._current_month()

        return state

    def _save(self, state: Dict[str, Any]) -> None:
        with open(self._path, "w") as f:
            json.dump(state, f, indent=2)

    def record_session(
        self, mode: str, model: str, tokens_in: int = 0, tokens_out: int = 0
    ) -> None:
        """Increment session count; add tokens/cost for API mode only."""
        with self._lock:
            state = self._load()
            state["session_count"] += 1
            state["mode"] = mode
            state["model"] = model
            if mode == "api" and (tokens_in or tokens_out):
                state["tokens_in"] += tokens_in
                state["tokens_out"] += tokens_out
                pricing = _MODEL_PRICING.get(model, (3.0, 15.0))
                cost = (tokens_in / 1_000_000 * pricing[0]) + (
                    tokens_out / 1_000_000 * pricing[1]
                )
                state["estimated_cost"] = round(state["estimated_cost"] + cost, 4)
            self._save(state)

    def record_mention(self, mode: str, model: str) -> None:
        """Increment quick-reply mention count."""
        with self._lock:
            state = self._load()
            state["mention_count"] += 1
            state["mode"] = mode
            state["model"] = model
            self._save(state)

    def get_stats(self) -> Dict[str, Any]:
        """Return current stats, applying monthly reset if needed."""
        with self._lock:
            return self._load()

    def format_usage_message(self) -> str:
        """Return a formatted Slack message string for @Shellack usage.

        Mode and model are read from os.environ (live values) so the display
        always reflects current config, even right after a monthly reset.
        """
        stats = self.get_stats()
        # Use live env values for mode/model — file values may lag after reset
        mode = os.environ.get("SESSION_BACKEND", stats.get("mode", "api"))
        model = os.environ.get("SESSION_MODEL", stats.get("model", "claude-sonnet-4-6"))
        month = stats.get("reset_month") or self._current_month()
        try:
            month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        except ValueError:
            month_label = month

        lines = [
            f"🦞 *Shellack — Usage ({month_label})*",
            f"Mode: {'Claude Max' if mode == 'max' else 'Anthropic API'}",
        ]
        if mode == "api":
            lines.append(f"Model: `{model}`")
        else:
            lines.append("Model: Subscription")
        lines += [
            f"Sessions: {stats['session_count']} run: sessions started",
            f"Quick replies: {stats['mention_count']} @mentions",
        ]
        if mode == "api":
            lines += [
                f"Tokens in: {stats['tokens_in']:,}",
                f"Tokens out: {stats['tokens_out']:,}",
                f"Est. cost: ~${stats['estimated_cost']:.2f}",
            ]
        else:
            lines.append("API cost: $0.00 ✓")
        return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_usage_tracker.py -v
```

Expected: all 7 tests pass.

- [ ] **Step 5: Commit**

```bash
git add tools/usage_tracker.py tests/test_usage_tracker.py
git commit -m "feat: add UsageTracker with monthly-reset file persistence"
```

---

## Task 2: `ConfigWriter` + Config Commands

**Files:**
- Create: `tools/config_writer.py`
- Create: `tests/test_config_writer.py`
- Modify: `bot_unified.py` — add `usage_tracker` instance, `_handle_config_command`, call from `handle_mention`
- Create: `tests/test_bot_config_commands.py`

- [ ] **Step 1: Write the failing tests for `config_writer`**

```python
# tests/test_config_writer.py
import os
import pytest


def test_set_env_var_writes_new_key(tmp_path):
    from tools.config_writer import set_env_var
    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=value\n")
    set_env_var("NEW_KEY", "new_val", env_path=str(env_file))
    assert "NEW_KEY=new_val" in env_file.read_text()
    assert os.environ.get("NEW_KEY") == "new_val"


def test_set_env_var_replaces_existing_key(tmp_path):
    from tools.config_writer import set_env_var
    env_file = tmp_path / ".env"
    env_file.write_text("SESSION_BACKEND=api\n")
    set_env_var("SESSION_BACKEND", "max", env_path=str(env_file))
    content = env_file.read_text()
    assert content.count("SESSION_BACKEND") == 1
    assert "SESSION_BACKEND=max" in content


def test_set_env_var_creates_file_if_missing(tmp_path):
    from tools.config_writer import set_env_var
    env_file = tmp_path / ".env"
    set_env_var("FRESH_KEY", "fresh_val", env_path=str(env_file))
    assert "FRESH_KEY=fresh_val" in env_file.read_text()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_config_writer.py -v 2>&1 | head -10
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement `config_writer`**

```python
# tools/config_writer.py
"""Write or update KEY=VALUE in .env without requiring a bot restart."""
from __future__ import annotations

import os
import re

_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def set_env_var(key: str, value: str, env_path: str = _ENV_PATH) -> None:
    """Write or update KEY=VALUE in the .env file, then update os.environ."""
    try:
        with open(env_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    replaced = False
    new_lines = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    os.environ[key] = value
```

- [ ] **Step 4: Run config_writer tests to verify they pass**

```bash
pytest tests/test_config_writer.py -v
```

Expected: all 3 tests pass.

- [ ] **Step 5: Write failing tests for config commands in bot**

```python
# tests/test_bot_config_commands.py
"""Tests for @Shellack set mode, set model, usage, config commands."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def _make_say():
    return MagicMock()


def _make_event(text, ts="100.0", thread_ts=None):
    e = {"text": text, "channel": "C123", "ts": ts}
    if thread_ts:
        e["thread_ts"] = thread_ts
    return e


def test_set_mode_max_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set mode max")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "max")
    say.assert_called_once()
    assert "max" in say.call_args[1]["text"].lower()


def test_set_mode_api_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set mode api")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_BACKEND", "api")


def test_set_model_sonnet_updates_env():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.set_env_var") as mock_set, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> set model sonnet")
        bot_unified.handle_mention(event, say=say)
    mock_set.assert_called_once_with("SESSION_MODEL", "claude-sonnet-4-6")


def test_usage_command_posts_stats():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch.object(bot_unified.usage_tracker, "format_usage_message", return_value="stats"), \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"):
        event = _make_event("<@BOT> usage")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "stats" in say.call_args[1]["text"]


def test_config_command_posts_settings():
    import bot_unified
    importlib.reload(bot_unified)
    say = _make_say()
    with patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):
        event = _make_event("<@BOT> config")
        bot_unified.handle_mention(event, say=say)
    say.assert_called_once()
    assert "api" in say.call_args[1]["text"].lower()
```

- [ ] **Step 6: Run bot config tests to verify they fail**

```bash
pytest tests/test_bot_config_commands.py -v 2>&1 | head -15
```

Expected: `AttributeError: module 'bot_unified' has no attribute 'usage_tracker'`.

- [ ] **Step 7: Add config commands to `bot_unified.py`**

At the top of `bot_unified.py`, add new imports after the existing ones:

```python
from tools.usage_tracker import UsageTracker
from tools.config_writer import set_env_var
```

After the `RUN_SESSIONS: dict = {}` line, add:

```python
# Usage tracking — persists to usage.json, monthly auto-reset
usage_tracker = UsageTracker()
```

Add this helper function before `handle_mention`:

```python
def _handle_config_command(clean_text: str, say, thread_ts: str) -> bool:
    """Handle config commands. Returns True if the command was consumed."""
    lower = clean_text.lower()

    # set mode max|api
    if lower.startswith("set mode "):
        mode = lower[9:].strip()
        if mode in ("max", "api"):
            set_env_var("SESSION_BACKEND", mode)
            say(text=f"✅ Mode set to `{mode}`. No restart required.", thread_ts=thread_ts)
        else:
            say(text="Usage: `@Shellack set mode max|api`", thread_ts=thread_ts)
        return True

    # set model opus|sonnet|haiku
    if lower.startswith("set model "):
        alias = lower[10:].strip()
        model_map = {
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        }
        model = model_map.get(alias)
        if model:
            set_env_var("SESSION_MODEL", model)
            say(text=f"✅ Model set to `{model}`.", thread_ts=thread_ts)
        else:
            say(text="Usage: `@Shellack set model opus|sonnet|haiku`", thread_ts=thread_ts)
        return True

    # usage
    if lower == "usage":
        say(text=usage_tracker.format_usage_message(), thread_ts=thread_ts)
        return True

    # config
    if lower == "config":
        mode = os.environ.get("SESSION_BACKEND", "api")
        model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        onboarding = os.environ.get("ONBOARDING_COMPLETE", "false")
        lines = [
            "🦞 *Shellack — Config*",
            f"Backend: `{mode}`",
            f"Model: `{model}`",
            f"Onboarding: {'complete ✓' if onboarding == 'true' else 'pending'}",
        ]
        say(text="\n".join(lines), thread_ts=thread_ts)
        return True

    return False
```

In `handle_mention`, insert this block **immediately after** the line `clean_text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()` and **before** the `is_top_level = (thread_ts == ts)` line:

```python
    # --- config commands (any channel, any context) ---
    if _handle_config_command(clean_text, say, thread_ts):
        return

    # --- run: session trigger (top-level mentions only) ---
    is_top_level = (thread_ts == ts)
```

Remove the existing `is_top_level = (thread_ts == ts)` line since it is now included above.

- [ ] **Step 8: Run all config tests to verify they pass**

```bash
pytest tests/test_bot_config_commands.py tests/test_config_writer.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 9: Run full test suite**

```bash
pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
git add tools/config_writer.py bot_unified.py \
        tests/test_config_writer.py tests/test_bot_config_commands.py
git commit -m "feat: add config commands (set mode/model, usage, config)"
```

---

## Task 3: Onboarding Flow

**Files:**
- Modify: `bot_unified.py` — `check_and_post_onboarding()`, `@app.action("onboarding_mode_select")`, `@app.action("onboarding_model_select")`, call from startup
- Create: `tests/test_onboarding.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_onboarding.py
"""Tests for first-run onboarding flow."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def test_onboarding_skipped_when_complete():
    """check_and_post_onboarding does nothing when ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    with patch.dict("os.environ", {"ONBOARDING_COMPLETE": "true"}), \
         patch.object(bot_unified.app, "client") as mock_client:
        bot_unified.check_and_post_onboarding()
    mock_client.chat_postMessage.assert_not_called()


def test_onboarding_posts_buttons_when_not_complete():
    """check_and_post_onboarding posts Block Kit buttons when flag is absent."""
    import bot_unified
    importlib.reload(bot_unified)
    mock_channel_list = {
        "channels": [{"id": "C999", "name": "slackclaw-dev"}]
    }
    # Use patch.dict to ensure ONBOARDING_COMPLETE is absent from the environment
    env_without_flag = {k: v for k, v in __import__("os").environ.items() if k != "ONBOARDING_COMPLETE"}
    with patch.dict("os.environ", env_without_flag, clear=True), \
         patch.object(bot_unified.app.client, "conversations_list", return_value=mock_channel_list), \
         patch.object(bot_unified.app.client, "chat_postMessage") as mock_post:
        bot_unified.check_and_post_onboarding()
    mock_post.assert_called_once()
    call_kwargs = mock_post.call_args[1]
    assert call_kwargs["channel"] == "C999"
    assert "blocks" in call_kwargs


def test_mode_select_max_completes_onboarding():
    """Clicking Max button sets SESSION_BACKEND=max and ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    ack = MagicMock()
    body = {"message": {"ts": "123.0"}, "channel": {"id": "C999"}}
    action = {"value": "max"}
    client = MagicMock()
    with patch("bot_unified.set_env_var") as mock_set:
        bot_unified.handle_onboarding_mode_select(ack, body, action, client)
    ack.assert_called_once()
    calls = {c[0][0]: c[0][1] for c in mock_set.call_args_list}
    assert calls.get("SESSION_BACKEND") == "max"
    assert calls.get("ONBOARDING_COMPLETE") == "true"


def test_model_select_completes_api_onboarding():
    """Clicking a model button sets SESSION_MODEL and ONBOARDING_COMPLETE=true."""
    import bot_unified
    importlib.reload(bot_unified)
    ack = MagicMock()
    body = {"message": {"ts": "123.0"}, "channel": {"id": "C999"}}
    action = {"value": "claude-sonnet-4-6"}
    client = MagicMock()
    with patch("bot_unified.set_env_var") as mock_set:
        bot_unified.handle_onboarding_model_select(ack, body, action, client)
    ack.assert_called_once()
    calls = {c[0][0]: c[0][1] for c in mock_set.call_args_list}
    assert calls.get("SESSION_MODEL") == "claude-sonnet-4-6"
    assert calls.get("ONBOARDING_COMPLETE") == "true"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_onboarding.py -v 2>&1 | head -15
```

Expected: `AttributeError` — `check_and_post_onboarding` not defined.

- [ ] **Step 3: Add onboarding to `bot_unified.py`**

Add the following function before the startup block (`if __name__ == "__main__":`):

```python
def check_and_post_onboarding() -> None:
    """Post onboarding message to #slackclaw-dev if not already complete."""
    if os.environ.get("ONBOARDING_COMPLETE") == "true":
        return

    # Find the slackclaw-dev channel ID
    channel_id = None
    try:
        result = app.client.conversations_list(types="public_channel,private_channel", limit=200)
        for ch in result.get("channels", []):
            if ch["name"] == "slackclaw-dev":
                channel_id = ch["id"]
                break
    except Exception as e:
        print(f"⚠️  Could not list channels for onboarding: {e}")
        return

    if not channel_id:
        print("⚠️  Could not find #slackclaw-dev for onboarding. Skipping.")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👋 *Welcome to Shellack!* Let's get you set up.\n\n"
                    "How would you like to power AI sessions?"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⚡ Claude Max subscription"},
                    "action_id": "onboarding_mode_select",
                    "value": "max",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔑 Anthropic API key"},
                    "action_id": "onboarding_mode_select",
                    "value": "api",
                },
            ],
        },
    ]
    try:
        app.client.chat_postMessage(
            channel=channel_id,
            text="👋 Welcome to Shellack! Choose your AI backend.",
            blocks=blocks,
        )
        print("📋 Onboarding message posted to #slackclaw-dev")
    except Exception as e:
        print(f"⚠️  Could not post onboarding: {e}")


@app.action("onboarding_mode_select")
def handle_onboarding_mode_select(ack, body, action, client):
    """Handle Max vs API mode selection during onboarding."""
    ack()
    mode = action.get("value", "api")
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")

    if mode == "max":
        set_env_var("SESSION_BACKEND", "max")
        set_env_var("ONBOARDING_COMPLETE", "true")
        text = (
            "✅ *Mode set to Claude Max.* All AI calls will use your Max subscription.\n\n"
            "Change anytime: `@Shellack set mode api`"
        )
        if channel and message_ts:
            client.chat_update(channel=channel, ts=message_ts, text=text, blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": text}}
            ])
    else:
        # API mode: ask for model selection
        set_env_var("SESSION_BACKEND", "api")
        model_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Which model would you like to use?"},
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Opus 4.6 · ~$15/Mtok"},
                        "action_id": "onboarding_model_select",
                        "value": "claude-opus-4-6",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Sonnet 4.6 ✓ recommended · ~$3/Mtok"},
                        "action_id": "onboarding_model_select",
                        "value": "claude-sonnet-4-6",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Haiku 4.5 · ~$0.25/Mtok"},
                        "action_id": "onboarding_model_select",
                        "value": "claude-haiku-4-5-20251001",
                    },
                ],
            },
        ]
        if channel and message_ts:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                text="Which model would you like to use?",
                blocks=model_blocks,
            )


@app.action("onboarding_model_select")
def handle_onboarding_model_select(ack, body, action, client):
    """Handle model selection during API mode onboarding."""
    ack()
    model = action.get("value", "claude-sonnet-4-6")
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")

    set_env_var("SESSION_MODEL", model)
    set_env_var("ONBOARDING_COMPLETE", "true")
    text = (
        f"✅ *Model set to `{model}`.* Ready to go!\n\n"
        "Change anytime: `@Shellack set model opus|sonnet|haiku`"
    )
    if channel and message_ts:
        client.chat_update(channel=channel, ts=message_ts, text=text, blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": text}}
        ])
```

In the `if __name__ == "__main__":` startup block, add this line **after** `handler = SocketModeHandler(...)` and **before** `handler.start()`:

```python
    # Post onboarding if first run
    check_and_post_onboarding()
```

- [ ] **Step 4: Run onboarding tests**

```bash
pytest tests/test_onboarding.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 5: Run full suite**

```bash
pytest tests/ --tb=short 2>&1 | tail -5
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add bot_unified.py tests/test_onboarding.py
git commit -m "feat: add onboarding flow with Block Kit mode/model selection"
```

---

## Task 4: Usage Integration + `.env.example`

Wire `usage_tracker` into session completion and quick replies. Update `.env.example` with Phase 2 variables.

**Note on token counts:** The spec mentions posting a cost summary at session end (API mode). Token count tracking from `APIBackend` requires `stream.get_final_message().usage` and additional `SlackSession` plumbing — this is deferred to a future patch. Phase 2 records `session_count`/`mention_count` correctly; cost tracking will be added once the backend exposes usage data.

**Files:**
- Modify: `bot_unified.py` — call `usage_tracker` in `on_close` callback and `handle_project_message`
- Modify: `.env.example` — document new vars
- Create: `tests/test_usage_integration.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_usage_integration.py
"""Tests that usage_tracker is called at the right integration points."""
import importlib
import pytest
from unittest.mock import MagicMock, patch


def test_run_session_close_records_session():
    """When a run: session closes, usage_tracker.record_session is called."""
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.get_channel_name", return_value="dayist-dev"), \
         patch.object(bot_unified.usage_tracker, "record_session") as mock_record, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):

        event = {"text": "<@BOT> run: do the thing", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_mention(event, say=MagicMock())

        # Simulate session close by calling the on_close callback
        on_close_fn = bot_unified.SlackSession.call_args[1]["on_close"]
        on_close_fn()

    mock_record.assert_called_once_with(
        "api", "claude-sonnet-4-6"
    )


def test_project_message_records_mention():
    """handle_project_message calls usage_tracker.record_mention."""
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.agent_factory") as mock_factory, \
         patch.object(bot_unified.usage_tracker, "record_mention") as mock_record, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):
        mock_factory.get_agent.return_value.handle_message.return_value = "done"
        event = {"text": "hello", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

    mock_record.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_usage_integration.py -v 2>&1 | head -15
```

Expected: tests fail because `record_session` / `record_mention` are not called yet.

- [ ] **Step 3: Wire usage tracking in `bot_unified.py`**

In `handle_mention`, update the `on_close` lambda inside the `run:` session creation block. Replace:

```python
        on_close=lambda: RUN_SESSIONS.pop(thread_ts, None),
```

With a proper closure that records usage:

```python
        def _on_run_close(
            _mode=os.environ.get("SESSION_BACKEND", "api"),
            _model=os.environ.get("SESSION_MODEL", "claude-sonnet-4-6"),
            _ts=thread_ts,
        ):
            usage_tracker.record_session(_mode, _model)
            RUN_SESSIONS.pop(_ts, None)

        session = SlackSession(
            thread_ts=thread_ts,
            channel_id=channel_id,
            client=app.client,
            backend=backend,
            on_close=_on_run_close,
        )
```

In `handle_project_message`, add this call at the end of the function (after the agent response is posted):

```python
    # Track mention
    usage_tracker.record_mention(
        os.environ.get("SESSION_BACKEND", "api"),
        os.environ.get("SESSION_MODEL", "claude-sonnet-4-6"),
    )
```

Read `handle_project_message` first to find the right location — add it after the successful response is posted, inside the main try block if one exists, or at the end of the function body.

- [ ] **Step 4: Run usage integration tests**

```bash
pytest tests/test_usage_integration.py -v
```

Expected: both tests pass.

- [ ] **Step 5: Update `.env.example`**

Add these lines to `.env.example` after the `ANTHROPIC_API_KEY` section:

```
# Slack Terminal Tunnel (Phase 2)
# Backend: "max" = Claude Max subscription (zero API cost), "api" = Anthropic API
SESSION_BACKEND=api
# Model used in API mode (ignored in max mode)
SESSION_MODEL=claude-sonnet-4-6
# Set to "true" after onboarding completes — bot sets this automatically
ONBOARDING_COMPLETE=false
```

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -v --tb=short 2>&1 | tail -10
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add bot_unified.py .env.example tests/test_usage_integration.py
git commit -m "feat: integrate usage tracking into sessions and mentions"
```

---

## Phase 2 Complete

```bash
pytest tests/ 2>&1 | tail -3
```

All tests green. Phase 3 (plugin management) is the next plan.
