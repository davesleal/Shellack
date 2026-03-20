#!/usr/bin/env python3
"""
SlackClaw Peer Review System
Autonomous agents review each other's work
"""

import json
import os
from typing import Dict, List
from dataclasses import dataclass
from anthropic import Anthropic

anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))


@dataclass
class CodeReview:
    """Code review result"""

    reviewer: str
    status: str  # "approved", "changes_requested", "commented"
    score: int  # 0-100
    strengths: List[str]
    concerns: List[str]
    suggestions: List[str]
    blocking_issues: List[str]


class PeerReviewAgent:
    """Agent that performs code reviews"""

    def __init__(self, focus_area: str):
        self.focus_area = focus_area
        self.system_prompts = {
            "code-quality": """You are a senior software engineer focused on code quality.
Evaluate code for:
- Readability and clarity
- Maintainability
- Adherence to best practices
- Proper abstractions
- DRY principle
- SOLID principles""",
            "security": """You are a security engineer focused on finding vulnerabilities.
Evaluate code for:
- Authentication/authorization issues
- Data exposure risks
- SQL injection, XSS, CSRF vulnerabilities
- Insecure dependencies
- Proper error handling
- Secrets in code""",
            "performance": """You are a performance engineer.
Evaluate code for:
- Memory leaks
- Inefficient algorithms (O(n²) where O(n) possible)
- Database N+1 queries
- Unnecessary network calls
- Blocking operations
- Resource cleanup""",
        }

    def _call_claude(self, messages: list, system: str):
        return anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=2048,
            system=system,
            messages=messages,
        )

    def review(self, changes: Dict) -> CodeReview:
        system_prompt = self.system_prompts.get(
            self.focus_area, "You are a code reviewer."
        )
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
                reviewer=self.focus_area,
                status="error",
                score=0,
                strengths=[],
                concerns=[f"Review failed: {str(e)}"],
                suggestions=[],
                blocking_issues=[],
            )


class PeerReviewCoordinator:
    """Coordinates multiple review agents"""

    def __init__(self):
        self.reviewers = {
            "code-quality": PeerReviewAgent("code-quality"),
            "security": PeerReviewAgent("security"),
            "performance": PeerReviewAgent("performance"),
        }

    def review_pr(self, pr_data: Dict) -> Dict[str, CodeReview]:
        """
        Coordinate full peer review of PR

        Args:
            pr_data: PR information with files, diff, description

        Returns:
            Dict of reviewer_name -> CodeReview
        """
        reviews = {}

        for name, agent in self.reviewers.items():
            print(f"🔍 {name} reviewing...")
            review = agent.review(pr_data)
            reviews[name] = review

        return reviews

    def format_review_summary(self, reviews: Dict[str, CodeReview]) -> str:
        """Format reviews into Slack message"""
        blocking_count = sum(len(r.blocking_issues) for r in reviews.values())

        summary = "## 🔍 Peer Review Summary\n\n"

        for reviewer, review in reviews.items():
            emoji = "✅" if review.status == "approved" else "⚠️"
            summary += f"### {emoji} {reviewer.replace('-', ' ').title()}\n"
            summary += f"**Status:** {review.status}\n"
            summary += f"**Score:** {review.score}/100\n\n"

            if review.strengths:
                summary += "**Strengths:**\n"
                for s in review.strengths[:3]:
                    summary += f"- {s}\n"
                summary += "\n"

            if review.concerns:
                summary += "**Concerns:**\n"
                for c in review.concerns[:3]:
                    summary += f"- {c}\n"
                summary += "\n"

            if review.blocking_issues:
                summary += "**🚫 Blocking Issues:**\n"
                for b in review.blocking_issues:
                    summary += f"- {b}\n"
                summary += "\n"

        # Overall recommendation
        if blocking_count > 0:
            summary += (
                f"\n❌ **Cannot merge** - {blocking_count} blocking issue(s) found"
            )
        elif not reviews:
            summary += "\n✅ **No reviewers** - skipped"
        else:
            avg_score = sum(r.score for r in reviews.values()) / len(reviews)
            if avg_score >= 80:
                summary += "\n✅ **Approved** - Ready to merge"
            else:
                summary += "\n⚠️ **Conditional** - Address concerns before merging"

        return summary


class StagedPeerReview:
    """Orchestrates Stage 1 (automated) + Stage 2 (cross-project) peer review."""

    def __init__(
        self, app, code_review_channel_id: str, owner_user_id: str, projects: dict = None
    ):
        self.app = app
        self.review_channel = code_review_channel_id
        self.owner_user_id = owner_user_id
        self.projects = projects or {}
        self.coordinator = PeerReviewCoordinator()

    def trigger(
        self,
        summary: str,
        changed_files: list,
        project_key: str,
        origin_thread_ts: str,
        origin_channel_id: str,
    ):
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

        # Post back-link to origin project thread
        if origin_channel_id and origin_thread_ts:
            self.app.client.chat_postMessage(
                channel=origin_channel_id,
                thread_ts=origin_thread_ts,
                text=f"👀 Review posted in #code-review",
            )

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
                text=f"🙋 <@{self.owner_user_id}> — blocking issues found, needs review",
            )

        # Stage 2: tag ≤2 peer project agents with same platform/language
        project = self.projects.get(project_key, {})
        platform = project.get("platform")
        language = project.get("language")
        peers = [
            key
            for key, cfg in self.projects.items()
            if key != project_key
            and (
                (platform and cfg.get("platform") == platform)
                or (language and cfg.get("language") == language)
            )
        ][:2]

        for peer_key in peers:
            self.app.client.chat_postMessage(
                channel=self.review_channel,
                thread_ts=review_thread_ts,
                text=f"[{peer_key}-review] @SlackClaw please review the above changes from a {peer_key} perspective.",
            )


# Example usage
if __name__ == "__main__":
    coordinator = PeerReviewCoordinator()

    # Mock PR data
    pr_data = {
        "description": "Fix race condition in login flow",
        "files": ["LoginView.swift", "AuthManager.swift"],
        "diff": """
@@ -45,7 +45,10 @@ func login(email: String, password: String) {
-    user = try await authService.login(email, password)
+    guard let user = try await authService.login(email, password) else {
+        throw AuthError.loginFailed
+    }
+    self.user = user
""",
    }

    reviews = coordinator.review_pr(pr_data)
    summary = coordinator.format_review_summary(reviews)
    print(summary)
