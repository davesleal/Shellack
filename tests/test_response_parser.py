"""Tests for tools/response_parser.py — tag parsing + message splitter."""

from tools.response_parser import parse_response, ParsedResponse, split_message


def test_reply_only():
    """[reply] tag only — think is empty."""
    result = parse_response("[reply] Here is the answer.")
    assert result.think == ""
    assert result.reply == "Here is the answer."
    assert result.actions == []


def test_think_and_reply():
    """Both tags present."""
    text = "[think] Let me check the files.\nFound 3 modules.\n\n[reply] The auth uses OAuth2."
    result = parse_response(text)
    assert "check the files" in result.think
    assert "Found 3 modules" in result.think
    assert result.reply == "The auth uses OAuth2."


def test_no_tags_fallback():
    """No tags at all — entire text is reply (backward compatible)."""
    result = parse_response("Just a plain response with no tags.")
    assert result.think == ""
    assert result.reply == "Just a plain response with no tags."


def test_think_only_no_reply():
    """[think] only, no [reply] — reply is empty."""
    result = parse_response("[think] Reasoning about the problem.")
    assert "Reasoning" in result.think
    assert result.reply == ""


def test_action_tags():
    """[action] lines are collected."""
    text = (
        "[action] Reading files...\n[action] Running tests...\n[reply] All tests pass."
    )
    result = parse_response(text)
    assert len(result.actions) == 2
    assert "Reading files" in result.actions[0]
    assert "Running tests" in result.actions[1]
    assert result.reply == "All tests pass."


def test_multiline_reply():
    """Reply content spans multiple lines."""
    text = "[think] Quick check.\n[reply] Line one.\n\nLine two.\n\nLine three."
    result = parse_response(text)
    assert result.think == "Quick check."
    assert "Line one." in result.reply
    assert "Line three." in result.reply


def test_tags_case_insensitive():
    """Tags work regardless of case."""
    result = parse_response("[THINK] reasoning\n[REPLY] answer")
    assert result.think == "reasoning"
    assert result.reply == "answer"


def test_tags_with_leading_whitespace():
    """Tags with spaces before them still parse."""
    result = parse_response("  [think] reasoning\n  [reply] answer")
    assert result.think == "reasoning"
    assert result.reply == "answer"


def test_empty_string():
    """Empty input — empty result."""
    result = parse_response("")
    assert result.think == ""
    assert result.reply == ""
    assert result.actions == []


# --- Message splitter tests ---


def test_split_short_message():
    """Under limit — returns single chunk."""
    result = split_message("Short message.", max_chars=3500)
    assert result == ["Short message."]


def test_split_on_paragraph_boundary():
    """Splits on double newline when over limit."""
    para1 = "A" * 2000
    para2 = "B" * 2000
    text = f"{para1}\n\n{para2}"
    result = split_message(text, max_chars=3500)
    assert len(result) == 2
    assert result[0] == para1
    assert result[1] == para2


def test_split_preserves_code_fence():
    """Never splits inside a code fence."""
    code_block = "```python\n" + "x = 1\n" * 500 + "```"
    text = f"Before.\n\n{code_block}\n\nAfter."
    result = split_message(text, max_chars=3500)
    # Code block must be intact in one chunk
    for chunk in result:
        if "```python" in chunk:
            assert "```" in chunk[chunk.index("```python") + 1 :]  # has closing fence


def test_split_long_paragraph_on_sentence():
    """Single paragraph over limit splits on sentence boundary."""
    sentences = ". ".join(["This is sentence " + str(i) for i in range(100)])
    result = split_message(sentences, max_chars=500)
    assert len(result) > 1
    # Each chunk should end at a sentence boundary (contains ". " or is last)
    for chunk in result[:-1]:
        assert chunk.rstrip().endswith(".")


def test_split_empty():
    """Empty string — returns empty list."""
    assert split_message("") == []
