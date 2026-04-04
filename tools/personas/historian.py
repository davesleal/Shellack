"""
Historian persona — prior decisions and conflict detection.

Fires on moderate and complex turns. Reads observer + token_cart,
surfaces relevant prior decisions and flags conflicts.
"""

from __future__ import annotations

from tools.personas import Persona


class Historian(Persona):
    name = "historian"
    emoji = "\U0001f4dc"
    model = "haiku"
    reads = ["observer", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a historian agent. Your job is to recall relevant prior decisions from
handoff context and project registry, then detect conflicts with the current request.

Rules:
- List only decisions directly relevant to the current task.
- A conflict is when the current request contradicts or undoes a prior decision.
- Lessons are short observations that would help future decisions.

Respond ONLY with valid JSON in this exact shape:
{
  "prior_decisions": ["description of prior decision", ...],
  "conflicts": [
    {"decision": "prior decision text", "conflict_with": "current request element"}
  ],
  "lessons": ["short lesson", ...]
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        observer = inputs.get("observer", {})
        if observer.get("summary"):
            parts.append(f"## Current Request\n{observer['summary']}")
        if observer.get("prior_context"):
            parts.append(f"## Prior Context\n{observer['prior_context']}")
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("registry_snapshot"):
            parts.append(f"## Registry Snapshot\n{token_cart['registry_snapshot']}")
        return "\n\n".join(parts) if parts else "No context available."
