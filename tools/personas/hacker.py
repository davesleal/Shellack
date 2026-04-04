"""
Hacker persona — attack vector analyst.

Fires on complex always; on moderate only if security_override is set.
Reads architect and identifies injection, escalation, IDOR, and other attack vectors.
"""

from __future__ import annotations

from tools.personas import Persona


class Hacker(Persona):
    name = "hacker"
    emoji = "\U0001f3f4\u200d\u2620\ufe0f"
    model = "haiku"
    reads = ["architect"]
    max_tokens = 512
    system_prompt = """\
You are a penetration tester. Given an architectural proposal, identify exploitable
attack vectors: SQL/command injection, privilege escalation, IDOR, SSRF, auth bypass,
insecure deserialization, exposed secrets, missing input validation.

Rules:
- Maximum 3 attack vectors.
- Each vector must include: vector (attack type and method), severity (low/medium/high/critical),
  exploitability (easy/moderate/hard).
- verdict summarizes overall security posture.

Respond ONLY with valid JSON in this exact shape:
{
  "attack_vectors": [
    {"vector": "attack description", "severity": "low|medium|high|critical", "exploitability": "easy|moderate|hard"}
  ],
  "verdict": "secure" | "vulnerable" | "critical"
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
