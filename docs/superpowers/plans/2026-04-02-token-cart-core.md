# Token Cart Core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the quadratic-cost full-history replay with a Haiku-powered Token Cart that compacts context between turns, reducing token consumption by ~57%+ on 10-turn threads.

**Architecture:** A `HaikuTokenCart` class encapsulates pre-call enrichment and post-call compaction using Haiku 4.5. The `active_sessions` dict changes from a message list to a structured handoff store. `handle_project_message` wires pre/post calls around the agent invocation. `ProjectAgent.handle` accepts enriched context (string) instead of raw history (list).

**Tech Stack:** Python 3.13, Anthropic SDK (Haiku 4.5), pytest, unittest.mock

---

### Task 1: Create HaikuTokenCart class

**Files:**
- Create: `tools/token_cart.py`
- Test: `tests/test_token_cart.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_token_cart.py
"""Tests for tools/token_cart.py — all Anthropic calls mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tools.token_cart import HaikuTokenCart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_anthropic(text: str):
    """Return a mock Anthropic class whose .messages.create() returns `text`."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ---------------------------------------------------------------------------
# pre_call tests
# ---------------------------------------------------------------------------

def test_pre_call_first_turn_no_handoff():
    """First turn — no handoff exists. Returns prompt as-is."""
    cart = HaikuTokenCart.__new__(HaikuTokenCart)
    cart._client = MagicMock()
    result = cart.pre_call(handoff=None, prompt="explain the auth system")
    assert result == "explain the auth system"
    cart._client.messages.create.assert_not_called()


def test_pre_call_with_handoff_enriches():
    """With handoff — Haiku enriches context."""
    enriched = "Auth system uses OAuth2. User asked about token refresh."
    mock_cls = _mock_anthropic(enriched)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.pre_call(
        handoff="## Handoff\nAuth discussion ongoing",
        prompt="how does token refresh work?",
    )
    assert result == enriched
    cart._client.messages.create.assert_called_once()


def test_pre_call_with_handoff_includes_registry():
    """Registry sections are included in enrichment call."""
    enriched = "Use apiClient for all API calls."
    mock_cls = _mock_anthropic(enriched)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.pre_call(
        handoff="## Handoff\nAPI work",
        prompt="add a new endpoint",
        registry="## Shared Utilities\n- apiClient: lib/api.ts",
    )
    assert result == enriched
    call_kwargs = cart._client.messages.create.call_args[1]
    user_content = call_kwargs["messages"][0]["content"]
    assert "apiClient" in user_content


def test_pre_call_haiku_failure_falls_back_to_raw():
    """If Haiku fails, return handoff + prompt concatenated."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("API down")
    result = cart.pre_call(
        handoff="## Handoff\nPrior context here",
        prompt="next question",
    )
    assert "Prior context here" in result
    assert "next question" in result


# ---------------------------------------------------------------------------
# post_call tests
# ---------------------------------------------------------------------------

def test_post_call_first_turn_creates_handoff():
    """First turn — no prior handoff. Creates initial handoff + journal."""
    response_text = (
        "---HANDOFF---\n## Handoff Context\n**Task:** explain auth\n"
        "---JOURNAL---\nOperator asked about auth system."
    )
    mock_cls = _mock_anthropic(response_text)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.post_call(
        handoff=None,
        prompt="explain the auth system",
        response="The auth system uses OAuth2...",
    )
    assert "Handoff Context" in result["handoff"]
    assert "auth" in result["journal_draft"].lower()


def test_post_call_subsequent_turn_updates_handoff():
    """Second turn — has prior handoff. Updates it."""
    response_text = (
        "---HANDOFF---\n## Handoff Context\n**Task:** token refresh\n"
        "### Decisions Made\n- Use refresh tokens\n"
        "---JOURNAL---\nDiscussed token refresh mechanism."
    )
    mock_cls = _mock_anthropic(response_text)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.post_call(
        handoff="## Handoff Context\n**Task:** explain auth",
        prompt="how does token refresh work?",
        response="Token refresh uses rotating keys...",
    )
    assert "token refresh" in result["handoff"].lower()
    assert "journal_draft" in result


def test_post_call_haiku_failure_preserves_prior():
    """If Haiku fails post-call, return prior handoff unchanged."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("timeout")
    result = cart.post_call(
        handoff="## Prior handoff",
        prompt="question",
        response="answer",
    )
    assert result["handoff"] == "## Prior handoff"
    assert result["journal_draft"] == ""


def test_post_call_no_prior_handoff_failure_returns_empty():
    """First turn Haiku failure — returns empty handoff."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("timeout")
    result = cart.post_call(handoff=None, prompt="q", response="a")
    assert result["handoff"] == ""
    assert result["journal_draft"] == ""


# ---------------------------------------------------------------------------
# parse response tests
# ---------------------------------------------------------------------------

def test_parse_response_splits_sections():
    """Response with both markers splits correctly."""
    from tools.token_cart import _parse_cart_response
    text = "---HANDOFF---\nhandoff content here\n---JOURNAL---\njournal content here"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "handoff content here"
    assert journal == "journal content here"


def test_parse_response_handoff_only():
    """Response with only handoff marker."""
    from tools.token_cart import _parse_cart_response
    text = "---HANDOFF---\nhandoff only"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "handoff only"
    assert journal == ""


def test_parse_response_no_markers():
    """Response with no markers — treat entire text as handoff."""
    from tools.token_cart import _parse_cart_response
    text = "some raw text without markers"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "some raw text without markers"
    assert journal == ""
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_token_cart.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'tools.token_cart'`

