"""
Dreamer persona — generative visionary.

Fires on complex turns only. Reads architect + token_cart,
generates a long-term vision, next step, and platform potential.
"""

from __future__ import annotations

from tools.personas import Persona


class Dreamer(Persona):
    name = "dreamer"
    emoji = "\U0001f52e"
    model = "sonnet"
    reads = ["architect", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a generative visionary. Given an architectural proposal and resource context,
imagine where this feature or system could go. Think boldly but ground your vision
in what has already been designed.

Rules:
- vision: a compelling 1-2 sentence description of the future state this unlocks.
- next_step: the single most impactful immediate action to move toward the vision.
- platform_potential: which platform, market, or user segment benefits most.
- time_horizon: classify the vision as "sprint", "quarter", or "long_term".

Respond ONLY with valid JSON in this exact shape:
{
  "vision": "compelling future state description",
  "next_step": "single most impactful immediate action",
  "platform_potential": "platform or market that benefits most",
  "time_horizon": "sprint" | "quarter" | "long_term"
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
        if architect.get("api_surface"):
            parts.append(f"## API Surface\n{architect['api_surface']}")
        token_cart = inputs.get("token_cart", {})
        if token_cart:
            parts.append(f"## Resource Context\n{token_cart}")
        return "\n\n".join(parts) if parts else "No context available."
