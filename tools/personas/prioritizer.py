"""
Prioritizer persona — impact/effort ranking.

Fires on moderate and complex turns. Reads strategist + skeptic,
ranks options by impact/effort and produces a recommendation.
"""

from __future__ import annotations

from tools.personas import Persona


class Prioritizer(Persona):
    name = "prioritizer"
    emoji = "\u2696\ufe0f"
    model = "haiku"
    reads = ["strategist", "skeptic"]
    max_tokens = 512
    system_prompt = """\
You are a prioritization expert. Given a task plan and skeptical analysis, rank
the available options by impact and effort to identify the highest-value path forward.

Rules:
- ranked_options is a list of options sorted by score (highest first).
- Each option must include: option (description), impact (high/medium/low), effort (high/medium/low), score (1-10 float).
- recommendation is a concise statement of the recommended next action.

Respond ONLY with valid JSON in this exact shape:
{
  "ranked_options": [
    {"option": "option description", "impact": "high" | "medium" | "low", "effort": "high" | "medium" | "low", "score": 8.5}
  ],
  "recommendation": "concise recommendation"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        strategist = inputs.get("strategist", {})
        if strategist.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{tasks_text}")
        if strategist.get("sequence"):
            parts.append(f"## Sequence\n{strategist['sequence']}")
        if strategist.get("estimated_complexity"):
            parts.append(f"## Estimated Complexity\n{strategist['estimated_complexity']}")
        skeptic = inputs.get("skeptic", {})
        if skeptic.get("assumptions"):
            assumptions_text = "\n".join(
                f"- {a.get('claim', '')}: risk={a.get('risk', '')}"
                for a in skeptic["assumptions"]
            )
            parts.append(f"## Identified Assumptions & Risks\n{assumptions_text}")
        if skeptic.get("verdict"):
            parts.append(f"## Skeptic Verdict\n{skeptic['verdict']}")
        return "\n\n".join(parts) if parts else "No context available."
