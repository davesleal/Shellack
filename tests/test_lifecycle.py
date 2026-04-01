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
        project_name="Alpha",
        owner_user_id="U999",
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


def test_issue_created_posts_to_thread_only(notifier, app):
    notifier.issue_created("https://github.com/x/y/issues/42", 42)
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["thread_ts"] == "111.222"
    assert "🐛" in calls[0].kwargs["text"]
    assert "#42" in calls[0].kwargs["text"]


def test_needs_human_mentions_owner_in_thread(notifier, app):
    notifier.needs_human("ambiguous scope")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert calls[0].kwargs["thread_ts"] == "111.222"
    assert "U999" in calls[0].kwargs["text"]


def test_failed_posts_to_thread_only(notifier, app):
    notifier.failed("API timeout")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert "❌" in calls[0].kwargs["text"]
