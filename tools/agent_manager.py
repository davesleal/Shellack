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

SIMPLE — greeting, status check, uptime, quick question, yes/no, explanation of a concept, lookup, "what is X", "how do I", opinion/preference, single file read, rename, format
MODERATE — code review, analysis, single-file change, debugging help, "how does [specific code] work", reading/explaining a specific file or module
COMPLEX — multi-file edits, refactor, long debugging, architecture work, tracing across systems, "trace the lifecycle", design proposals

Default to SIMPLE unless the request clearly requires code analysis or changes. One word only. No explanation."""

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
