"""Thread observer — maintains append-only running context for active threads."""

from __future__ import annotations

import json
import logging
from typing import Optional

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-haiku-4-5-20251001"
_TIMEOUT = 10.0

_APPEND_SYSTEM = """You are a thread observer. You maintain a running context summary for an ongoing conversation.

You will receive:
1. The current running context (may be empty if this is the first turn)
2. A new message (user or agent)

Your job: APPEND a concise summary of the new message to the running context. Do NOT rewrite or reorganize the existing context — only ADD to it.

Format each append as:
- Turn N (user/agent): {one-line summary of what was said/decided/asked}

If the message contains:
- A decision → mark it: "DECIDED: ..."
- An open question → mark it: "OPEN: ..."
- A file reference → mark it: "FILE: path/to/file"
- A technical fact → mark it: "FACT: ..."

Keep each append to 1-2 lines. Be precise, not verbose."""

_IDENTIFY_FILES_SYSTEM = """You are a file identification agent. Given a conversation context and a user's latest message, identify which project files would help answer the question.

Return ONLY a JSON array of relative file paths, max 3 files. Example:
["src/services/socialService.ts", "supabase/migrations/001_init.sql", "apps/web/src/lib/supabase.ts"]

If no specific files are needed, return: []

Rules:
- Only suggest files that likely exist based on the project structure and tech stack
- Prefer service files, schemas, configs over components
- Be specific — exact paths, not directories"""


class ThreadObserver:
    """Append-only thread context observer."""

    def __init__(self) -> None:
        self._client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(_TIMEOUT)),
            max_retries=1,
        )
        self._context: str = ""
        self._turn: int = 0

    @property
    def context(self) -> str:
        return self._context

    def observe(self, role: str, message: str) -> str:
        """Append a new message observation to the running context.

        Args:
            role: "user" or "agent"
            message: the message content

        Returns: updated running context
        """
        self._turn += 1

        try:
            user_content = (
                f"## Current Running Context\n"
                f"{self._context or '(empty — first turn)'}\n\n"
                f"## New Message ({role}, turn {self._turn})\n"
                f"{message[:2000]}"
            )

            msg = self._client.messages.create(
                model=_MODEL,
                max_tokens=256,
                system=_APPEND_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            append = msg.content[0].text.strip()
            if append:
                self._context = f"{self._context}\n{append}".strip()
        except Exception as exc:
            logger.warning(f"Thread observer append failed: {exc}")
            # Fallback: manual append
            self._context += f"\n- Turn {self._turn} ({role}): {message[:100]}"

        return self._context

    def identify_needed_files(
        self, prompt: str, project_structure: str = ""
    ) -> list[str]:
        """Identify which project files would help answer the current prompt.

        Returns list of relative file paths.
        """
        try:
            user_content = (
                f"## Thread Context\n{self._context}\n\n" f"## User's Message\n{prompt}"
            )
            if project_structure:
                user_content += f"\n\n## Project File Structure\n{project_structure}"

            msg = self._client.messages.create(
                model=_MODEL,
                max_tokens=128,
                system=_IDENTIFY_FILES_SYSTEM,
                messages=[{"role": "user", "content": user_content}],
            )
            text = msg.content[0].text.strip()
            # Parse JSON array
            if text.startswith("["):
                files = json.loads(text)
                if isinstance(files, list):
                    return [f for f in files if isinstance(f, str)][:3]
        except Exception as exc:
            logger.warning(f"File identification failed: {exc}")

        return []

    def finalize(self) -> str:
        """Return the final context for thread memory persistence."""
        return self._context
