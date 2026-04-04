"""
Specialist persona — framework idiom validation.

Fires on moderate and complex turns. Reads architect + token_cart,
validates that the proposed approach follows framework idioms.
"""

from __future__ import annotations

from tools.personas import Persona


class Specialist(Persona):
    name = "specialist"
    emoji = "\U0001f9ec"
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a framework specialist. Given an architectural proposal, validate that it follows
the idioms and conventions of the relevant frameworks and languages.

Rules:
- idiom_violations lists patterns that violate framework conventions.
- Each violation must include: pattern (what was proposed), fix (correct approach), framework (which framework).
- verdict summarizes the overall idiomatic quality.

Respond ONLY with valid JSON in this exact shape:
{
  "idiom_violations": [
    {"pattern": "what was proposed", "fix": "correct approach", "framework": "framework name"}
  ],
  "verdict": "idiomatic" | "fixable" | "wrong"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Enriched Prompt\n{token_cart['enriched_prompt']}")
        return "\n\n".join(parts) if parts else "No context available."
