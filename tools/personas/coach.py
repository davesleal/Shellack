"""
Coach persona — final ship/iterate/hold decision.

Fires on complex turns only. Reads ALL slots in TurnContext and returns a
final verdict on whether the work is ready to ship, needs iteration, or must hold.

If any persona returned verdict "blocker", Coach MUST return "hold".
"""

from __future__ import annotations

from tools.personas import Persona


class Coach(Persona):
    name = "coach"
    emoji = "\U0001f4aa"
    model = "haiku"
    reads: list[str] = []  # special case: receives ALL slots
    max_tokens = 128
    system_prompt = """\
You are a senior engineering coach making the final go/no-go call.

Given the full context of a conversation turn, decide:
  "ship"    — work is complete and safe to release
  "iterate" — work is directionally correct but needs refinement
  "hold"    — work has a blocking issue that must be resolved first

Rules:
- If ANY persona verdict is "blocker", you MUST return "hold". No exceptions.
- confidence is a float between 0.0 and 1.0.
- reasoning must be a single concise sentence.

Respond ONLY with valid JSON in this exact shape:
{
  "verdict": "ship" | "iterate" | "hold",
  "confidence": 0.0,
  "reasoning": "one sentence explanation"
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
