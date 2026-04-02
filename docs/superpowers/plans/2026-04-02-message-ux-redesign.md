# Message UX Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Separate thinking from answers — agent responses use `[think]/[reply]` tags, reasoning renders as a collapsible block, the answer posts as a clean separate message.

**Architecture:** New `response_parser.py` parses tags. `ThinkingIndicator.done()` shows only the Churned header + think block. `bot_unified.py` posts `[reply]` as separate message(s) with code-fence-safe splitting at 3500 chars. System prompt updated to mandate tags.

**Tech Stack:** Python 3.13, Slack SDK, pytest, unittest.mock

---

### Task 1: Create response parser

**Files:**
- Create: `tools/response_parser.py`
- Create: `tests/test_response_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_response_parser.py
"""Tests for tools/response_parser.py — tag parsing."""
from tools.response_parser import parse_response, ParsedResponse


def test_reply_only():
    """[reply] tag only — think is empty."""
    result = parse_response("[reply] Here is the answer.")
    assert result.think == ""
    assert result.reply == "Here is the answer."
    assert result.actions == []


def test_think_and_reply():
    """Both tags present."""
    text = "[think] Let me check the files.\nFound 3 modules.\n\n[reply] The auth uses OAuth2."
    result = parse_response(text)
    assert "check the files" in result.think
    assert "Found 3 modules" in result.think
    assert result.reply == "The auth uses OAuth2."


def test_no_tags_fallback():
    """No tags at all — entire text is reply (backward compatible)."""
    result = parse_response("Just a plain response with no tags.")
    assert result.think == ""
    assert result.reply == "Just a plain response with no tags."


def test_think_only_no_reply():
    """[think] only, no [reply] — reply is empty."""
    result = parse_response("[think] Reasoning about the problem.")
    assert "Reasoning" in result.think
    assert result.reply == ""


def test_action_tags():
    """[action] lines are collected."""
    text = "[action] Reading files...\n[action] Running tests...\n[reply] All tests pass."
    result = parse_response(text)
    assert len(result.actions) == 2
    assert "Reading files" in result.actions[0]
    assert "Running tests" in result.actions[1]
    assert result.reply == "All tests pass."


def test_multiline_reply():
    """Reply content spans multiple lines."""
    text = "[think] Quick check.\n[reply] Line one.\n\nLine two.\n\nLine three."
    result = parse_response(text)
    assert result.think == "Quick check."
    assert "Line one." in result.reply
    assert "Line three." in result.reply


def test_tags_case_insensitive():
    """Tags work regardless of case."""
    result = parse_response("[THINK] reasoning\n[REPLY] answer")
    assert result.think == "reasoning"
    assert result.reply == "answer"


def test_tags_with_leading_whitespace():
    """Tags with spaces before them still parse."""
    result = parse_response("  [think] reasoning\n  [reply] answer")
    assert result.think == "reasoning"
    assert result.reply == "answer"


def test_empty_string():
    """Empty input — empty result."""
    result = parse_response("")
    assert result.think == ""
    assert result.reply == ""
    assert result.actions == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_response_parser.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write the implementation**

```python
# tools/response_parser.py
"""Response parser — extracts [think]/[action]/[reply] tags from agent responses."""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class ParsedResponse:
    """Parsed agent response split by tags."""
    think: str = ""
    actions: list[str] = field(default_factory=list)
    reply: str = ""


_TAG_RE = re.compile(r"^\s*\[(think|action|reply)\]\s*", re.IGNORECASE | re.MULTILINE)


def parse_response(text: str) -> ParsedResponse:
    """Parse a tag-prefixed response into structured sections.

    Tags: [think], [action], [reply] — case insensitive, at start of line.
    If no tags found, entire text is treated as reply (backward compatible).
    """
    if not text or not text.strip():
        return ParsedResponse()

    # Find all tag positions
    matches = list(_TAG_RE.finditer(text))

    if not matches:
        return ParsedResponse(reply=text.strip())

    result = ParsedResponse()
    for i, match in enumerate(matches):
        tag = match.group(1).lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = text[start:end].strip()

        if tag == "think":
            result.think = content
        elif tag == "action":
            result.actions.append(content)
        elif tag == "reply":
            result.reply = content

    return result
