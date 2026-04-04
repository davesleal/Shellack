"""
Infosec persona — defensive security prescriptions.

Fires on complex always; on moderate only if security_override is set.
Reads architect + rogue + hacker and prescribes mitigations.
A "blocker" verdict is non-negotiable and triggers a micro-loop back to Architect.
"""

from __future__ import annotations

from tools.personas import Persona


class Infosec(Persona):
    name = "infosec"
    emoji = "\U0001f6e1\ufe0f"
    model = "sonnet"
    reads = ["architect", "rogue", "hacker"]
    max_tokens = 768
    system_prompt = """\
You are a defensive security engineer. Given an architectural proposal, stress scenarios,
and identified attack vectors, prescribe concrete mitigations and security controls.

Rules:
- Address every identified threat from Rogue and Hacker outputs.
- Each mitigation must include: threat (what is being mitigated), defense (concrete control or fix),
  priority (low/medium/high/critical).
- verdict: "clear" if no critical issues, "mitigable" if issues exist but are addressable,
  "blocker" if critical unmitigable security flaws that must be resolved before shipping.
- A "blocker" verdict triggers a revision loop back to Architect — it is non-negotiable.

Respond ONLY with valid JSON in this exact shape:
{
  "mitigations": [
    {"threat": "threat description", "defense": "concrete control", "priority": "low|medium|high|critical"}
  ],
  "verdict": "clear" | "mitigable" | "blocker"
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
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        rogue = inputs.get("rogue", {})
        if rogue.get("stress_scenarios"):
            scenarios_text = "\n".join(
                f"- {s['scenario']} (impact: {s['impact']}, likelihood: {s['likelihood']})"
                for s in rogue["stress_scenarios"]
            )
            parts.append(f"## Stress Scenarios\n{scenarios_text}")
        if rogue.get("verdict"):
            parts.append(f"## Rogue Verdict\n{rogue['verdict']}")
        hacker = inputs.get("hacker", {})
        if hacker.get("attack_vectors"):
            vectors_text = "\n".join(
                f"- {v['vector']} (severity: {v['severity']}, exploitability: {v['exploitability']})"
                for v in hacker["attack_vectors"]
            )
            parts.append(f"## Attack Vectors\n{vectors_text}")
        if hacker.get("verdict"):
            parts.append(f"## Hacker Verdict\n{hacker['verdict']}")
        return "\n\n".join(parts) if parts else "No context available."
