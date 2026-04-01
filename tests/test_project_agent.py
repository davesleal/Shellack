import pytest
from unittest.mock import MagicMock, patch
from agents.project_agent import ProjectAgent

PROJECT_CONFIG = {
    "name": "Alpha",
    "path": "/tmp/alpha",
    "platform": "ios",
    "language": "swift",
    "github_repo": "test-org/Alpha",
    "context": {
        "description": "Test project for unit tests",
        "purpose": "Validate ProjectAgent behavior",
        "tech": "SwiftUI",
        "patterns": ["MVVM architecture"],
        "watch_out": ["Force unwraps"],
    },
}


def make_agent(tmp_path):
    """Create a ProjectAgent with all external dependencies mocked."""
    app = MagicMock()
    app.client.chat_postMessage = MagicMock(return_value={"ts": "999.000"})
    client = MagicMock()
    config = dict(PROJECT_CONFIG)
    config["path"] = str(tmp_path)

    with patch("agents.project_agent.GitHubClient"), patch(
        "peer_review.StagedPeerReview"
    ), patch("orchestrator_config.PROJECTS", {}):
        agent = ProjectAgent(
            project_key="alpha",
            project_config=config,
            client=client,
            app=app,
            channel_id="C123",
            thread_ts="111.222",
        )
    return agent, app, client


# All tests patch quick_reply so no real AI calls are made.
QUICK_REPLY_PATH = "agents.project_agent.quick_reply"


def test_handle_resets_opened_issue_number_each_call(tmp_path):
    """Stale issue number from a previous call must not bleed into the next."""
    agent, app, client = make_agent(tmp_path)
    agent._opened_issue_number = 99  # simulate stale state

    with patch(QUICK_REPLY_PATH, return_value="Here is the answer"):
        agent.handle("What is the architecture?", [])

    assert agent._opened_issue_number is None


def test_handle_skips_lifecycle_for_plain_qa(tmp_path):
    """Lifecycle started() must NOT fire for plain Q&A — only for bug/crash tasks."""
    agent, app, client = make_agent(tmp_path)
    with patch(QUICK_REPLY_PATH, return_value="Answer"), patch.object(
        agent._lifecycle, "started"
    ) as mock_started:
        agent.handle("explain the codebase", [])
    mock_started.assert_not_called()


def test_handle_returns_error_tuple_on_exception(tmp_path):
    agent, app, client = make_agent(tmp_path)
    with patch(QUICK_REPLY_PATH, side_effect=Exception("backend down")):
        with pytest.raises(Exception, match="backend down"):
            agent.handle("explain something", [])


def test_handle_does_not_trigger_review_for_general_text_response(tmp_path):
    """General questions never trigger peer review (peer review was removed)."""
    agent, app, client = make_agent(tmp_path)
    with patch(QUICK_REPLY_PATH, return_value="Plain text answer, no code"):
        response, label = agent.handle("what does this app do?", [])
    assert response == "Plain text answer, no code"


def test_handle_does_not_trigger_review_for_read_only_response(tmp_path):
    """Peer review is removed — code in response never triggers it."""
    with patch(QUICK_REPLY_PATH, return_value="Here:\n```swift\nlet x = 1\n```"):
        agent, app, client = make_agent(tmp_path)
        response, _ = agent.handle("show me a code example", [])
    assert "let x = 1" in response


def test_handle_passes_model_to_quick_reply(tmp_path):
    """handle() with model kwarg forwards it to quick_reply."""
    agent, app, client = make_agent(tmp_path)

    with patch(QUICK_REPLY_PATH, return_value="Here is the answer") as mock_quick_reply:
        agent.handle("explain the architecture", [], model="claude-haiku-4-5-20251001")

    mock_quick_reply.assert_called_once()
    _, kwargs = mock_quick_reply.call_args
    assert kwargs.get("model") == "claude-haiku-4-5-20251001"