- [ ] **Step 3: Write the HaikuTokenCart implementation**

```python
# tools/token_cart.py
"""
HaikuTokenCart — persistent context layer for Shellack.

Encapsulates pre-call enrichment and post-call compaction using Haiku 4.5.
Reduces token consumption by replacing full-history replay with structured
handoff documents that carry forward only what matters.
"""
from __future__ import annotations

import logging
from typing import Optional

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT = 10.0
_MAX_TOKENS = 2048

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

_PRE_CALL_SYSTEM = """You are a context enrichment agent. Given a conversation handoff and a new user prompt, produce a focused context injection for the reasoning model.

Rules:
- Surface ONLY context relevant to the new prompt
- If the handoff mentions topics unrelated to the new prompt, omit them
- Preserve all file paths, error messages, and user-stated constraints verbatim
- Do not infer, expand, or editorialize
- Do not add suggestions or opinions
- Output the enriched context as a concise markdown block
- If a registry is provided, include relevant entries that the reasoning model should know about"""

_POST_CALL_SYSTEM = """You are a conversation compaction agent. Given the previous handoff (if any), the user's prompt, and the model's response, produce TWO sections separated by markers.

Output format (you MUST use these exact markers):
---HANDOFF---
## Handoff Context
**Turn:** {increment from previous or 1 if first}
**Task:** {one-line summary of what the user is working on}

### Decisions Made
- {bullet list — only confirmed decisions, not suggestions}

### Current State
{what's been done, what's pending, where we are}

### Critical Details
{anything the next turn MUST know — file paths, error messages, user-stated constraints}

### Open Questions
{unresolved items}

---JOURNAL---
{One paragraph: what was asked, what was done, what was learned this turn. Past tense, third person. Include specific details.}

Rules:
- Follow the template exactly
- Extract ONLY what was discussed — do not infer or expand
- If the user stated a constraint, include it verbatim
- Carry forward unresolved items from the previous handoff
- Drop items that have been resolved in this turn
- Never drop file paths, error messages, or user-stated requirements
- If a decision was made, record it. If a suggestion was offered but not confirmed, do not record it as a decision"""


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_cart_response(text: str) -> tuple[str, str]:
    """Split a post-call response into (handoff, journal_draft)."""
    handoff = ""
    journal = ""

    if "---HANDOFF---" in text:
        parts = text.split("---HANDOFF---", 1)[1]
        if "---JOURNAL---" in parts:
            handoff, journal = parts.split("---JOURNAL---", 1)
        else:
            handoff = parts
    else:
        # No markers — treat entire text as handoff
        handoff = text

    return handoff.strip(), journal.strip()


# ---------------------------------------------------------------------------
# HaikuTokenCart
# ---------------------------------------------------------------------------

class HaikuTokenCart:
    """Haiku-powered context compaction layer.

    Pre-call: enriches context for the reasoning model.
    Post-call: compacts the turn into a structured handoff + journal draft.
    """

    def __init__(self, model: str = _MODEL) -> None:
        self._client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(_TIMEOUT)),
            max_retries=1,
        )
        self._model = model

    def pre_call(
        self,
        handoff: Optional[str],
        prompt: str,
        registry: Optional[str] = None,
    ) -> str:
        """Enrich context for the reasoning model.

        First turn (no handoff): returns prompt as-is.
        Subsequent turns: Haiku surfaces relevant context from handoff.
        """
        if not handoff:
            return prompt

        user_content = f"## Previous Handoff\n{handoff}\n\n## New Prompt\n{prompt}"
        if registry:
            user_content += f"\n\n## Project Registry\n{registry}"

        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_PRE_CALL_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            enriched = msg.content[0].text.strip()
            if enriched:
                return enriched
        except Exception as exc:
            logger.warning(f"Token cart pre-call failed: {exc}")

        # Fallback: concatenate raw handoff + prompt
        return f"{handoff}\n\n{prompt}"

    def post_call(
        self,
        handoff: Optional[str],
        prompt: str,
        response: str,
    ) -> dict:
        """Compact the turn into a structured handoff + journal draft.

        Returns: {"handoff": str, "journal_draft": str}
        """
        user_content = ""
        if handoff:
            user_content += f"## Previous Handoff\n{handoff}\n\n"
        user_content += f"## User Prompt\n{prompt}\n\n## Model Response\n{response}"

        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_POST_CALL_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            text = msg.content[0].text.strip()
            h, j = _parse_cart_response(text)
            return {"handoff": h, "journal_draft": j}
        except Exception as exc:
            logger.warning(f"Token cart post-call failed: {exc}")

        # Fallback: preserve prior handoff
        return {"handoff": handoff or "", "journal_draft": ""}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `venv/bin/pytest tests/test_token_cart.py -v`
Expected: all 11 tests PASS

- [ ] **Step 5: Commit**

```bash
git add tools/token_cart.py tests/test_token_cart.py
git commit -m "feat: add HaikuTokenCart — pre-call enrichment + post-call compaction"
```

---

### Task 2: Restructure active_sessions

**Files:**
- Modify: `bot_unified.py:55,153-155,170,198`
- Test: `tests/test_bot_run_trigger.py` (update existing assertions)

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_bot_run_trigger.py at the end

def test_active_sessions_uses_handoff_structure():
    """active_sessions stores handoff dict, not message list."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, \
         patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False):

        event = _make_event("<@BOT> explain auth", ts="300.0")
        bot_unified.handle_mention(event, say=MagicMock())

    # After routing, session should exist
    # (handle_project_message is mocked, so it won't populate, but
    # we verify the structure is initialized correctly in the real path)
```

