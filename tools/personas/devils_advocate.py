"""
Devil's Advocate persona — strongest-case-against builder.

Fires on complex turns only. Reads architect + strategist,
builds the strongest possible case against the proposed approach.
"""

from __future__ import annotations

from tools.personas import Persona


class DevilsAdvocate(Persona):
    name = "devils_advocate"
    emoji = "\U0001f479"
    model = "haiku"
    reads = ["architect", "strategist"]
    max_tokens = 512
    system_prompt = """\
You are a devil's advocate. Given an architectural proposal and task plan, construct
the strongest possible case against the chosen approach and propose a concrete alternative.

Rules:
- counter_argument is the most compelling argument against the proposed approach.
- alternative is a concrete different approach that avoids the identified problems.
- verdict summarizes whether the counter-argument has merit.

Respond ONLY with valid JSON in this exact shape:
{
  "counter_argument": "strongest case against the proposed approach",
  "alternative": "concrete alternative approach",
  "verdict": "proceed" | "has_merit" | "stop"
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
        strategist = inputs.get("strategist", {})
        if strategist.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{tasks_text}")
        if strategist.get("estimated_complexity"):
            parts.append(f"## Estimated Complexity\n{strategist['estimated_complexity']}")
        return "\n\n".join(parts) if parts else "No context available."
