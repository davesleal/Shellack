"""
SlackClaw — Slack↔Terminal Bridge utilities

Provides Block Kit formatting for interactive Claude Code input prompts,
project channel detection, and session-start notification.
"""

from __future__ import annotations

import logging
import re
import subprocess
import sys

import requests

from orchestrator_config import CHANNEL_ROUTING, PROJECTS

_FALLBACK_CHANNEL_ID = "C0AMEEP7EFL"  # #claude-code
_FALLBACK_PROJECT = "Unknown"

logger = logging.getLogger(__name__)


def format_bridge_blocks(
    question: str,
    options: list[str],
    session_id: str,
    input_type: str = "choice",
) -> list[dict]:
    """Return Block Kit blocks for a bridge input prompt.

    Each button's action_id is ``"claude_bridge_input"`` and its value is
    ``"{session_id}|{option_value}"``.  Options are split into rows of 5
    (Slack's limit per ``actions`` block).

    When ``input_type="confirm"``, ``options`` is ignored; the buttons are
    always "Yes" (value: "yes") and "No" (value: "no").
    When ``input_type="choice"``, each item in ``options`` becomes one button.
    """
    blocks: list[dict] = [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": question},
        }
    ]

    if input_type == "confirm":
        btn_options = [("Yes", "yes"), ("No", "no")]
    else:
        btn_options = [(opt, opt) for opt in options]

    # Split into rows of 5 (Slack limit per actions block)
    for i in range(0, max(len(btn_options), 1), 5):
        row = btn_options[i : i + 5]
        blocks.append(
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": label},
                        "value": f"{session_id}|{value}",
                        "action_id": "claude_bridge_input",
                    }
                    for label, value in row
                ],
            }
        )

    return blocks


def detect_channel_id() -> tuple[str, str]:
    """Return (channel_id, project_name) for the current git repo.

    Looks up the git remote URL, normalises it to ``owner/repo``, then
    matches against ``PROJECTS``.  Falls back to ``#claude-code`` for
    unknown repos or any error.  Logs a stderr warning when a project is
    recognised but its CHANNEL_ROUTING entry is missing ``channel_id``
    (misconfiguration that would cause silent wrong-channel routing).
    """
    try:
        remote = subprocess.check_output(
            ["git", "remote", "get-url", "origin"],
            stderr=subprocess.DEVNULL,
        ).decode().strip()
        slug = re.sub(r"\.git$", "", remote)
        slug = re.sub(r"^git@github\.com:", "", slug)
        slug = re.sub(r"^https://github\.com/", "", slug)

        for _key, cfg in PROJECTS.items():
            if cfg.get("github_repo") == slug:
                primary = cfg.get("primary_channel", "")
                routing = CHANNEL_ROUTING.get(primary, {})
                channel_id = routing.get("channel_id", "")
                if channel_id:
                    return channel_id, cfg["name"]
                # Recognised project but channel_id not yet configured
                print(
                    f"[claude-slack] WARNING: project '{cfg['name']}' matched but "
                    f"CHANNEL_ROUTING['{primary}'] has no 'channel_id'. "
                    "Add channel_id to orchestrator_config.py. "
                    "Falling back to #claude-code.",
                    file=sys.stderr,
                )
                return _FALLBACK_CHANNEL_ID, cfg["name"]
    except Exception:
        pass
    return _FALLBACK_CHANNEL_ID, _FALLBACK_PROJECT


def post_session_start(channel_id: str, project_name: str) -> None:
    """Post a session-start message to Slack via direct API call.

    ``claude-slack`` is a standalone script with no Bolt App instance, so we
    call the Slack Web API directly.  Raises ``requests.HTTPError`` on HTTP
    failures.  Logs a warning (but does not raise) on Slack application-level
    errors (e.g. ``channel_not_found``).
    """
    import os
    token = os.environ["SLACK_BOT_TOKEN"]
    resp = requests.post(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "channel": channel_id,
            "text": f"🟢 Claude Code session started — *{project_name}*",
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if not data.get("ok"):
        logger.warning("[claude-slack] post_session_start failed: %s", data.get("error"))
