"""Skill mapper — determines which skills to load per project based on stack."""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

# Always loaded regardless of stack
GLOBAL_SKILLS = [
    "fixing-accessibility",
    "audit",
    "harden",
    "clarify",
    "optimize",
]

# Stack-specific skill mappings
_STACK_SKILLS = {
    "web": [
        "frontend-design",
        "baseline-ui",
        "fixing-motion-performance",
        "fixing-metadata",
        "animate",
        "colorize",
        "typeset",
        "overdrive",
        "arrange",
        "delight",
        "adapt",
    ],
    "react": [
        "frontend-design",
        "baseline-ui",
        "fixing-motion-performance",
        "fixing-metadata",
        "animate",
        "colorize",
        "typeset",
        "overdrive",
        "arrange",
        "delight",
        "adapt",
    ],
    "nextjs": [
        "frontend-design",
        "baseline-ui",
        "fixing-motion-performance",
        "fixing-metadata",
        "animate",
        "colorize",
        "typeset",
        "overdrive",
        "arrange",
        "delight",
        "adapt",
    ],
    "swift": [
        "polish",
        "critique",
        "adapt",
        "normalize",
        "distill",
    ],
    "ios": [
        "polish",
        "critique",
        "adapt",
        "normalize",
        "distill",
    ],
    "python": [
        "normalize",
        "distill",
        "extract",
        "onboard",
    ],
    "server": [
        "normalize",
        "distill",
        "extract",
        "onboard",
    ],
}

# File markers that identify a stack
_STACK_MARKERS = {
    "Package.swift": "swift",
    "Package.resolved": "swift",
    "*.xcodeproj": "swift",
    "package.json": "web",
    "next.config.js": "nextjs",
    "next.config.ts": "nextjs",
    "next.config.mjs": "nextjs",
    "tsconfig.json": "web",
    "requirements.txt": "python",
    "pyproject.toml": "python",
    "Pipfile": "python",
    "setup.py": "python",
    "Cargo.toml": "rust",
    "go.mod": "go",
}


def detect_stack(project_path: str) -> list[str]:
    """Detect the project's tech stack from file markers.

    Returns list of detected stack identifiers (e.g., ["web", "nextjs"]).
    """
    if not project_path or not os.path.isdir(project_path):
        return []

    detected = set()
    path = Path(project_path)

    for marker, stack in _STACK_MARKERS.items():
        if "*" in marker:
            # Glob pattern
            if list(path.glob(marker)):
                detected.add(stack)
        elif (path / marker).exists():
            detected.add(stack)

    return list(detected)


def get_skills_for_project(
    project_path: str,
    language: str = "",
    platform: str = "",
) -> list[str]:
    """Determine which skills should be active for a project.

    Combines:
    1. Global skills (always on)
    2. Stack-specific skills based on detected or configured stack

    Never loads cross-stack skills.
    """
    skills = set(GLOBAL_SKILLS)

    # Detect from files
    detected_stacks = detect_stack(project_path)

    # Also use configured language/platform
    if language:
        detected_stacks.append(language.lower())
    if platform:
        detected_stacks.append(platform.lower())

    # Deduplicate
    detected_stacks = list(set(detected_stacks))

    # Add stack-specific skills
    for stack in detected_stacks:
        if stack in _STACK_SKILLS:
            skills.update(_STACK_SKILLS[stack])

    # Filter to only skills that are actually installed
    installed = _get_installed_skills()
    available = [s for s in sorted(skills) if s in installed]

    return available


def _get_installed_skills() -> set[str]:
    """Get the set of installed skill names."""
    installed = set()

    # Check .claude/skills/
    skills_dir = Path(".claude/skills")
    if skills_dir.exists():
        for item in skills_dir.iterdir():
            installed.add(item.name)

    # Check .agents/skills/
    agents_dir = Path(".agents/skills")
    if agents_dir.exists():
        for item in agents_dir.iterdir():
            installed.add(item.name)

    return installed


def format_skill_manifest(skills: list[str]) -> str:
    """Format a skill list for inclusion in a system prompt."""
    if not skills:
        return ""

    lines = ["## Available Skills", "Invoke these when relevant to the task:", ""]
    for skill in skills:
        lines.append(f"- `/{skill}`")

    lines.append("")
    lines.append(
        "Use `/skill-name` to invoke. Do NOT invoke skills that are not listed here."
    )
    return "\n".join(lines)
