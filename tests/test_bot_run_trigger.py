# tests/test_bot_run_trigger.py
"""Tests for @Shellack run: trigger and thread reply routing."""
import pytest
from unittest.mock import MagicMock, patch


def _make_event(text, channel="C123", ts="100.0", thread_ts=None):
    event = {"text": text, "channel": channel, "ts": ts}
    if thread_ts:
        event["thread_ts"] = thread_ts
    return event


def test_run_prefix_creates_slack_session():
    """Top-level @Shellack run: creates a SlackSession in RUN_SESSIONS."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.get_channel_name", return_value="dayist-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "SESSION_MODEL": "claude-sonnet-4-6"}):

        event = _make_event("<@BOT> run: investigate the crash")
        bot_unified.handle_mention(event, say=MagicMock())

    assert "100.0" in bot_unified.RUN_SESSIONS
    mock_session.start.assert_called_once()


def test_run_prefix_uses_max_backend_when_configured():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False

    with patch("bot_unified.SlackSession", return_value=mock_session), \
         patch("bot_unified.MaxBackend") as MockMax, \
         patch("bot_unified.get_channel_name", return_value="slackclaw-dev"), \
         patch.dict("os.environ", {"SESSION_BACKEND": "max"}):

        MockMax.available.return_value = True
        event = _make_event("<@BOT> run: do stuff")
        bot_unified.handle_mention(event, say=MagicMock())

    MockMax.assert_called_once()


def test_thread_run_prefix_does_not_create_session():
    """run: in a thread reply must NOT trigger a new session."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, \
         patch("bot_unified.get_channel_name", return_value="dayist-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False):

        # Thread reply that starts with "run:" — should NOT create a session
        event = _make_event("<@BOT> run: keep going", ts="101.0", thread_ts="99.0")
        bot_unified.handle_mention(event, say=MagicMock())

    assert bot_unified.RUN_SESSIONS == {}
    mock_proj.assert_called_once()  # routed normally


def test_thread_reply_routes_to_active_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_session = MagicMock()
    mock_session._closed = False
    bot_unified.RUN_SESSIONS["99.0"] = mock_session

    event = _make_event("keep going", ts="100.0", thread_ts="99.0")
    bot_unified.handle_message(event, say=MagicMock())

    mock_session.feed_input.assert_called_once_with("keep going")


def test_thread_reply_falls_through_when_no_active_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    event = _make_event("hello", ts="200.0", thread_ts="150.0")
    with patch.object(bot_unified, "handle_mention") as mock_handle:
        bot_unified.handle_message(event, say=MagicMock())

    assert "150.0" not in bot_unified.RUN_SESSIONS


def test_non_run_mention_does_not_create_session():
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    with patch("bot_unified.handle_project_message") as mock_proj, \
         patch("bot_unified.get_channel_name", return_value="dayist-dev"), \
         patch("bot_unified.is_orchestrator_channel", return_value=False), \
         patch("bot_unified.is_peer_review_channel", return_value=False):

        event = _make_event("<@BOT> what files are in Settings?")
        bot_unified.handle_mention(event, say=MagicMock())

    assert bot_unified.RUN_SESSIONS == {}
    mock_proj.assert_called_once()


