# tests/test_agent_factory.py
"""Tests for AgentFactory channel-keyed caching and warmup."""

import pytest
from unittest.mock import MagicMock, patch


def _make_factory():
    from agents.agent_factory import AgentFactory

    return AgentFactory(client=MagicMock())


def _make_routing(channel_ids):
    """Build a minimal CHANNEL_ROUTING dict for testing."""
    return {
        f"proj-{cid}-dev": {
            "mode": "dedicated",
            "channel_id": cid,
            "project": f"proj-{cid}",
        }
        for cid in channel_ids
    }


def _make_projects(channel_ids):
    return {
        f"proj-{cid}": {"name": f"Proj{cid}", "path": "/tmp", "language": "python"}
        for cid in channel_ids
    }


@patch("agents.agent_factory.ProjectAgent")
def test_get_agent_caches_by_channel_id(MockAgent):
    factory = _make_factory()
    MockAgent.return_value = MagicMock()

    agent1 = factory.get_agent(
        "key", {"name": "X", "path": "/"}, MagicMock(), "C1", "ts1"
    )
    agent2 = factory.get_agent(
        "key", {"name": "X", "path": "/"}, MagicMock(), "C1", "ts2"
    )

    assert agent1 is agent2
    assert MockAgent.call_count == 1  # only created once


@patch("agents.agent_factory.ProjectAgent")
def test_get_agent_updates_thread_ts_on_reuse(MockAgent):
    factory = _make_factory()
    mock_instance = MagicMock()
    MockAgent.return_value = mock_instance

    factory.get_agent("key", {"name": "X", "path": "/"}, MagicMock(), "C1", "ts1")
    factory.get_agent("key", {"name": "X", "path": "/"}, MagicMock(), "C1", "ts2")

    assert mock_instance.thread_ts == "ts2"


@patch("agents.agent_factory.ProjectAgent")
def test_get_agent_separate_agents_per_channel(MockAgent):
    factory = _make_factory()
    MockAgent.side_effect = [MagicMock(), MagicMock()]

    a1 = factory.get_agent("k1", {"name": "A"}, MagicMock(), "C1", "ts1")
    a2 = factory.get_agent("k2", {"name": "B"}, MagicMock(), "C2", "ts1")

    assert a1 is not a2
    assert MockAgent.call_count == 2


@patch("agents.agent_factory.ProjectAgent")
def test_warmup_all_creates_agents_for_dedicated_channels(MockAgent):
    MockAgent.return_value = MagicMock()
    factory = _make_factory()
    routing = _make_routing(["C1", "C2"])
    projects = _make_projects(["C1", "C2"])

    factory.warmup_all(projects, routing, app=MagicMock())

    assert MockAgent.call_count == 2
    assert "C1" in factory._agents
    assert "C2" in factory._agents


@patch("agents.agent_factory.ProjectAgent")
def test_warmup_all_skips_empty_channel_id(MockAgent):
    MockAgent.return_value = MagicMock()
    factory = _make_factory()
    routing = {
        "proj-dev": {"mode": "dedicated", "channel_id": "", "project": "proj"},
    }
    projects = {"proj": {"name": "Proj", "path": "/tmp", "language": "python"}}

    factory.warmup_all(projects, routing, app=MagicMock())

    MockAgent.assert_not_called()


@patch("agents.agent_factory.ProjectAgent")
def test_warmup_all_skips_non_dedicated_modes(MockAgent):
    MockAgent.return_value = MagicMock()
    factory = _make_factory()
    routing = {
        "orchestrator": {
            "mode": "orchestrator",
            "channel_id": "C99",
            "project": "shellack",
        },
        "code-review": {
            "mode": "peer_review",
            "channel_id": "C88",
            "project": "shellack",
        },
    }
    projects = {"shellack": {"name": "Shellack", "path": "/tmp", "language": "python"}}

    factory.warmup_all(projects, routing, app=MagicMock())

    MockAgent.assert_not_called()


@patch("agents.agent_factory.ProjectAgent")
def test_warmup_all_does_not_duplicate_existing_agents(MockAgent):
    MockAgent.return_value = MagicMock()
    factory = _make_factory()
    routing = _make_routing(["C1"])
    projects = _make_projects(["C1"])

    factory.warmup_all(projects, routing, app=MagicMock())
    factory.warmup_all(projects, routing, app=MagicMock())  # second call

    assert MockAgent.call_count == 1  # still only one agent
