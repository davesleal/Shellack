"""Tests for tools/self_improver.py — all Anthropic calls mocked."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tools.self_improver import (
    _append_to_claude_md,
    _detect_block,
    _reflect,
    reflect_and_update,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_anthropic(text: str):
    """Return a mock Anthropic class whose .messages.create() returns `text`."""
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    mock_client.messages.create.return_value = mock_msg
    mock_anthropic_cls = MagicMock(return_value=mock_client)
    return mock_anthropic_cls


def _long_response(signal_words: list[str], filler: str = "x") -> str:
    """Build a response >= 400 chars containing the given signal words in the first 80%."""
    # Put signals near the beginning, pad to >400 chars
    body = " ".join(signal_words) + " " + (filler * 300)
    # Ensure length >= 400
    while len(body) < 400:
        body += filler
    return body


# ---------------------------------------------------------------------------
# _detect_block tests
# ---------------------------------------------------------------------------


def test_no_block_signal_returns_none():
    """Clean response with zero signal words → None."""
    response = "Everything worked great. " * 20  # >400 chars, no signals
    assert _detect_block(response) is None


def test_single_signal_word_below_threshold():
    """One match is below _MIN_BLOCK_SIGNALS=2 → None."""
    # "couldn't" is one signal word; pad to >400 chars
    response = "I couldn't find a better name for this variable. " + "x" * 400
    assert _detect_block(response) is None


def test_response_shorter_than_400_chars_returns_none():
    """Response < 400 chars → None, regardless of signals."""
    response = "error: something failed unfortunately"  # 2 signals, but <400 chars
    assert len(response) < 400
    assert _detect_block(response) is None


def test_block_detected_returns_excerpts():
    """Two signals in first 80% → (block_excerpt, resolution_excerpt)."""
    response = _long_response(["error: boom", "failed"])
    result = _detect_block(response)
    assert result is not None
    block_excerpt, resolution_excerpt = result
    assert "error:" in block_excerpt.lower() or "failed" in block_excerpt.lower()
    assert len(resolution_excerpt) <= 300


def test_block_signal_in_final_20_percent_not_triggered():
    """Signals only in the final 20% → None (cutoff logic)."""
    # Build a >400-char clean prefix, then add signals at the very end
    prefix = "a" * 401  # just past 400
    # Final 20% of total string
    total_len = len(prefix) + 50
    cutoff = int(total_len * 0.8)
    # Place signals AFTER the cutoff
    suffix = " error: failed boom"
    response = prefix + suffix
    # Verify signals land after cutoff
    signal_pos = response.index("error:")
    assert signal_pos >= int(len(response) * 0.8)
    assert _detect_block(response) is None


# ---------------------------------------------------------------------------
# _reflect tests
# ---------------------------------------------------------------------------


def test_reflect_succeeds():
    """Valid JSON from Haiku → dict with rule and section."""
    payload = json.dumps(
        {"rule": "Always validate inputs.", "section": "Watch Out For"}
    )
    mock_cls = _make_mock_anthropic(payload)
    with patch("tools.self_improver.Anthropic", mock_cls):
        result = _reflect("do a thing", "error here", "fixed it")
    assert result == {"rule": "Always validate inputs.", "section": "Watch Out For"}


def test_reflect_bad_json_returns_none():
    """Non-JSON Haiku response → None."""
    mock_cls = _make_mock_anthropic("not json at all")
    with patch("tools.self_improver.Anthropic", mock_cls):
        result = _reflect("do a thing", "error here", "fixed it")
    assert result is None


def test_reflect_api_failure_returns_none():
    """Haiku raises Exception → None."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("network error")
    mock_cls = MagicMock(return_value=mock_client)
    with patch("tools.self_improver.Anthropic", mock_cls):
        result = _reflect("do a thing", "error here", "fixed it")
    assert result is None


def test_reflect_fenced_json_strips_fences():
    """Haiku wraps output in ```json ... ``` → fences stripped, parsed successfully."""
    payload = (
        "```json\n"
        + json.dumps({"rule": "Use async/await.", "section": "Patterns"})
        + "\n```"
    )
    mock_cls = _make_mock_anthropic(payload)
    with patch("tools.self_improver.Anthropic", mock_cls):
        result = _reflect("do a thing", "error here", "fixed it")
    assert result == {"rule": "Use async/await.", "section": "Patterns"}


def test_reflect_invalid_section_falls_back_to_general():
    """Unknown section from Haiku → falls back to General."""
    payload = json.dumps({"rule": "Some rule.", "section": "Unknown"})
    mock_cls = _make_mock_anthropic(payload)
    with patch("tools.self_improver.Anthropic", mock_cls):
        result = _reflect("do a thing", "error here", "fixed it")
    assert result == {"rule": "Some rule.", "section": "General"}


