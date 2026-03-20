import pytest
from unittest.mock import MagicMock, patch
from peer_review import StagedPeerReview, PeerReviewAgent


def make_app(channel_id="C_REVIEW"):
    app = MagicMock()
    app.client.chat_postMessage = MagicMock(
        return_value={"ts": "999.000", "channel": channel_id}
    )
    return app


def test_stage1_posts_to_code_review_channel():
    app = make_app()
    spr = StagedPeerReview(app=app, code_review_channel_id="C_REVIEW",
                           owner_user_id="U999")

    with patch.object(spr.coordinator, "review_pr") as mock_review:
        mock_review.return_value = {
            "code-quality": MagicMock(blocking_issues=[], status="approved",
                                      score=90, strengths=[], concerns=[], suggestions=[]),
        }
        spr.trigger(
            summary="Fixed login crash",
            changed_files=["LoginView.swift"],
            project_key="dayist",
            origin_thread_ts="111.222",
            origin_channel_id="C_DAYIST",
        )

    app.client.chat_postMessage.assert_called()
    calls = app.client.chat_postMessage.call_args_list
    review_post = next((c for c in calls if c.kwargs.get("channel") == "C_REVIEW"), None)
    assert review_post is not None


def test_stage1_tags_owner_on_blocking_issue():
    app = make_app()
    spr = StagedPeerReview(app=app, code_review_channel_id="C_REVIEW",
                           owner_user_id="U999")

    with patch.object(spr.coordinator, "review_pr") as mock_review:
        mock_review.return_value = {
            "security": MagicMock(blocking_issues=["SQL injection risk"],
                                  status="changes_requested", score=40,
                                  strengths=[], concerns=[], suggestions=[]),
        }
        spr.trigger("Summary", ["file.py"], "dayist", "111.222", "C_DAYIST")

    texts = [c.kwargs["text"] for c in app.client.chat_postMessage.call_args_list]
    assert any("U999" in t for t in texts)


def test_stage2_posts_cross_project_review_request():
    app = make_app()
    projects = {
        "dayist": {"platform": "ios", "language": "swift", "name": "Dayist"},
        "nova": {"platform": "ios", "language": "swift", "name": "NOVA"},
    }
    spr = StagedPeerReview(app=app, code_review_channel_id="C_REVIEW",
                           owner_user_id="U999", projects=projects)

    with patch.object(spr.coordinator, "review_pr", return_value={}):
        spr.trigger("Summary", ["file.swift"], "dayist", "111.222", "C_DAYIST")

    texts = [c.kwargs.get("text", "") for c in app.client.chat_postMessage.call_args_list]
    assert any("[nova-review]" in t for t in texts)


def test_peer_review_agent_parses_structured_json():
    agent = PeerReviewAgent("code-quality")
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='''{
        "status": "approved",
        "score": 88,
        "strengths": ["Clean code"],
        "concerns": [],
        "suggestions": ["Add tests"],
        "blocking_issues": []
    }''')]

    with patch.object(agent, "_call_claude", return_value=mock_response):
        result = agent.review({"description": "test", "files": [], "diff": ""})

    assert result.score == 88
    assert result.status == "approved"
    assert result.strengths == ["Clean code"]
