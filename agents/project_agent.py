#!/usr/bin/env python3
"""
ProjectAgent — specialized agent per project.
Carries project-specific context in its system prompt and
dispatches to sub-agents based on task type.
"""

import logging
import os
from pathlib import Path
from tools.github_client import GitHubClient
from tools.lifecycle import LifecycleNotifier
from tools.journal_writer import JournalWriter
from tools.session_backend import quick_reply
from tools.self_improver import reflect_and_update
from .sub_agents import (
    detect_sub_agent,
    CrashInvestigatorAgent,
    TestingAgent,
    CodeReviewAgent,
    DocsAgent,
)

logger = logging.getLogger(__name__)

from tools.slack_session import _strip_tool_xml


def _clean_response(text: str) -> str:
    """Strip tool call XML from claude CLI output before posting to Slack."""
    return _strip_tool_xml(text)


CODE_CHANGING_AGENTS = (CrashInvestigatorAgent, TestingAgent)


LANGUAGE_CONVENTIONS = {
    "swift": """
Coding conventions (Swift API Design Guidelines):
- Use descriptive, grammatically correct names
- Prefer guard statements for early returns
- Never force unwrap unless guaranteed safe — use guard let or if let
- Use async/await over completion handlers
- Prefer value types (structs) over classes where possible
- Mark UI code with @MainActor
""",
    "python": """
Coding conventions (PEP 8 + project standards):
- Type hints on all function signatures
- Docstrings on all public functions and classes
- Max line length: 100 characters
- Use black for formatting
- Prefer explicit over implicit
""",
}