# ---------------------------------------------------------------------------
# _append_to_claude_md tests
# ---------------------------------------------------------------------------


def test_append_to_existing_section(tmp_path):
    """Rule appended after last existing bullet in section."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "## Watch Out For\n- First rule\n- Second rule\n\n## Patterns\n- A pattern\n"
    )
    _append_to_claude_md(str(tmp_path), "New rule here.", "Watch Out For")
    content = claude_md.read_text()
    lines = content.splitlines()
    # "- New rule here." should come after "- Second rule" and before "## Patterns"
    idx_second = lines.index("- Second rule")
    idx_new = lines.index("- New rule here.")
    idx_patterns = lines.index("## Patterns")
    assert idx_second < idx_new < idx_patterns


def test_append_section_followed_by_another_section(tmp_path):
    """Rule inserted before the next ## heading."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text(
        "## Watch Out For\n- Existing bullet\n## Patterns\n- Pattern one\n"
    )
    _append_to_claude_md(str(tmp_path), "Watch out for this.", "Watch Out For")
    content = claude_md.read_text()
    lines = content.splitlines()
    idx_new = lines.index("- Watch out for this.")
    idx_patterns = lines.index("## Patterns")
    assert idx_new < idx_patterns


def test_missing_section_appended_at_end(tmp_path):
    """If section doesn't exist, new section + rule appended at end of file."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## Watch Out For\n- Something\n")
    _append_to_claude_md(str(tmp_path), "Follow this pattern.", "Patterns")
    content = claude_md.read_text()
    assert "## Patterns" in content
    assert "- Follow this pattern." in content
    # New section must be at the end
    assert content.rstrip().endswith("- Follow this pattern.")


def test_claude_md_missing_raises(tmp_path):
    """FileNotFoundError raised when CLAUDE.md is absent."""
    with pytest.raises(FileNotFoundError):
        _append_to_claude_md(str(tmp_path), "Some rule.", "General")


def test_relative_project_path_raises():
    """ValueError raised for relative project_path."""
    with pytest.raises(ValueError, match="absolute"):
        _append_to_claude_md(".", "Some rule.", "General")


def test_duplicate_rule_both_appear(tmp_path):
    """Same rule written twice → both entries present (no deduplication)."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Existing rule\n")
    _append_to_claude_md(str(tmp_path), "Repeat rule.", "General")
    _append_to_claude_md(str(tmp_path), "Repeat rule.", "General")
    content = claude_md.read_text()
    assert content.count("- Repeat rule.") == 2


# ---------------------------------------------------------------------------
# reflect_and_update integration tests
# ---------------------------------------------------------------------------


def test_reflect_and_update_no_block_returns_none(tmp_path):
    """No block signal in response → returns None, CLAUDE.md unchanged."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Rule one\n")
    original = claude_md.read_text()

    result = reflect_and_update(
        prompt="Do a thing",
        response="Everything worked perfectly. " * 20,
        project_path=str(tmp_path),
    )
    assert result is None
    assert claude_md.read_text() == original


def test_reflect_and_update_block_detected_rule_appended(tmp_path):
    """Block detected + good reflection → rule appended at end of section, rule returned."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## Watch Out For\n- Existing rule\n")

    response = _long_response(["error: connection refused", "failed to connect"])
    payload = json.dumps(
        {
            "rule": "Always check connection before calling API.",
            "section": "Watch Out For",
        }
    )
    mock_cls = _make_mock_anthropic(payload)

    with patch("tools.self_improver.Anthropic", mock_cls), patch.dict(
        "os.environ", {"SELF_IMPROVER_ENABLED": "true"}
    ):
        result = reflect_and_update(
            prompt="Connect to service",
            response=response,
            project_path=str(tmp_path),
        )

    assert result == "Always check connection before calling API."
    content = claude_md.read_text()
    assert "- Always check connection before calling API." in content
    # Must appear after the existing rule
    idx_existing = content.index("- Existing rule")
    idx_new = content.index("- Always check connection before calling API.")
    assert idx_existing < idx_new


