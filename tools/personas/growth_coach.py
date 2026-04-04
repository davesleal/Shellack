"""
GrowthCoach persona — AARRR funnel evaluator.

Fires on complex turns only. Reads architect + insights,
evaluates funnel impact, conversion risk, and A/B test opportunities.
"""

from __future__ import annotations

from tools.personas import Persona


class GrowthCoach(Persona):
    name = "growth_coach"
    emoji = "\U0001f4c8"
    model = "haiku"
    reads = ["architect", "insights"]
    max_tokens = 512
    system_prompt = """\
You are a growth coach specializing in the AARRR funnel (Acquisition, Activation,
Retention, Revenue, Referral). Given an architectural proposal and success metrics,
evaluate the funnel impact and readiness to ship.

Rules:
- funnel_impact: which AARRR stage(s) this affects and how.
- conversion_risk: the main risk to conversion or user activation.
- ab_test_opportunity: a specific hypothesis worth A/B testing, or "none" if not applicable.
- verdict: classify readiness as "ship", "measure_first", or "reconsider".

Respond ONLY with valid JSON in this exact shape:
{
  "funnel_impact": "AARRR stage(s) affected and how",
  "conversion_risk": "main conversion risk",
  "ab_test_opportunity": "specific A/B test hypothesis or none",
  "verdict": "ship" | "measure_first" | "reconsider"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        architect = inputs.get("architect", {})
        if architect.get("proposal"):
            parts.append(f"## Architectural Proposal\n{architect['proposal']}")
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        insights = inputs.get("insights", {})
        if insights.get("success_criteria"):
            criteria = "\n".join(f"- {c}" for c in insights["success_criteria"])
            parts.append(f"## Success Criteria\n{criteria}")
        if insights.get("metrics"):
            metrics = "\n".join(f"- {m}" for m in insights["metrics"])
            parts.append(f"## Metrics\n{metrics}")
        if insights.get("verdict"):
            parts.append(f"## Measurability Verdict\n{insights['verdict']}")
        return "\n\n".join(parts) if parts else "No context available."
