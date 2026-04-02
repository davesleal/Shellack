"""Tests for session cleanup and journal finalization."""

from unittest.mock import MagicMock, patch
import time


def test_finalize_journal_polishes_and_posts():
    """Journal draft gets polished by Sonnet and posted to GitHub."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    session = {
        "journal_draft": "Raw draft about auth changes.",
        "project_key": "alpha",
        "handoff": "## Handoff",
        "turn_count": 3,
        "last_active": 0,
    }

    fake_projects = {"alpha": {"name": "Alpha", "github_repo": "org/Alpha"}}

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.polish_journal", return_value="Polished entry."
    ) as mock_polish, patch(
        "bot_unified.post_journal_entry", return_value=True
    ) as mock_post:
        bot_unified._finalize_journal(session)

    mock_polish.assert_called_once_with("Raw draft about auth changes.", "Alpha")
    mock_post.assert_called_once_with("org/Alpha", "Journal", "Polished entry.")


def test_finalize_journal_empty_draft_skips():
    """Empty journal draft does not trigger polish or post."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    session = {"journal_draft": "", "project_key": "alpha"}
    fake_projects = {"alpha": {"name": "Alpha", "github_repo": "org/Alpha"}}

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.polish_journal"
    ) as mock_polish:
        bot_unified._finalize_journal(session)

    mock_polish.assert_not_called()


def test_finalize_journal_polish_failure_uses_raw():
    """If Sonnet polish fails, raw draft is posted."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    session = {"journal_draft": "Raw draft.", "project_key": "alpha"}
    fake_projects = {"alpha": {"name": "Alpha", "github_repo": "org/Alpha"}}

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.polish_journal", return_value=None
    ), patch("bot_unified.post_journal_entry", return_value=True) as mock_post:
        bot_unified._finalize_journal(session)

    mock_post.assert_called_once_with("org/Alpha", "Journal", "Raw draft.")


def test_finalize_journal_no_repo_skips_post():
    """If project has no github_repo, post is skipped."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    session = {"journal_draft": "Some draft.", "project_key": "alpha"}
    fake_projects = {"alpha": {"name": "Alpha"}}  # no github_repo

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.polish_journal", return_value="Polished."
    ), patch("bot_unified.post_journal_entry") as mock_post:
        bot_unified._finalize_journal(session)

    mock_post.assert_not_called()


def test_finalize_journal_exception_logged_not_raised():
    """Exceptions in finalization are caught, not propagated."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    session = {"journal_draft": "Draft.", "project_key": "alpha"}
    fake_projects = {"alpha": {"name": "Alpha", "github_repo": "org/Alpha"}}

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.polish_journal", side_effect=RuntimeError("boom")
    ):
        # Should not raise
        bot_unified._finalize_journal(session)


def test_cleanup_loop_removes_stale_sessions():
    """Stale sessions are popped and finalized."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    stale_session = {
        "journal_draft": "Draft text.",
        "project_key": "alpha",
        "last_active": time.time() - 9999,
    }
    fresh_session = {
        "journal_draft": "Fresh draft.",
        "project_key": "beta",
        "last_active": time.time(),
    }

    bot_unified.active_sessions["stale.1"] = stale_session
    bot_unified.active_sessions["fresh.1"] = fresh_session

    fake_projects = {
        "alpha": {"name": "Alpha", "github_repo": "org/Alpha"},
        "beta": {"name": "Beta", "github_repo": "org/Beta"},
    }

    # Patch sleep to break after one iteration
    call_count = 0

    def fake_sleep(secs):
        nonlocal call_count
        call_count += 1
        if call_count > 1:
            raise StopIteration("break loop")

    with patch.dict(bot_unified.PROJECTS, fake_projects, clear=True), patch(
        "bot_unified.time.sleep", side_effect=fake_sleep
    ), patch("bot_unified._finalize_journal") as mock_finalize:
        try:
            bot_unified._session_cleanup_loop()
        except StopIteration:
            pass

    # Stale session removed
    assert "stale.1" not in bot_unified.active_sessions
    # Fresh session still present
    assert "fresh.1" in bot_unified.active_sessions
    # Finalize called for stale session
    mock_finalize.assert_called_once_with(stale_session)

    # Cleanup
    bot_unified.active_sessions.pop("fresh.1", None)


def test_session_gets_last_active_timestamp():
    """handle_project_message sets last_active on the session."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {
        "alpha": {
            "name": "Alpha",
            "path": "/tmp/alpha",
            "features": {"token-cart": False},
        }
    }

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.agent_factory"
    ) as mock_factory, patch(
        "bot_unified.ThinkingIndicator"
    ) as MockIndicator, patch(
        "bot_unified.app"
    ) as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("response", "Alpha")
        mock_factory.get_agent.return_value = mock_agent
        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = {
            "text": "<@BOT> hello",
            "channel": "C123",
            "ts": "100.0",
            "user": "U_USER",
        }
        bot_unified.handle_mention(event, say=MagicMock())

    session = bot_unified.active_sessions.get("100.0")
    assert session is not None
    assert "last_active" in session
    assert session["last_active"] > 0

    # Cleanup
    bot_unified.active_sessions.pop("100.0", None)
