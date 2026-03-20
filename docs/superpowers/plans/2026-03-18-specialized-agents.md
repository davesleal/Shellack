# Specialized Product Agents Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade each project agent with CLAUDE.md context loading, GitHub issue auto-creation, Slack lifecycle posts (thread + channel), staged peer review, and per-project journaling.

**Architecture:** Agent-managed lifecycle — each `ProjectAgent` owns its full task lifecycle, reads its project's `CLAUDE.md` at init, uses three new tools (`GitHubClient`, `LifecycleNotifier`, `JournalWriter`) during `handle()`, and triggers `StagedPeerReview` before completing any significant task. High-signal events cross-post top-level to the project channel for Claude app visibility.

**Tech Stack:** Python 3.13, Slack Bolt, Anthropic API, GitHub REST API (via `requests`), pytest for tests.

**Spec:** `docs/superpowers/specs/2026-03-18-specialized-agents-design.md`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tools/__init__.py` | Create | Package init |
| `tools/github_client.py` | Create | GitHub issue creation/closing, repo routing |
| `tools/lifecycle.py` | Create | Slack thread + channel status posts |
| `tools/journal_writer.py` | Create | Append narrative entries to project JOURNAL.md |
| `tests/__init__.py` | Create | Test package init |
| `tests/test_github_client.py` | Create | Unit tests for GitHubClient |
| `tests/test_lifecycle.py` | Create | Unit tests for LifecycleNotifier |
| `tests/test_journal_writer.py` | Create | Unit tests for JournalWriter |
| `tests/test_staged_peer_review.py` | Create | Unit tests for StagedPeerReview |
| `peer_review.py` | Modify | Fix brittle JSON parsing; add StagedPeerReview class |
| `orchestrator_config.py` | Modify | Add `github_repo` to all 7 projects |
| `agents/project_agent.py` | Rewrite | CLAUDE.md loading, full lifecycle wiring |
| `agents/agent_factory.py` | Modify | Keyed by thread_ts; new constructor signature |
| `agents/sub_agents.py` | Modify | Fix label: "test" → "testing" in TRIGGER_MAP |
| `bot_unified.py` | Modify | Pass app, channel_id, thread_ts to factory |
| `CLAUDE.md` | Create | Maestro coordination instructions |
| `.env.example` | Modify | Add GITHUB_TOKEN, DAVE_SLACK_USER_ID |
| `STATE.md` | Update | Reflect new capabilities |
| `docs/JOURNAL.md` | Update | Log this session's work |

---

## Task 1: Test infrastructure + package scaffolding

**Files:**
- Create: `tools/__init__.py`
- Create: `tests/__init__.py`
- Modify: `requirements.txt`

- [ ] **Step 1.1: Add pytest to requirements**

```bash
source venv/bin/activate
pip install pytest pytest-mock requests
# Overwrite requirements.txt with full current environment (avoids duplicates)
pip freeze > requirements.txt
```

- [ ] **Step 1.2: Create package inits**

Create `tools/__init__.py` (empty):
```python
```

Create `tests/__init__.py` (empty):
```python
```

- [ ] **Step 1.3: Verify pytest works**

```bash
source venv/bin/activate && pytest tests/ -v
```
Expected: `no tests ran` (no errors)

- [ ] **Step 1.4: Commit**

```bash
git add tools/__init__.py tests/__init__.py requirements.txt
git commit -m "chore: add test infrastructure and tools package"
```

---

## Task 2: `tools/github_client.py`

**Files:**
- Create: `tools/github_client.py`
- Create: `tests/test_github_client.py`

- [ ] **Step 2.1: Write failing tests**

Create `tests/test_github_client.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from tools.github_client import GitHubClient

PROJECTS = {
    "dayist": {"github_repo": "davesleal/Dayist", "platform": "ios"},
}


@pytest.fixture
def client():
    return GitHubClient(token="test-token", projects=PROJECTS)


def test_create_issue_returns_number_and_url(client):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 42, "html_url": "https://github.com/davesleal/Dayist/issues/42"}

    with patch("tools.github_client.requests.post", return_value=mock_response):
        result = client.create_issue("dayist", "Login crash", "Details here", "crash")

    assert result["number"] == 42
    assert result["url"] == "https://github.com/davesleal/Dayist/issues/42"


def test_create_issue_returns_none_on_api_error(client):
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "Bad credentials"}

    with patch("tools.github_client.requests.post", return_value=mock_response):
        result = client.create_issue("dayist", "Title", "Body", "crash")

    assert result is None


def test_create_issue_returns_none_for_unknown_project(client):
    result = client.create_issue("unknown_project", "Title", "Body", "crash")
    assert result is None


def test_create_issue_applies_correct_labels_for_crash(client):
    mock_response = MagicMock()
    mock_response.status_code = 201
    mock_response.json.return_value = {"number": 1, "html_url": "https://github.com/x/y/issues/1"}

    with patch("tools.github_client.requests.post", return_value=mock_response) as mock_post:
        client.create_issue("dayist", "Title", "Body", "crash")
        call_json = mock_post.call_args.kwargs["json"]
        assert "crash" in call_json["labels"]
        assert "bug" in call_json["labels"]
        assert "ios" in call_json["labels"]


