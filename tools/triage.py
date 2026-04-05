from __future__ import annotations
import json
import logging
import os
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_HAIKU = "claude-haiku-4-5-20251001"


@dataclass
class TriageResult:
    tier: str  # "simple" | "moderate" | "complex"
    model: str  # full model ID
    reason: str  # one sentence, for logging only


def _configured_model() -> str:
    return os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")


_SYSTEM_PROMPT = """Classify this developer request. Reply with JSON only, no prose.
{"tier": "simple|moderate|complex", "reason": "one sentence"}

simple   = greeting, status check, uptime, quick question, yes/no, explanation of a concept, lookup, "what is X", "how do I", opinion/preference questions
moderate = code review, analysis, single-file change, debugging help, "how does [specific code] work", reading/explaining a specific file
complex  = multi-file edits, refactor, long debugging, architecture work, tracing across systems, "trace the lifecycle", design proposals

Default to simple unless the request clearly requires code analysis or changes."""


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
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = msg.content[0].text.strip()
        if not raw:
            raise ValueError("empty response from triage model")
        data = json.loads(raw)
        tier = data.get("tier", "")
        if tier not in ("simple", "moderate", "complex"):
            raise ValueError(f"Unknown tier: {tier!r}")
        result = TriageResult(
            tier=tier,
            model=_configured_model(),
            reason=data.get("reason", ""),
        )
        logger.info(f'Triage: {result.tier} -> {result.model} -- "{result.reason}"')
        return result
    except Exception as exc:
        logger.warning(f"Triage failed: {exc} -- using default (moderate/sonnet)")
        return TriageResult(
            tier="moderate",
            model=_configured_model(),
            reason="triage unavailable",
        )
