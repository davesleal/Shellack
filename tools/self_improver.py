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
    Raises ValueError if project_path is not absolute (safety guard against writing to wrong directory).
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
