"""Tests for tools/agent_manager.py — complexity classification and model selection."""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from tools.agent_manager import classify_complexity, select_model, _MODEL_MAP

# --- classify_complexity ---


def _mock_anthropic_response(text: str):
    """Build a mock Anthropic response with the given text."""
    block = MagicMock()
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    return msg


@patch("tools.agent_manager.Anthropic")
def test_classify_simple(mock_cls):
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("SIMPLE")
    mock_cls.return_value = client

    assert classify_complexity("rename this variable") == "simple"


@patch("tools.agent_manager.Anthropic")
def test_classify_moderate(mock_cls):
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("MODERATE")
    mock_cls.return_value = client

    assert classify_complexity("fix the login bug") == "moderate"


@patch("tools.agent_manager.Anthropic")
def test_classify_complex(mock_cls):
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("COMPLEX")
    mock_cls.return_value = client

    assert classify_complexity("refactor the entire auth system") == "complex"


@patch("tools.agent_manager.Anthropic")
def test_classify_fuzzy_match(mock_cls):
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("Simple task")
    mock_cls.return_value = client

    assert classify_complexity("format this file") == "simple"


@patch("tools.agent_manager.Anthropic")
def test_classify_failure_defaults_moderate(mock_cls):
    mock_cls.side_effect = RuntimeError("API down")

    assert classify_complexity("anything") == "moderate"


@patch("tools.agent_manager.Anthropic")
def test_classify_with_handoff(mock_cls):
    client = MagicMock()
    client.messages.create.return_value = _mock_anthropic_response("COMPLEX")
    mock_cls.return_value = client

    result = classify_complexity("do the thing", handoff="prior context here")
    assert result == "complex"

    # Verify the user content included the handoff
    call_kwargs = client.messages.create.call_args[1]
    assert "prior context here" in call_kwargs["messages"][0]["content"]


# --- select_model ---


def test_select_model_simple():
    assert select_model("simple") == "claude-haiku-4-5-20251001"


def test_select_model_moderate():
    assert select_model("moderate") == "claude-sonnet-4-6"


def test_select_model_complex():
    assert select_model("complex") == "claude-opus-4-6"


def test_select_model_unknown_defaults_moderate():
    assert select_model("unknown") == _MODEL_MAP["moderate"]


def test_select_model_env_override(monkeypatch):
    monkeypatch.setenv("AGENT_MANAGER_SIMPLE_MODEL", "claude-custom-model")
    assert select_model("simple") == "claude-custom-model"