```

- [ ] **Step 4: Run tests**

Run: `venv/bin/pytest tests/test_response_parser.py -v`
Expected: All 9 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/response_parser.py tests/test_response_parser.py
git commit -m "feat: add response parser — [think]/[action]/[reply] tag extraction"
```

---

### Task 2: Add message splitter

**Files:**
- Add to: `tools/response_parser.py`
- Add to: `tests/test_response_parser.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_response_parser.py

from tools.response_parser import split_message


def test_split_short_message():
    """Under limit — returns single chunk."""
    result = split_message("Short message.", max_chars=3500)
    assert result == ["Short message."]


def test_split_on_paragraph_boundary():
    """Splits on double newline when over limit."""
    para1 = "A" * 2000
    para2 = "B" * 2000
    text = f"{para1}\n\n{para2}"
    result = split_message(text, max_chars=3500)
    assert len(result) == 2
    assert result[0] == para1
    assert result[1] == para2


def test_split_preserves_code_fence():
    """Never splits inside a code fence."""
    code_block = "```python\n" + "x = 1\n" * 500 + "```"
    text = f"Before.\n\n{code_block}\n\nAfter."
    result = split_message(text, max_chars=3500)
    # Code block must be intact in one chunk
    for chunk in result:
        if "```python" in chunk:
            assert "```" in chunk[chunk.index("```python") + 1:]  # has closing fence


def test_split_long_paragraph_on_sentence():
    """Single paragraph over limit splits on sentence boundary."""
    sentences = ". ".join(["This is sentence " + str(i) for i in range(100)])
    result = split_message(sentences, max_chars=500)
    assert len(result) > 1
    # Each chunk should end at a sentence boundary (contains ". " or is last)
    for chunk in result[:-1]:
        assert chunk.rstrip().endswith(".")


def test_split_empty():
    """Empty string — returns empty list."""
    assert split_message("") == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `venv/bin/pytest tests/test_response_parser.py::test_split_short_message -v`
Expected: FAIL — `split_message` not defined

- [ ] **Step 3: Write the implementation**

```python
# Add to tools/response_parser.py

_CODE_FENCE_RE_FULL = re.compile(r"```[\s\S]*?```")


def split_message(text: str, max_chars: int = 3500) -> list[str]:
    """Split text into chunks safe for Slack posting.

    Rules:
    - Never split inside a fenced code block
    - Split on paragraph boundaries (\\n\\n) first
    - Fall back to sentence boundaries ('. ') for long paragraphs
    - Single code blocks exceeding max_chars are kept intact
    """
    if not text or not text.strip():
        return []

    text = text.strip()
    if len(text) <= max_chars:
        return [text]

    # Identify code fence ranges (protected — never split inside)
    protected = [(m.start(), m.end()) for m in _CODE_FENCE_RE_FULL.finditer(text)]

    def _in_fence(pos: int) -> bool:
        return any(s <= pos < e for s, e in protected)

    # Split on paragraph boundaries
    chunks = []
    current = ""

    for para in text.split("\n\n"):
        candidate = f"{current}\n\n{para}".strip() if current else para
        if len(candidate) <= max_chars:
            current = candidate
        elif not current:
            # Single paragraph exceeds limit — try sentence split
            if not _in_fence(text.index(para) if para in text else 0):
                chunks.extend(_split_on_sentences(para, max_chars))
            else:
                chunks.append(para)  # code block — keep intact
            current = ""
        else:
            chunks.append(current.strip())
            current = para

    if current.strip():
        chunks.append(current.strip())

    return chunks


def _split_on_sentences(text: str, max_chars: int) -> list[str]:
    """Split a paragraph on sentence boundaries."""
    sentences = re.split(r'(?<=\.)\s+', text)
    chunks = []
    current = ""
    for sent in sentences:
        candidate = f"{current} {sent}".strip() if current else sent
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                chunks.append(current)
            current = sent
    if current:
        chunks.append(current)
    return chunks
```

- [ ] **Step 4: Run tests**

Run: `venv/bin/pytest tests/test_response_parser.py -v`
Expected: All 14 PASS

