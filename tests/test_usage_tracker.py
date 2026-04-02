# tests/test_usage_tracker.py
import json
import os
import pytest


def test_record_session_increments_count(tmp_path):
    from tools.usage_tracker import UsageTracker

    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("api", "claude-sonnet-4-6")
    assert tracker.get_stats()["session_count"] == 1


def test_record_mention_increments_count(tmp_path):
    from tools.usage_tracker import UsageTracker

    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_mention("api", "claude-sonnet-4-6")
    assert tracker.get_stats()["mention_count"] == 1


def test_api_session_accumulates_tokens_and_cost(tmp_path):
    from tools.usage_tracker import UsageTracker

    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session(
        "api", "claude-sonnet-4-6", tokens_in=1_000_000, tokens_out=100_000
    )
    stats = tracker.get_stats()
    assert stats["tokens_in"] == 1_000_000
    assert stats["tokens_out"] == 100_000
    # sonnet: $3/Mtok in, $15/Mtok out → $3.00 + $1.50 = $4.50
    assert abs(stats["estimated_cost"] - 4.50) < 0.01


def test_max_session_does_not_record_tokens(tmp_path):
    from tools.usage_tracker import UsageTracker

    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session(
        "max", "claude-sonnet-4-6", tokens_in=500_000, tokens_out=50_000
    )
    stats = tracker.get_stats()
    assert stats["tokens_in"] == 0
    assert stats["estimated_cost"] == 0.0


def test_monthly_reset_on_stale_month(tmp_path):
    from tools.usage_tracker import UsageTracker

    path = str(tmp_path / "usage.json")
    stale = {
        "reset_month": "2020-01",
        "session_count": 99,
        "mention_count": 50,
        "tokens_in": 1000,
        "tokens_out": 500,
        "estimated_cost": 5.0,
        "mode": "api",
        "model": "claude-sonnet-4-6",
    }
    with open(path, "w") as f:
        json.dump(stale, f)
    tracker = UsageTracker(path=path)
    stats = tracker.get_stats()
    assert stats["session_count"] == 0
    assert stats["tokens_in"] == 0
    assert stats["estimated_cost"] == 0.0


def test_format_usage_message_api_mode(tmp_path, monkeypatch):
    from tools.usage_tracker import UsageTracker

    monkeypatch.setenv("SESSION_BACKEND", "api")
    monkeypatch.setenv("SESSION_MODEL", "claude-sonnet-4-6")
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session(
        "api", "claude-sonnet-4-6", tokens_in=500_000, tokens_out=100_000
    )
    msg = tracker.format_usage_message()
    assert "Anthropic API" in msg
    assert "claude-sonnet-4-6" in msg
    assert "500,000" in msg


def test_format_usage_message_max_mode(tmp_path, monkeypatch):
    from tools.usage_tracker import UsageTracker

    monkeypatch.setenv("SESSION_BACKEND", "max")
    monkeypatch.setenv("SESSION_MODEL", "claude-sonnet-4-6")
    tracker = UsageTracker(path=str(tmp_path / "usage.json"))
    tracker.record_session("max", "claude-sonnet-4-6")
    msg = tracker.format_usage_message()
    assert "Claude Max" in msg
    assert "$0.00" in msg
