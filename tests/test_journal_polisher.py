"""Tests for journal polisher module."""
from unittest.mock import MagicMock, patch

import pytest

from tools.journal_polisher import polish_journal


def test_polish_journal_empty_draft_returns_none():
    assert polish_journal("") is None
    assert polish_journal("   ") is None
    assert polish_journal(None) is None


@patch("tools.journal_polisher.Anthropic")
def test_polish_journal_returns_polished_text(MockAnthropic):
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client

    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="  Polished journal entry.  ")]
    mock_client.messages.create.return_value = mock_msg

    result = polish_journal("rough draft here", project_name="SlackClaw")

    assert result == "Polished journal entry."
    mock_client.messages.create.assert_called_once()
    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["max_tokens"] == 1024
    assert "SlackClaw" in call_kwargs["messages"][0]["content"]


@patch("tools.journal_polisher.Anthropic")
def test_polish_journal_api_failure_returns_none(MockAnthropic):
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    mock_client.messages.create.side_effect = RuntimeError("API down")

    result = polish_journal("some draft")
    assert result is None


@patch("tools.journal_polisher.Anthropic")
def test_polish_journal_respects_model_env(MockAnthropic, monkeypatch):
    monkeypatch.setenv("JOURNAL_MODEL", "claude-haiku-4-5-20251001")
    mock_client = MagicMock()
    MockAnthropic.return_value = mock_client
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="entry")]
    mock_client.messages.create.return_value = mock_msg

    polish_journal("draft")

    call_kwargs = mock_client.messages.create.call_args[1]
    assert call_kwargs["model"] == "claude-haiku-4-5-20251001"
