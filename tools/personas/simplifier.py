"""
Simplifier persona — YAGNI enforcement.

Fires on complex turns only. Reads architect,
identifies over-engineering and proposes simpler alternatives.
"""

from __future__ import annotations

from tools.personas import Persona


class Simplifier(Persona):
    name = "simplifier"
    emoji = "\u2702\ufe0f"
    model = "haiku"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """\
You are a YAGNI enforcement agent. Given an architectural proposal, identify
components, abstractions, or features that are not needed yet and propose simpler alternatives.

Rules:
- simplifications is a list of over-engineered elements and their simpler replacements.
- Each simplification must include: current (what's proposed), proposed (the simpler alternative), savings (what complexity is avoided).
- verdict summarizes the overall complexity verdict.

Respond ONLY with valid JSON in this exact shape:
{
  "simplifications": [
    {"current": "current over-engineered element", "proposed": "simpler alternative", "savings": "complexity avoided"}
  ],
  "verdict": "minimal" | "reducible" | "overengineered"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        if architect.get("files_affected"):
            files_text = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files Affected\n{files_text}")
        return "\n\n".join(parts) if parts else "No context available."
