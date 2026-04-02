"""Animated thinking indicator for Slack threads.

Posts a clay-colored attachment that cycles through activity verbs while the
agent is working. Replaces itself with a gray completion message when done.
"""
from __future__ import annotations

import logging
import random
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

_VERBS = [
    "Accomplishing", "Actioning", "Actualizing", "Baking", "Booping",
    "Brewing", "Calculating", "Cerebrating", "Channelling", "Churning",
    "Clauding", "Coalescing", "Cogitating", "Combobulating", "Computing",
    "Concocting", "Conjuring", "Considering", "Contemplating", "Cooking",
    "Crafting", "Creating", "Crunching", "Deciphering", "Deliberating",
    "Determining", "Discombobulating", "Divining", "Doing", "Effecting",
    "Elucidating", "Enchanting", "Envisioning", "Finagling", "Flibbertigibbeting",
    "Forging", "Forming", "Frolicking", "Generating", "Germinating",
    "Hatching", "Herding", "Honking", "Hustling", "Ideating",
    "Imagining", "Incubating", "Inferring", "Jiving", "Manifesting",
    "Marinating", "Meandering", "Moseying", "Mulling", "Mustering",
    "Musing", "Noodling", "Percolating", "Perusing", "Philosophising",
    "Pondering", "Pontificating", "Processing", "Puttering", "Puzzling",
    "Reticulating", "Ruminating", "Scheming", "Schlepping", "Shellacking", "Shimmying",
    "Shucking", "Simmering", "Smooshing", "Spelunking", "Spinning",
    "Stewing", "Sussing", "Synthesizing", "Thinking", "Tinkering",
    "Transmuting", "Unfurling", "Unravelling", "Vibing", "Wandering",
    "Whirring", "Wibbling", "Wizarding", "Working", "Wrangling",
]

_CLAY = "#C17F4E"
_GRAY = "#888888"
_UPDATE_INTERVAL = 5.0  # seconds between verb rotations


def _fmt_tokens(n: int) -> str:
    return f"{n / 1000:.1f}k" if n >= 1000 else str(n)


def _fmt_elapsed(seconds: float) -> str:
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m}m {s}s" if m else f"{s}s"


class ThinkingIndicator:
    """Animated clay-colored Slack message that cycles verbs while the agent thinks.

    Usage:
        indicator = ThinkingIndicator(app.client, channel_id, thread_ts)
        indicator.start(input_tokens=1200)
        # ... agent work ...
        indicator.done()
    """

    def __init__(self, client, channel_id: str, thread_ts: str):
        self._client = client
        self._channel_id = channel_id
        self._thread_ts = thread_ts
        self._ts: Optional[str] = None
        self._start: float = 0.0
        self._input_tokens: int = 0
        self._stop = threading.Event()
        self._bg: Optional[threading.Thread] = None

    def start(self, input_tokens: int = 0) -> None:
        """Post the initial indicator message and start the background update loop."""
        self._start = time.monotonic()
        self._input_tokens = input_tokens
        verb = random.choice(_VERBS)
        text = self._render(verb)
        try:
            resp = self._client.chat_postMessage(
                channel=self._channel_id,
                thread_ts=self._thread_ts,
                text="",
                attachments=[{"color": _CLAY, "text": text, "fallback": text}],
            )
            self._ts = resp["ts"]
        except Exception as exc:
            logger.warning(f"ThinkingIndicator: failed to post: {exc}")
            return

        self._stop.clear()
        self._bg = threading.Thread(target=self._loop, daemon=True)
        self._bg.start()

    def _render(self, verb: str) -> str:
        elapsed = time.monotonic() - self._start
        suffix = f"({_fmt_elapsed(elapsed)}"
        if self._input_tokens:
            suffix += f" · ↑ {_fmt_tokens(self._input_tokens)}"
        suffix += ")"
        return f"{verb}… {suffix}"

    def _loop(self) -> None:
        while not self._stop.wait(_UPDATE_INTERVAL):
            if not self._ts:
                return
            verb = random.choice(_VERBS)
            text = self._render(verb)
            try:
                self._client.chat_update(
                    channel=self._channel_id,
                    ts=self._ts,
                    text="",
                    attachments=[{"color": _CLAY, "text": text, "fallback": text}],
                )
            except Exception as exc:
                logger.warning(f"ThinkingIndicator: update failed: {exc}")

    def done(self, response: str = "", cost_summary: str = "") -> None:
        """Stop cycling and replace the message with the churned summary + response."""
        self._stop.set()
        if self._bg:
            self._bg.join(timeout=2.0)
        if not self._ts:
            return
        elapsed = time.monotonic() - self._start
        header = f"✻ Churned for {_fmt_elapsed(elapsed)}"
        if cost_summary:
            header += f" · {cost_summary}"
        body = f"{header}\n\n{response}" if response else header
        try:
            self._client.chat_update(
                channel=self._channel_id,
                ts=self._ts,
                text="",
                attachments=[{"color": _GRAY, "text": body, "fallback": header}],
            )
        except Exception as exc:
            logger.warning(f"ThinkingIndicator: done update failed: {exc}")
            # Fallback: stamp the indicator as done, post response separately
            try:
                self._client.chat_update(
                    channel=self._channel_id,
                    ts=self._ts,
                    text="",
                    attachments=[{"color": _GRAY, "text": header, "fallback": header}],
                )
            except Exception:
                pass
            if response:
                try:
                    self._client.chat_postMessage(
                        channel=self._channel_id,
                        thread_ts=self._thread_ts,
                        text=response,
                    )
                except Exception:
                    pass
