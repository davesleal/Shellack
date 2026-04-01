# tests/test_triage.py
"""Unit tests for tools/triage.py — all Anthropic calls mocked."""
import json
import pytest
import httpx
from unittest.mock import MagicMock, patch

from tools.triage import classify, TriageResult, _DEFAULT, _HAIKU, _configured_model


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
    mock_client.messages.create.return_value = _make_mock_response("simple", "just a question")

    with patch("tools.triage.Anthropic", return_value=mock_client), \
         patch.dict("os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}):
        result = classify("What does this project do?")

    assert result.tier == "simple"
    assert result.model == "claude-sonnet-4-6"
    assert result.reason == "just a question"


def test_moderate_tier():
    """Moderate request => tier=moderate, model=SESSION_MODEL."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response("moderate", "code review needed")

    with patch("tools.triage.Anthropic", return_value=mock_client), \
         patch.dict("os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}):
        result = classify("Review this function for bugs")

    assert result.tier == "moderate"
    assert result.model == "claude-sonnet-4-6"


def test_complex_tier():
    """Complex request => tier=complex, model=SESSION_MODEL."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response("complex", "multi-file refactor")

    with patch("tools.triage.Anthropic", return_value=mock_client), \
         patch.dict("os.environ", {"SESSION_MODEL": "claude-sonnet-4-6"}):
        result = classify("Refactor the entire auth system across all files")

    assert result.tier == "complex"
    assert result.model == "claude-sonnet-4-6"


def test_api_exception_returns_default():
    """Any API exception => _DEFAULT returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == _DEFAULT.tier
    assert result.reason == _DEFAULT.reason


def test_malformed_json_returns_default():
    """Non-JSON response => _DEFAULT returned, no raise."""
    content_block = MagicMock()
    content_block.text = "not json"
    msg = MagicMock()
    msg.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = msg

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == _DEFAULT.tier


def test_unknown_tier_returns_default():
    """Unknown tier in JSON => _DEFAULT returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response("unknown", "weird tier")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == _DEFAULT.tier


def test_timeout_returns_default():
    """httpx.TimeoutException => _DEFAULT returned, no raise."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = httpx.TimeoutException("timed out")

    with patch("tools.triage.Anthropic", return_value=mock_client):
        result = classify("some prompt")

    assert result.tier == _DEFAULT.tier
