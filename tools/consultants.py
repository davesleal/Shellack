"""Consultant agents — specialist reviewers invoked on trigger detection."""
from __future__ import annotations

import logging
import os
import re
from typing import Optional

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_MODEL = "claude-sonnet-4-6"
_TIMEOUT = 15.0
_MAX_TOKENS = 1024

# ---------------------------------------------------------------------------
# Singleton Anthropic client (lazy)
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = Anthropic(
            http_client=httpx.Client(timeout=httpx.Timeout(_TIMEOUT)),
            max_retries=1,
        )
    return _client

# ---------------------------------------------------------------------------
# Trigger detection (lightweight, no API call)
# ---------------------------------------------------------------------------

_INFOSEC_PATTERNS = [
    r"\bauth\b", r"\blogin\b", r"\bsession\b", r"\btoken\b",
    r"\bcrypto\b", r"\bpassword\b", r"\bsanitiz", r"\bvalidat",
    r"\bcors\b", r"\bcsrf\b", r"\binjection\b", r"\bxss\b",
]

_ARCHITECT_PATTERNS = [
    r"\bnew\s+file\b", r"\bnew\s+module\b", r"\bnew\s+class\b",
    r"\bschema\s+change\b", r"\bmigration\b", r"\bdependenc",
    r"\brefactor\b", r"\bsplit\s+(into|the)\b",
]

_TESTER_PATTERNS = [
    r"\btest\b", r"\bspec\b", r"\bassert\b", r"\bmock\b",
    r"\bfixture\b", r"\bcoverage\b", r"\bpytest\b", r"\bjest\b",
    r"\bxctest\b",
]


def detect_triggers(response: str) -> list[str]:
    """Detect which consultant roles should be invoked based on response content.

    Returns list of role names: ["infosec", "architect", "tester"]
    """
    lower = response.lower()
    roles = []
    if any(re.search(p, lower) for p in _INFOSEC_PATTERNS):
        roles.append("infosec")
    if any(re.search(p, lower) for p in _ARCHITECT_PATTERNS):
        roles.append("architect")
    if any(re.search(p, lower) for p in _TESTER_PATTERNS):
        roles.append("tester")
    return roles


# ---------------------------------------------------------------------------
# Consultant prompts
# ---------------------------------------------------------------------------

_INFOSEC_SYSTEM = """You are an infosec consultant reviewing code changes for security issues.

Check for:
- Authentication/authorization flaws
- Input validation gaps
- Injection vulnerabilities (SQL, XSS, command)
- Secrets handling (hardcoded keys, leaked env vars)
- Session management issues
- Crypto misuse

Respond concisely:
- If no issues: "\u2705 No security concerns."
- If issues found: "\ud83d\udd34 SECURITY: {one-line per issue}"

Max 3 issues. Be specific \u2014 name the file/function/line if you can."""

_ARCHITECT_SYSTEM = """You are an architecture consultant reviewing structural changes.

Check for:
- Unnecessary complexity (YAGNI violations)
- Poor separation of concerns
- Missing interfaces or abstractions where needed
- Dependency direction violations
- Files that are growing too large

Respond concisely:
- If no issues: "\u2705 Architecture looks sound."
- If concerns: "\ud83d\udcd0 ARCHITECTURE: {one-line per concern}"

Max 3 concerns. Be constructive."""

_TESTER_SYSTEM = """You are a testing consultant reviewing code changes for test adequacy.

Check for:
- Missing test coverage for new/changed code
- Test quality (meaningful assertions, not just "runs without error")
- Edge cases not covered
- Test isolation (no shared state between tests)
- Appropriate use of mocks vs integration tests

Respond concisely:
- If adequate: "\u2705 Test coverage looks good."
- If gaps: "\ud83e\uddea TESTING: {one-line per gap}"

Max 3 items. Be specific about what needs testing."""

_OUTPUT_EDITOR_SYSTEM = """You are an output editor polishing text for external publication (GitHub issues, PRs, documentation).

Check for:
- Clear, professional language
- Proper markdown formatting
- Accurate technical details
- Appropriate level of detail (not too verbose, not too terse)
- Follows conventional format for the output type

Respond with the polished version of the text. If no changes needed, return the text unchanged."""

_CONSULTANT_PROMPTS = {
    "infosec": _INFOSEC_SYSTEM,
    "architect": _ARCHITECT_SYSTEM,
    "tester": _TESTER_SYSTEM,
    "output_editor": _OUTPUT_EDITOR_SYSTEM,
}


# ---------------------------------------------------------------------------
# Consultant call
# ---------------------------------------------------------------------------

def consult(
    role: str,
    response: str,
    handoff: str | None = None,
    registry: str | None = None,
) -> Optional[str]:
    """Invoke a consultant agent. Returns feedback string or None on failure."""
    system = _CONSULTANT_PROMPTS.get(role)
    if not system:
        logger.warning(f"Unknown consultant role: {role}")
        return None

    model = os.environ.get("CONSULTANT_MODEL", _MODEL)
    user_content = f"## Agent Response to Review\n{response[:3000]}"
    if handoff:
        user_content += f"\n\n## Current Context\n{handoff[:1000]}"
    if registry:
        user_content += f"\n\n## Project Registry\n{registry[:1000]}"

    try:
        client = _get_client()
        msg = client.messages.create(
            model=model,
            max_tokens=_MAX_TOKENS,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        text = msg.content[0].text.strip()
        # Only return if there are actual findings (not "no issues")
        _no_issue_phrases = [
            "no security concerns",
            "architecture looks sound",
            "test coverage looks good",
        ]
        if any(phrase in text.lower() for phrase in _no_issue_phrases):
            return None
        return text
    except Exception as exc:
        logger.warning(f"Consultant {role} failed: {exc}")
        return None
