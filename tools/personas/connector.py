"""
Connector persona — cross-project pattern matching.

Fires on complex turns only. Reads architect + token_cart,
identifies patterns from other projects that could be reused or adapted.
"""

from __future__ import annotations

from tools.personas import Persona


class Connector(Persona):
    name = "connector"
    emoji = "\U0001f517"
    model = "haiku"
    reads = ["architect", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a cross-project connector. Given an architectural proposal and project registry,
identify similar patterns from other projects and reuse opportunities.

Rules:
- similar_patterns lists patterns from other projects that match the current proposal.
- Each pattern must include: project (project name), pattern (what the pattern is), relevance (how it applies here).
- reuse_opportunities lists specific components, modules, or patterns that could be directly reused.

Respond ONLY with valid JSON in this exact shape:
{
  "similar_patterns": [
    {"project": "project name", "pattern": "pattern description", "relevance": "how it applies"}
  ],
  "reuse_opportunities": ["reuse opportunity description", ...]
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
        token_cart = inputs.get("token_cart", {})
        if token_cart.get("enriched_prompt"):
            parts.append(f"## Enriched Prompt\n{token_cart['enriched_prompt']}")
        if token_cart.get("registry"):
            parts.append(f"## Registry\n{token_cart['registry']}")
        return "\n\n".join(parts) if parts else "No context available."
