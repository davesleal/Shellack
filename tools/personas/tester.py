"""
Tester persona — test strategy from Inspector gaps.

Fires on moderate and complex turns. Reads architect + inspector and
produces a concrete test strategy targeting identified gaps.
"""

from __future__ import annotations

from tools.personas import Persona


class Tester(Persona):
    name = "tester"
    emoji = "\U0001f9ea"
    model = "sonnet"
    reads = ["architect", "inspector"]
    max_tokens = 768
    system_prompt = """\
You are a senior test engineer. Given an architectural proposal and a list of quality gaps
identified by an inspector, produce a concrete test strategy.

Rules:
- Each test case must target a specific gap or architectural concern.
- Each test case must include: name (descriptive test name), type (unit/integration/e2e/property),
  assertion (what the test asserts).
- coverage_gaps lists any gaps that still lack adequate test coverage after your strategy.
- verdict summarizes test coverage.

Respond ONLY with valid JSON in this exact shape:
{
  "test_cases": [
    {"name": "test name", "type": "unit|integration|e2e|property", "assertion": "what is asserted"}
  ],
  "coverage_gaps": ["gap description", ...],
  "verdict": "covered" | "gaps" | "untested"
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
        if architect.get("files_affected"):
            files_text = "\n".join(f"- {f}" for f in architect["files_affected"])
            parts.append(f"## Files Affected\n{files_text}")
        inspector = inputs.get("inspector", {})
        if inspector.get("gaps"):
            gaps_text = "\n".join(
                f"- [{g['severity']}] {g['type']} in {g['location']}"
                for g in inspector["gaps"]
            )
            parts.append(f"## Quality Gaps\n{gaps_text}")
        if inspector.get("verdict"):
            parts.append(f"## Inspector Verdict\n{inspector['verdict']}")
        return "\n\n".join(parts) if parts else "No context available."