- [ ] **Step 2: Modify active_sessions initialization in bot_unified.py**

Change line 55 from:
```python
active_sessions: Dict[str, list] = {}
```
to:
```python
active_sessions: Dict[str, dict] = {}
```

Change lines 153-155 from:
```python
if thread_ts not in active_sessions:
    active_sessions[thread_ts] = []
context = list(active_sessions[thread_ts])
```
to:
```python
if thread_ts not in active_sessions:
    active_sessions[thread_ts] = {
        "handoff": None,
        "journal_draft": "",
        "turn_count": 0,
        "project_key": project_key,
    }
session = active_sessions[thread_ts]
```

Remove line 170:
```python
active_sessions[thread_ts].append({"role": "user", "content": prompt})
```

Remove line 198:
```python
active_sessions[thread_ts].append({"role": "assistant", "content": response})
```

- [ ] **Step 3: Run existing tests to check what breaks**

Run: `venv/bin/pytest tests/ -v --tb=short 2>&1 | tail -30`
Expected: Some tests may reference old `active_sessions` structure — fix them.

- [ ] **Step 4: Fix any broken tests**

Update any test that references `active_sessions` as a list to use the new dict structure.

- [ ] **Step 5: Run full test suite**

Run: `venv/bin/pytest -q`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add bot_unified.py tests/
git commit -m "refactor: change active_sessions from message list to handoff dict"
```

---

### Task 3: Wire Token Cart into handle_project_message

**Files:**
- Modify: `bot_unified.py:129-213`
- Modify: `agents/project_agent.py:197-260`
- Test: `tests/test_token_cart_integration.py` (create)

- [ ] **Step 1: Write integration tests**

```python
# tests/test_token_cart_integration.py
"""Integration tests: Token Cart wired into handle_project_message."""
from unittest.mock import MagicMock, patch
import pytest


