# tools/session_backend.py
"""
Session backends for Slack Terminal Tunnel.

SessionBackend is the abstract interface. Two implementations:
- APIBackend: Anthropic SDK streaming, manages conversation history.
- MaxBackend: claude CLI subprocess per turn, --session-id / --resume for continuity.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from typing import Generator, Optional

from anthropic import Anthropic


class SessionBackend(ABC):
    """Abstract base for Claude session backends."""

    @abstractmethod
    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        """Start session with initial task. Yields text chunks."""
        ...

    @abstractmethod
    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        """Continue session with user input. Yields text chunks."""
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by this backend."""
        ...


class APIBackend(SessionBackend):
    """Anthropic SDK streaming backend. Costs API credits per token."""

    def __init__(self, model: str = "claude-sonnet-4-6"):
        self._client = Anthropic()
        self._model = model
        self._history: list[dict] = []
        self._system: str = ""
        self._started = False

    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        self._system = system_prompt
        self._history = [{"role": "user", "content": task}]
        self._started = True
        yield from self._stream()

    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        if not self._started:
            raise RuntimeError("next_turn called before first_turn")
        self._history.append({"role": "user", "content": user_input})
        yield from self._stream()

    def _stream(self) -> Generator[str, None, None]:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": 8096,
            "messages": self._history,
        }
        if self._system:
            kwargs["system"] = self._system

        assistant_text = ""
        try:
            with self._client.messages.stream(**kwargs) as stream:
                for text in stream.text_stream:
                    assistant_text += text
                    yield text
        except Exception:
            # Pop the user message we just appended so history stays consistent
            if self._history and self._history[-1]["role"] == "user":
                self._history.pop()
            raise

        self._history.append({"role": "assistant", "content": assistant_text})

    def close(self) -> None:
        self._history.clear()
        self._started = False
        self._system = ""
