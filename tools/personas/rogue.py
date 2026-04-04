"""
Rogue persona — stress scenario tester.

Fires on complex always; on moderate only if security_override is set.
Reads architect and stress-tests the proposal with 10x load, race conditions, etc.
"""

from __future__ import annotations

from tools.personas import Persona


class Rogue(Persona):
    name = "rogue"
    emoji = "\U0001f608"
    model = "haiku"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """\
You are a chaos engineer and stress tester. Given an architectural proposal, identify
scenarios where the system fails under stress: 10x load, race conditions, cascading failures,
resource exhaustion, timeout storms, thundering herds.

Rules:
- Maximum 3 stress scenarios.
- Each scenario must include: scenario (description of the stress condition), impact (what breaks),
  likelihood (low/medium/high).
- verdict summarizes system resilience.

Respond ONLY with valid JSON in this exact shape:
{
  "stress_scenarios": [
    {"scenario": "description", "impact": "what breaks", "likelihood": "low|medium|high"}
  ],
  "verdict": "resilient" | "fragile" | "breaks"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        if complexity == "complex":
            return True
        if complexity == "moderate":
            return turn_context.get("agent_manager", {}).get("security_override", False)
        return False

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
