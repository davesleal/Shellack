"""Agent discussion log — collects inter-agent chatter for transparency."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Agent emoji personas
AGENT_EMOJI = {
    # Infrastructure (always active)
    "observer": "\U0001f441\ufe0f",       # 👁️
    "file_fetcher": "\U0001f4c2",          # 📂
    "token_cart": "\U0001f6d2",            # 🛒
    "agent_manager": "\U0001f4cb",         # 📋
    # Phase 3: Plan & Research
    "strategist": "\U0001f3af",            # 🎯
    "researcher": "\U0001f310",            # 🌐
    "historian": "\U0001f4dc",             # 📜
    # Phase 4: Design & Propose
    "architect": "\U0001f4d0",             # 📐
    "specialist": "\U0001f9ec",            # 🧬
    "data_scientist": "\U0001f4ca",        # 📊
    "empathizer": "\U0001fac2",            # 🫂
    "connector": "\U0001f517",             # 🔗
    "reuser": "\u267b\ufe0f",             # ♻️
    # Phase 5: Vision & Measurement
    "dreamer": "\U0001f52e",               # 🔮
    "insights": "\U0001f4c9",              # 📉
    "growth_coach": "\U0001f4c8",          # 📈
    # Phase 6: Challenge
    "skeptic": "\U0001f928",               # 🤨
    "devils_advocate": "\U0001f479",       # 👹
    "simplifier": "\u2702\ufe0f",          # ✂️
    "prioritizer": "\u2696\ufe0f",         # ⚖️
    # Phase 7: Security
    "rogue": "\U0001f608",                 # 😈
    "hacker": "\U0001f3f4\u200d\u2620\ufe0f",  # 🏴‍☠️
    "infosec": "\U0001f6e1\ufe0f",         # 🛡️
    # Phase 8: Quality Gate
    "inspector": "\U0001f50d",             # 🔍
    "tester": "\U0001f9ea",                # 🧪
    "visual_ux": "\U0001f3a8",             # 🎨
    # Phase 9: Synthesis
    "learner": "\U0001f9e0",               # 🧠
    "coach": "\U0001f4aa",                 # 💪
    "output_editor": "\u270d\ufe0f",       # ✍️
    # Legacy (kept for backwards compat during migration)
    "gut_check": "\u2705",                 # ✅
    "correction": "\U0001f504",            # 🔄
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

    def add_phase_header(self, phase_id: str, emoji: str, label: str) -> None:
        """Add a phase separator header."""
        self._entries.append(f"\n{emoji} {label}")

    def add_phase_entries(self, phase_name: str, phase_emoji: str, entries: list[str]) -> None:
        """Add a full phase block: header + indented entries."""
        if not entries:
            return
        self.add_phase_header(phase_name, phase_emoji, phase_name.replace("_", " ").title())
        for entry in entries:
            self._entries.append(f"  {entry}")
