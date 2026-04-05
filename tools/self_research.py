"""Self-research — multi-step autonomous investigation for complex questions.

When the Toolkeeper's single-pass context gathering isn't enough (e.g., tracing
call chains, understanding subsystems, correlating git history with code), this
module runs a Haiku-driven loop that iteratively executes safe read-only commands
and accumulates findings until it has enough context to answer.

Reuses the safety infrastructure from Toolkeeper (same whitelist, same runner).
"""

from __future__ import annotations

import json
import logging
import re

from anthropic import Anthropic

from tools.personas.toolkeeper import _is_safe_command, _run_command

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_MAX_STEPS_DEFAULT = 5
_TOTAL_OUTPUT_CAP = 8000  # chars across all command outputs
_HAIKU_MAX_TOKENS = 512

_SYSTEM_PROMPT = (
    "You are a research assistant investigating a codebase question. "
    "You can run one safe read-only command per step. "
    "Respond with JSON: {\"done\": bool, \"command\": str|null, \"summary\": str}. "
    "When done=true, put your final answer in summary."
)


def run_research(
    question: str,
    project_path: str,
    max_steps: int = _MAX_STEPS_DEFAULT,
    client: Anthropic | None = None,
) -> dict:
    """Run a multi-step research loop to investigate a codebase question.

    Args:
        question: The user's question to investigate.
        project_path: Filesystem path to the project root.
        max_steps: Hard cap on iterations (default 5).
        client: Optional Anthropic client (created if not provided).

    Returns:
        {"findings": str, "commands_run": list[str], "steps": int}
    """
    if client is None:
        client = Anthropic()

    commands_run: list[str] = []
    findings: list[str] = []
    total_output_len = 0

    for step in range(max_steps):
        # Build user message with accumulated context
        user_parts = [f"## Question\n{question}"]
        if findings:
            user_parts.append(
                "## Findings So Far\n" + "\n\n".join(findings)
            )
        if step > 0:
            user_parts.append(
                f"Step {step + 1} of {max_steps}. "
                "If you have enough information, set done=true."
            )
        user_content = "\n\n".join(user_parts)

        # Call Haiku
        try:
            msg = client.messages.create(
                model=_MODEL,
                max_tokens=_HAIKU_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            raw = msg.content[0].text.strip()
        except Exception as exc:
            logger.warning(f"Self-research Haiku call failed at step {step}: {exc}")
            break

        # Parse JSON response
        decision = _parse_decision(raw)
        if decision is None:
            logger.warning(f"Self-research: unparseable Haiku response at step {step}")
            break

        # Check for done
        if decision.get("done"):
            summary = decision.get("summary", "")
            if summary:
                findings.append(f"### Final Summary\n{summary}")
            return {
                "findings": "\n\n".join(findings),
                "commands_run": commands_run,
                "steps": step + 1,
            }

        # Execute command
        command = decision.get("command")
        if not command or not isinstance(command, str):
            logger.info("Self-research: Haiku returned no command, treating as done")
            break

        command = command.strip()

        # Safety check
        if not _is_safe_command(command):
            findings.append(f"BLOCKED: `{command[:80]}` — not in safe command list")
            logger.warning(f"Self-research blocked unsafe command: {command[:80]}")
            continue  # Don't count blocked commands toward meaningful steps

        # Output cap check
        if total_output_len >= _TOTAL_OUTPUT_CAP:
            findings.append("Output cap reached — stopping research.")
            break

        # Run it
        output = _run_command(command, project_path)
        commands_run.append(command)

        # Enforce total output cap
        remaining = _TOTAL_OUTPUT_CAP - total_output_len
        if len(output) > remaining:
            output = output[:remaining] + "\n... (output cap reached)"
        total_output_len += len(output)

        findings.append(f"$ {command}\n{output}")

        summary = decision.get("summary", "")
        if summary:
            findings.append(f"*Observation:* {summary}")

        logger.info(
            f"Self-research step {step + 1}: {command[:60]} "
            f"({len(output)} chars, total {total_output_len})"
        )

    return {
        "findings": "\n\n".join(findings),
        "commands_run": commands_run,
        "steps": len(commands_run),
    }


def _parse_decision(raw: str) -> dict | None:
    """Extract JSON from Haiku's response, handling markdown fences."""
    # Strip markdown code fences
    cleaned = re.sub(r"^```[a-z]*\n?", "", raw).rstrip("`").strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to find JSON object in the text
        match = re.search(r"\{[^{}]+\}", cleaned, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
    return None
