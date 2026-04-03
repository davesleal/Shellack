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
_CLOSING_TAG_RE = re.compile(
    r"\s*\[/(think|action|reply)\]\s*", re.IGNORECASE | re.MULTILINE
)


def parse_response(text: str) -> ParsedResponse:
    """Parse a tag-prefixed response into structured sections.

    Tags: [think], [action], [reply] — case insensitive, at start of line.
    If no tags found, entire text is treated as reply (backward compatible).
    Tags inside code fences are ignored (not treated as real tags).
    """
    if not text or not text.strip():
        return ParsedResponse()

    # Identify code fence ranges — tags inside these are NOT real tags
    protected = [(m.start(), m.end()) for m in _CODE_FENCE_RE_FULL.finditer(text)]

    def _in_fence(pos):
        return any(s <= pos < e for s, e in protected)

    # Find all tag positions, excluding those inside code fences
    matches = [m for m in _TAG_RE.finditer(text) if not _in_fence(m.start())]

    if not matches:
        return ParsedResponse(reply=text.strip())

    result = ParsedResponse()
    for i, match in enumerate(matches):
        tag = match.group(1).lower()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        content = _CLOSING_TAG_RE.sub("", text[start:end]).strip()

        if tag == "think":
            result.think = content
        elif tag == "action":
            result.actions.append(content)
        elif tag == "reply":
            result.reply = content

    return result


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
    chunks: list[str] = []
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

    return [c for c in chunks if c.strip()]


def _split_on_sentences(text: str, max_chars: int) -> list[str]:
    """Split a paragraph on sentence boundaries."""
    sentences = re.split(r"(?<=\.)\s+", text)
    chunks: list[str] = []
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
