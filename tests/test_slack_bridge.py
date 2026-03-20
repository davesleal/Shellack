import pytest
import sys
from unittest.mock import patch, MagicMock
import responses  # pip install responses


# ---------------------------------------------------------------------------
# format_bridge_blocks
# ---------------------------------------------------------------------------

def test_format_choice_returns_section_and_actions():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Which approach?", ["A", "B", "C"], "sess1")
    types = [b["type"] for b in blocks]
    assert "section" in types
    assert "actions" in types


def test_format_choice_button_values():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick one", ["X", "Y"], "abc")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    values = [btn["value"] for btn in actions_block["elements"]]
    assert "abc|X" in values
    assert "abc|Y" in values


def test_format_choice_action_ids():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick one", ["X", "Y"], "abc")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    for btn in actions_block["elements"]:
        assert btn["action_id"] == "claude_bridge_input"


def test_format_choice_splits_beyond_five_options():
    """6 options must produce two separate actions blocks (Slack limit is 5 per block)."""
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Pick", ["A", "B", "C", "D", "E", "F"], "s")
    actions_blocks = [b for b in blocks if b["type"] == "actions"]
    assert len(actions_blocks) == 2
    assert len(actions_blocks[0]["elements"]) == 5
    assert len(actions_blocks[1]["elements"]) == 1


def test_format_confirm_ignores_options():
    """input_type='confirm' always produces Yes/No regardless of options argument."""
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Are you sure?", ["Maybe", "Later"], "s", input_type="confirm")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    texts = [btn["text"]["text"] for btn in actions_block["elements"]]
    assert texts == ["Yes", "No"]


def test_format_confirm_button_values():
    from tools.slack_bridge import format_bridge_blocks
    blocks = format_bridge_blocks("Confirm?", [], "s42", input_type="confirm")
    actions_block = next(b for b in blocks if b["type"] == "actions")
    values = [btn["value"] for btn in actions_block["elements"]]
    assert "s42|yes" in values
    assert "s42|no" in values


def test_format_choice_empty_options_raises():
    from tools.slack_bridge import format_bridge_blocks
    with pytest.raises(ValueError, match="options must not be empty"):
        format_bridge_blocks("Pick one", [], "sess", input_type="choice")


# ---------------------------------------------------------------------------
# detect_channel_id
# ---------------------------------------------------------------------------

FAKE_PROJECTS = {
    "slackclaw": {
        "name": "Shellack",
        "primary_channel": "slackclaw-dev",
        "github_repo": "YOUR_ORG/Shellack",
    }
}

FAKE_ROUTING_OK = {
    "slackclaw-dev": {"mode": "dedicated", "channel_id": "C_SC"},
}

FAKE_ROUTING_MISSING = {
    "slackclaw-dev": {"mode": "dedicated"},  # no channel_id
}


def test_detect_known_repo_returns_channel_id():
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:YOUR_ORG/Shellack.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_OK):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C_SC"
    assert project_name == "Shellack"


def test_detect_unknown_repo_falls_back():
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:someone/other.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_OK):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "Unknown"


def test_detect_missing_channel_id_falls_back_with_warning(capsys):
    from tools.slack_bridge import detect_channel_id
    with patch("subprocess.check_output", return_value=b"git@github.com:YOUR_ORG/Shellack.git"), \
         patch("tools.slack_bridge.PROJECTS", FAKE_PROJECTS), \
         patch("tools.slack_bridge.CHANNEL_ROUTING", FAKE_ROUTING_MISSING):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "Shellack"
    captured = capsys.readouterr()
    assert "WARNING" in captured.err


def test_detect_not_a_git_repo_falls_back():
    from tools.slack_bridge import detect_channel_id
    import subprocess
    with patch("subprocess.check_output", side_effect=subprocess.CalledProcessError(128, "git")):
        channel_id, project_name = detect_channel_id()
    assert channel_id == "C0AMEEP7EFL"
    assert project_name == "Unknown"


# ---------------------------------------------------------------------------
# post_session_start
# ---------------------------------------------------------------------------

@responses.activate
def test_post_session_start_success():
    import responses as rsps
    rsps.add(rsps.POST, "https://slack.com/api/chat.postMessage",
             json={"ok": True}, status=200)
    from tools.slack_bridge import post_session_start
    import os
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        post_session_start("C_SC", "Shellack")  # must not raise


@responses.activate
def test_post_session_start_logs_warning_on_slack_error(caplog):
    import responses as rsps, logging
    rsps.add(rsps.POST, "https://slack.com/api/chat.postMessage",
             json={"ok": False, "error": "channel_not_found"}, status=200)
    from tools.slack_bridge import post_session_start
    import os
    with patch.dict(os.environ, {"SLACK_BOT_TOKEN": "xoxb-test"}):
        with caplog.at_level(logging.WARNING):
            post_session_start("CBAD", "Shellack")
    assert "channel_not_found" in caplog.text
