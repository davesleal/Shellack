"""
DataScientist persona — scale and query analysis.

Fires on complex turns only. Reads architect,
analyzes scale concerns, query patterns, and index suggestions.
"""

from __future__ import annotations

from tools.personas import Persona


class DataScientist(Persona):
    name = "data_scientist"
    emoji = "\U0001f4ca"
    model = "haiku"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """\
You are a data scientist and database analyst. Given an architectural proposal with
data models, analyze scale implications, query patterns, and indexing needs.

Rules:
- scale_concerns lists potential performance or scalability issues.
- query_patterns lists anticipated query shapes (e.g., "filter by user_id + date range").
- index_suggestions lists specific indexes that would improve performance.
- verdict summarizes whether the data design is scalable.

Respond ONLY with valid JSON in this exact shape:
{
  "scale_concerns": ["concern description", ...],
  "query_patterns": ["query pattern description", ...],
  "index_suggestions": ["index suggestion", ...],
  "verdict": "scalable" | "review" | "blocker"
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
        if architect.get("files_affected"):
            files_text = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files Affected\n{files_text}")
        return "\n\n".join(parts) if parts else "No context available."
