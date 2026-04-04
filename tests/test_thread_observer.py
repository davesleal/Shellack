"""Tests for tools/thread_observer.py."""

from unittest.mock import MagicMock, patch
from tools.thread_observer import ThreadObserver


def _mock_anthropic(text):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    mock_cls = MagicMock(return_value=mock_client)
    return mock_cls


def test_observe_appends_context():
    mock_cls = _mock_anthropic("- Turn 1 (user): Asked about Phase 3 migration")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    result = obs.observe("user", "What's the plan for Phase 3?")
    assert "Phase 3" in result
    assert obs._turn == 1


def test_observe_accumulates():
    mock_cls = _mock_anthropic("- Turn 1 (user): Asked about migration")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    obs.observe("user", "migration question")
    mock_cls.return_value.messages.create.return_value.content[0].text = (
        "- Turn 2 (agent): Proposed 5-step plan"
    )
    obs.observe("agent", "Here's my 5-step plan...")
    assert "Turn 1" in obs.context or "migration" in obs.context
    assert obs._turn == 2


def test_observe_failure_fallback():
    mock_cls = _mock_anthropic("")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    obs._client.messages.create.side_effect = Exception("timeout")
    result = obs.observe("user", "test message")
    assert "test message" in result  # fallback manual append


def test_identify_files_returns_list():
    mock_cls = _mock_anthropic(
        '["src/services/social.ts", "supabase/migrations/001.sql"]'
    )
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    files = obs.identify_needed_files("What Firestore collections?")
    assert len(files) == 2
    assert "src/services/social.ts" in files


def test_identify_files_empty():
    mock_cls = _mock_anthropic("[]")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    files = obs.identify_needed_files("What's the weather?")
    assert files == []


def test_identify_files_failure():
    mock_cls = _mock_anthropic("")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    obs._client.messages.create.side_effect = Exception("timeout")
    files = obs.identify_needed_files("anything")
    assert files == []


def test_finalize_returns_context():
    mock_cls = _mock_anthropic("- Turn 1: test")
    with patch("tools.thread_observer.Anthropic", mock_cls):
        obs = ThreadObserver()
    obs.observe("user", "test")
    assert obs.finalize() == obs.context
