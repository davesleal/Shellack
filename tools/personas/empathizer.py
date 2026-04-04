"""
Empathizer persona — user-facing friction analysis.

Fires on complex turns only. Reads architect + observer,
identifies friction points in the user experience.
"""

from __future__ import annotations

from tools.personas import Persona


class Empathizer(Persona):
    name = "empathizer"
    emoji = "\U0001fac2"
    model = "haiku"
    reads = ["architect", "observer"]
    max_tokens = 512
    system_prompt = """\
You are a UX empathizer. Given an architectural proposal and the original user request,
identify friction points in the user-facing experience.

Rules:
- friction_points lists UI/UX elements that could cause user confusion or frustration.
- Each point must include: element (what UI/UX element), issue (what's wrong), suggestion (how to fix it).
- verdict summarizes the overall user experience quality.

Respond ONLY with valid JSON in this exact shape:
{
  "friction_points": [
    {"element": "UI element name", "issue": "what is wrong", "suggestion": "how to improve it"}
  ],
  "verdict": "smooth" | "rough" | "blocking"
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
        observer = inputs.get("observer", {})
        if observer.get("summary"):
            parts.append(f"## User Request\n{observer['summary']}")
        if observer.get("intent"):
            parts.append(f"## User Intent\n{observer['intent']}")
        return "\n\n".join(parts) if parts else "No context available."
