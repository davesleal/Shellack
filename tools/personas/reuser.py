"""
Reuser persona — DRY enforcement and registry duplication check.

Fires on moderate and complex turns. Reads architect + token_cart,
enforces DRY principles and checks for duplication against the registry.
"""

from __future__ import annotations

from tools.personas import Persona


class Reuser(Persona):
    name = "reuser"
    emoji = "\u267b\ufe0f"
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a DRY enforcement agent. Given an architectural proposal and project registry,
identify existing components that overlap with what's being proposed and flag library inconsistencies.

Rules:
- existing_components lists registry entries that match or overlap with the proposal.
- Each component must include: name (component name), path (file path), match_score (0.0-1.0 float).
- lib_consistency lists cases where a different library is proposed vs. what's already adopted.
- Each inconsistency must include: adopted (what's already in use), proposed (what's being suggested), fix (how to align).
- verdict summarizes the DRY status.

Respond ONLY with valid JSON in this exact shape:
{
  "existing_components": [
    {"name": "component name", "path": "path/to/file.py", "match_score": 0.9}
  ],
  "lib_consistency": [
    {"adopted": "existing library", "proposed": "new library", "fix": "use existing library"}
  ],
  "verdict": "clean" | "duplicate" | "inconsistent"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("files_affected"):
            files_text = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files Affected\n{files_text}")
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Enriched Prompt\n{token_cart['enriched_prompt']}")
        if token_cart.get("registry"):
            parts.append(f"## Registry\n{token_cart['registry']}")
        return "\n\n".join(parts) if parts else "No context available."
