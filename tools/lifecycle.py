#!/usr/bin/env python3
"""Lifecycle notifier — posts structured status to Slack thread and channel."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LifecycleNotifier:
    def __init__(
        self,
        app,
        channel_id: str,
        thread_ts: str,
        project_name: str,
        owner_user_id: str,
    ):
        self.app = app
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.project_name = project_name
        self.owner_user_id = owner_user_id

    def _post_thread(self, text: str):
        """Post reply in the active thread."""
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=self.thread_ts,
                text=text,
            )
        except Exception as e:
            logger.error(f"Lifecycle thread post failed: {e}")

    def _post_channel(self, text: str):
        """Post top-level to the project channel (no thread_ts)."""
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
            )
        except Exception as e:
            logger.error(f"Lifecycle channel post failed: {e}")

    # Thread-only events
    def started(self, summary: str):
        self._post_thread(f"🔵 Started: {summary}")

    def in_progress(self, detail: str):
        self._post_thread(f"🔨 {detail}")

    def failed(self, error: str):
        self._post_thread(f"❌ Failed: {error}")

    def issue_created(self, url: str, number: int):
        self._post_thread(f"🐛 Issue #{number} created → {url}")

    def needs_human(self, reason: str):
        self._post_thread(f"🙋 <@{self.owner_user_id}> — {reason}")
