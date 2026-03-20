import pytest
from unittest.mock import MagicMock, patch
from agents.project_agent import ProjectAgent

PROJECT_CONFIG = {
    "name": "Dayist",
    "path": "/tmp/dayist",
    "platform": "ios",
    "language": "swift",
    "github_repo": "YOUR_ORG/Dayist",
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
            project_key="dayist",
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

    with patch(QUICK_REPLY_PATH, return_value="Here is the answer"), patch.object(
        agent, "_trigger_peer_review"
    ):
        agent.handle("What is the project structure?", [])

    assert agent._opened_issue_number is None


def test_handle_calls_lifecycle_started(tmp_path):
    agent, app, client = make_agent(tmp_path)
    with patch(QUICK_REPLY_PATH, return_value="Answer"), patch.object(
        agent._lifecycle, "started"
    ) as mock_started, patch.object(agent, "_trigger_peer_review"):
        agent.handle("explain the codebase", [])
    mock_started.assert_called_once()


def test_handle_returns_error_tuple_on_exception(tmp_path):
    agent, app, client = make_agent(tmp_path)
    with patch(QUICK_REPLY_PATH, side_effect=Exception("backend down")):
        response, label = agent.handle("explain something", [])
    assert "Error" in response
    assert label == "Error"


def test_handle_does_not_trigger_review_for_general_text_response(tmp_path):
    """General questions should not trigger peer review."""
    agent, app, client = make_agent(tmp_path)
    with patch(
        QUICK_REPLY_PATH, return_value="Plain text answer, no code"
    ), patch.object(agent, "_trigger_peer_review") as mock_review:
        agent.handle("what does this project do?", [])
    mock_review.assert_not_called()


def test_handle_does_not_trigger_review_for_read_only_response(tmp_path):
    """Even responses with code blocks do NOT trigger peer review.
    Peer review only fires for CODE_CHANGING_AGENTS or opened issues."""
    with patch(QUICK_REPLY_PATH, return_value="Here:\n```swift\nlet x = 1\n```"):
        agent, app, client = make_agent(tmp_path)
        with patch.object(agent, "_trigger_peer_review") as mock_review, patch.object(
            agent, "_write_journal"
        ):
            agent.handle("show me a code example", [])
    mock_review.assert_not_called()