- [ ] **Step 5: Commit**

```bash
git add tools/response_parser.py tests/test_response_parser.py
git commit -m "feat: add code-fence-safe message splitter for Slack char limit"
```

---

### Task 3: Update ThinkingIndicator

**Files:**
- Modify: `tools/thinking_indicator.py:39,118-157`
- Modify: `tests/test_thinking_indicator.py`

- [ ] **Step 1: Write the failing tests**

```python
# Add to tests/test_thinking_indicator.py

def test_done_with_think_block():
    """done() renders think block as collapsible code fence."""
    from tools.thinking_indicator import ThinkingIndicator
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.0"}
    indicator = ThinkingIndicator(client, "C123", "99.0")
    indicator._ts = "1.0"
    indicator._start = time.monotonic() - 5  # 5 seconds ago

    indicator.done(think_block="Let me check the files.\nFound 3 modules.", cost_summary="$0.01")

    call_kwargs = client.chat_update.call_args[1]
    body = call_kwargs["attachments"][0]["text"]
    assert "Churned for" in body
    assert "$0.01" in body
    assert "💭 Reasoning" in body
    assert "Let me check the files" in body
    assert "```" in body  # collapsible code fence


def test_done_without_think_block():
    """done() with no think block shows only churned header."""
    from tools.thinking_indicator import ThinkingIndicator
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.0"}
    indicator = ThinkingIndicator(client, "C123", "99.0")
    indicator._ts = "1.0"
    indicator._start = time.monotonic() - 5

    indicator.done(think_block="", cost_summary="$0.01")

    call_kwargs = client.chat_update.call_args[1]
    body = call_kwargs["attachments"][0]["text"]
    assert "Churned for" in body
    assert "💭" not in body


def test_update_interval_is_one_second():
    """_UPDATE_INTERVAL should be 1.0, not 5.0."""
    from tools.thinking_indicator import _UPDATE_INTERVAL
    assert _UPDATE_INTERVAL == 1.0
```

- [ ] **Step 2: Run tests to see what fails**

Run: `venv/bin/pytest tests/test_thinking_indicator.py -v`
Expected: Some failures due to old `done()` signature and 5s interval

- [ ] **Step 3: Modify thinking_indicator.py**

Change line 39:
```python
_UPDATE_INTERVAL = 1.0  # seconds between verb rotations
```

Change `done()` method (line 118-157):
```python
    def done(self, think_block: str = "", cost_summary: str = "") -> None:
        """Stop cycling and show churned summary + optional think block."""
        self._stop.set()
        if self._bg:
            self._bg.join(timeout=2.0)
        if not self._ts:
            return
        elapsed = time.monotonic() - self._start
        header = f"✻ Churned for {_fmt_elapsed(elapsed)}"
        if cost_summary:
            header += f" · {cost_summary}"

        if think_block:
            body = f"{header}\n\n💭 Reasoning\n```\n{think_block}\n```"
        else:
            body = header

        try:
            self._client.chat_update(
                channel=self._channel_id,
                ts=self._ts,
                text="",
                attachments=[{"color": _GRAY, "text": body, "fallback": header}],
            )
        except Exception as exc:
            logger.warning(f"ThinkingIndicator: done update failed: {exc}")
            try:
                self._client.chat_update(
                    channel=self._channel_id,
                    ts=self._ts,
                    text="",
                    attachments=[{"color": _GRAY, "text": header, "fallback": header}],
                )
            except Exception:
                pass
