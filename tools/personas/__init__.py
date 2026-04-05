"""
Persona base class and registry for the cognitive pipeline.

Each Persona reads declared input slots from TurnContext, calls the Anthropic API,
and writes its output to its named slot.
"""

from __future__ import annotations

import json
import logging
from abc import abstractmethod
from typing import ClassVar

log = logging.getLogger(__name__)

MODEL_MAP: dict[str, str] = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
}

PERSONA_REGISTRY: dict[str, "Persona"] = {}

_anthropic_client = None


def _get_client():
    global _anthropic_client
    if _anthropic_client is None:
        import anthropic
        _anthropic_client = anthropic.Anthropic()
    return _anthropic_client


class Persona:
    """Base class for all pipeline personas."""

    name: ClassVar[str]
    emoji: ClassVar[str]
    model: ClassVar[str]
    reads: ClassVar[list[str]]
    system_prompt: ClassVar[str]
    max_tokens: ClassVar[int] = 256

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if hasattr(cls, "name") and cls.name:
            PERSONA_REGISTRY[cls.name] = cls()

    @property
    def writes(self) -> str:
        return self.name

    def run(self, inputs: dict[str, dict]) -> dict:
        """Call the API and return parsed JSON, falling back to {"raw": text}."""
        system = self.system_prompt
        user = self._build_user_content(inputs)
        resolved_model = MODEL_MAP.get(self.model, self.model)
        msg = self._call_api(system, user, resolved_model, self.max_tokens)
        text = msg.content[0].text.strip()
        try:
            result = json.loads(text)
        except (json.JSONDecodeError, ValueError):
            result = {"raw": text}
        result["_usage"] = {
            "input_tokens": msg.usage.input_tokens,
            "output_tokens": msg.usage.output_tokens,
        }
        return result

    @abstractmethod
    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        """Return True if this persona should run for this turn."""
        ...

    @abstractmethod
    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        """Build the user message from gathered input slots."""
        ...

    def _call_api(self, system: str, user: str, model: str, max_tokens: int):
        """Separated for testability."""
        client = _get_client()
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )


def get_persona(name: str) -> Persona:
    """Retrieve a registered persona by name."""
    if name not in PERSONA_REGISTRY:
        raise KeyError(f"Persona '{name}' not found in registry. Available: {list(PERSONA_REGISTRY)}")
    return PERSONA_REGISTRY[name]
