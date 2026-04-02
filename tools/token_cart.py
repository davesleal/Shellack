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
            logger.warning("Token cart pre-call returned empty response, using fallback")
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