def _make_event(text, channel="C123", ts="100.0", thread_ts=None):
    event = {"text": text, "channel": channel, "ts": ts, "user": "U_USER"}
    if thread_ts:
        event["thread_ts"] = thread_ts
    return event


def test_first_turn_skips_pre_call_runs_post_call():
    """First turn: no pre-call enrichment, but post-call compaction runs."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha"}}

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "explain auth"
    mock_cart.post_call.return_value = {"handoff": "## Handoff", "journal_draft": "Entry"}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False), \
         patch.dict(bot_unified.CHANNEL_ROUTING, fake_routing, clear=True), \
         patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), \
         patch("bot_unified.token_cart", mock_cart), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.ThinkingIndicator") as MockIndicator, \
         patch("bot_unified.app") as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("Auth uses OAuth2", "Alpha")
        mock_factory.get_agent.return_value = mock_agent

        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> explain auth", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    # Post-call should have been called
    mock_cart.post_call.assert_called_once()
    # Session should have the handoff
    assert bot_unified.active_sessions["100.0"]["handoff"] == "## Handoff"
    assert bot_unified.active_sessions["100.0"]["journal_draft"] == "Entry"


def test_second_turn_uses_pre_call_enrichment():
    """Second turn: pre-call enriches with prior handoff."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    # Pre-seed session with existing handoff
    bot_unified.active_sessions["99.0"] = {
        "handoff": "## Prior handoff content",
        "journal_draft": "Prior journal",
        "turn_count": 1,
        "project_key": "alpha",
    }

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha"}}

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "enriched context about auth"
    mock_cart.post_call.return_value = {"handoff": "## Updated", "journal_draft": "Updated entry"}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False), \
         patch.dict(bot_unified.CHANNEL_ROUTING, fake_routing, clear=True), \
         patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), \
         patch("bot_unified.token_cart", mock_cart), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.ThinkingIndicator") as MockIndicator, \
         patch("bot_unified.app") as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("Token refresh uses rotating keys", "Alpha")
        mock_factory.get_agent.return_value = mock_agent

        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> how does token refresh work?", ts="100.0", thread_ts="99.0")
        bot_unified.handle_mention(event, say=MagicMock())

    # Pre-call should have been called with prior handoff
    mock_cart.pre_call.assert_called_once()
    pre_call_args = mock_cart.pre_call.call_args
    assert pre_call_args[1]["handoff"] == "## Prior handoff content"

    # Agent should receive enriched context string, not raw history
    agent_call = mock_factory.get_agent.return_value.handle
    agent_call.assert_called_once()
    call_args = agent_call.call_args
    assert call_args[0][1] == "enriched context about auth"  # thread_context is now a string


