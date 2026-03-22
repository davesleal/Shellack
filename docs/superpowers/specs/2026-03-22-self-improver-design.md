# Self-Improver Design

**Goal:** When an agent task is blocked and recovers, automatically extract the lesson learned and append it to the project's `CLAUDE.md`. Notify the operator in the Slack thread after the update is written — no approval required.

**Architecture:** A single `tools/self_improver.py` module with one public function. Called at the end of `ProjectAgent.handle()` when a block signal is detected in the response. Uses Haiku to reflect on the block and generate a one-sentence rule. Writes the rule to `CLAUDE.md` and returns it so the caller can post a Slack notification.

**Tech Stack:** Python, Anthropic SDK (Haiku for reflection), file I/O on project `CLAUDE.md`.

---

## Data Flow

```
ProjectAgent.handle(prompt) completes
      │
      ▼
reflect_and_update(prompt, response, project_path)
      │
      ▼
_detect_block(response)
  ├── None → return None (no block, no update)
  └── (block_excerpt, resolution_excerpt)
        │
        ▼
      _reflect(prompt, block_excerpt, resolution_excerpt)
        │ {"rule": "...", "section": "Watch Out For|Patterns|General"}
        ▼
      _append_to_claude_md(project_path, rule, section)
        │
        ▼
      return rule string
            │
            ▼ (in ProjectAgent.handle)
      _lifecycle._post_thread(
        f"📝 Learned something — updated CLAUDE.md:\n_{rule}_"
      )
```

---

## Components

### New: `tools/self_improver.py`