def test_close_issue_returns_true_on_success(client):
    mock_response = MagicMock()
    mock_response.status_code = 200

    with patch("tools.github_client.requests.patch", return_value=mock_response):
        result = client.close_issue("dayist", 42)

    assert result is True


def test_close_issue_returns_false_on_error(client):
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("tools.github_client.requests.patch", return_value=mock_response):
        result = client.close_issue("dayist", 999)

    assert result is False
```

- [ ] **Step 2.2: Run tests to confirm they fail**

```bash
source venv/bin/activate && pytest tests/test_github_client.py -v
```
Expected: `ImportError` or `ModuleNotFoundError` — `github_client` doesn't exist yet.

- [ ] **Step 2.3: Implement `tools/github_client.py`**

```python
#!/usr/bin/env python3
"""GitHub API client for issue creation and management."""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

LABEL_MAP = {
    "crash":       ["crash", "bug"],
    "investigate": ["bug"],
    "review":      ["review"],
    "testing":     ["testing"],
    "documentation": ["documentation"],
}

PLATFORM_LABELS = {
    "ios":    "ios",
    "macos":  "macos",
    "server": "server",
}


class GitHubClient:
    BASE_URL = "https://api.github.com"

    def __init__(self, token: str, projects: dict):
        self.token = token
        self.projects = projects
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    def _repo(self, project_key: str) -> Optional[str]:
        project = self.projects.get(project_key)
        if not project:
            logger.warning(f"Unknown project key: {project_key}")
            return None
        return project.get("github_repo")

    def _platform_label(self, project_key: str) -> Optional[str]:
        project = self.projects.get(project_key, {})
        platform = project.get("platform", "")
        return PLATFORM_LABELS.get(platform)

    def create_issue(self, project_key: str, title: str, body: str,
                     task_type: str) -> Optional[dict]:
        """Create a GitHub issue. Returns {"number": int, "url": str} or None on error."""
        repo = self._repo(project_key)
        if not repo:
            return None

        labels = list(LABEL_MAP.get(task_type, []))
        platform = self._platform_label(project_key)
        if platform:
            labels.append(platform)

        try:
            resp = requests.post(
                f"{self.BASE_URL}/repos/{repo}/issues",
                headers=self.headers,
                json={"title": title, "body": body, "labels": labels},
            )
            if resp.status_code == 201:
                data = resp.json()
                return {"number": data["number"], "url": data["html_url"]}
            else:
                logger.error(f"GitHub issue creation failed [{resp.status_code}]: {resp.json()}")
                return None
        except Exception as e:
            logger.error(f"GitHub API error: {e}")
            return None

    def close_issue(self, project_key: str, issue_number: int) -> bool:
        """Close a GitHub issue. Returns True on success."""
        repo = self._repo(project_key)
        if not repo:
            return False

        try:
            resp = requests.patch(
                f"{self.BASE_URL}/repos/{repo}/issues/{issue_number}",
                headers=self.headers,
                json={"state": "closed"},
            )
            if resp.status_code == 200:
                return True
            else:
                logger.error(f"GitHub close issue failed [{resp.status_code}]")
                return False
        except Exception as e:
            logger.error(f"GitHub API error closing issue: {e}")
            return False
```

- [ ] **Step 2.4: Run tests — expect all pass**

```bash
source venv/bin/activate && pytest tests/test_github_client.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 2.5: Commit**

```bash
git add tools/github_client.py tests/test_github_client.py
git commit -m "feat: add GitHubClient for issue creation and closing"
```

---

## Task 3: `tools/lifecycle.py`

**Files:**
- Create: `tools/lifecycle.py`
- Create: `tests/test_lifecycle.py`

- [ ] **Step 3.1: Write failing tests**

Create `tests/test_lifecycle.py`:

```python
import pytest
from unittest.mock import MagicMock, call
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


def test_failed_posts_to_thread_only(notifier, app):
    notifier.failed("API timeout")
    calls = app.client.chat_postMessage.call_args_list
    assert len(calls) == 1
    assert "❌" in calls[0].kwargs["text"]
```

- [ ] **Step 3.2: Run tests to confirm fail**

```bash
source venv/bin/activate && pytest tests/test_lifecycle.py -v
```
Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3.3: Implement `tools/lifecycle.py`**

