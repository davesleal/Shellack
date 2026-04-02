"""Tests for GitHub Discussions journal module."""
import subprocess
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from tools.github_journal import (
    _monday_of_week,
    _week_title,
    _find_weekly_discussion,
    _create_discussion,
    _comment_on_discussion,
    post_journal_entry,
)


# --- date helpers ---

def test_monday_of_week_on_monday():
    dt = datetime(2026, 3, 30)  # Monday
    assert _monday_of_week(dt) == "2026-03-30"


def test_monday_of_week_on_wednesday():
    dt = datetime(2026, 4, 1)  # Wednesday
    assert _monday_of_week(dt) == "2026-03-30"


def test_monday_of_week_on_sunday():
    dt = datetime(2026, 4, 5)  # Sunday
    assert _monday_of_week(dt) == "2026-03-30"


def test_week_title_format():
    dt = datetime(2026, 4, 2)  # Thursday
    title = _week_title(dt)
    assert title == "\U0001f4c5 Week of 2026-03-30"


# --- _find_weekly_discussion ---

@patch("tools.github_journal.subprocess.run")
def test_find_weekly_discussion_found(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="42\n")
    result = _find_weekly_discussion("owner/repo", "Journal", datetime(2026, 4, 2))
    assert result == 42
    mock_run.assert_called_once()


@patch("tools.github_journal.subprocess.run")
def test_find_weekly_discussion_not_found(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="null\n")
    result = _find_weekly_discussion("owner/repo", "Journal", datetime(2026, 4, 2))
    assert result is None


@patch("tools.github_journal.subprocess.run")
def test_find_weekly_discussion_empty_output(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="")
    result = _find_weekly_discussion("owner/repo", "Journal", datetime(2026, 4, 2))
    assert result is None


@patch("tools.github_journal.subprocess.run")
def test_find_weekly_discussion_gh_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1, stdout="")
    result = _find_weekly_discussion("owner/repo", "Journal", datetime(2026, 4, 2))
    assert result is None


@patch("tools.github_journal.subprocess.run")
def test_find_weekly_discussion_exception(mock_run):
    mock_run.side_effect = subprocess.TimeoutExpired(cmd="gh", timeout=15)
    result = _find_weekly_discussion("owner/repo", "Journal", datetime(2026, 4, 2))
    assert result is None


# --- _create_discussion ---

@patch("tools.github_journal.subprocess.run")
def test_create_discussion_success(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="journal\n"),  # category lookup
        MagicMock(returncode=0, stdout="https://github.com/owner/repo/discussions/99\n"),
    ]
    result = _create_discussion("owner/repo", "Journal", "Title", "Body")
    assert result == 99
    assert mock_run.call_count == 2


@patch("tools.github_journal.subprocess.run")
def test_create_discussion_no_category(mock_run):
    mock_run.return_value = MagicMock(returncode=0, stdout="null\n")
    result = _create_discussion("owner/repo", "Journal", "Title", "Body")
    assert result is None


@patch("tools.github_journal.subprocess.run")
def test_create_discussion_gh_create_fails(mock_run):
    mock_run.side_effect = [
        MagicMock(returncode=0, stdout="journal\n"),  # category found
        MagicMock(returncode=1, stdout=""),  # create fails
    ]
    result = _create_discussion("owner/repo", "Journal", "Title", "Body")
    assert result is None


# --- _comment_on_discussion ---

@patch("tools.github_journal.subprocess.run")
def test_comment_on_discussion_success(mock_run):
    mock_run.return_value = MagicMock(returncode=0)
    assert _comment_on_discussion("owner/repo", 42, "Hello") is True


@patch("tools.github_journal.subprocess.run")
def test_comment_on_discussion_failure(mock_run):
    mock_run.return_value = MagicMock(returncode=1)
    assert _comment_on_discussion("owner/repo", 42, "Hello") is False


@patch("tools.github_journal.subprocess.run")
def test_comment_on_discussion_exception(mock_run):
    mock_run.side_effect = OSError("gh not found")
    assert _comment_on_discussion("owner/repo", 42, "Hello") is False


# --- post_journal_entry ---

@patch("tools.github_journal._comment_on_discussion", return_value=True)
@patch("tools.github_journal._find_weekly_discussion", return_value=42)
def test_post_journal_entry_comments_on_existing(mock_find, mock_comment):
    dt = datetime(2026, 4, 2)
    result = post_journal_entry("owner/repo", "Journal", "Did stuff.", dt=dt)
    assert result is True
    mock_find.assert_called_once_with("owner/repo", "Journal", dt)
    mock_comment.assert_called_once_with("owner/repo", 42, "## Thu 04/02\n\nDid stuff.")


@patch("tools.github_journal._comment_on_discussion", return_value=True)
@patch("tools.github_journal._create_discussion", return_value=99)
@patch("tools.github_journal._find_weekly_discussion", return_value=None)
def test_post_journal_entry_creates_discussion(mock_find, mock_create, mock_comment):
    dt = datetime(2026, 4, 2)
    result = post_journal_entry("owner/repo", "Journal", "New entry.", dt=dt)
    assert result is True
    mock_create.assert_called_once()
    title_arg = mock_create.call_args[0][2]
    assert "2026-03-30" in title_arg
    mock_comment.assert_called_once_with("owner/repo", 99, "## Thu 04/02\n\nNew entry.")


@patch("tools.github_journal._create_discussion", return_value=None)
@patch("tools.github_journal._find_weekly_discussion", return_value=None)
def test_post_journal_entry_gh_failure(mock_find, mock_create):
    result = post_journal_entry("owner/repo", "Journal", "Entry.", dt=datetime(2026, 4, 2))
    assert result is False
