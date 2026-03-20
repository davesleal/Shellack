"""
UsageTracker — tracks Shellack session/mention counts and API token usage.

Persists to usage.json in the Shellack root. Monthly reset: on every read,
compare the stored reset_month to the current month — if different, zero all
counters and update reset_month. No cron required.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from typing import Any, Dict

_DEFAULT_STATE: Dict[str, Any] = {
    "reset_month": "",
    "session_count": 0,
    "mention_count": 0,
    "tokens_in": 0,
    "tokens_out": 0,
    "estimated_cost": 0.0,
    "mode": "api",
    "model": "claude-sonnet-4-6",
}

# Cost per million tokens: (input_price, output_price)
_MODEL_PRICING: Dict[str, tuple] = {
    "claude-opus-4-6": (15.0, 75.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (0.25, 1.25),
}

USAGE_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "usage.json")


class UsageTracker:
    def __init__(self, path: str = USAGE_FILE) -> None:
        self._path = path
        self._lock = threading.Lock()

    def _current_month(self) -> str:
        return datetime.now().strftime("%Y-%m")

    def _load(self) -> Dict[str, Any]:
        """Load state from file, applying a monthly reset if needed."""
        try:
            with open(self._path) as f:
                state = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            state = dict(_DEFAULT_STATE)

        if state.get("reset_month") != self._current_month():
            state = dict(_DEFAULT_STATE)
            state["reset_month"] = self._current_month()

        return state

    def _save(self, state: Dict[str, Any]) -> None:
        with open(self._path, "w") as f:
            json.dump(state, f, indent=2)

    def record_session(
        self, mode: str, model: str, tokens_in: int = 0, tokens_out: int = 0
    ) -> None:
        """Increment session count; add tokens/cost for API mode only."""
        with self._lock:
            state = self._load()
            state["session_count"] += 1
            state["mode"] = mode
            state["model"] = model
            if mode == "api" and (tokens_in or tokens_out):
                state["tokens_in"] += tokens_in
                state["tokens_out"] += tokens_out
                pricing = _MODEL_PRICING.get(model, (3.0, 15.0))
                cost = (tokens_in / 1_000_000 * pricing[0]) + (
                    tokens_out / 1_000_000 * pricing[1]
                )
                state["estimated_cost"] = round(state["estimated_cost"] + cost, 4)
            self._save(state)

    def record_mention(self, mode: str, model: str) -> None:
        """Increment quick-reply mention count."""
        with self._lock:
            state = self._load()
            state["mention_count"] += 1
            state["mode"] = mode
            state["model"] = model
            self._save(state)

    def get_stats(self) -> Dict[str, Any]:
        """Return current stats, applying monthly reset if needed."""
        with self._lock:
            return self._load()

    def format_usage_message(self) -> str:
        """Return a formatted Slack message string for @Shellack usage.

        Mode and model are read from os.environ (live values) so the display
        always reflects current config, even right after a monthly reset.
        """
        stats = self.get_stats()
        mode = os.environ.get("SESSION_BACKEND", stats.get("mode", "api"))
        model = os.environ.get("SESSION_MODEL", stats.get("model", "claude-sonnet-4-6"))
        month = stats.get("reset_month") or self._current_month()
        try:
            month_label = datetime.strptime(month, "%Y-%m").strftime("%B %Y")
        except ValueError:
            month_label = month

        lines = [
            f"🦞 *Shellack — Usage ({month_label})*",
            f"Mode: {'Claude Max' if mode == 'max' else 'Anthropic API'}",
        ]
        if mode == "api":
            lines.append(f"Model: `{model}`")
        else:
            lines.append("Model: Subscription")
        lines += [
            f"Run sessions: {stats['session_count']}",
            f"Quick replies: {stats['mention_count']} @mentions",
        ]
        if mode == "api":
            lines += [
                f"Tokens in: {stats['tokens_in']:,}",
                f"Tokens out: {stats['tokens_out']:,}",
                f"Est. cost: ~${stats['estimated_cost']:.2f}",
            ]
        else:
            lines.append("API cost: $0.00 ✓")
        return "\n".join(lines)