```python
#!/usr/bin/env python3
"""Lifecycle notifier — posts structured status to Slack thread and channel."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class LifecycleNotifier:
    def __init__(self, app, channel_id: str, thread_ts: str,
                 project_name: str, dave_user_id: str):
        self.app = app
        self.channel_id = channel_id
        self.thread_ts = thread_ts
        self.project_name = project_name
        self.dave_user_id = dave_user_id

    def _post_thread(self, text: str):
        """Post reply in the active thread."""
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                thread_ts=self.thread_ts,
                text=text,
            )
        except Exception as e:
            logger.error(f"Lifecycle thread post failed: {e}")

    def _post_channel(self, text: str):
        """Post top-level to the project channel (no thread_ts)."""
        try:
            self.app.client.chat_postMessage(
                channel=self.channel_id,
                text=text,
            )
        except Exception as e:
            logger.error(f"Lifecycle channel post failed: {e}")

    # Thread-only events
    def started(self, summary: str):
        self._post_thread(f"🔵 Started: {summary}")

    def in_progress(self, detail: str):
        self._post_thread(f"🔨 {detail}")

    def failed(self, error: str):
        self._post_thread(f"❌ Failed: {error}")

    # Thread + channel events
    def issue_created(self, url: str, number: int):
        self._post_thread(f"🐛 Issue #{number} created → {url}")
        self._post_channel(
            f"🐛 [{self.project_name}] Issue #{number} opened → {url}"
        )

    def pending_review(self, thread_link: str = ""):
        self._post_thread("👀 Sending to #code-review...")
        link_text = f" → {thread_link}" if thread_link else ""
        self._post_channel(
            f"👀 [{self.project_name}] Peer review requested{link_text}"
        )

    def done(self, summary: str, issue_number: Optional[int] = None):
        issue_text = f", issue #{issue_number} closed" if issue_number else ""
        self._post_thread(f"✅ Done: {summary}{issue_text}")
        self._post_channel(
            f"✅ [{self.project_name}] Done: {summary}{issue_text}"
        )

    def needs_human(self, reason: str):
        self._post_thread(f"🙋 <@{self.dave_user_id}> — {reason}")
        self._post_channel(
            f"🙋 [{self.project_name}] <@{self.dave_user_id}> — {reason}"
        )
```

- [ ] **Step 3.4: Run tests — expect all pass**

```bash
source venv/bin/activate && pytest tests/test_lifecycle.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 3.5: Commit**

```bash
git add tools/lifecycle.py tests/test_lifecycle.py
git commit -m "feat: add LifecycleNotifier with thread and channel posting"
```

---

## Task 4: `tools/journal_writer.py`

**Files:**
- Create: `tools/journal_writer.py`
- Create: `tests/test_journal_writer.py`

- [ ] **Step 4.1: Write failing tests**

Create `tests/test_journal_writer.py`:

```python
import pytest
import os
from pathlib import Path
from tools.journal_writer import JournalWriter


@pytest.fixture
def tmp_project(tmp_path):
    return str(tmp_path)


