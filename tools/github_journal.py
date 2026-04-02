"""GitHub Discussions journal — weekly threads with daily entries."""
from __future__ import annotations

import json
import logging
import subprocess
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


def _monday_of_week(dt: datetime) -> str:
    """Return the Monday date string for the week containing dt."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("%Y-%m-%d")


def _week_title(dt: datetime) -> str:
    """Weekly discussion title."""
    monday = dt - timedelta(days=dt.weekday())
    return monday.strftime("\U0001f4c5 Week of %Y-%m-%d")


def _find_weekly_discussion(repo: str, category: str, dt: datetime) -> Optional[int]:
    """Find existing weekly discussion by title. Returns discussion number or None."""
    title = _week_title(dt)
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/discussions",
             "--jq", f'[.[] | select(.title == "{title}")] | .[0].number'],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            num = result.stdout.strip()
            if num != "null":
                return int(num)
    except Exception as exc:
        logger.warning(f"Failed to find weekly discussion: {exc}")
    return None


def _create_discussion(repo: str, category: str, title: str, body: str) -> Optional[int]:
    """Create a GitHub Discussion. Returns discussion number or None."""
    try:
        # Get category ID first
        cat_result = subprocess.run(
            ["gh", "api", f"repos/{repo}/discussions/categories",
             "--jq", f'[.[] | select(.name == "{category}")] | .[0].slug'],
            capture_output=True, text=True, timeout=15,
        )
        category_slug = cat_result.stdout.strip() if cat_result.returncode == 0 else ""

        if not category_slug or category_slug == "null":
            logger.warning(f"Discussion category '{category}' not found in {repo}")
            return None

        # Create via gh CLI
        result = subprocess.run(
            ["gh", "discussion", "create",
             "--repo", repo,
             "--category", category,
             "--title", title,
             "--body", body],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            # Parse discussion number from URL in output
            url = result.stdout.strip()
            if "/" in url:
                return int(url.rstrip("/").split("/")[-1])
    except Exception as exc:
        logger.warning(f"Failed to create discussion: {exc}")
    return None


def _comment_on_discussion(repo: str, number: int, body: str) -> bool:
    """Add a comment to an existing discussion."""
    try:
        result = subprocess.run(
            ["gh", "discussion", "comment", str(number),
             "--repo", repo,
             "--body", body],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception as exc:
        logger.warning(f"Failed to comment on discussion: {exc}")
        return False


def _monthly_title(dt: datetime) -> str:
    """Monthly summary discussion title."""
    return f"📊 {dt.strftime('%B %Y')} — Monthly Summary"


def post_monthly_summary(
    repo: str,
    category: str,
    summary: str,
    dt: datetime | None = None,
) -> bool:
    """Post a monthly summary discussion linking back to weekly threads.

    Creates a new discussion with the summary content.
    Returns True if successful.
    """
    dt = dt or datetime.now()
    title = _monthly_title(dt)

    # Check if monthly summary already exists
    try:
        result = subprocess.run(
            ["gh", "api", f"repos/{repo}/discussions",
             "--jq", f'[.[] | select(.title == "{title}")] | .[0].number'],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip() and result.stdout.strip() != "null":
            # Already exists — add as comment instead
            number = int(result.stdout.strip())
            return _comment_on_discussion(repo, number, summary)
    except Exception as exc:
        logger.warning(f"Failed to check for existing monthly summary: {exc}")

    # Create new monthly summary discussion
    return _create_discussion(repo, category, title, summary) is not None


def post_journal_entry(
    repo: str,
    category: str,
    entry: str,
    dt: datetime | None = None,
) -> bool:
    """Post a journal entry to the weekly discussion thread.

    Creates the weekly discussion if it doesn't exist.
    Adds the entry as a comment.

    Returns True if successful.
    """
    dt = dt or datetime.now()
    date_str = dt.strftime("%a %m/%d")

    # Find or create weekly discussion
    number = _find_weekly_discussion(repo, category, dt)
    if number is None:
        title = _week_title(dt)
        body = (
            f"Weekly journal for the week of {_monday_of_week(dt)}.\n\n"
            "Daily entries are added as comments below."
        )
        number = _create_discussion(repo, category, title, body)
        if number is None:
            logger.warning("Failed to create weekly discussion, falling back to file")
            return False

    # Post entry as comment
    comment_body = f"## {date_str}\n\n{entry}"
    return _comment_on_discussion(repo, number, comment_body)
