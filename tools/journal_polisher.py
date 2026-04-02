"""Journal polisher — Sonnet refines Haiku's journal draft."""

from __future__ import annotations

import logging
import os
from typing import Optional

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_POLISH_SYSTEM = """You are a technical writer polishing a journal draft into a final entry.

Rules:
- Keep it concise but informative (2-4 paragraphs max)
- Write in past tense, third person
- Structure: Context > Approach > Outcome > Insights (if noteworthy)
- Include specific details: file names, function names, metrics
- Write the opening as if starting a blog post — engaging, not dry
- Do not add information that isn't in the draft
- Do not add emojis"""

_MODEL = "claude-sonnet-4-6"
_TIMEOUT = 15.0


def polish_journal(draft: str, project_name: str = "") -> Optional[str]:
    """Polish a Haiku journal draft using Sonnet. Returns polished text or None."""
    if not draft or not draft.strip():
        return None

    model = os.environ.get("JOURNAL_MODEL", _MODEL)
    prompt = f"Project: {project_name}\n\nDraft:\n{draft}"

    try:
        client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(_TIMEOUT)),
            max_retries=1,
        )
        msg = client.messages.create(
            model=model,
            max_tokens=1024,
            system=_POLISH_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text.strip()
    except Exception as exc:
        logger.warning(f"Journal polish failed: {exc}")
        return None