```python
from __future__ import annotations
import json
import logging
import re
from pathlib import Path

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_HAIKU = "claude-haiku-4-5-20251001"  # Claude Haiku 4.5 — correct model ID

# Patterns that indicate the agent hit a block and recovered
_BLOCK_SIGNALS = [
    r"error:",
    r"exception",
    r"traceback",
    r"couldn'?t",
    r"failed",
    r"retrying",
    r"instead,?\s+I\b",    # "instead, I tried..." (uppercase I + word boundary avoids "instead, if/it/is")
    r"however,",
    r"unfortunately",
    r"let me try",
    r"alternative",
]
_BLOCK_RE = re.compile("|".join(_BLOCK_SIGNALS), re.IGNORECASE)

# Minimum matches required to consider a response "blocked"
# Prevents single casual uses of signal words (e.g. "couldn't find a better name") from triggering
_MIN_BLOCK_SIGNALS = 2

_VALID_SECTIONS = {"Watch Out For", "Patterns", "General"}

_REFLECT_PROMPT = """A developer agent was blocked during a task and recovered. Extract one actionable rule to add to CLAUDE.md so this block doesn't happen again.

Reply with JSON only, no prose:
{{"rule": "one sentence, imperative, specific", "section": "Watch Out For|Patterns|General"}}

- Watch Out For: pitfalls, things that break, anti-patterns
- Patterns: preferred approaches, conventions to follow
- General: anything else worth knowing

Original task: {prompt}
What blocked the agent: {block_excerpt}
How it was resolved: {resolution_excerpt}"""


def reflect_and_update(
    prompt: str,
    response: str,
    project_path: str,
) -> str | None:
    """Detect block in response, reflect, update CLAUDE.md. Returns rule or None."""
    result = _detect_block(response)
    if result is None:
        return None

    block_excerpt, resolution_excerpt = result

    rule_data = _reflect(prompt, block_excerpt, resolution_excerpt)
    if rule_data is None:
        return None

    rule = rule_data["rule"]
    section = rule_data["section"]

    try:
        _append_to_claude_md(project_path, rule, section)
    except Exception as exc:
        logger.warning(f"self_improver: failed to write CLAUDE.md: {exc}")
        return None

    logger.info(f"📝 self_improver: added rule to CLAUDE.md [{section}]: {rule}")
    return rule


_MIN_RESPONSE_LENGTH = 400  # responses shorter than this lack distinct block + resolution sections


def _detect_block(response: str) -> tuple[str, str] | None:
    """Return (block_excerpt, resolution_excerpt) if enough block signals are found, else None.

    Pure regex — no API call. Cheap to run on every response.

    Requires at least _MIN_BLOCK_SIGNALS matches to avoid triggering on casual signal words.
    Block signals must appear in the first 80% of the response — signals in the final 20%
    are likely summary language, not actual blocks.
    Responses shorter than _MIN_RESPONSE_LENGTH are skipped — too short for distinct excerpts.
    """
    if len(response) < _MIN_RESPONSE_LENGTH:
        return None

    cutoff = int(len(response) * 0.8)
    searchable = response[:cutoff]
    matches = list(_BLOCK_RE.finditer(searchable))
    if len(matches) < _MIN_BLOCK_SIGNALS:
        return None

    # Extract context around the first block signal
    first_match = matches[0]
    start = max(0, first_match.start() - 50)
    end = min(len(searchable), first_match.end() + 150)
    block_excerpt = searchable[start:end].strip()

    # Resolution is the last 300 chars of the response (guaranteed non-overlapping
    # because response >= 400 chars and block is in first 80%)
    resolution_excerpt = response[-300:].strip()

    return block_excerpt, resolution_excerpt


def _reflect(prompt: str, block_excerpt: str, resolution_excerpt: str) -> dict | None:
    """Call Haiku to generate a CLAUDE.md rule. Returns {rule, section} or None."""
    client = Anthropic(
        http_client=httpx.Client(timeout=httpx.Timeout(5.0)),
        max_retries=0,
    )
    try:
        msg = client.messages.create(
            model=_HAIKU,
            max_tokens=128,
            messages=[{
                "role": "user",
                "content": _REFLECT_PROMPT.format(
                    prompt=prompt[:300],
                    block_excerpt=block_excerpt[:300],
                    resolution_excerpt=resolution_excerpt[:300],
                ),
            }],
        )
        raw = msg.content[0].text.strip()
        # Strip markdown code fences if Haiku wraps output (e.g. ```json\n{...}\n```)
        raw = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
        data = json.loads(raw)
        rule = data.get("rule", "").strip()
        section = data.get("section", "General").strip()
        if not rule:
            return None
        if section not in _VALID_SECTIONS:
            section = "General"
        return {"rule": rule, "section": section}
    except Exception as exc:
        logger.warning(f"self_improver: reflection failed: {exc}")
        return None


def _append_to_claude_md(project_path: str, rule: str, section: str) -> None:
    """Append rule at the END of the correct section in CLAUDE.md. Creates section if missing.

    Raises FileNotFoundError if CLAUDE.md is absent.
    Raises ValueError if project_path is "." (safety guard against writing to wrong directory).
    """
    if not Path(project_path).is_absolute():
        raise ValueError(f"project_path must be absolute, got: {project_path!r}")

    claude_md = Path(project_path) / "CLAUDE.md"
    if not claude_md.exists():
        raise FileNotFoundError(f"CLAUDE.md not found at {claude_md}")

    content = claude_md.read_text()
    entry = f"- {rule}"
    section_header = f"## {section}"

    if section_header in content:
        # Find the section and insert the rule after the last non-blank line in it,
        # before the next ## heading or end of file.
        lines = content.splitlines(keepends=True)
        in_section = False
        last_content_line = None  # index of last non-blank line in section
        next_section_line = None  # index of next ## heading after section

        for i, line in enumerate(lines):
            if line.strip() == section_header:
                in_section = True
                continue
            if in_section:
                if line.startswith("## "):
                    next_section_line = i
                    break
                if line.strip():  # non-blank
                    last_content_line = i

        # Insert after last content line in section, or before next section if no content
        if last_content_line is not None:
            insert_at = last_content_line + 1
        elif next_section_line is not None:
            insert_at = next_section_line
        else:
            insert_at = len(lines)

        lines.insert(insert_at, entry + "\n")
        content = "".join(lines)
    else:
        # Append new section at end of file
        content = content.rstrip() + f"\n\n{section_header}\n{entry}\n"

    claude_md.write_text(content)
```

### New: `tests/test_self_improver.py`

Unit tests — all Anthropic calls mocked via `unittest.mock.patch("tools.self_improver.Anthropic")`:

| Test | Input | Expected |
|---|---|---|
| No block signal | Clean response, zero signal words | Returns `None`, CLAUDE.md unchanged |
| Single signal word | "couldn't find a better name" (1 match) | Returns `None` — below `_MIN_BLOCK_SIGNALS` threshold |
| Block detected, reflection succeeds | Response with 2+ signals + resolution | Rule appended at END of section, rule string returned |
| Block detected, reflection returns bad JSON | Haiku returns `"not json"` | Returns `None`, CLAUDE.md unchanged |
| Block detected, reflection API fails | Haiku raises `Exception` | Returns `None`, CLAUDE.md unchanged |
| Block and resolution excerpts overlap | Block signal in final 20% of response | Mid-section used as resolution_excerpt |
| Existing section in CLAUDE.md | `## Watch Out For` present with bullets | Rule appended AFTER last existing bullet in section |
| Section followed by another section | `## Watch Out For` then `## Patterns` | Rule inserted before `## Patterns` header |
| Missing section in CLAUDE.md | No `## Patterns` | New section + rule appended at end of file |
| CLAUDE.md missing | `project_path` has no CLAUDE.md | Returns `None`, logs warning |
| `project_path` is `"."` or relative | Fallback path | Returns `None`, logs warning (`is_absolute()` check) |
| Duplicate rule | Same rule written twice | Both entries appear in CLAUDE.md — deduplication is explicitly deferred |
| Response shorter than 400 chars | Very short response | Returns `None` — too short for distinct excerpts |
| Haiku returns fenced JSON | ` ```json\n{...}\n``` ` | Fences stripped, parsed successfully |
| Invalid section from Haiku | `{"section": "Unknown"}` | Falls back to `General` section |

All tests use a temp directory for CLAUDE.md — no real project files touched.

### Modified: `agents/project_agent.py` — `handle()`

`reflect_and_update` is called after `_clean_response(response)` on ALL response paths — both sub-agent and main agent responses pass through `_clean_response`, so both are eligible for reflection. The error path (`return f"Error: {e}", "Error"`) returns before `_clean_response` and is excluded.

`self._lifecycle._post_thread()` is a private method called here deliberately — this matches existing usage patterns within `ProjectAgent` itself (which already calls `self._lifecycle` methods directly). No new public API is needed.

Add `from tools.self_improver import reflect_and_update` at the **module level** (top of `project_agent.py`, with the other imports). There is no circular dependency risk — `self_improver` imports only standard library modules and `anthropic`, not anything from `agents/`.

Add after `response = _clean_response(response)`:

```python
# Reflect on any block and update CLAUDE.md autonomously
rule = reflect_and_update(
    prompt=prompt,
    response=response,
    project_path=self.project.get("path", "."),
)
if rule:
    self._lifecycle._post_thread(
        f"📝 Learned something — updated CLAUDE.md:\n_{rule}_"
    )
```

No other files modified.

---

## Behavior Details

**5-second Haiku timeout is safe with Slack's 3-second ack window.** Slack Bolt in socket mode acks events automatically in a background thread. The `handle()` processing function runs in a separate thread and is NOT subject to the 3-second ack deadline. The 5s timeout in `_reflect()` only bounds the Haiku API call itself — it does not risk a Slack timeout error.

**Per-call Anthropic client:** `_reflect()` instantiates a new `Anthropic` client on every call. This is intentional — same pattern as `tools/triage.py`. For a low-frequency event (recovered blocks) on a solo-dev bot, connection overhead is negligible. Statelessness simplifies testing.

**`project_path == "."` is rejected** to prevent accidentally writing to the SlackClaw repo's own CLAUDE.md when a project config is missing its `"path"` key.

**Block detection is intentionally broad.** False positives (responses that mention "error" in passing) result in a Haiku call that either returns a useful rule or returns nothing. Cost of a false positive: ~$0.0001 and no CLAUDE.md change.

**False negatives** (blocked tasks that don't use signal words) are acceptable — not every learning needs to be captured.

**CLAUDE.md is the only file written.** No separate knowledge store, no database, no vector index. Simplicity is the point — CLAUDE.md is already read by every agent on every task, so updates take effect immediately on the next call.

**Duplicate rules:** No deduplication. If the same lesson is learned twice, it appears twice. This is acceptable for now — a future cleanup pass can deduplicate.

**The Slack notification is a single thread-only post.** This is intentionally different from the channel-level `✅ Task done` lifecycle post — a learned rule is a low-signal observational event, not a task completion. It stays in thread to avoid channel noise. The existing lifecycle `done()` post is unaffected and still fires normally.

---

## What Does Not Change

- `CLAUDE.md` loading in `ProjectAgent._load_claude_md()` — already reads on every instantiation
- `LifecycleNotifier` — `_post_thread` used as-is, no new methods
- `bot_unified.py` — no changes
- Max and API modes — both pass through `ProjectAgent.handle()`, both benefit equally
