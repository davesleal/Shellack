# tests/test_triage.py
"""Unit tests for tools/triage.py — all Anthropic calls mocked."""

import json
import pytest
import httpx
from unittest.mock import MagicMock, patch

from tools.triage import classify, TriageResult, _HAIKU, _configured_model


def _make_mock_response(tier: str, reason: str = "test reason") -> MagicMock:
    """Build a mock Anthropic message response."""
    content_block = MagicMock()
    content_block.text = json.dumps({"tier": tier, "reason": reason})
    msg = MagicMock()
    msg.content = [content_block]
    return msg


def test_simple_tier():
    """Simple request => tier=simple, model=SESSION_MODEL."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "simple", "just a question"
    )

    with patch("tools.triage.Anthropic", return_value=mock_client), patch.dict(
        "os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}
    ):
        result = classify("What does this project do?")

    assert result.tier == "simple"
    assert result.model == "claude-sonnet-4-6"
    assert result.reason == "just a question"


def test_moderate_tier():
    """Moderate request => tier=moderate, model=SESSION_MODEL."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "moderate", "code review needed"
    )

    with patch("tools.triage.Anthropic", return_value=mock_client), patch.dict(
        "os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}
    ):
        result = classify("Review this function for bugs")

    assert result.tier == "moderate"
    assert result.model == "claude-sonnet-4-6"


def test_complex_tier():
    """Complex request => tier=complex, model=SESSION_MODEL."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "complex", "multi-file refactor"
    )

    with patch("tools.triage.Anthropic", return_value=mock_client), patch.dict(
        "os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}
    ):
        result = classify("Refactor the entire auth system across all files")

    assert result.tier == "complex"
    assert result.model == "claude-sonnet-4-6"


def test_api_exception_returns_default():
    """Any API exception => moderate fallback returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == "moderate"
    assert result.reason == "triage unavailable"


def test_malformed_json_returns_default():
    """Non-JSON response => moderate fallback returned, no raise."""
    content_block = MagicMock()
    content_block.text = "not json"
    msg = MagicMock()
    msg.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = msg

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == "moderate"


def test_unknown_tier_returns_default():
    """Unknown tier in JSON => moderate fallback returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "unknown", "weird tier"
    )

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == "moderate"


def test_timeout_returns_default():
    """httpx.TimeoutException => moderate fallback returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = httpx.TimeoutException("timed out")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == "moderate"


def test_default_fallback_uses_current_session_model():
    """Fallback must reflect SESSION_MODEL at call time, not import time."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = RuntimeError("boom")

    with patch("tools.triage.Anthropic", return_value=mock_client), patch.dict(
        "os.environ", {"SESSION_MODEL": "claude-opus-4-6"}
    ):
        result = classify("anything")

    assert result.model == "claude-opus-4-6"


def test_classify_uses_system_kwarg():
    """Classification prompt must be in system= kwarg, NOT concatenated into messages."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response("simple", "test")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        classify("What is this?")

    call_kwargs = mock_client.messages.create.call_args[1]
    # system= kwarg must be present and non-empty
    assert "system" in call_kwargs, "classify must pass prompt via system= kwarg"
    assert call_kwargs["system"], "system= kwarg must not be empty"
    # user input must be in messages, not in system prompt
    messages = call_kwargs["messages"]
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert messages[0]["content"] == "What is this?"
    # system prompt must NOT contain the user input
    assert "What is this?" not in call_kwargs["system"]
