#!/usr/bin/env python3
"""GitHub API client for issue creation and management."""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)

LABEL_MAP = {
    "crash":         ["crash", "bug"],
    "investigate":   ["bug"],
    "review":        ["review"],
    "testing":       ["testing"],
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