def test_token_cart_failure_does_not_block_agent():
    """If token cart fails entirely, agent still runs."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha"}}

    mock_cart = MagicMock()
    mock_cart.pre_call.side_effect = Exception("cart exploded")
    mock_cart.post_call.side_effect = Exception("cart exploded again")

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False), \
         patch.dict(bot_unified.CHANNEL_ROUTING, fake_routing, clear=True), \
         patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), \
         patch("bot_unified.token_cart", mock_cart), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.ThinkingIndicator") as MockIndicator, \
         patch("bot_unified.app") as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("response here", "Alpha")
        mock_factory.get_agent.return_value = mock_agent

        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> do something", channel="C123")
        # Should NOT raise — agent still runs
        bot_unified.handle_mention(event, say=MagicMock())

    mock_factory.get_agent.return_value.handle.assert_called_once()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_token_cart_integration.py -v`
Expected: FAIL — `token_cart` not wired into `bot_unified` yet

- [ ] **Step 3: Modify bot_unified.py to wire Token Cart**

Add import at top:
```python
from tools.token_cart import HaikuTokenCart
```

Add module-level instance (near line 55):
```python
token_cart = HaikuTokenCart()
```

Rewrite `handle_project_message` context handling (lines 153-198):

Replace the old context/session lines with:
```python
    # Initialize session
    if thread_ts not in active_sessions:
        active_sessions[thread_ts] = {
            "handoff": None,
            "journal_draft": "",
            "turn_count": 0,
            "project_key": project_key,
        }
    session = active_sessions[thread_ts]

    # Pre-call: enrich context via Token Cart
    try:
        enriched_context = token_cart.pre_call(
            handoff=session["handoff"],
            prompt=prompt,
        )
    except Exception as exc:
        logger.warning(f"Token cart pre-call failed: {exc}")
        enriched_context = prompt
```

After the agent call and response formatting, add post-call:
```python
    # Post-call: compact via Token Cart (async-safe, non-blocking)
    try:
        cart_result = token_cart.post_call(
            handoff=session["handoff"],
            prompt=prompt,
            response=response,
        )
        session["handoff"] = cart_result["handoff"]
        session["journal_draft"] = cart_result["journal_draft"]
        session["turn_count"] += 1
    except Exception as exc:
        logger.warning(f"Token cart post-call failed: {exc}")
```

- [ ] **Step 4: Modify ProjectAgent.handle to accept enriched context**

Change `thread_context` parameter from `list` to `str | list | None`:

In `agents/project_agent.py`, change lines 242-253:
```python
            else:
                label = self.project["name"]
                full_prompt = prompt
                if thread_context:
                    if isinstance(thread_context, str):
                        # Enriched context from Token Cart
                        full_prompt = f"{thread_context}\n\nUser: {prompt}"
                    else:
                        # Legacy list format (backward compatible)
                        history = "\n".join(
                            f"{m['role'].title()}: {m['content']}" for m in thread_context
                        )
                        full_prompt = f"{history}\n\nUser: {prompt}"
```

Also update `agents/sub_agents.py` `BaseSubAgent.run` with the same dual handling.

- [ ] **Step 5: Update handle_project_message agent call**

Change the agent call to pass enriched_context instead of raw context:
```python
        response, agent_label = agent.handle(prompt, enriched_context, model=model)
```

- [ ] **Step 6: Run tests**

Run: `venv/bin/pytest tests/test_token_cart_integration.py tests/test_token_cart.py tests/test_project_agent.py -v`
Expected: All PASS

- [ ] **Step 7: Run full test suite**

Run: `venv/bin/pytest -q`
Expected: All tests PASS (263+ tests)

- [ ] **Step 8: Commit**

```bash
git add bot_unified.py agents/project_agent.py agents/sub_agents.py tests/test_token_cart_integration.py
git commit -m "feat: wire Token Cart into handle_project_message — pre/post Haiku enrichment"
```

---

### Task 4: Update orchestrator_config.py for features config

**Files:**
- Modify: `orchestrator_config.py:26-29,81-82`
- Modify: `projects.example.yaml`
- Test: `tests/test_config_loader.py` (add tests)

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_config_loader.py

def test_features_config_loaded(tmp_path):
    """projects.yaml with features block loads into project config."""
    yaml_content = """
github_org: test-org
projects:
  alpha:
    name: Alpha
    primary_channel: alpha-dev
    language: python
    platform: server
    github_repo: test-org/Alpha
    path: /tmp/alpha
    features:
      token-cart: true
      gut-check: true
      agent-manager: false
"""
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(yaml_content)
    from orchestrator_config import load_config
    cfg = load_config(str(config_file))
    assert cfg["PROJECTS"]["alpha"]["features"]["token-cart"] is True
    assert cfg["PROJECTS"]["alpha"]["features"]["agent-manager"] is False


def test_team_config_loaded(tmp_path):
    """projects.yaml with team block loads into project config."""
    yaml_content = """
