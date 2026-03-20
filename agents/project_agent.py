#!/usr/bin/env python3
"""
ProjectAgent — specialized agent per project.
Carries project-specific context in its system prompt and
dispatches to sub-agents based on task type.
"""

import logging
import os
import re
from pathlib import Path
from tools.github_client import GitHubClient
from tools.lifecycle import LifecycleNotifier
from tools.journal_writer import JournalWriter
from tools.session_backend import quick_reply
from .sub_agents import (
    detect_sub_agent,
    CrashInvestigatorAgent,
    TestingAgent,
    CodeReviewAgent,
    DocsAgent,
)

logger = logging.getLogger(__name__)

# Matches XML-style tool call blocks that the claude CLI may narrate in text output
_TOOL_XML_RE = re.compile(
    r"<(write_file|read_file|bash|str_replace_editor|create_file|delete_file)"
    r"[^>]*>[\s\S]*?</\1>",
    re.IGNORECASE,
)


def _clean_response(text: str) -> str:
    """Strip tool call XML from claude CLI output before posting to Slack."""
    return _TOOL_XML_RE.sub("", text).strip()


CODE_CHANGING_AGENTS = (CrashInvestigatorAgent, TestingAgent)


# Rich project knowledge baked into each agent's system prompt
PROJECT_KNOWLEDGE = {
    "dayist": {
        "description": "iOS 26+ personal productivity and wellness app",
        "purpose": "Unify tasks, calendar, health insights, and subscription tracking with on-device Apple Intelligence",
        "tech": "SwiftUI, SwiftData (local), CloudKit (sync), HealthKit, EventKit, Apple Foundation Models, Google OAuth",
        "patterns": [
            "MVVM architecture with @Observable",
            "SwiftData for local persistence, CloudKit for sync",
            "HealthKit queries are async — always handle authorization",
            "Apple Foundation Models run on-device — no network calls",
            "EventKit requires explicit calendar authorization",
        ],
        "watch_out": [
            "Force unwrapping optional CloudKit records",
            "Blocking the main thread with HealthKit queries",
            "Leaking sensitive health data in logs",
        ],
    },
    "nova": {
        "description": "iOS application",
        "purpose": "In active development — details TBD",
        "tech": "Swift, iOS",
        "patterns": ["Standard iOS MVC/MVVM patterns"],
        "watch_out": [],
    },
    "nudge": {
        "description": "iOS application",
        "purpose": "In active development — details TBD",
        "tech": "Swift, iOS",
        "patterns": ["Standard iOS MVC/MVVM patterns"],
        "watch_out": [],
    },
    "tiledock": {
        "description": "macOS grid control surface — one tap triggers multiple actions",
        "purpose": "Productivity automation for macOS: configure a grid of tiles that execute multi-step actions across apps",
        "tech": "SwiftUI, AppKit",
        "patterns": [
            "Grid layout managed via AppKit NSView backing for pixel precision",
            "Action execution is async — always show progress",
            "Tiles are user-configurable — validate config on load",
            "Menu bar app — minimal memory footprint required",
        ],
        "watch_out": [
            "Main thread violations (AppKit is not thread-safe)",
            "Memory growth from long-running action queues",
            "Accessibility — control surfaces must support VoiceOver",
        ],
    },
    "atmosuniversal": {
        "description": "macOS weather application",
        "purpose": "Universal macOS weather app with modern SwiftUI interface",
        "tech": "SwiftUI, macOS",
        "patterns": [
            "WeatherKit or OpenMeteo for weather data",
            "CoreLocation for user location",
            "Async/await for all network requests",
        ],
        "watch_out": [
            "Location permission must be requested gracefully",
            "Network failures must show cached data with staleness indicator",
        ],
    },
    "sideplane": {
        "description": "macOS ↔ Vision Pro bridge app (formerly Mac2Vision)",
        "purpose": "Seamless workflows between macOS and visionOS — stream Mac content into Vision Pro spatial environment",
        "tech": "SwiftUI, Spatial Computing APIs, Network framework",
        "patterns": [
            "Bonjour/Network framework for Mac ↔ Vision Pro discovery",
            "RealityKit for spatial rendering on visionOS side",
            "SharePlay or custom streaming for screen content",
            "Companion app pattern: macOS host + visionOS client",
        ],
        "watch_out": [
            "Latency is critical — minimize serialization overhead",
            "Privacy: screen capture requires explicit user permission on macOS",
            "visionOS has no traditional keyboard — design for spatial input",
        ],
    },
    "slackclaw": {
        "description": "Slack bot integrated with Claude AI for multi-project dev automation",
        "purpose": "Development automation hub: project agents, orchestrator, peer review, App Store Connect monitoring",
        "tech": "Python, Slack Bolt, Anthropic API, App Store Connect API",
        "patterns": [
            "Channel-based routing: each channel → dedicated agent or special handler",
            "Thread TS as session key for conversation context",
            "orchestrator_config.py is the single source of truth for project registry",
            "All secrets in .env — never hardcode tokens",
        ],
        "watch_out": [
            "Slack rate limits: don't burst messages in loops",
            "Thread context grows unbounded — consider pruning for long sessions",
            "App Store Connect JWT tokens expire — refresh before polling",
        ],
    },
}

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
        backend_mode = os.environ.get("SESSION_BACKEND", "api")
        if backend_mode == "max":
            role_text = (
                "\n## Your Role\n"
                "You have full Claude Code tool access (file read/write, bash, git) in the project directory.\n"
                "Make changes directly. Don't narrate what you're about to do — just do it and summarise the outcome in one sentence per action.\n"
            )
        else:
            role_text = (
                "\n## Your Role\n"
                "You are a *conversational* assistant in Slack with NO tool access.\n"
                "You cannot read files or run commands — answer from context only.\n"
                'If the task needs file access or code changes, say: "Try `@SlackClaw run: <task>`"\n'
            )
        role_text += (
            "\n**Reasoning format:** If you need to think before answering, put a one-line "
            "summary on the first line prefixed with `Thinking: `, then a blank line, then "
            "your answer. Omit if no reasoning is needed.\n\nBe concise."
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

    def handle(self, prompt: str, thread_context: list = None) -> tuple[str, str]:
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
            self._lifecycle.started(task_summary)
            title = f"[{task_type.title()}] {task_summary}"
            body = f"Reported via Slack:\n\n> {prompt}"
            issue = self._github.create_issue(self.project_key, title, body, task_type)
            if issue:
                self._opened_issue_number = issue["number"]
                self._lifecycle.issue_created(issue["url"], issue["number"])
            else:
                self._lifecycle.in_progress(
                    "⚠️ Could not create GitHub issue — continuing"
                )

        # Run sub-agent or main agent
        try:
            if sub_agent_class:
                self._lifecycle.in_progress("Analyzing...")
                agent = sub_agent_class(self.client, self.project)
                label = sub_agent_class.__name__.replace("Agent", "")
                response = agent.run(prompt, thread_context)
            else:
                label = self.project["name"]
                full_prompt = prompt
                if thread_context:
                    history = "\n".join(
                        f"{m['role'].title()}: {m['content']}" for m in thread_context
                    )
                    full_prompt = f"{history}\n\nUser: {prompt}"
                response = quick_reply(
                    full_prompt,
                    system_prompt=self._system_prompt,
                    cwd=self.project.get("path", "."),
                )
        except Exception as e:
            self._lifecycle.failed(str(e))
            return f"Error: {e}", "Error"

        # Strip tool call XML before any further processing or posting
        response = _clean_response(response)

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
            self._write_journal(prompt, response)

        return response, label

    def _trigger_peer_review(self, prompt: str, response: str):
        self._lifecycle.pending_review()
        self._staged_review.trigger(
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
