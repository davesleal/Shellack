"""Tests for tools/action_buttons.py."""

from tools.action_buttons import detect_options, format_buttons


def test_detect_options_with_description():
    text = "Here are the options:\n1. Activity feed — auto-post on publish\n2. Missing videos — rendering issue\n3. Phase 3 — Supabase migration"
    opts = detect_options(text)
    assert len(opts) == 3
    assert opts[0]["label"] == "Activity feed"
    assert opts[0]["number"] == "1"
    assert "auto-post" in opts[0]["description"]


def test_detect_options_simple():
    text = "Pick one:\n1. Fix the bug\n2. Add the feature\n3. Write tests"
    opts = detect_options(text)
    assert len(opts) == 3
    assert opts[1]["label"] == "Add the feature"


def test_detect_options_bold():
    text = "1. **Activity feed** — auto-post\n2. **Videos** — fix rendering"
    opts = detect_options(text)
    assert len(opts) == 2
    assert opts[0]["label"] == "Activity feed"


def test_detect_options_max_five():
    text = "\n".join(f"{i}. Option {i}" for i in range(1, 10))
    opts = detect_options(text)
    assert len(opts) == 5


def test_detect_options_none():
    text = "No numbered options here, just prose."
    opts = detect_options(text)
    assert opts == []


def test_format_buttons():
    opts = [{"number": "1", "label": "Fix bug", "description": "crash on login"}]
    blocks = format_buttons(opts, "99.0")
    assert len(blocks) == 1
    assert blocks[0]["type"] == "actions"
    assert blocks[0]["elements"][0]["text"]["text"] == "1. Fix bug"
    assert "99.0" in blocks[0]["elements"][0]["value"]


def test_format_buttons_empty():
    assert format_buttons([], "99.0") == []