```

- [ ] **Step 4: Run tests**

Run: `venv/bin/pytest tests/test_thinking_indicator.py -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add tools/thinking_indicator.py tests/test_thinking_indicator.py
git commit -m "feat: ThinkingIndicator — 1s updates, done() renders collapsible think block"
```

---

### Task 4: Wire everything into bot_unified.py

**Files:**
- Modify: `bot_unified.py:343-360`
- Modify: `tests/test_token_cart_integration.py` (update existing tests)

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/test_token_cart_integration.py

def test_reply_posted_as_separate_message():
    """[reply] content is posted as a separate Slack message, not in the indicator."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha", "features": {"token-cart": False}}}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False), \
         patch.dict(bot_unified.CHANNEL_ROUTING, fake_routing, clear=True), \
         patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.ThinkingIndicator") as MockIndicator, \
         patch("bot_unified.app") as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("[think] Checking files.\n[reply] The answer is 42.", "Alpha")
        mock_factory.get_agent.return_value = mock_agent

        mock_indicator = MagicMock()
        MockIndicator.return_value = mock_indicator
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()
        mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "200.0"})

        event = {"text": "<@BOT> question", "channel": "C123", "ts": "100.0", "user": "U_USER"}
        bot_unified.handle_mention(event, say=MagicMock())

    # Indicator.done() should receive think block, NOT the full response
    mock_indicator.done.assert_called_once()
    done_kwargs = mock_indicator.done.call_args[1]
    assert "Checking files" in done_kwargs.get("think_block", "")

    # Reply should be posted as a separate message
    post_calls = mock_app.client.chat_postMessage.call_args_list
    reply_posted = any("The answer is 42" in str(c) for c in post_calls)
    assert reply_posted
```

- [ ] **Step 2: Modify bot_unified.py — replace step 9**

Replace lines ~343-354 (the current step 9 block):

```python
    # 9. Parse response tags and render
    from tools.response_parser import parse_response, split_message
    from tools.slack_session import _md_to_mrkdwn

    parsed = parse_response(response)

    # Cost string for the churned block
    cost_str = ""
    if project.get("features", {}).get("cost-observability", True) and session.get("cost"):
        last_turn = session["cost"].turns[-1] if session["cost"].turns else None
        if last_turn:
            cost_str = session["cost"].format_turn_summary(last_turn)

    # Stop indicator — gray block with churned header + collapsible think block
    indicator.done(think_block=parsed.think, cost_summary=cost_str)

    # Post [reply] as separate message(s)
    if parsed.reply:
        formatted_reply = _md_to_mrkdwn(parsed.reply)
        chunks = split_message(formatted_reply, max_chars=3500)
        for chunk in chunks:
            try:
                app.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=chunk,
                )
            except Exception:
                pass  # never crash on posting

    # 10. Remove :claude: reaction — we're done
```

- [ ] **Step 3: Fix any existing tests that call indicator.done(response=...)**

Search for `indicator.done(response=` in tests and update to the new signature.

- [ ] **Step 4: Run full test suite**

Run: `venv/bin/pytest -q`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add bot_unified.py tests/test_token_cart_integration.py
git commit -m "feat: wire tag parser — think in churned block, reply as separate message"
```

---

### Task 5: Update system prompt with tag instructions

**Files:**
- Modify: `agents/project_agent.py:156-168`
- Test: verify manually or with existing test

- [ ] **Step 1: Modify the system prompt**

In `agents/project_agent.py`, replace lines 156-168 (the reasoning format and formatting section):

```python
        role_text += (
            "\n\n**Response format:** Structure your response with tags:\n"
            "\n`[think]` Your reasoning — what you're checking, key observations, decisions. "
            "Shown in a collapsible block. Keep it concise. Skip if no reasoning needed.\n"
            "\n`[reply]` Your answer to the operator. This is the main response. "
            "Always include [reply]. Be direct and actionable.\n"
            "\nExample:\n"
            "[think] Checking auth/middleware.py — the session token handling looks outdated.\n"
            "[reply] The middleware at `auth/middleware.py:42` stores session tokens without "
            "the `SameSite` attribute. Here's the fix: ...\n"
            "\n**Formatting:** This response renders in Slack. Rules:\n"
            "- Wrap ALL code in triple-backtick fences with a language tag: "
            "```swift\\n...\\n``` or ```python\\n...\\n```\n"
            "- Always close every code block before continuing prose\n"
            "- Use `inline backticks` only for identifiers, file names, and short values\n"
            "\nBe concise."
        )
```

- [ ] **Step 2: Run tests**

Run: `venv/bin/pytest tests/test_project_agent.py -v`
Expected: All PASS

- [ ] **Step 3: Run full suite**

Run: `venv/bin/pytest -q`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add agents/project_agent.py
git commit -m "feat: update system prompt — mandate [think]/[reply] tag format"
```
