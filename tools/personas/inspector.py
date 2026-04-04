"""
Inspector persona — completeness checker.

Fires on moderate and complex turns. Reads architect and checks for
edge cases, missing returns, incomplete coverage.
"""

from __future__ import annotations

from tools.personas import Persona


class Inspector(Persona):
    name = "inspector"
    emoji = "\U0001f50d"
    model = "haiku"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """\
You are a code quality inspector. Given an architectural proposal, check for completeness:
missing edge cases, unhandled error paths, missing return values, incomplete validations,
null/empty input handling, boundary conditions.

Rules:
- Maximum 5 gaps.
- Each gap must include: type (edge_case/missing_return/validation/boundary/error_handling),
  location (file or component where the gap exists), severity (low/medium/high).
- verdict summarizes completeness.

Respond ONLY with valid JSON in this exact shape:
{
  "gaps": [
    {"type": "edge_case|missing_return|validation|boundary|error_handling", "location": "file or component", "severity": "low|medium|high"}
  ],
  "verdict": "complete" | "gaps" | "incomplete"
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
        if architect.get("files_affected"):
            files_text = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files Affected\n{files_text}")
        return "\n\n".join(parts) if parts else "No context available."
