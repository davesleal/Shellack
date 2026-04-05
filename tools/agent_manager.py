"""Agent Manager — intelligent model selection based on task complexity."""

from __future__ import annotations

import logging
import os

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT = 5.0

_CLASSIFY_SYSTEM = """Classify the complexity of this task. Respond with EXACTLY one word:

SIMPLE — greeting, status check, uptime, quick question, yes/no, opinion, "what time is it", general knowledge, no code needed
MODERATE — explain how code works, code review, analysis, single-file change, debugging, "how does [system] work", "how does [module] decide", reading a specific file
COMPLEX — multi-file refactor, architecture, tracing across systems, "trace the lifecycle", design proposals, security audit

If the question asks about HOW specific code or a system works, that is MODERATE (not simple). One word only. No explanation."""

_MODEL_MAP = {
    "simple": "claude-haiku-4-5-20251001",
    "moderate": "claude-sonnet-4-6",
    "complex": "claude-opus-4-6",
}


def classify_complexity(prompt: str, handoff: str | None = None) -> str:
    """Classify task complexity. Returns 'simple', 'moderate', or 'complex'."""
    user_content = prompt
    if handoff:
        user_content = f"Context:\n{handoff[:500]}\n\nTask:\n{prompt}"

    try:
        client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(_TIMEOUT)),
            max_retries=0,
        )
        msg = client.messages.create(
            model=_CLASSIFIER_MODEL,
            max_tokens=8,
            system=_CLASSIFY_SYSTEM,
            messages=[{"role": "user", "content": user_content}],
        )
        text = msg.content[0].text.strip().lower()
        if text in _MODEL_MAP:
            return text
        # Fuzzy match
        for level in _MODEL_MAP:
            if level in text:
                return level
    except Exception as exc:
        logger.warning(f"Agent manager classification failed: {exc}")

    return "moderate"  # default to moderate on failure


def select_model(complexity: str) -> str:
    """Return the model ID for the given complexity level."""
    model = _MODEL_MAP.get(complexity, _MODEL_MAP["moderate"])
    # Allow env var overrides per tier
    env_key = f"AGENT_MANAGER_{complexity.upper()}_MODEL"
    return os.environ.get(env_key, model)