def test_reflect_and_update_bad_json_returns_none(tmp_path):
    """Block detected but reflection returns bad JSON → returns None, CLAUDE.md unchanged."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Rule\n")
    original = claude_md.read_text()

    response = _long_response(["error: bad thing", "failed"])
    mock_cls = _make_mock_anthropic("not json")

    with patch("tools.self_improver.Anthropic", mock_cls), patch.dict(
        "os.environ", {"SELF_IMPROVER_ENABLED": "true"}
    ):
        result = reflect_and_update(
            prompt="Do a thing",
            response=response,
            project_path=str(tmp_path),
        )

    assert result is None
    assert claude_md.read_text() == original


def test_reflect_and_update_api_fails_returns_none(tmp_path):
    """Block detected but Haiku raises → returns None, CLAUDE.md unchanged."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Rule\n")
    original = claude_md.read_text()

    response = _long_response(["error: boom", "failed to proceed"])
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("timeout")
    mock_cls = MagicMock(return_value=mock_client)

    with patch("tools.self_improver.Anthropic", mock_cls), patch.dict(
        "os.environ", {"SELF_IMPROVER_ENABLED": "true"}
    ):
        result = reflect_and_update(
            prompt="Do a thing",
            response=response,
            project_path=str(tmp_path),
        )

    assert result is None
    assert claude_md.read_text() == original


def test_reflect_and_update_missing_claude_md_returns_none(tmp_path):
    """project_path has no CLAUDE.md → returns None, logs warning."""
    response = _long_response(["error: something", "failed"])
    payload = json.dumps({"rule": "A rule.", "section": "General"})
    mock_cls = _make_mock_anthropic(payload)

    with patch("tools.self_improver.Anthropic", mock_cls), patch.dict(
        "os.environ", {"SELF_IMPROVER_ENABLED": "true"}
    ):
        result = reflect_and_update(
            prompt="Do a thing",
            response=response,
            project_path=str(tmp_path),
        )

    assert result is None


def test_reflect_and_update_relative_path_returns_none(tmp_path):
    """Relative project_path → returns None, logs warning."""
    response = _long_response(["error: something", "failed"])
    payload = json.dumps({"rule": "A rule.", "section": "General"})
    mock_cls = _make_mock_anthropic(payload)

    with patch("tools.self_improver.Anthropic", mock_cls):
        result = reflect_and_update(
            prompt="Do a thing",
            response=response,
            project_path=".",
        )

    assert result is None


def test_reflect_and_update_short_response_returns_none(tmp_path):
    """Response shorter than 400 chars → returns None."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Rule\n")
    original = claude_md.read_text()

    # Two signals but very short
    with patch.dict("os.environ", {"SELF_IMPROVER_ENABLED": "true"}):
        result = reflect_and_update(
            prompt="Do a thing",
            response="error: failed unfortunately",
            project_path=str(tmp_path),
        )

    assert result is None
    assert claude_md.read_text() == original


# ---------------------------------------------------------------------------
# Opt-in gate tests
# ---------------------------------------------------------------------------

import os


def test_disabled_by_default(tmp_path):
    """reflect_and_update returns None when SELF_IMPROVER_ENABLED is not set."""
    claude_md = tmp_path / "CLAUDE.md"
    claude_md.write_text("## General\n- Rule\n")
    response = _long_response(["error: bad", "failed"])

    env = {k: v for k, v in os.environ.items() if k != "SELF_IMPROVER_ENABLED"}
    with patch.dict("os.environ", env, clear=True):
        result = reflect_and_update("prompt", response, str(tmp_path))

    assert result is None


def test_disabled_when_not_true(tmp_path):
    """reflect_and_update returns None when SELF_IMPROVER_ENABLED != 'true'."""
    response = _long_response(["error: bad", "failed"])
    with patch.dict("os.environ", {"SELF_IMPROVER_ENABLED": "false"}):
        result = reflect_and_update("prompt", response, str(tmp_path))
    assert result is None


# ---------------------------------------------------------------------------
# Sanitization tests
# ---------------------------------------------------------------------------

from tools.self_improver import _sanitize_rule


def test_sanitize_clean_rule():
    assert _sanitize_rule("Always validate inputs") == "Always validate inputs"


def test_sanitize_rejects_long_rule():
    assert _sanitize_rule("x" * 201) is None


def test_sanitize_rejects_suspicious_patterns():
    for word in [
        "ignore",
        "override",
        "exfiltrate",
        ".env",
        "token",
        "credential",
        "password",
        "api key",
    ]:
        assert (
            _sanitize_rule(f"Always {word} the settings") is None
        ), f"should reject: {word}"


def test_sanitize_rejects_non_ascii():
    """Unicode lookalike bypass: Cyrillic 'е' in 'ignore' should be rejected."""
    assert _sanitize_rule("Always ignor\u0435 the rules") is None  # Cyrillic е
    assert _sanitize_rule("Use p\u0430ssword manager") is None  # Cyrillic а
