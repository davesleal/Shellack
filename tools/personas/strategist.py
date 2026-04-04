"""
Strategist persona — task decomposition and sequencing.

Fires on moderate and complex turns. Reads observer + token_cart,
produces a decomposed task plan with sequence and dependencies.
"""

from __future__ import annotations

from tools.personas import Persona


class Strategist(Persona):
    name = "strategist"
    emoji = "\U0001f3af"
    model = "haiku"
    reads = ["observer", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a task strategist. Given context about a user's request, decompose it into
concrete tasks, determine their sequence, and identify dependencies.

Rules:
- Maximum 6 tasks.
- Tasks should be atomic and actionable.
- Sequence is a list of task indices (0-based) in execution order.
- Dependencies is a list of [task_index, depends_on_index] pairs.

Respond ONLY with valid JSON in this exact shape:
{
  "tasks": ["task description", ...],
  "sequence": [0, 1, 2, ...],
  "dependencies": [[1, 0], ...],
  "estimated_complexity": "simple" | "moderate" | "complex"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        observer = inputs.get("observer", {})
        if observer.get("summary"):
            parts.append(f"## Request Summary\n{observer['summary']}")
        if observer.get("intent"):
            parts.append(f"## Intent\n{observer['intent']}")
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("budget_remaining") is not None:
            parts.append(f"## Token Budget Remaining\n{token_cart['budget_remaining']}")
        return "\n\n".join(parts) if parts else "No context available."
