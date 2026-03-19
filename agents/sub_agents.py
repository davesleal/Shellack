#!/usr/bin/env python3
"""
Specialized sub-agents for project-specific tasks.
Each sub-agent has a focused system prompt and skill set.
"""

from anthropic import Anthropic

from tools.session_backend import quick_reply


class BaseSubAgent:
    def __init__(self, client: Anthropic, project_context: dict):
        self.client = (
            client  # kept for backward compat; AI calls go through quick_reply
        )
        self.project = project_context

    def run(self, prompt: str, thread_context: list = None) -> str:
        # Prepend thread context as plain text so both Max and API backends see it
        full_prompt = prompt
        if thread_context:
            history = "\n".join(
                f"{m['role'].title()}: {m['content']}" for m in thread_context
            )
            full_prompt = f"{history}\n\nUser: {prompt}"
        return quick_reply(
            full_prompt,
            system_prompt=self.system_prompt(),
            cwd=self.project.get("path", "."),
        )

    def system_prompt(self) -> str:
        raise NotImplementedError


class CrashInvestigatorAgent(BaseSubAgent):
    """Specializes in crash logs, App Store reviews, and bug investigations."""

    def system_prompt(self) -> str:
        p = self.project
        return f"""You are an expert crash investigator and debugger for {p['name']}.

Project: {p['name']}
Platform: {p['platform']}
Language: {p['language']}
Path: {p['path']}

Your expertise:
- Analyzing iOS/macOS crash logs and stack traces
- Identifying root causes from App Store review descriptions
- Reproducing and isolating bugs
- Proposing minimal, targeted fixes
- Assessing severity and affected versions

When investigating:
1. Identify the likely crash site (file, line, function)
2. State the root cause clearly
3. Propose a concrete fix with code if possible
4. Note affected OS versions / devices if determinable
5. Suggest a test case to prevent regression

Be direct and diagnostic. Avoid speculation — if uncertain, say so."""


class CodeReviewAgent(BaseSubAgent):
    """Performs focused code quality, security, and performance review."""

    def system_prompt(self) -> str:
        p = self.project
        platform = p["platform"]
        lang = p["language"]
        conventions = {
            "swift": "Swift API Design Guidelines, prefer guard for early returns, avoid force unwrap, use async/await",
            "python": "PEP 8, type hints required, max line 100, docstrings on public functions",
        }.get(lang, "standard conventions for " + lang)

        return f"""You are a senior {lang} engineer performing code review for {p['name']}.

Project: {p['name']}
Platform: {platform}
Conventions: {conventions}

Review dimensions (in order of priority):
1. **Correctness** — logic errors, edge cases, race conditions
2. **Security** — injection, data exposure, auth issues, insecure APIs
3. **Crashes** — force unwraps, nil access, out-of-bounds, retain cycles
4. **Performance** — memory leaks, N+1, inefficient loops, main thread blocking
5. **Maintainability** — readability, naming, unnecessary complexity

Format your review as:
- 🔴 **Blocking** — must fix before merge
- 🟡 **Warning** — should fix, acceptable with justification
- 🟢 **Suggestion** — optional improvement

End with an overall verdict: APPROVE / REQUEST CHANGES / NEEDS DISCUSSION"""


class TestingAgent(BaseSubAgent):
    """Writes and analyzes tests for the project."""

    def system_prompt(self) -> str:
        p = self.project
        framework = "XCTest / Swift Testing" if p["language"] == "swift" else "pytest"
        return f"""You are a test engineering specialist for {p['name']}.

Project: {p['name']}
Platform: {p['platform']}
Language: {p['language']}
Test framework: {framework}
Path: {p['path']}

Your responsibilities:
- Write unit tests and integration tests
- Identify untested code paths and edge cases
- Analyze existing tests for gaps
- Suggest mocking/stubbing strategies
- Ensure tests are deterministic and fast

Test quality standards:
- Arrange/Act/Assert structure
- One assertion per logical concern
- Descriptive test names that document behavior
- Cover happy path, edge cases, and failure modes
- Minimum 80% coverage target"""


class DocsAgent(BaseSubAgent):
    """Generates and updates documentation."""

    def system_prompt(self) -> str:
        p = self.project
        return f"""You are a technical writer and documentation specialist for {p['name']}.

Project: {p['name']}
Platform: {p['platform']}
Language: {p['language']}

Your responsibilities:
- Write clear, accurate docstrings and inline comments
- Generate or update README sections
- Document APIs and public interfaces
- Create CLAUDE.md context entries for AI assistants
- Write architectural decision records (ADRs)

Style: Clear, concise, developer-focused. Avoid filler. Include examples where helpful."""


# Map trigger keywords to sub-agent classes
TRIGGER_MAP = {
    "crash": CrashInvestigatorAgent,
    "exception": CrashInvestigatorAgent,
    "signal": CrashInvestigatorAgent,
    "investigate": CrashInvestigatorAgent,
    "bug": CrashInvestigatorAgent,
    "review": CodeReviewAgent,
    "pr": CodeReviewAgent,
    "pull request": CodeReviewAgent,
    "test": TestingAgent,
    "testing": TestingAgent,
    "coverage": TestingAgent,
    "doc": DocsAgent,
    "document": DocsAgent,
    "readme": DocsAgent,
    "claude.md": DocsAgent,
}


def detect_sub_agent(prompt: str) -> str | None:
    """Return sub-agent key if the prompt triggers one, else None."""
    lower = prompt.lower()
    for keyword, agent_class in TRIGGER_MAP.items():
        if keyword in lower:
            return agent_class
    return None
