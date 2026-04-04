"""File fetcher — reads project files on demand for agent context."""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 4000  # chars per file
_MAX_FILES = 3  # max files per fetch


def read_file(project_path: str, relative_path: str) -> Optional[str]:
    """Read a single file from the project. Returns content or None."""
    full_path = Path(project_path) / relative_path
    # Security: don't allow path traversal outside project
    try:
        full_path = full_path.resolve()
        project_resolved = Path(project_path).resolve()
        if not str(full_path).startswith(str(project_resolved)):
            logger.warning(f"Path traversal blocked: {relative_path}")
            return None
    except Exception:
        return None

    if not full_path.exists() or not full_path.is_file():
        return None

    try:
        content = full_path.read_text()
        if len(content) > _MAX_FILE_SIZE:
            content = content[:_MAX_FILE_SIZE] + "\n... (truncated)"
        return content
    except Exception as exc:
        logger.warning(f"Failed to read {full_path}: {exc}")
        return None


def scan_project_structure(project_path: str, extensions: list[str] = None) -> str:
    """Quick scan of project file structure. Returns a tree-like summary."""
    if not project_path or not os.path.isdir(project_path):
        return ""

    if extensions is None:
        extensions = [
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".swift",
            ".py",
            ".sql",
            ".yaml",
            ".yml",
        ]

    try:
        ext_args = []
        for ext in extensions:
            ext_args.extend(["-name", f"*{ext}", "-o"])
        if ext_args:
            ext_args = ext_args[:-1]  # remove trailing -o

        result = subprocess.run(
            ["find", ".", "-type", "f", "("]
            + ext_args
            + [
                ")",
                "-not",
                "-path",
                "*/node_modules/*",
                "-not",
                "-path",
                "*/.next/*",
                "-not",
                "-path",
                "*/venv/*",
                "-not",
                "-path",
                "*/.git/*",
            ],
            capture_output=True,
            text=True,
            cwd=project_path,
            timeout=5,
        )
        if result.returncode == 0:
            files = result.stdout.strip().split("\n")[:60]
            return "\n".join(files)
    except Exception as exc:
        logger.warning(f"Project scan failed: {exc}")

    return ""


def fetch_files_for_context(project_path: str, file_paths: list[str]) -> str:
    """Read multiple files and format as context block."""
    if not file_paths:
        return ""

    parts = []
    for fp in file_paths[:_MAX_FILES]:
        content = read_file(project_path, fp)
        if content:
            parts.append(f"### {fp}\n```\n{content}\n```")
        else:
            parts.append(f"### {fp}\n(file not found)")

    return "\n\n".join(parts)