def test_simple_triage_uses_quick_reply():
    """Simple triage => no SlackSession created, agent.handle() called with haiku model."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    from tools.triage import TriageResult
    mock_triage_result = TriageResult(tier="simple", model="claude-haiku-4-5-20251001", reason="simple question")

    mock_app = MagicMock()
    mock_app.client.reactions_add = MagicMock()
    mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "101.0"})
    mock_app.client.chat_delete = MagicMock()
    mock_app.client.reactions_remove = MagicMock()

    mock_agent = MagicMock()
    mock_agent.handle.return_value = ("answer", "DayistAgent")

    with patch("bot_unified.SlackSession") as MockSession, \
         patch("bot_unified.classify", return_value=mock_triage_result), \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.app", mock_app), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "TRIAGE_ENABLED": "true"}):

        mock_factory.get_agent.return_value = mock_agent
        event = {"text": "what does this project do?", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

    # SlackSession must NOT have been constructed
    MockSession.assert_not_called()
    # agent.handle must have been called with the haiku model
    mock_agent.handle.assert_called_once()
    _, kwargs = mock_agent.handle.call_args
    assert kwargs.get("model") == "claude-haiku-4-5-20251001"


def test_complex_triage_starts_slack_session():
    """Complex triage => SlackSession created and registered, active_sessions cleared."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    from tools.triage import TriageResult
    mock_triage_result = TriageResult(tier="complex", model="claude-sonnet-4-6", reason="big refactor")

    mock_app = MagicMock()
    mock_app.client.reactions_add = MagicMock()
    mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "101.0"})
    mock_app.client.chat_delete = MagicMock()
    mock_app.client.reactions_remove = MagicMock()

    mock_session = MagicMock()

    with patch("bot_unified.SlackSession", return_value=mock_session) as MockSession, \
         patch("bot_unified.classify", return_value=mock_triage_result), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.app", mock_app), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "TRIAGE_ENABLED": "true"}):

        event = {"text": "refactor the auth system", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

    # SlackSession must have been created
    MockSession.assert_called_once()
    # Session registered in RUN_SESSIONS
    assert "100.0" in bot_unified.RUN_SESSIONS
    # session.start called
    mock_session.start.assert_called_once()
    # active_sessions must NOT contain thread_ts
    assert "100.0" not in bot_unified.active_sessions


def test_complex_triage_on_close_records_session():
    """The on_close closure from a complex-triage session calls record_session."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    from tools.triage import TriageResult
    mock_triage_result = TriageResult(tier="complex", model="claude-sonnet-4-6", reason="big refactor")

    mock_app = MagicMock()
    mock_app.client.reactions_add = MagicMock()
    mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "101.0"})
    mock_app.client.chat_delete = MagicMock()
    mock_app.client.reactions_remove = MagicMock()

    mock_session = MagicMock()

    with patch("bot_unified.SlackSession", return_value=mock_session) as MockSession, \
         patch("bot_unified.classify", return_value=mock_triage_result), \
         patch("bot_unified.APIBackend"), \
         patch("bot_unified.app", mock_app), \
         patch.object(bot_unified.usage_tracker, "record_session") as mock_record_session, \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "TRIAGE_ENABLED": "true"}):

        event = {"text": "refactor the auth system", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

        # Retrieve on_close kwarg from SlackSession constructor and call it
        on_close_fn = MockSession.call_args[1]["on_close"]
        on_close_fn()

    mock_record_session.assert_called_once_with("api", "claude-sonnet-4-6")


def test_triage_disabled_skips_classify():
    """TRIAGE_ENABLED=false => classify is never called, agent runs with model=None."""
    import importlib
    import bot_unified
    importlib.reload(bot_unified)

    mock_app = MagicMock()
    mock_app.client.reactions_add = MagicMock()
    mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "101.0"})
    mock_app.client.chat_delete = MagicMock()
    mock_app.client.reactions_remove = MagicMock()

    mock_agent = MagicMock()
    mock_agent.handle.return_value = ("answer", "DayistAgent")

    with patch("bot_unified.classify") as mock_classify, \
         patch("bot_unified.agent_factory") as mock_factory, \
         patch("bot_unified.app", mock_app), \
         patch.dict("os.environ", {"SESSION_BACKEND": "api", "TRIAGE_ENABLED": "false"}):

        mock_factory.get_agent.return_value = mock_agent
        event = {"text": "what does this project do?", "channel": "C123", "ts": "100.0"}
        bot_unified.handle_project_message(event, say=MagicMock(), channel_name="dayist-dev")

    mock_classify.assert_not_called()
    mock_agent.handle.assert_called_once()
    _, kwargs = mock_agent.handle.call_args
    assert kwargs.get("model") is None
