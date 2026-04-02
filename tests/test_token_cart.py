"""Tests for tools/token_cart.py — all Anthropic calls mocked."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from tools.token_cart import HaikuTokenCart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_anthropic(text: str):
    """Return a mock Anthropic class whose .messages.create() returns `text`."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


# ---------------------------------------------------------------------------
# pre_call tests
# ---------------------------------------------------------------------------

def test_pre_call_first_turn_no_handoff():
    """First turn — no handoff exists. Returns prompt as-is."""
    cart = HaikuTokenCart.__new__(HaikuTokenCart)
    cart._client = MagicMock()
    result = cart.pre_call(handoff=None, prompt="explain the auth system")
    assert result == "explain the auth system"
    cart._client.messages.create.assert_not_called()


def test_pre_call_with_handoff_enriches():
    """With handoff — Haiku enriches context."""
    enriched = "Auth system uses OAuth2. User asked about token refresh."
    mock_cls = _mock_anthropic(enriched)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.pre_call(
        handoff="## Handoff\nAuth discussion ongoing",
        prompt="how does token refresh work?",
    )
    assert result == enriched
    cart._client.messages.create.assert_called_once()


def test_pre_call_with_handoff_includes_registry():
    """Registry sections are included in enrichment call."""
    enriched = "Use apiClient for all API calls."
    mock_cls = _mock_anthropic(enriched)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.pre_call(
        handoff="## Handoff\nAPI work",
        prompt="add a new endpoint",
        registry="## Shared Utilities\n- apiClient: lib/api.ts",
    )
    assert result == enriched
    call_kwargs = cart._client.messages.create.call_args[1]
    user_content = call_kwargs["messages"][0]["content"]
    assert "apiClient" in user_content


def test_pre_call_haiku_failure_falls_back_to_raw():
    """If Haiku fails, return handoff + prompt concatenated."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("API down")
    result = cart.pre_call(
        handoff="## Handoff\nPrior context here",
        prompt="next question",
    )
    assert "Prior context here" in result
    assert "next question" in result


# ---------------------------------------------------------------------------
# post_call tests
# ---------------------------------------------------------------------------

def test_post_call_first_turn_creates_handoff():
    """First turn — no prior handoff. Creates initial handoff + journal."""
    response_text = (
        "---HANDOFF---\n## Handoff Context\n**Task:** explain auth\n"
        "---JOURNAL---\nOperator asked about auth system."
    )
    mock_cls = _mock_anthropic(response_text)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.post_call(
        handoff=None,
        prompt="explain the auth system",
        response="The auth system uses OAuth2...",
    )
    assert "Handoff Context" in result["handoff"]
    assert "auth" in result["journal_draft"].lower()


def test_post_call_subsequent_turn_updates_handoff():
    """Second turn — has prior handoff. Updates it."""
    response_text = (
        "---HANDOFF---\n## Handoff Context\n**Task:** token refresh\n"
        "### Decisions Made\n- Use refresh tokens\n"
        "---JOURNAL---\nDiscussed token refresh mechanism."
    )
    mock_cls = _mock_anthropic(response_text)
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    result = cart.post_call(
        handoff="## Handoff Context\n**Task:** explain auth",
        prompt="how does token refresh work?",
        response="Token refresh uses rotating keys...",
    )
    assert "token refresh" in result["handoff"].lower()
    assert "journal_draft" in result


def test_post_call_haiku_failure_preserves_prior():
    """If Haiku fails post-call, return prior handoff unchanged."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("timeout")
    result = cart.post_call(
        handoff="## Prior handoff",
        prompt="question",
        response="answer",
    )
    assert result["handoff"] == "## Prior handoff"
    assert result["journal_draft"] == ""


def test_post_call_no_prior_handoff_failure_returns_empty():
    """First turn Haiku failure — returns empty handoff."""
    mock_cls = _mock_anthropic("")
    with patch("tools.token_cart.Anthropic", mock_cls):
        cart = HaikuTokenCart()
    cart._client.messages.create.side_effect = Exception("timeout")
    result = cart.post_call(handoff=None, prompt="q", response="a")
    assert result["handoff"] == ""
    assert result["journal_draft"] == ""


# ---------------------------------------------------------------------------
# parse response tests
# ---------------------------------------------------------------------------

def test_parse_response_splits_sections():
    """Response with both markers splits correctly."""
    from tools.token_cart import _parse_cart_response
    text = "---HANDOFF---\nhandoff content here\n---JOURNAL---\njournal content here"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "handoff content here"
    assert journal == "journal content here"


def test_parse_response_handoff_only():
    """Response with only handoff marker."""
    from tools.token_cart import _parse_cart_response
    text = "---HANDOFF---\nhandoff only"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "handoff only"
    assert journal == ""


def test_parse_response_no_markers():
    """Response with no markers — treat entire text as handoff."""
    from tools.token_cart import _parse_cart_response
    text = "some raw text without markers"
    handoff, journal = _parse_cart_response(text)
    assert handoff == "some raw text without markers"
    assert journal == ""
