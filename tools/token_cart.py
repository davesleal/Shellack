"""
HaikuTokenCart — persistent context layer for Shellack.

Encapsulates pre-call enrichment and post-call compaction using Haiku 4.5.
Reduces token consumption by replacing full-history replay with structured
handoff documents that carry forward only what matters.
"""
from __future__ import annotations

import logging
import re
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

_EXTERNAL_HANDOFF_SYSTEM = """You are a cross-thread memory agent. Given a thread's final handoff and journal, produce a persistent context summary for future threads on this project.

Extract ONLY what should persist:
- Decisions that affect future work
- Patterns discovered or established
- Corrections the operator made
- Unfinished work or open items
- Project state changes

Drop:
- Turn-specific details that won't matter next time
- Resolved questions
- Intermediate reasoning

Output format:
## Persistent Context
**Last updated:** {date}

### Recent Decisions
- {decisions that affect future work}

### Learned Corrections
- {corrections the operator made}

### Open Items
- {unfinished work}

### Project State
- {current state, recent changes}"""

_CORRECTION_PATTERNS = [
    r"\bno[,.]?\s+(use|try|do)\b",
    r"\bdon'?t\b",
    r"\bstop\s+(doing|using|creating)\b",
    r"\binstead[,.]?\s+(use|try)\b",
    r"\bwe\s+(already|have)\b",
    r"\bthere'?s\s+already\b",
    r"\bthat'?s\s+not\s+how\b",
    r"\bthe\s+pattern\s+is\b",
    r"\balways\s+use\b",
    r"\bnever\s+(use|create|write|add)\b",
]

_GUT_CHECK_SYSTEM = """You are a sanity check agent. Review the reasoning model's planned response against the project registry and handoff context.

Check for:
- Registry compliance: Is the response about to create something that already exists in the registry?
- Scope creep: Is the response doing more than what was asked?
- Consistency: Does the approach match established patterns in the registry?
- Risk: Is anything being deleted or overwritten?

Respond with EXACTLY one of:
PROCEED
or
CONCERN: {one-line description of the concern}

Nothing else. No explanation."""

_CORRECTION_SYSTEM = """You are a correction extraction agent. The operator corrected the AI agent. Extract the correction as a registry rule.

Output format (exactly):
---SECTION---
{section name: one of "Architecture Rules", "UI Components", "Shared Utilities", "API Patterns", "Design Tokens", "Data Models"}
---RULE---
| {rule/component} | {scope/path} | {rationale/notes} |

If you cannot extract a clear rule, output:
---NONE---

Rules:
- Extract ONLY what the operator explicitly stated
- Do not infer or expand
- Keep the rule concise (one table row)
- Choose the most specific section that fits"""


def detect_correction(prompt: str) -> bool:
    """Check if the user's message contains a correction pattern."""
    lower = prompt.lower()
    return any(re.search(p, lower) for p in _CORRECTION_PATTERNS)


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

---REVIEW---
Quick code scan of the response. Check for:
- Obvious bugs (unclosed resources, missing returns, off-by-one)
- Security (hardcoded secrets, unsanitized input, injection vectors)
- Consistency (naming doesn't match surrounding code, wrong patterns)

If clean, output: CLEAN
If issues found, output one line per issue, max 3.

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

def _parse_cart_response(text: str) -> tuple[str, str, str]:
    """Split a post-call response into (handoff, journal_draft, review)."""
    handoff = ""
    journal = ""
    review = ""

    if "---HANDOFF---" in text:
        parts = text.split("---HANDOFF---", 1)[1]
        if "---JOURNAL---" in parts:
            handoff, rest = parts.split("---JOURNAL---", 1)
            if "---REVIEW---" in rest:
                journal, review = rest.split("---REVIEW---", 1)
            else:
                journal = rest
        else:
            if "---REVIEW---" in parts:
                handoff, review = parts.split("---REVIEW---", 1)
            else:
                handoff = parts
    else:
        # No markers — treat entire text as handoff
        handoff = text

    return handoff.strip(), journal.strip(), review.strip()


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
            h, j, r = _parse_cart_response(text)
            return {"handoff": h, "journal_draft": j, "review": r}
        except Exception as exc:
            logger.warning(f"Token cart post-call failed: {exc}")

        # Fallback: preserve prior handoff with failure note
        prior = handoff or ""
        if prior:
            prior += "\n\n*[Note: post-call compaction failed; prior handoff preserved as-is]*"
        return {"handoff": prior, "journal_draft": "", "review": ""}

    def extract_correction(self, prompt: str, response: str) -> dict | None:
        """Extract a registry correction from the operator's message.

        Returns {"section": str, "entry": str} or None.
        """
        user_content = f"## Operator's correction\n{prompt}\n\n## Agent's prior response\n{response}"
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                system=_CORRECTION_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            text = msg.content[0].text.strip()
            if "---NONE---" in text:
                return None
            if "---SECTION---" in text and "---RULE---" in text:
                section = text.split("---SECTION---")[1].split("---RULE---")[0].strip()
                entry = text.split("---RULE---")[1].strip()
                if section and entry:
                    return {"section": section, "entry": entry}
        except Exception as exc:
            logger.warning(f"Token cart correction extraction failed: {exc}")
        return None

    def external_handoff(self, handoff: str, journal_draft: str) -> str:
        """Produce a persistent cross-thread summary from a completed thread."""
        user_content = f"## Final Handoff\n{handoff}\n\n## Journal Draft\n{journal_draft}"
        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=_EXTERNAL_HANDOFF_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            return msg.content[0].text.strip()
        except Exception as exc:
            logger.warning(f"Token cart external handoff failed: {exc}")
            return ""

    def gut_check(
        self,
        response: str,
        registry: str | None = None,
        handoff: str | None = None,
    ) -> str | None:
        """Quick sanity check on agent response. Returns concern string or None."""
        user_content = f"## Agent Response\n{response[:2000]}"
        if registry:
            user_content += f"\n\n## Project Registry\n{registry[:2000]}"
        if handoff:
            user_content += f"\n\n## Current Handoff\n{handoff[:1000]}"

        try:
            msg = self._client.messages.create(
                model=self._model,
                max_tokens=128,
                system=_GUT_CHECK_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            text = msg.content[0].text.strip()
            if text.startswith("CONCERN:"):
                return text[len("CONCERN:"):].strip()
            return None  # PROCEED
        except Exception as exc:
            logger.warning(f"Gut check failed: {exc}")
            return None  # on failure, proceed
