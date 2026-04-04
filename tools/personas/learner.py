"""
Learner persona — lesson extractor.

Fires on complex turns only. Reads ALL slots in TurnContext and extracts
reusable lessons, patterns, and corrections from the full turn.

Persistence levels:
  "thread"    → store in thread memory
  "project"   → store in project registry
  "permanent" → update CLAUDE.md
"""

from __future__ import annotations

from tools.personas import Persona


class Learner(Persona):
    name = "learner"
    emoji = "\U0001f9e0"
    model = "haiku"
    reads: list[str] = []  # special case: receives ALL slots
    max_tokens = 512
    system_prompt = """\
You are a meta-learning agent. Given the full context of a conversation turn — including all
persona outputs, decisions, and outcomes — extract reusable lessons and flag any corrections.

Rules:
- Identify patterns that would help future turns of similar complexity.
- Assign persistence: "thread" for session-only insights, "project" for repo-level knowledge,
  "permanent" for universal principles worth adding to CLAUDE.md.
- corrections captures any errors, contradictions, or mis-steps that occurred during the turn.
- Be concise: max 5 lessons, max 3 corrections.

Respond ONLY with valid JSON in this exact shape:
{
  "lessons": [
    {"pattern": "short description", "insight": "what to do differently or reinforce", "persistence": "thread|project|permanent"}
  ],
  "corrections": [
    {"issue": "what went wrong", "fix": "what should have happened"}
  ]
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        if not inputs:
            return "No context available."
        parts = []
        for slot_name, slot_value in inputs.items():
            parts.append(f"## {slot_name}\n{slot_value!r}")
        return "\n\n".join(parts)
