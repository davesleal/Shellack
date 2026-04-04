"""
Insights persona — success measurement analyst.

Fires on complex turns only. Reads architect + dreamer,
defines success criteria, metrics, and instrumentation requirements.
"""

from __future__ import annotations

from tools.personas import Persona


class Insights(Persona):
    name = "insights"
    emoji = "\U0001f4c9"
    model = "haiku"
    reads = ["architect", "dreamer"]
    max_tokens = 512
    system_prompt = """\
You are a success measurement analyst. Given an architectural proposal and a visionary
direction, define how success will be measured. Focus on what can actually be tracked.

Rules:
- success_criteria: list of 2-4 concrete outcomes that define success.
- metrics: list of 2-4 specific quantitative or qualitative signals to track.
- instrumentation: list of 1-3 specific logging, analytics, or monitoring additions needed.
- verdict: classify measurability as "measurable", "needs_definition", or "unmeasurable".

Respond ONLY with valid JSON in this exact shape:
{
  "success_criteria": ["criterion 1", "criterion 2"],
  "metrics": ["metric 1", "metric 2"],
  "instrumentation": ["instrumentation step 1"],
  "verdict": "measurable" | "needs_definition" | "unmeasurable"
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
        dreamer = inputs.get("dreamer", {})
        if dreamer.get("vision"):
            parts.append(f"## Vision\n{dreamer['vision']}")
        if dreamer.get("next_step"):
            parts.append(f"## Next Step\n{dreamer['next_step']}")
        if dreamer.get("platform_potential"):
            parts.append(f"## Platform Potential\n{dreamer['platform_potential']}")
        if dreamer.get("time_horizon"):
            parts.append(f"## Time Horizon\n{dreamer['time_horizon']}")
        return "\n\n".join(parts) if parts else "No context available."
