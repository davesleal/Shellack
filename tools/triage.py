from __future__ import annotations
import json
import logging
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"

_TIER_TO_MODEL: dict[str, str] = {
    "simple": _HAIKU,
    "moderate": _SONNET,
    "complex": _SONNET,
}


@dataclass
class TriageResult:
    tier: str    # "simple" | "moderate" | "complex"
    model: str   # full model ID
    reason: str  # one sentence, for logging only


# Safe default — returned on any triage failure
_DEFAULT = TriageResult(tier="moderate", model=_SONNET, reason="triage unavailable")

_PROMPT = """Classify this developer request. Reply with JSON only, no prose.
{"tier": "simple|moderate|complex", "reason": "one sentence"}

simple   = question, explanation, lookup, read-only, status check
moderate = code review, analysis, single-file change, debugging help
complex  = multi-file edits, refactor, long debugging, architecture work

Request: """


def classify(prompt: str, project_key: str = "") -> TriageResult:
    """Classify prompt using Haiku. Always returns a TriageResult — never raises."""
    client = Anthropic(
        http_client=httpx.Client(timeout=httpx.Timeout(5.0)),
        max_retries=0,  # no retries — triage must be fast; failures use _DEFAULT
    )
    try:
        msg = client.messages.create(
            model=_HAIKU,
            max_tokens=64,
            messages=[{"role": "user", "content": _PROMPT + prompt}],
        )
        data = json.loads(msg.content[0].text)
        tier = data.get("tier", "")
        if tier not in _TIER_TO_MODEL:
            raise ValueError(f"Unknown tier: {tier!r}")
        result = TriageResult(
            tier=tier,
            model=_TIER_TO_MODEL[tier],
            reason=data.get("reason", ""),
        )
        logger.info(f"Triage: {result.tier} -> {result.model} -- \"{result.reason}\"")
        return result
    except Exception as exc:
        logger.warning(f"Triage failed: {exc} -- using default (moderate/sonnet)")
        return _DEFAULT
