# tests/test_md_to_mrkdwn.py
"""Tests for _md_to_mrkdwn conversion and unclosed fence handling."""
import pytest
from tools.slack_session import _md_to_mrkdwn


def test_converts_bold():
    assert _md_to_mrkdwn("**hello**") == "*hello*"


def test_converts_headings():
    assert _md_to_mrkdwn("## Title") == "*Title*"


def test_converts_bullets():
    result = _md_to_mrkdwn("- item one\n- item two")
    assert "• item one" in result
    assert "• item two" in result


def test_code_block_passes_through_unchanged():
    text = "before\n```python\nx = 1\n```\nafter"
    result = _md_to_mrkdwn(text)
    assert "```python\nx = 1\n```" in result
    # Prose outside is still converted
    assert result.startswith("before")


def test_bold_inside_code_not_converted():
    text = "```\n**not bold**\n```"
    result = _md_to_mrkdwn(text)
    assert "**not bold**" in result


def test_unclosed_fence_is_auto_closed():
    # Odd number of ``` — the dangling fence gets closed
    text = "Here is code:\n```python\nx = 1"
    result = _md_to_mrkdwn(text)
    assert result.count("```") % 2 == 0


def test_unclosed_fence_prose_after_is_not_lost():
    # Text after an unclosed fence must still appear in output
    text = "intro\n```python\ncode here"
    result = _md_to_mrkdwn(text)
    assert "intro" in result
    assert "code here" in result


def test_inline_code_passes_through():
    assert "`foo`" in _md_to_mrkdwn("use `foo` here")


def test_closed_fence_not_double_closed():
    text = "```swift\nlet x = 1\n```"
    result = _md_to_mrkdwn(text)
    assert result.count("```") == 2  # exactly open + close
