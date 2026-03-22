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


class MaxBackend(SessionBackend):
    """Claude CLI subprocess backend. Uses Max subscription — zero API cost.

    Design: each turn spawns a fresh `claude -p` subprocess.
    - first_turn: passes --session-id <uuid> so Claude Code persists the
      conversation under our pre-assigned ID.
    - next_turn: passes --resume <uuid> to continue that exact conversation.

    This gives per-session isolation with no --continue collision risk.
    Requires: `claude` CLI on PATH, `--output-format stream-json --verbose`.

    Thread safety: all backend calls must be serialized by the caller (SlackSession).
    """

    def __init__(self) -> None:
        self._session_id: Optional[str] = None
        self._cwd: str = "."

    def first_turn(
        self, task: str, system_prompt: str = "", cwd: str = "."
    ) -> Generator[str, None, None]:
        self._cwd = cwd
        self._session_id = str(uuid.uuid4())
        cmd = [
            "claude",
            "-p",
            task,
            "--output-format",
            "stream-json",
            "--verbose",
            "--session-id",
            self._session_id,
        ]
        if system_prompt:
            cmd += ["--system-prompt", system_prompt]
        yield from self._run(cmd)

    def next_turn(self, user_input: str) -> Generator[str, None, None]:
        if self._session_id is None:
            raise RuntimeError("next_turn called before first_turn")
        cmd = [
            "claude",
            "-p",
            user_input,
            "--output-format",
            "stream-json",
            "--verbose",
            "--resume",
            self._session_id,
        ]
        yield from self._run(cmd)

    def _run(self, cmd: list[str]) -> Generator[str, None, None]:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=self._cwd,
        )
        try:
            for line in proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if event.get("type") == "assistant":
                    for block in event.get("message", {}).get("content", []):
                        if isinstance(block, dict) and block.get("type") == "text":
                            yield block["text"]
        finally:
            # Drain and close stdout to unblock the subprocess, then terminate it
            try:
                proc.stdout.read()
            except Exception:
                pass
            proc.stdout.close()
            proc.terminate()
            proc.wait()
            # Check exit code — non-zero means claude CLI errored
            if proc.returncode not in (0, -15):  # -15 = SIGTERM (our terminate)
                stderr_output = proc.stderr.read() if proc.stderr else ""
                proc.stderr.close()
                raise RuntimeError(
                    f"claude CLI exited with code {proc.returncode}: {stderr_output.strip()}"
                )
            if proc.stderr:
                proc.stderr.close()

    @classmethod
    def available(cls) -> bool:
        """Return True if `claude` CLI is on PATH."""
        return shutil.which("claude") is not None

    def close(self) -> None:
        self._session_id = None


def quick_reply(
    prompt: str,
    system_prompt: str = "",
    cwd: str = ".",
    model: str | None = None,  # overrides SESSION_MODEL env var; ignored in max mode
) -> str:
    """Single-turn AI call routed through the configured backend.

    Reads SESSION_BACKEND and SESSION_MODEL from os.environ so the caller
    is always billed through whichever backend the user configured — never
    silently falls back to the API when Max is selected.

    Max mode  → claude CLI subprocess (subscription, zero API cost).
    API mode  → Anthropic SDK (costs API tokens at the configured model rate).
    """
    backend_mode = os.environ.get("SESSION_BACKEND", "api")
    if backend_mode == "max" and MaxBackend.available():
        backend: SessionBackend = MaxBackend()
    else:
        resolved_model = model or os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        backend = APIBackend(model=resolved_model)

    try:
        chunks = list(backend.first_turn(prompt, system_prompt=system_prompt, cwd=cwd))
        return "".join(chunks)
    finally:
        backend.close()