github_org: test-org
projects:
  alpha:
    name: Alpha
    primary_channel: alpha-dev
    language: python
    platform: server
    github_repo: test-org/Alpha
    path: /tmp/alpha
    team:
      primary: opus-4-6
      token-cart: haiku-4-5
"""
    config_file = tmp_path / "projects.yaml"
    config_file.write_text(yaml_content)
    from orchestrator_config import load_config
    cfg = load_config(str(config_file))
    assert cfg["PROJECTS"]["alpha"]["team"]["primary"] == "opus-4-6"


def test_missing_features_defaults_to_empty():
    """Project without features block gets empty dict."""
    import importlib
    import orchestrator_config
    importlib.reload(orchestrator_config)
    from orchestrator_config import PROJECTS
    for key, proj in PROJECTS.items():
        # features should exist (possibly empty) but never KeyError
        features = proj.get("features", {})
        assert isinstance(features, dict)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_config_loader.py::test_features_config_loaded -v`
Expected: FAIL — features not loaded

- [ ] **Step 3: Add features and team loading to orchestrator_config.py**

In `_build_projects()`, after the context loading (around line 82):
```python
        if "features" in proj:
            projects[key]["features"] = proj["features"]
        else:
            projects[key]["features"] = {}
        if "team" in proj:
            projects[key]["team"] = proj["team"]
        else:
            projects[key]["team"] = {}
```

Add to `_KNOWN_TOP_LEVEL_KEYS`:
```python
_KNOWN_TOP_LEVEL_KEYS = {
    "github_org", "projects", "channels", "standards",
    "orchestrator_commands", "peer_review",
}
```
(No change needed — `features` and `team` are per-project, not top-level)

- [ ] **Step 4: Update projects.example.yaml with features and team examples**

Add a commented section to projects.example.yaml showing the features config.

- [ ] **Step 5: Run tests**

Run: `venv/bin/pytest tests/test_config_loader.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add orchestrator_config.py projects.example.yaml tests/test_config_loader.py
git commit -m "feat: load features and team config from projects.yaml"
```

---

### Task 5: Feature gate Token Cart calls

**Files:**
- Modify: `bot_unified.py`
- Test: `tests/test_token_cart_integration.py` (add test)

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_token_cart_integration.py

def test_token_cart_disabled_skips_haiku_calls():
    """When token-cart feature is disabled, no Haiku calls are made."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {
        "name": "Alpha",
        "path": "/tmp/alpha",
        "features": {"token-cart": False},
    }}

    mock_cart = MagicMock()

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False), \
         patch.dict(bot_unified.CHANNEL_ROUTING, fake_routing, clear=True), \
         patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), \
         patch("bot_unified.token_cart", mock_cart), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.ThinkingIndicator") as MockIndicator, \
         patch("bot_unified.app") as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("response", "Alpha")
        mock_factory.get_agent.return_value = mock_agent
        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> do stuff", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    # Token cart should NOT have been called
    mock_cart.pre_call.assert_not_called()
    mock_cart.post_call.assert_not_called()
```

- [ ] **Step 2: Add feature gate to handle_project_message**

In `handle_project_message`, wrap token cart calls with feature check:
```python
    use_token_cart = project.get("features", {}).get("token-cart", True)

    if use_token_cart:
        try:
            enriched_context = token_cart.pre_call(handoff=session["handoff"], prompt=prompt)
        except Exception as exc:
            logger.warning(f"Token cart pre-call failed: {exc}")
            enriched_context = prompt
    else:
        enriched_context = prompt
```

And for post-call:
```python
    if use_token_cart:
        try:
            cart_result = token_cart.post_call(...)
            ...
        except Exception:
            ...
```

- [ ] **Step 3: Run tests**

Run: `venv/bin/pytest tests/test_token_cart_integration.py -v`
Expected: All PASS

- [ ] **Step 4: Run full test suite**

Run: `venv/bin/pytest -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot_unified.py tests/test_token_cart_integration.py
git commit -m "feat: feature-gate Token Cart — disabled projects skip Haiku calls"
```