def test_creates_docs_journal_if_none_exists(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry("Fix crash", "User reported crash", "Investigated", "Fixed", "Guard statements matter")
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    assert journal.exists()


def test_appends_to_existing_docs_journal(tmp_project):
    docs = Path(tmp_project) / "docs"
    docs.mkdir()
    journal = docs / "JOURNAL.md"
    journal.write_text("# Journal\n\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "Context", "Approach", "Outcome", "Insights")
    content = journal.read_text()
    assert "Task" in content
    assert "Context" in content
    assert "Insights" in content


def test_appends_to_root_journal_if_docs_missing(tmp_project):
    root_journal = Path(tmp_project) / "JOURNAL.md"
    root_journal.write_text("# Journal\n\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "Context", "Approach", "Outcome", "Insights")
    content = root_journal.read_text()
    assert "Task" in content


def test_prefers_docs_journal_over_root(tmp_project):
    docs = Path(tmp_project) / "docs"
    docs.mkdir()
    docs_journal = docs / "JOURNAL.md"
    docs_journal.write_text("# Docs Journal\n")
    root_journal = Path(tmp_project) / "JOURNAL.md"
    root_journal.write_text("# Root Journal\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "C", "A", "O", "I")
    assert "Task" in docs_journal.read_text()
    assert "Task" not in root_journal.read_text()


def test_entry_includes_issue_number_when_provided(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry("Fix", "Context", "Approach", "Outcome", "Insights", issue_number=42)
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    assert "#42" in journal.read_text()


def test_entry_has_date_header(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "C", "A", "O", "I")
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    content = journal.read_text()
    import re
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)
```

- [ ] **Step 4.2: Run tests to confirm fail**

```bash
source venv/bin/activate && pytest tests/test_journal_writer.py -v
```
Expected: `ImportError`.

- [ ] **Step 4.3: Implement `tools/journal_writer.py`**

```python
#!/usr/bin/env python3
"""Appends narrative journal entries to per-project JOURNAL.md files."""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class JournalWriter:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def _resolve_journal_path(self) -> Path:
        docs_journal = self.project_path / "docs" / "JOURNAL.md"
        root_journal = self.project_path / "JOURNAL.md"

        if docs_journal.exists():
            return docs_journal
        if root_journal.exists():
            return root_journal

        # Neither exists — create docs/JOURNAL.md
        docs_journal.parent.mkdir(parents=True, exist_ok=True)
        docs_journal.write_text("# Project Journal\n\n")
        return docs_journal

    def append_entry(self, title: str, context: str, approach: str,
                     outcome: str, insights: str,
                     issue_number: Optional[int] = None):
        """Append a dated narrative entry to the project journal."""
        today = date.today().isoformat()
        issue_line = f"\n**GitHub Issue:** #{issue_number}" if issue_number else ""

        entry = f"""
## {today} — {title}

**Context:** {context}

**Approach:** {approach}

**Outcome:** {outcome}{issue_line}

**Insights:** {insights}

---
"""
        try:
            journal_path = self._resolve_journal_path()
            with open(journal_path, "a") as f:
                f.write(entry)
            logger.info(f"Journal entry written to {journal_path}")
        except Exception as e:
            logger.error(f"Failed to write journal entry: {e}")
```

- [ ] **Step 4.4: Run tests — expect all pass**

```bash
source venv/bin/activate && pytest tests/test_journal_writer.py -v
```
Expected: 6 tests PASSED.

- [ ] **Step 4.5: Commit**

```bash
git add tools/journal_writer.py tests/test_journal_writer.py
git commit -m "feat: add JournalWriter for per-project narrative journaling"
```

---

## Task 5: Fix `peer_review.py` + add `StagedPeerReview`

**Files:**
- Modify: `peer_review.py`
- Create: `tests/test_staged_peer_review.py`

- [ ] **Step 5.1: Write failing tests**

Create `tests/test_staged_peer_review.py`:

```python
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
                           dave_user_id="U999")

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


def test_stage1_tags_dave_on_blocking_issue():
    app = make_app()
    spr = StagedPeerReview(app=app, code_review_channel_id="C_REVIEW",
                           dave_user_id="U999")

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
                           dave_user_id="U999", projects=projects)

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
```

- [ ] **Step 5.2: Run tests to confirm fail**

```bash
source venv/bin/activate && pytest tests/test_staged_peer_review.py -v
```
Expected: `ImportError` for `StagedPeerReview`.

- [ ] **Step 5.3: Refactor `PeerReviewAgent` to use structured JSON + extract `_call_claude`**

In `peer_review.py`:
1. Add `import json` at the top (after existing imports)
2. **Delete** the existing `review()`, `_extract_score()`, and `_extract_list()` methods entirely
3. Add these replacements inside `PeerReviewAgent`:

```python
import json

def _call_claude(self, messages: list, system: str):
    return anthropic_client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=2048,
        system=system,
        messages=messages,
    )

def review(self, changes: Dict) -> CodeReview:
    system_prompt = self.system_prompts.get(self.focus_area, "You are a code reviewer.")
    system_prompt += """

IMPORTANT: Respond ONLY with valid JSON matching this exact schema:
{
  "status": "approved" | "changes_requested",
  "score": <integer 0-100>,
  "strengths": [<string>, ...],
  "concerns": [<string>, ...],
  "suggestions": [<string>, ...],
  "blocking_issues": [<string>, ...]
}
Do not include any text outside the JSON object."""

    review_prompt = f"""Review these changes:
Description: {changes.get('description', 'No description')}
Files: {', '.join(changes.get('files', []))}
Diff:
{changes.get('diff', 'No diff')}"""

    try:
        response = self._call_claude(
            messages=[{"role": "user", "content": review_prompt}],
            system=system_prompt,
        )
        content = response.content[0].text.strip()
        # Strip markdown fences if present
        if content.startswith("```"):
            content = content.split("```")[1]
            if content.startswith("json"):
                content = content[4:]
        data = json.loads(content)
        return CodeReview(
            reviewer=self.focus_area,
            status=data.get("status", "changes_requested"),
            score=int(data.get("score", 0)),
            strengths=data.get("strengths", []),
            concerns=data.get("concerns", []),
            suggestions=data.get("suggestions", []),
            blocking_issues=data.get("blocking_issues", []),
        )
    except Exception as e:
        print(f"Error in {self.focus_area} review: {e}")
        return CodeReview(
            reviewer=self.focus_area, status="error", score=0,
            strengths=[], concerns=[f"Review failed: {str(e)}"],
            suggestions=[], blocking_issues=[],
        )
```

- [ ] **Step 5.4: Add `StagedPeerReview` class to `peer_review.py`**

Append at end of `peer_review.py`:

```python
class StagedPeerReview:
    """Orchestrates Stage 1 (automated) + Stage 2 (cross-project) peer review."""

    def __init__(self, app, code_review_channel_id: str, dave_user_id: str,
                 projects: dict = None):
        self.app = app
        self.review_channel = code_review_channel_id
        self.dave_user_id = dave_user_id
        self.projects = projects or {}
        self.coordinator = PeerReviewCoordinator()

    def trigger(self, summary: str, changed_files: list, project_key: str,
                origin_thread_ts: str, origin_channel_id: str):
        """Fire-and-forget: run Stage 1 then Stage 2."""
        pr_data = {
            "description": summary,
            "files": changed_files,
            "diff": f"Agent summary: {summary}",
        }

        # Stage 1: post opening message to #code-review
        opening = self.app.client.chat_postMessage(
            channel=self.review_channel,
            text=f"🔍 *Peer Review* — {project_key}\n{summary}\nFiles: {', '.join(changed_files) or 'none'}",
        )
        review_thread_ts = opening.get("ts")

        # Run reviewers and post results
        reviews = self.coordinator.review_pr(pr_data)
        summary_text = self.coordinator.format_review_summary(reviews)
        self.app.client.chat_postMessage(
            channel=self.review_channel,
            thread_ts=review_thread_ts,
            text=summary_text,
        )

        # Escalate if blocking
        has_blocking = any(r.blocking_issues for r in reviews.values())
        if has_blocking:
            self.app.client.chat_postMessage(
                channel=self.review_channel,
                thread_ts=review_thread_ts,
                text=f"🙋 <@{self.dave_user_id}> — blocking issues found, needs review",
            )

        # Stage 2: tag ≤2 peer project agents with same platform/language
        project = self.projects.get(project_key, {})
        platform = project.get("platform")
        language = project.get("language")
        peers = [
            key for key, cfg in self.projects.items()
            if key != project_key and (
                cfg.get("platform") == platform or cfg.get("language") == language
            )
        ][:2]

        for peer_key in peers:
            self.app.client.chat_postMessage(
                channel=self.review_channel,
                thread_ts=review_thread_ts,
                text=f"[{peer_key}-review] @Shellack please review the above changes from a {peer_key} perspective.",
            )
```

- [ ] **Step 5.5: Run all tests**

```bash
source venv/bin/activate && pytest tests/ -v
```
Expected: all existing tests PASS. New staged peer review tests PASS.

- [ ] **Step 5.6: Commit**

```bash
git add peer_review.py tests/test_staged_peer_review.py
git commit -m "feat: add StagedPeerReview and fix brittle JSON parsing in PeerReviewAgent"
```

---

## Task 6: `orchestrator_config.py` — add `github_repo`

**Files:**
- Modify: `orchestrator_config.py`

- [ ] **Step 6.1: Add `github_repo` to all 7 projects**

In `orchestrator_config.py`, update each project entry:

```python
"dayist": {
    "name": "Dayist",
    "github_repo": "davesleal/Dayist",
    ...
},
"nova": {
    "name": "NOVA",
    "github_repo": "davesleal/NOVA",
    ...
},
"nudge": {
    "name": "Nudge",
    "github_repo": "davesleal/Nudge",
    ...
},
"slackclaw": {
    "name": "Shellack",
    "github_repo": "davesleal/Shellack",
    ...
},
"tiledock": {
    "name": "TileDock",
    "github_repo": "davesleal/TileDock",
    ...
},
"atmosuniversal": {
    "name": "Atmos Universal",
    "github_repo": "davesleal/atmos-universal",
    ...
},
"sideplane": {
    "name": "SidePlane",
    "github_repo": "davesleal/SidePlane",
    ...
},
```

- [ ] **Step 6.2: Verify import still works**

```bash
source venv/bin/activate && python3 -c "from orchestrator_config import PROJECTS; print([p['github_repo'] for p in PROJECTS.values()])"
```
Expected: list of 7 repo slugs printed.

- [ ] **Step 6.3: Verify `agents/sub_agents.py` TRIGGER_MAP**

Open `agents/sub_agents.py` and confirm `"test"` and `"testing"` both map to `TestingAgent` (not `CrashInvestigatorAgent`). No code change needed — labels are applied by `GitHubClient`, not here. Just a sanity check.

- [ ] **Step 6.4: Commit**

```bash
git add orchestrator_config.py
git commit -m "feat: add github_repo to all projects in orchestrator_config"
```

---

## Task 7: Rewrite `agents/project_agent.py`

**Files:**
- Modify: `agents/project_agent.py`
- Modify: `agents/agent_factory.py`

This is the core integration task. The agent now owns the full lifecycle.

- [ ] **Step 7.1: Update `agents/project_agent.py`**

Full replacement of the `ProjectAgent` class (keep `PROJECT_KNOWLEDGE` and `LANGUAGE_CONVENTIONS` dicts as-is):

```python
import os
from pathlib import Path
from tools.github_client import GitHubClient
from tools.lifecycle import LifecycleNotifier
from tools.journal_writer import JournalWriter
# Import all sub-agent classes used in this module (including DocsAgent for type checks)
from .sub_agents import (
    detect_sub_agent,
    CrashInvestigatorAgent,
    TestingAgent,
    CodeReviewAgent,
    DocsAgent,
)


CODE_CHANGING_AGENTS = (CrashInvestigatorAgent, TestingAgent)


class ProjectAgent:
    def __init__(self, project_key: str, project_config: dict, client,
                 app, channel_id: str, thread_ts: str):
        self.project_key = project_key
        self.project = project_config
        self.client = client
        self.app = app
        self.channel_id = channel_id
        self.thread_ts = thread_ts

        self._system_prompt = self._build_system_prompt()
        self._lifecycle = LifecycleNotifier(
            app=app,
            channel_id=channel_id,
            thread_ts=thread_ts,
            project_name=project_config["name"],
            dave_user_id=os.environ.get("DAVE_SLACK_USER_ID", ""),
        )
        self._github = GitHubClient(
            token=os.environ.get("GITHUB_TOKEN", ""),
            projects=self._load_projects(),
        )
        self._journal = JournalWriter(project_config["path"])
        self._opened_issue_number: int | None = None

    def _load_projects(self) -> dict:
        from orchestrator_config import PROJECTS
        return PROJECTS

    def _load_claude_md(self) -> str:
        claude_md_path = Path(self.project["path"]) / "CLAUDE.md"
        if claude_md_path.exists():
            return claude_md_path.read_text()
        import logging
        logging.getLogger(__name__).warning(
            f"CLAUDE.md not found for {self.project['name']} at {claude_md_path}"
        )
        return ""

    def _build_system_prompt(self) -> str:
        # Build base prompt from PROJECT_KNOWLEDGE + LANGUAGE_CONVENTIONS
        # (existing logic preserved)
        p = self.project
        knowledge = PROJECT_KNOWLEDGE.get(self.project_key, {})
        lang = p.get("language", "unknown")
        conventions = LANGUAGE_CONVENTIONS.get(lang, "")
        patterns = "\n".join(f"- {pat}" for pat in knowledge.get("patterns", []))
        watch_out = "\n".join(f"- {w}" for w in knowledge.get("watch_out", []))

        prompt = f"""You are a senior {lang} developer and specialist agent for {p['name']}.

## Project: {p['name']}
{knowledge.get('description', '')}

**Purpose:** {knowledge.get('purpose', 'See project documentation')}
**Platform:** {p.get('platform', 'unknown')}
**Tech stack:** {knowledge.get('tech', p.get('language', ''))}
**Codebase:** {p.get('path', 'configured path')}
"""
        if patterns:
            prompt += f"\n## Key Patterns\n{patterns}\n"
        if watch_out:
            prompt += f"\n## Watch Out For\n{watch_out}\n"
        prompt += f"\n{conventions}"
        prompt += """
## Your Role
You have deep knowledge of this specific codebase and can:
- Analyze and explain code in context of this project's patterns
- Investigate bugs with platform-specific expertise
- Implement features following project conventions
- Coordinate code reviews with sub-agents
- Post findings to #code-review when appropriate

Be concise and precise. Reference specific files/patterns when relevant."""

        # Prepend CLAUDE.md (project rules take highest priority)
        claude_md = self._load_claude_md()
        if claude_md:
            prompt = f"## Project Rules (from CLAUDE.md)\n\n{claude_md}\n\n---\n\n{prompt}"

        return prompt

    def _is_code_changing(self, sub_agent_class, response: str) -> bool:
        if sub_agent_class in CODE_CHANGING_AGENTS:
            return True
        if sub_agent_class is CodeReviewAgent:
            return False
        # General/Docs: only if response contains fenced code block
        return "```" in response

    def _task_type_for_github(self, sub_agent_class) -> str | None:
        """Return GitHub task type label or None if no issue should be created."""
        mapping = {
            CrashInvestigatorAgent: "crash",
            TestingAgent: "testing",
            DocsAgent: "documentation",
            CodeReviewAgent: None,  # never create issue for reviews
        }
        return mapping.get(sub_agent_class, None)

    def handle(self, prompt: str, thread_context: list = None) -> tuple[str, str]:
        sub_agent_class = detect_sub_agent(prompt)
        task_type = self._task_type_for_github(sub_agent_class) if sub_agent_class else None
        # Only auto-create issues for crash/bug task types, never for None/review/docs
        is_bug_task = task_type == "crash"

        # Summarise task for lifecycle
        words = prompt.split()[:8]
        task_summary = " ".join(words) + ("..." if len(prompt.split()) > 8 else "")
        self._lifecycle.started(task_summary)

        # Auto-create GitHub issue for bugs/crashes
        if is_bug_task and task_type:
            title = f"[{task_type.title()}] {task_summary}"
            body = f"Reported via Slack:\n\n> {prompt}"
            issue = self._github.create_issue(self.project_key, title, body, task_type)
            if issue:
                self._opened_issue_number = issue["number"]
                self._lifecycle.issue_created(issue["url"], issue["number"])
            else:
                self._lifecycle.in_progress("⚠️ Could not create GitHub issue — continuing")

        # Run sub-agent or main agent
        self._lifecycle.in_progress("Analyzing...")

        try:
            if sub_agent_class:
                agent = sub_agent_class(self.client, self.project)
                label = sub_agent_class.__name__.replace("Agent", "")
                response = agent.run(prompt, thread_context)
            else:
                label = self.project["name"]
                messages = list(thread_context or [])
                messages.append({"role": "user", "content": prompt})
                api_response = self.client.messages.create(
                    model="claude-sonnet-4-5-20250929",
                    max_tokens=4096,
                    system=self._system_prompt,
                    messages=messages,
                )
                response = api_response.content[0].text
        except Exception as e:
            self._lifecycle.failed(str(e))
            return f"Error: {e}", "Error"

        # Determine if this is a significant task
        code_changed = self._is_code_changing(sub_agent_class, response)
        issue_created = self._opened_issue_number is not None
        is_significant = code_changed or issue_created

        if is_significant:
            self._trigger_peer_review(prompt, response)
            if self._opened_issue_number:
                self._github.close_issue(self.project_key, self._opened_issue_number)

        summary = " ".join(response.split()[:12]) + "..."
        self._lifecycle.done(summary, issue_number=self._opened_issue_number)

        if is_significant:
            self._write_journal(prompt, response)

        return response, label

    def _trigger_peer_review(self, prompt: str, response: str):
        from peer_review import StagedPeerReview
        from orchestrator_config import PROJECTS
        spr = StagedPeerReview(
            app=self.app,
            code_review_channel_id=os.environ.get("CODE_REVIEW_CHANNEL_ID", "code-review"),
            dave_user_id=os.environ.get("DAVE_SLACK_USER_ID", ""),
            projects=PROJECTS,
        )
        self._lifecycle.pending_review()
        spr.trigger(
            summary=f"{self.project['name']}: {prompt[:100]}",
            changed_files=[],
            project_key=self.project_key,
            origin_thread_ts=self.thread_ts,
            origin_channel_id=self.channel_id,
        )

    def _write_journal(self, prompt: str, response: str):
        self._journal.append_entry(
            title=f"{self.project['name']}: {prompt[:60]}",
            context=f"Slack request: {prompt}",
            approach="Agent analysis and response",
            outcome=response[:400],
            insights="See full response in Slack thread",
            issue_number=self._opened_issue_number,
        )
```

- [ ] **Step 7.2: Update `agents/agent_factory.py`**

```python
class AgentFactory:
    def __init__(self, client):
        self.client = client
        self._agents: dict[str, "ProjectAgent"] = {}

    def get_agent(self, project_key: str, project_config: dict,
                  app, channel_id: str, thread_ts: str) -> "ProjectAgent":
        """One agent per thread — keyed by thread_ts."""
        if thread_ts not in self._agents:
            self._agents[thread_ts] = ProjectAgent(
                project_key, project_config, self.client,
                app, channel_id, thread_ts
            )
            print(f"🤖 Created {project_config['name']} agent for thread {thread_ts}")
        return self._agents[thread_ts]
```

- [ ] **Step 7.3: Verify import chain**

```bash
source venv/bin/activate && python3 -c "
from agents import AgentFactory
from anthropic import Anthropic
import os
from dotenv import load_dotenv
load_dotenv()
print('✅ Import chain OK')
"
```
Expected: `✅ Import chain OK`

- [ ] **Step 7.4: Commit**

```bash
git add agents/project_agent.py agents/agent_factory.py
git commit -m "feat: rewrite ProjectAgent with CLAUDE.md loading, lifecycle, GitHub, and peer review"
```

---

## Task 8: Update `bot_unified.py`

**Files:**
- Modify: `bot_unified.py`

- [ ] **Step 8.1: Pass `app`, `channel_id`, `thread_ts` to factory in `handle_project_message`**

In `handle_project_message`, add `channel_id = event["channel"]` immediately after the existing `thread_ts = event.get("thread_ts", event["ts"])` line.

Then replace the `agent_factory.get_agent(project_key, project)` call with:

```python
agent = agent_factory.get_agent(
    project_key, project,
    app, channel_id, thread_ts
)
response, agent_label = agent.handle(prompt, context)
```

- [ ] **Step 8.2: Add `CODE_REVIEW_CHANNEL_ID` to env lookup**

Add to `.env.example`:
```
CODE_REVIEW_CHANNEL_ID=code-review   # Slack channel name for peer review posts
GITHUB_TOKEN=ghp_your_token_here
DAVE_SLACK_USER_ID=<your-slack-user-id>
```

- [ ] **Step 8.3: Smoke test bot startup**

```bash
source venv/bin/activate && python3 -c "
import bot_unified
print('✅ bot_unified imports cleanly')
" 2>&1 | head -5
```
Expected: no import errors.

- [ ] **Step 8.4: Commit**

```bash
git add bot_unified.py .env.example
git commit -m "feat: wire agent factory with thread-scoped context in bot_unified"
```

---

## Task 9: Write `CLAUDE.md` (Maestro instructions)

**Files:**
- Create: `CLAUDE.md` (Shellack root)

- [ ] **Step 9.1: Write maestro CLAUDE.md**

Create `/Users/daveleal/Repos/Shellack/CLAUDE.md`:

```markdown
# Shellack — Maestro Agent Instructions

You are the orchestrator for Leal Labs' development workspace. You coordinate across 7 projects and ensure consistent standards, smooth handoffs, and clear communication to Dave.

## Projects & Channel Routing

| Project | Channel | Platform | Repo |
|---------|---------|----------|------|
| Dayist | #dayist-dev | iOS 26+ | davesleal/Dayist |
| NOVA | #nova-dev | iOS | davesleal/NOVA |
| Nudge | #nudge-dev | iOS | davesleal/Nudge |
| TileDock | #tiledock-dev | macOS | davesleal/TileDock |
| Atmos Universal | #atmos-dev | macOS | davesleal/atmos-universal |
| SidePlane | #sideplane-dev | macOS | davesleal/SidePlane |
| Shellack | #slackclaw-dev | Server/Python | davesleal/Shellack |

## GitHub Issue Standards

- Title format: `[Type] Brief description` — e.g. `[Crash] Login crash on iPhone 15`
- Severity: P0 = crash (auto-create), P1 = bug (auto-create), P2 = feature (ask first)
- Labels: use the taxonomy in `tools/github_client.py` — crash, bug, review, testing, documentation + platform

## Escalation Rules — When to Tag Dave

Tag `@Dave` when:
- A peer review Stage 1 flags a **blocking** issue
- Task is **ambiguous in scope** (unclear if it's P1 or P2, unclear which project)
- A **security vulnerability** is found
- Agent encounters an **unrecoverable error** mid-task
- Work requires **credentials or access** the agent doesn't have

Do NOT tag Dave for: warnings, suggestions, minor style issues, informational questions.

## Peer Review Protocol

Every task that produces a code change or GitHub issue must trigger `StagedPeerReview`:
1. Stage 1: Quality, Security, Performance agents run automatically
2. Stage 2: Maestro tags ≤2 peer agents from projects sharing the same platform or language
3. `CodeReviewAgent` tasks do NOT self-trigger peer review

## Journal Standards

After every significant task, write a `JOURNAL.md` entry in the project repo:
- **Context:** what triggered the task (user request, App Store review, etc.)
- **Approach:** how you investigated or implemented
- **Outcome:** what was resolved; include GitHub issue number if applicable
- **Insights:** something interesting or worth sharing — write this as if starting a blog post paragraph

## Completion Checklist

After every task, in this order:
1. Update `STATE.md` in Shellack root with current status
2. Append to `docs/JOURNAL.md` in Shellack
3. Update `README.md` only if a new user-facing capability was added

## Channel Visibility

High-signal events post top-level to the project channel (not just in thread):
- 🐛 Issue created
- 👀 Peer review triggered
- 🙋 Dave escalation
- ✅ Task done

This lets Claude app scan project channels for a workspace-wide status update.
```

- [ ] **Step 9.2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add maestro CLAUDE.md with coordination protocol for Shellack"
```

---

## Task 10: Run full test suite + update docs

**Files:**
- Modify: `STATE.md`
- Modify: `docs/JOURNAL.md`
- Modify: `README.md`

- [ ] **Step 10.1: Run full test suite**

```bash
source venv/bin/activate && pytest tests/ -v --tb=short
```
Expected: all tests PASS with no errors.

- [ ] **Step 10.2: Update `STATE.md`**

Update the checkpoint to reflect new capabilities:
- CLAUDE.md loading per agent ✅
- GitHub issue auto-creation ✅
- Lifecycle Slack posts (thread + channel) ✅
- Staged peer review (Stage 1 + Stage 2) ✅
- Per-project journaling ✅
- Maestro CLAUDE.md written ✅

- [ ] **Step 10.3: Append to `docs/JOURNAL.md`**

Add a session entry covering what was built today and why.

- [ ] **Step 10.4: Update `README.md` — add new capabilities**

Under Features, add:
- 🧠 **Project-Aware Agents** — each agent loads its project's `CLAUDE.md` for deep context
- 🐛 **GitHub Issue Auto-Creation** — bugs and crashes auto-open issues in the right repo
- 📋 **Lifecycle Visibility** — structured status posts in thread and channel
- 🔍 **Staged Peer Review** — automated Quality/Security/Performance + cross-project agent review
- 📔 **Project Journaling** — narrative JOURNAL.md entries suitable for blog posts

- [ ] **Step 10.5: Final commit**

```bash
git add STATE.md docs/JOURNAL.md README.md
git commit -m "docs: update STATE, JOURNAL, and README after specialized agents implementation"
```

---

## Quick Reference: Key Env Vars

| Var | Purpose |
|-----|---------|
| `GITHUB_TOKEN` | GitHub API — needs `repo` scope |
| `DAVE_SLACK_USER_ID` | Used in 🙋 escalations |
| `CODE_REVIEW_CHANNEL_ID` | Slack channel for peer review (default: `code-review`) |
| `SLACK_BOT_TOKEN` | Existing — Slack bot auth |
| `SLACK_APP_TOKEN` | Existing — Socket mode |
| `ANTHROPIC_API_KEY` | Existing — Claude API |

## Test Commands

```bash
source venv/bin/activate

# Individual suites
pytest tests/test_github_client.py -v
pytest tests/test_lifecycle.py -v
pytest tests/test_journal_writer.py -v
pytest tests/test_staged_peer_review.py -v

# Full suite
pytest tests/ -v --tb=short
```
