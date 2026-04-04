"""
Architect persona — structure, data models, API surface proposal.

Fires on moderate and complex turns. Reads strategist + historian + token_cart,
proposes system structure, data models, and API surface.
"""

from __future__ import annotations

from tools.personas import Persona


class Architect(Persona):
    name = "architect"
    emoji = "\U0001f4d0"
    model = "sonnet"
    reads = ["strategist", "historian", "token_cart"]
    max_tokens = 1024
    system_prompt = """\
You are a software architect. Given a task plan, prior decisions, and project context,
propose a concrete structure: data models, API surface, and files affected.

Rules:
- proposal is a brief narrative of the architectural approach.
- data_model describes entities, fields, and relationships in plain text.
- api_surface lists function/endpoint signatures (name, inputs, outputs).
- files_affected is a list of file paths that will need to be created or modified.

Respond ONLY with valid JSON in this exact shape:
{
  "proposal": "narrative description of the approach",
  "data_model": "entities and relationships description",
  "api_surface": "function/endpoint signatures",
  "files_affected": ["path/to/file.py", ...]
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity in ("moderate", "complex")

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        strategist = inputs.get("strategist", {})
        if strategist.get("tasks"):
            tasks_text = "\n".join(f"- {t}" for t in strategist["tasks"])
            parts.append(f"## Planned Tasks\n{tasks_text}")
        if strategist.get("estimated_complexity"):
            parts.append(f"## Estimated Complexity\n{strategist['estimated_complexity']}")
        historian = inputs.get("historian", {})
        if historian.get("prior_decisions"):
            decisions_text = "\n".join(f"- {d}" for d in historian["prior_decisions"])
            parts.append(f"## Prior Decisions\n{decisions_text}")
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Enriched Prompt\n{token_cart['enriched_prompt']}")
        if token_cart.get("registry"):
            parts.append(f"## Registry\n{token_cart['registry']}")
        return "\n\n".join(parts) if parts else "No context available."
