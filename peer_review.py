#!/usr/bin/env python3
"""
SlackClaw Peer Review System
Autonomous agents review each other's work
"""

import os
from typing import Dict, List, Optional
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
- Resource cleanup"""
        }

    def review(self, changes: Dict) -> CodeReview:
        """
        Perform code review

        Args:
            changes: Dict with 'files', 'diff', 'description'

        Returns:
            CodeReview object
        """
        system_prompt = self.system_prompts.get(
            self.focus_area,
            "You are a code reviewer."
        )

        # Build review prompt
        review_prompt = f"""Review the following code changes:

**Description:** {changes.get('description', 'No description')}

**Files Changed:**
{chr(10).join(f"- {f}" for f in changes.get('files', []))}

**Diff:**
```
{changes.get('diff', 'No diff provided')}
```

Provide a structured review with:
1. Overall assessment (approve/request changes)
2. Score (0-100)
3. Strengths (what's good)
4. Concerns (what needs attention)
5. Suggestions (how to improve)
6. Blocking issues (must be fixed before merge)

Format as JSON."""

        try:
            response = anthropic_client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=2048,
                system=system_prompt,
                messages=[{
                    "role": "user",
                    "content": review_prompt
                }]
            )

            # Parse response (simplified - would need proper JSON parsing)
            content = response.content[0].text

            # Extract key parts (this is a simple example)
            return CodeReview(
                reviewer=self.focus_area,
                status="approved" if "approve" in content.lower() else "changes_requested",
                score=self._extract_score(content),
                strengths=self._extract_list(content, "Strengths"),
                concerns=self._extract_list(content, "Concerns"),
                suggestions=self._extract_list(content, "Suggestions"),
                blocking_issues=self._extract_list(content, "Blocking")
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
                blocking_issues=[]
            )

    def _extract_score(self, content: str) -> int:
        """Extract numeric score from review"""
        import re
        match = re.search(r'score[:\s]+(\d+)', content, re.IGNORECASE)
        return int(match.group(1)) if match else 75

    def _extract_list(self, content: str, section: str) -> List[str]:
        """Extract list items from a section"""
        import re
        pattern = rf'{section}[:\s]+(.*?)(?=\n\n|\Z)'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if match:
            items = match.group(1).strip().split('\n')
            return [item.strip('- ').strip() for item in items if item.strip()]
        return []


class PeerReviewCoordinator:
    """Coordinates multiple review agents"""

    def __init__(self):
        self.reviewers = {
            "code-quality": PeerReviewAgent("code-quality"),
            "security": PeerReviewAgent("security"),
            "performance": PeerReviewAgent("performance")
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
        blocking_count = sum(
            len(r.blocking_issues) for r in reviews.values()
        )

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
            summary += f"\n❌ **Cannot merge** - {blocking_count} blocking issue(s) found"
        else:
            avg_score = sum(r.score for r in reviews.values()) / len(reviews)
            if avg_score >= 80:
                summary += "\n✅ **Approved** - Ready to merge"
            else:
                summary += "\n⚠️ **Conditional** - Address concerns before merging"

        return summary


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
"""
    }

    reviews = coordinator.review_pr(pr_data)
    summary = coordinator.format_review_summary(reviews)
    print(summary)
