"""
Skeptic persona — assumption challenger.

Fires on moderate and complex turns. Reads architect + strategist,
challenges assumptions, flags risks, and gates progress.
"""

from __future__ import annotations

from tools.personas import Persona


class Skeptic(Persona):
    name = "skeptic"
    emoji = "\U0001f928"
    model = "haiku"
    reads = ["architect", "strategist"]
    max_tokens = 512
    system_prompt = """\
You are a critical skeptic. Given an architectural proposal and task plan, identify
assumptions that may be incorrect, unsupported, or risky.

Rules:
- Maximum 3 assumptions.
- Each assumption must include: claim (the assumption being made), evidence (what supports or contradicts it), risk (consequence if wrong).
- verdict summarizes whether to proceed.
- revision_target is "architect" when verdict is "reconsider", otherwise null.

Respond ONLY with valid JSON in this exact shape:
{
  "assumptions": [
    {"claim": "assumption text", "evidence": "supporting or contradicting evidence", "risk": "consequence if wrong"}
  ],
  "verdict": "proceed" | "reconsider" | "block",
  "revision_target": "architect" | null
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("data_model"):
            parts.append(f"## Data Model\n{architect['data_model']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        strategist = inputs.get("strategist", {})
        if strategist.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{tasks_text}")
        if strategist.get("estimated_complexity"):
            parts.append(f"## Estimated Complexity\n{strategist['estimated_complexity']}")
        return "\n\n".join(parts) if parts else "No context available."
