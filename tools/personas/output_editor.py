"""
Output Editor persona — polishes final output for target medium.

Fires on complex turns only. Reads coach verdict and token_cart to
produce a polished, medium-appropriate version of the output.
"""

from __future__ import annotations

from tools.personas import Persona


class OutputEditor(Persona):
    name = "output_editor"
    emoji = "\u270d\ufe0f"
    model = "sonnet"
    reads = ["coach", "token_cart"]
    max_tokens = 512
    system_prompt = """\
You are a technical editor. Given the coach's verdict and the turn's token inventory,
produce a polished final output targeted at the appropriate delivery medium.

Delivery mediums:
  "slack"   — concise, scannable, uses Slack mrkdwn (*bold*, `code`, bullet lists)
  "github"  — structured markdown, suitable for PR descriptions or issue comments
  "docs"    — prose-style, complete, suitable for documentation or README sections

Rules:
- Infer the correct format from context (mention of PR/issue → github, mention of docs/README → docs, otherwise → slack).
- polished_output must be ready to send without further editing.
- Do not include the coach verdict itself in the output; it is context only.

Respond ONLY with valid JSON in this exact shape:
{
  "polished_output": "the final formatted text",
  "format": "slack" | "github" | "docs"
}"""

    def should_activate(self, complexity: str, turn_context: dict) -> bool:
        return complexity == "complex"

    def _build_user_content(self, inputs: dict[str, dict]) -> str:
        parts = []
        coach = inputs.get("coach", {})
        if coach.get("verdict"):
            parts.append(f"## Coach Verdict\n{coach['verdict']} (confidence: {coach.get('confidence', 'N/A')})")
        if coach.get("reasoning"):
            parts.append(f"## Coach Reasoning\n{coach['reasoning']}")
        token_cart = inputs.get("token_cart", {})
        if token_cart:
            parts.append(f"## Token Cart\n{token_cart!r}")
        return "\n\n".join(parts) if parts else "No context available."