class ProjectAgent:
    def __init__(
        self,
        project_key: str,
        project_config: dict,
        client,
        app,
        channel_id: str,
        thread_ts: str,
    ):
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
            owner_user_id=os.environ.get("OWNER_SLACK_USER_ID", ""),
        )
        self._github = GitHubClient(
            token=os.environ.get("GITHUB_TOKEN", ""),
            projects=self._load_projects(),
        )
        self._journal = JournalWriter(project_config["path"])
        from peer_review import StagedPeerReview
        from orchestrator_config import PROJECTS as _all_projects

        self._staged_review = StagedPeerReview(
            app=app,
            code_review_channel_id=os.environ.get(
                "CODE_REVIEW_CHANNEL_ID", "code-review"
            ),
            owner_user_id=os.environ.get("OWNER_SLACK_USER_ID", ""),
            projects=_all_projects,
        )
        self._opened_issue_number: int | None = None

    def _load_projects(self) -> dict:
        from orchestrator_config import PROJECTS

        return PROJECTS

    def _load_claude_md(self) -> str:
        claude_md_path = Path(self.project["path"]) / "CLAUDE.md"
        if claude_md_path.exists():
            return claude_md_path.read_text()
        logger.warning(
            f"CLAUDE.md not found for {self.project['name']} at {claude_md_path}"
        )
        return ""

    def _build_system_prompt(self) -> str:
        # Build base prompt from PROJECT_KNOWLEDGE + LANGUAGE_CONVENTIONS
        # (existing logic preserved)
        p = self.project
        knowledge = self.project.get("context", {})
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
        backend_mode = os.environ.get("SESSION_BACKEND", "api")
        if backend_mode == "max":
            role_text = (
                "\n## Your Role\n"
                "You have full Claude Code tool access (file read/write, bash, git) in the project directory.\n"
                "Make changes directly. Don't narrate what you're about to do — just do it and summarise the outcome in one sentence per action.\n"
                "\n**IMPORTANT:** Do NOT use Slack MCP tools or any messaging tools. "
                "Do NOT post to Slack channels or threads directly. "
                "Shellack handles all Slack output — just return your answer as text.\n"
            )
        else:
            role_text = (
                "\n## Your Role\n"
                "You are a *conversational* assistant in Slack with NO tool access.\n"
                "You cannot read files or run commands — answer from context only.\n"
                'If the task needs file access or code changes, say: "Try `@Shellack run: <task>`"\n'
            )
        role_text += (
            "\n**Reasoning format:** If you need to think before answering, put a one-line "
            "summary on the first line prefixed with `Thinking: `, then a blank line, then "
            "your answer. Omit if no reasoning is needed."
            "\n\n**Formatting:** This response renders in Slack. Rules:\n"
            "- Wrap ALL code (even a single line) in triple-backtick fences with a language tag: "
            "```swift\\n...\\n``` or ```python\\n...\\n```\n"
            "- Always close every code block with ``` before continuing prose\n"
            "- After a closing ``` resume normal text on a new line — never leave a block open\n"
            "- Use `inline backticks` only for identifiers, file names, and short values\n"
            "\nBe concise."
        )
        prompt += role_text

        # Prepend CLAUDE.md (project rules take highest priority)
        claude_md = self._load_claude_md()
        if claude_md:
            prompt = (
                f"## Project Rules (from CLAUDE.md)\n\n{claude_md}\n\n---\n\n{prompt}"
            )

        return prompt

    def _is_code_changing(self, sub_agent_class, response: str) -> bool:
        if sub_agent_class in CODE_CHANGING_AGENTS:
            return True
        # CodeReviewAgent and all other agents: never auto-trigger peer review.
        # Peer review requires explicit code changes, not just code in output.
        return False

    def _task_type_for_github(self, sub_agent_class) -> str | None:
        """Return GitHub task type label or None if no issue should be created."""
        mapping = {
            CrashInvestigatorAgent: "crash",
            TestingAgent: "testing",
            DocsAgent: "documentation",
            CodeReviewAgent: None,  # never create issue for reviews
        }
        return mapping.get(sub_agent_class, None)

    def handle(
        self,
        prompt: str,
        thread_context: list = None,
        model: str | None = None,  # triage-selected model; None = use SESSION_MODEL
    ) -> tuple[str, str]:
        # Refresh lifecycle notifier with current thread (channel_id/thread_ts may have
        # been updated by AgentFactory for a new message on a pre-warmed agent)
        self._lifecycle = LifecycleNotifier(
            app=self.app,
            channel_id=self.channel_id,
            thread_ts=self.thread_ts,
            project_name=self.project["name"],
            owner_user_id=os.environ.get("OWNER_SLACK_USER_ID", ""),
        )
        self._opened_issue_number = None  # reset per-call state
        sub_agent_class = detect_sub_agent(prompt)
        task_type = (
            self._task_type_for_github(sub_agent_class) if sub_agent_class else None
        )
        # Only auto-create issues for crash/bug task types, never for None/review/docs
        is_bug_task = task_type == "crash"

        # Summarise task for lifecycle
        words = prompt.split()[:8]
        task_summary = " ".join(words) + ("..." if len(prompt.split()) > 8 else "")

        # Auto-create GitHub issue for bugs/crashes (significant task)
        if is_bug_task and task_type:
            title = f"[{task_type.title()}] {task_summary}"
            body = f"Reported via Slack:\n\n> {prompt}"
            issue = self._github.create_issue(self.project_key, title, body, task_type)
            if issue:
                self._opened_issue_number = issue["number"]
                self._lifecycle.issue_created(issue["url"], issue["number"])

        # Run sub-agent or main agent
        try:
            if sub_agent_class:
                agent = sub_agent_class(self.client, self.project)
                label = sub_agent_class.__name__.replace("Agent", "")
                response = agent.run(prompt, thread_context)
            else:
                label = self.project["name"]
                full_prompt = prompt
                if thread_context:
                    if isinstance(thread_context, str):
                        full_prompt = f"{thread_context}\n\nUser: {prompt}"
                    else:
                        history = "\n".join(
                            f"{m['role'].title()}: {m['content']}" for m in thread_context
                        )
                        full_prompt = f"{history}\n\nUser: {prompt}"
                response = quick_reply(
                    full_prompt,
                    system_prompt=self._system_prompt,
                    cwd=self.project.get("path", "."),
                    model=model,
                )
        except Exception as e:
            raise

        # Strip tool call XML before any further processing or posting
        response = _clean_response(response)

        # Reflect on any block and update CLAUDE.md autonomously
        rule = reflect_and_update(
            prompt=prompt,
            response=response,
            project_path=self.project.get("path", "."),
        )
        if rule:
            try:
                self.app.client.chat_postMessage(
                    channel=self.channel_id,
                    thread_ts=self.thread_ts,
                    text="",
                    attachments=[{"color": "#888888", "text": f"✦ Learned: {rule}"}],
                )
            except Exception:
                pass

        if self._opened_issue_number:
            self._github.close_issue(self.project_key, self._opened_issue_number)

        return response, label

    def _write_journal(self, prompt: str, response: str):
        self._journal.append_entry(
            title=f"{self.project['name']}: {prompt[:60]}",
            context=f"Slack request: {prompt}",
            approach="Agent analysis and response",
            outcome=response[:400],
            insights="See full response in Slack thread",
            issue_number=self._opened_issue_number,
        )
