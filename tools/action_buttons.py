"""Action buttons — detect numbered options in agent responses and render as Slack Block Kit buttons."""

from __future__ import annotations

import re
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# Match numbered list items: "1. Activity feed — description" or "1. **Activity feed** — description"
_OPTION_RE = re.compile(
    r"^\s*(\d+)\.\s+\**([^*\n—–-]+?)\**\s*[—–-]\s*(.+)$", re.MULTILINE
)

# Simpler pattern: "1. Activity feed" (no description after dash)
_OPTION_SIMPLE_RE = re.compile(r"^\s*(\d+)\.\s+\**([^*\n]+?)\**\s*$", re.MULTILINE)


def detect_options(text: str) -> list[dict]:
    """Detect numbered options in response text.

    Returns list of {"number": "1", "label": "Activity feed", "description": "auto-post..."} dicts.
    Max 5 options.
    """
    options = []

    # Try detailed pattern first
    for match in _OPTION_RE.finditer(text):
        options.append(
            {
                "number": match.group(1),
                "label": match.group(2).strip(),
                "description": match.group(3).strip()[:80],
            }
        )

    # Fall back to simple pattern if no detailed matches
    if not options:
        for match in _OPTION_SIMPLE_RE.finditer(text):
            options.append(
                {
                    "number": match.group(1),
                    "label": match.group(2).strip(),
                    "description": "",
                }
            )

    return options[:5]  # cap at 5 buttons


def format_buttons(options: list[dict], thread_ts: str) -> list[dict]:
    """Format options as Slack Block Kit action buttons.

    Returns blocks list for use in chat_postMessage.
    """
    if not options:
        return []

    buttons = []
    for opt in options:
        label = f"{opt['number']}. {opt['label']}"
        if len(label) > 75:
            label = label[:72] + "..."
        buttons.append(
            {
                "type": "button",
                "text": {"type": "plain_text", "text": label},
                "value": f"{thread_ts}|{opt['number']}|{opt['label']}",
                "action_id": f"shellack_option_{opt['number']}",
            }
        )

    return [
        {
            "type": "actions",
            "elements": buttons,
        }
    ]
