"""Agent discussion log — collects inter-agent chatter for transparency."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Agent emoji personas
AGENT_EMOJI = {
    "observer": "\U0001f441\ufe0f",  # 👁️
    "file_fetcher": "\U0001f4c2",  # 📂
    "token_cart": "\U0001f6d2",  # 🛒
    "gut_check": "\u2705",  # ✅
    "infosec": "\U0001f6e1\ufe0f",  # 🛡️
    "architect": "\U0001f4d0",  # 📐
    "tester": "\U0001f9ea",  # 🧪
    "visual_ux": "\U0001f3a8",  # 🎨
    "output_editor": "\u270d\ufe0f",  # ✍️
    "agent_manager": "\U0001f4cb",  # 📋
    "correction": "\U0001f504",  # 🔄
}


class DiscussionLog:
    """Collects agent discussion entries for a single turn."""

    def __init__(self):
        self._entries: list[str] = []

    def add(self, agent: str, message: str) -> None:
        """Add a discussion entry. agent is a key from AGENT_EMOJI."""
        emoji = AGENT_EMOJI.get(agent, "\U0001f916")  # 🤖 fallback
        self._entries.append(f"{emoji} {message}")

    @property
    def entries(self) -> list[str]:
        return self._entries

    def format(self) -> str:
        """Format as a collapsible discussion block for Slack."""
        if not self._entries:
            return ""
        lines = "\n".join(self._entries)
        return f"\U0001f4ac Agent Discussion\n```\n{lines}\n```"

    def is_empty(self) -> bool:
        return len(self._entries) == 0
