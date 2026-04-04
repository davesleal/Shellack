"""Context manifest — persistent project understanding that grows over time."""

from __future__ import annotations

import logging
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MANIFEST_PATH = ".shellack/context.md"


def read_manifest(project_path: str) -> Optional[str]:
    """Read the context manifest."""
    path = Path(project_path) / _MANIFEST_PATH
    if path.exists():
        try:
            return path.read_text()
        except Exception:
            pass
    return None


def append_learned(project_path: str, entry: str) -> bool:
    """Append a 'learned this session' entry to the manifest."""
    path = Path(project_path) / _MANIFEST_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        if path.exists():
            content = path.read_text()
        else:
            content = f"# Context Manifest\n**Created:** {timestamp}\n\n## Learned\n"

        content += f"- [{timestamp}] {entry}\n"

        # Use atomic write
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return True
    except Exception as exc:
        logger.warning(f"Failed to append to manifest: {exc}")
        return False


def build_manifest(
    project_path: str,
    project_name: str,
    structure: str,
    state_summary: str = "",
) -> bool:
    """Build or rebuild the context manifest from a project scan."""
    path = Path(project_path) / _MANIFEST_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Preserve existing "Learned" entries if manifest exists
        learned = ""
        if path.exists():
            existing = path.read_text()
            if "## Learned" in existing:
                learned = existing.split("## Learned", 1)[1]

        content = (
            f"# Context Manifest — {project_name}\n**Last scanned:** {timestamp}\n\n"
        )

        if state_summary:
            content += f"## State Summary\n{state_summary[:2000]}\n\n"

        if structure:
            content += f"## File Structure\n```\n{structure}\n```\n\n"

        content += f"## Learned\n{learned}" if learned else "## Learned\n"

        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(content)
            os.replace(tmp, str(path))
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

        return True
    except Exception as exc:
        logger.warning(f"Failed to build manifest: {exc}")
        return False
