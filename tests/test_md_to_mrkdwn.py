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


def test_table_converted_to_code_block():
    text = "| Col A | Col B |\n|---|---|\n| val1 | val2 |"
    result = _md_to_mrkdwn(text)
    assert "```" in result
    assert "| Col A | Col B |" in result
    assert "| val1 | val2 |" in result
    # Separator row should be removed
    assert "|---|---|" not in result


def test_table_with_surrounding_text():
    text = "Here is a table:\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAnd more text."
    result = _md_to_mrkdwn(text)
    assert "Here is a table:" in result
    assert "And more text." in result
    assert "```" in result


def test_multiple_tables():
    text = "| A |\n|---|\n| 1 |\n\ntext\n\n| B |\n|---|\n| 2 |"
    result = _md_to_mrkdwn(text)
    # Should have two code blocks (4 fence markers)
    assert result.count("```") == 4


def test_pipe_in_code_block_not_treated_as_table():
    text = "```\n| not | a | table |\n```"
    result = _md_to_mrkdwn(text)
    # Should remain a single code block, not double-wrapped
    assert result.count("```") == 2


# ---------------------------------------------------------------------------
# _strip_tool_xml tests
# ---------------------------------------------------------------------------

from tools.slack_session import _strip_tool_xml


def test_strip_function_calls_block():
    text = 'before\n<function_calls>\n<invoke name="foo">\n</invoke>\n</function_calls>\nafter'
    assert _strip_tool_xml(text) == "before\n\nafter"


def test_strip_invoke_block():
    text = 'hello\n<invoke name="bash">\n<parameter name="cmd">ls</parameter>\n</invoke>\nworld'
    assert _strip_tool_xml(text) == "hello\n\nworld"


def test_strip_tool_result_blocks():
    text = "start\n<function_results>\noutput here\n</function_results>\nend"
    assert _strip_tool_xml(text) == "start\n\nend"


def test_strip_multiple_xml_blocks():
    text = (
        "intro\n"
        '<function_calls>\n<invoke name="a">\n</invoke>\n</function_calls>\n'
        "middle\n"
        "<function_results>\nresult\n</function_results>\n"
        "outro"
    )
    result = _strip_tool_xml(text)
    assert "intro" in result
    assert "middle" in result
    assert "outro" in result
    assert "<function_calls>" not in result
    assert "<function_results>" not in result


def test_strip_returns_empty_for_pure_xml():
    text = '<function_calls>\n<invoke name="bash">\n</invoke>\n</function_calls>'
    assert _strip_tool_xml(text) == ""


def test_strip_preserves_normal_angle_brackets():
    text = "x < 5 and y > 3"
    assert _strip_tool_xml(text) == "x < 5 and y > 3"


def test_strip_handles_tool_tags():
    """Tags like <bash>, <read_file>, etc. should also be stripped."""
    text = "note\n<bash>ls -la</bash>\nmore text"
    assert _strip_tool_xml(text) == "note\n\nmore text"


def test_strip_case_insensitive():
    text = "<Function_Calls>\nstuff\n</Function_Calls>"
    assert _strip_tool_xml(text) == ""
