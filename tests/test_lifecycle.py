import pytest
from unittest.mock import MagicMock
from tools.lifecycle import LifecycleNotifier


@pytest.fixture
def app():
    mock_app = MagicMock()
    mock_app.client.chat_postMessage = MagicMock()
    return mock_app


@pytest.fixture
def notifier(app):
    return LifecycleNotifier(
        app=app,
        channel_id="C123",
        thread_ts="111.222",
        project_name="Dayist",
        dave_user_id="U999",
    )


def test_started_posts_to_thread_only(notifier, app):
    notifier.started("investigating crash")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["thread_ts"] == "111.222"
    assert "🔵" in calls[0].kwargs["text"]


def test_in_progress_posts_to_thread_only(notifier, app):
    notifier.in_progress("analyzing LoginView")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["thread_ts"] == "111.222"


def test_issue_created_posts_to_thread_and_channel(notifier, app):
    notifier.issue_created("https://github.com/x/y/issues/42", 42)
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 2
    thread_call = next(c for c in calls if c.kwargs.get("thread_ts") == "111.222")
    channel_call = next(c for c in calls if "thread_ts" not in c.kwargs)
    assert "🐛" in thread_call.kwargs["text"]
    assert "[Dayist]" in channel_call.kwargs["text"]
    assert "#42" in channel_call.kwargs["text"]


def test_done_posts_to_thread_and_channel(notifier, app):
    notifier.done("fixed login crash", issue_number=42)
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 2
    channel_call = next(c for c in calls if "thread_ts" not in c.kwargs)
    assert "✅" in channel_call.kwargs["text"]
    assert "[Dayist]" in channel_call.kwargs["text"]


def test_needs_human_mentions_dave(notifier, app):
    notifier.needs_human("ambiguous scope")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 2
    texts = [c.kwargs["text"] for c in calls]
    assert any("U999" in t for t in texts)


def test_pending_review_includes_thread_link_in_channel_post(notifier, app):
    notifier.pending_review(thread_link="https://slack.com/thread/123")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 2
    channel_call = next(c for c in calls if "thread_ts" not in c.kwargs)
    assert "https://slack.com/thread/123" in channel_call.kwargs["text"]


def test_failed_posts_to_thread_only(notifier, app):
    notifier.failed("API timeout")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert "❌" in calls[0].kwargs["text"]
