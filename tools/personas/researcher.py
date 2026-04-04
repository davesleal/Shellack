"""
Researcher persona — external docs lookup and API reference.

Fires on complex turns only. Reads observer + strategist,
returns relevant external findings and API references.
"""

from __future__ import annotations

from tools.personas import Persona


class Researcher(Persona):
    name = "researcher"
    emoji = "\U0001f310"
    model = "sonnet"
    reads = ["observer", "strategist"]
    max_tokens = 768
    system_prompt = """\
You are a research agent. Given a task plan and request summary, identify relevant
external documentation, API references, and known best practices.

Rules:
- Each finding must have a source, a brief summary, and a relevance score (high/medium/low).
- List only directly applicable findings — no speculative references.
- apis_referenced is a flat list of API or library names mentioned.

Respond ONLY with valid JSON in this exact shape:
{
  "findings": [
    {"source": "docs URL or name", "summary": "what it says", "relevance": "high" | "medium" | "low"}
  ],
  "apis_referenced": ["APIName", ...]
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        observer = inputs.get("observer", {})
        if observer.get("summary"):
            parts.append(f"## Request Summary\n{observer['summary']}")
        strategist = inputs.get("strategist", {})
        if strategist.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{tasks_text}")
        if strategist.get("estimated_complexity"):
            parts.append(f"## Estimated Complexity\n{strategist['estimated_complexity']}")
        return "\n\n".join(parts) if parts else "No context available."
