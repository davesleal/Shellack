"""Integration tests: Token Cart wired into handle_project_message."""

from unittest.mock import MagicMock, patch
import pytest


def _make_event(text, channel="C123", ts="100.0", thread_ts=None):
    event = {"text": text, "channel": channel, "ts": ts, "user": "U_USER"}
    if thread_ts:
        event["thread_ts"] = thread_ts
    return event


def test_first_turn_runs_post_call():
    """First turn: post-call compaction runs and stores handoff."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha", "features": {}}}

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "explain auth"
    mock_cart.post_call.return_value = {
        "handoff": "## Handoff",
        "journal_draft": "Entry",
    }

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
    ), patch(
        "bot_unified.agent_factory"
    ) as mock_factory, patch(
        "bot_unified.ThinkingIndicator"
    ) as MockIndicator, patch(
        "bot_unified.app"
    ) as mock_app:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("Auth uses OAuth2", "Alpha")
        mock_factory.get_agent.return_value = mock_agent
        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> explain auth", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_cart.post_call.assert_called_once()
    assert bot_unified.active_sessions["100.0"]["handoff"] == "## Handoff"
    assert bot_unified.active_sessions["100.0"]["turn_count"] == 1


def test_second_turn_pre_call_uses_prior_handoff():
    """Second turn: pre-call receives prior handoff."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    bot_unified.active_sessions["99.0"] = {
        "handoff": "## Prior handoff",
        "journal_draft": "",
        "turn_count": 1,
        "project_key": "alpha",
    }

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha", "features": {}}}

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "enriched context"
    mock_cart.post_call.return_value = {
        "handoff": "## Updated",
        "journal_draft": "Updated",
    }

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
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

        event = _make_event("<@BOT> next question", ts="100.0", thread_ts="99.0")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_cart.pre_call.assert_called_once()
    assert mock_cart.pre_call.call_args[1]["handoff"] == "## Prior handoff"


def test_token_cart_failure_does_not_block_agent():
    """If token cart fails, agent still runs and responds."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha", "features": {}}}

    mock_cart = MagicMock()
    mock_cart.pre_call.side_effect = Exception("cart exploded")
    mock_cart.post_call.side_effect = Exception("cart exploded again")

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
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

        event = _make_event("<@BOT> do something", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_factory.get_agent.return_value.handle.assert_called_once()


def test_token_cart_disabled_skips_haiku_calls():
    """When token-cart feature is disabled, no Haiku calls are made."""
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

    mock_cart = MagicMock()

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
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

        event = _make_event("<@BOT> do stuff", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_cart.pre_call.assert_not_called()
    mock_cart.post_call.assert_not_called()


def test_new_thread_picks_up_thread_memory():
    """New thread with no active session reads thread memory for pre-call."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {"alpha": {"name": "Alpha", "path": "/tmp/alpha", "features": {}}}

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "enriched with thread memory"
    mock_cart.post_call.return_value = {
        "handoff": "## New Handoff",
        "journal_draft": "Entry",
    }

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
    ), patch(
        "bot_unified.agent_factory"
    ) as mock_factory, patch(
        "bot_unified.ThinkingIndicator"
    ) as MockIndicator, patch(
        "bot_unified.app"
    ) as mock_app, patch(
        "tools.thread_memory.read_thread_memory", return_value="## Prior Thread Context"
    ) as mock_read, patch(
        "tools.thread_memory.write_thread_memory", return_value=True
    ) as mock_write:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("response", "Alpha")
        mock_factory.get_agent.return_value = mock_agent
        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> start fresh", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    # pre_call should receive the thread memory as handoff (new thread, no session handoff)
    mock_cart.pre_call.assert_called_once()
    assert mock_cart.pre_call.call_args[1]["handoff"] == "## Prior Thread Context"

    # write_thread_memory should be called with the new handoff
    mock_write.assert_called_once_with("/tmp/alpha", "alpha", "## New Handoff")


def test_external_handoff_disabled_skips_thread_memory():
    """When external-handoff feature is disabled, thread memory is not read or written."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {
        "alpha": {
            "name": "Alpha",
            "path": "/tmp/alpha",
            "features": {"external-handoff": False},
        }
    }

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "enriched"
    mock_cart.post_call.return_value = {"handoff": "## H", "journal_draft": "J"}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
    ), patch(
        "bot_unified.agent_factory"
    ) as mock_factory, patch(
        "bot_unified.ThinkingIndicator"
    ) as MockIndicator, patch(
        "bot_unified.app"
    ) as mock_app, patch(
        "tools.thread_memory.read_thread_memory"
    ) as mock_read, patch(
        "tools.thread_memory.write_thread_memory"
    ) as mock_write:

        mock_agent = MagicMock()
        mock_agent.handle.return_value = ("response", "Alpha")
        mock_factory.get_agent.return_value = mock_agent
        MockIndicator.return_value = MagicMock()
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()

        event = _make_event("<@BOT> do stuff", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_read.assert_not_called()
    mock_write.assert_not_called()


def test_token_cart_enabled_by_default():
    """When no features config, token cart is enabled by default."""
    import importlib
    import bot_unified

    importlib.reload(bot_unified)

    fake_routing = {"alpha-dev": {"project": "alpha", "mode": "dedicated"}}
    fake_projects = {
        "alpha": {"name": "Alpha", "path": "/tmp/alpha"}
    }  # no features key

    mock_cart = MagicMock()
    mock_cart.pre_call.return_value = "enriched"
    mock_cart.post_call.return_value = {"handoff": "h", "journal_draft": "j"}

    with patch("bot_unified.get_channel_name", return_value="alpha-dev"), patch(
        "bot_unified.is_orchestrator_channel", return_value=False
    ), patch("bot_unified.is_peer_review_channel", return_value=False), patch.dict(
        bot_unified.CHANNEL_ROUTING, fake_routing, clear=True
    ), patch.dict(
        bot_unified.PROJECTS, fake_projects, clear=True
    ), patch(
        "bot_unified.token_cart", mock_cart
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

        event = _make_event("<@BOT> do stuff", channel="C123")
        bot_unified.handle_mention(event, say=MagicMock())

    mock_cart.pre_call.assert_called_once()
    mock_cart.post_call.assert_called_once()


def test_reply_posted_as_separate_message():
    """[reply] content is posted as a separate Slack message, not in the indicator."""
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
        mock_agent.handle.return_value = (
            "[think] Checking files.\n[reply] The answer is 42.",
            "Alpha",
        )
        mock_factory.get_agent.return_value = mock_agent

        mock_indicator = MagicMock()
        MockIndicator.return_value = mock_indicator
        mock_app.client.reactions_add = MagicMock()
        mock_app.client.reactions_remove = MagicMock()
        mock_app.client.chat_postMessage = MagicMock(return_value={"ts": "200.0"})

        event = {
            "text": "<@BOT> question",
            "channel": "C123",
            "ts": "100.0",
            "user": "U_USER",
        }
        bot_unified.handle_mention(event, say=MagicMock())

    # Indicator should get think block, not the full response
    mock_indicator.done.assert_called_once()
    done_kwargs = mock_indicator.done.call_args[1]
    assert "Checking files" in done_kwargs.get("think_block", "")
    # "The answer is 42" should NOT be in the indicator
    assert "42" not in str(done_kwargs.get("think_block", ""))

    # Reply should be posted as a separate message via chat_postMessage
    post_calls = mock_app.client.chat_postMessage.call_args_list
    reply_texts = [str(c) for c in post_calls]
    assert any(
        "42" in t for t in reply_texts
    ), f"Reply '42' not found in posted messages: {reply_texts}"
