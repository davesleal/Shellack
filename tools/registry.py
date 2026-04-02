"""Project Registry — auto-populated index of reusable patterns."""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_REGISTRY_DIR = ".shellack"
_REGISTRY_FILE = "registry.md"

_INITIAL_TEMPLATE = """# Project Registry

## UI Components
| Component | Path | Props/API | Notes |
|---|---|---|---|

## Design Tokens
| Token | Value | Usage |
|---|---|---|

## Shared Utilities
| Utility | Path | API | Notes |
|---|---|---|---|

## Data Models
| Model | Path | Key fields |
|---|---|---|

## API Patterns
| Pattern | Example | Rule |
|---|---|---|

## Architecture Rules
| Rule | Scope | Rationale |
|---|---|---|
"""


def read_registry(project_path: str) -> Optional[str]:
    """Read the project registry. Returns content or None if not found."""
    registry_path = Path(project_path) / _REGISTRY_DIR / _REGISTRY_FILE
    if registry_path.exists():
        try:
            return registry_path.read_text()
        except Exception as exc:
            logger.warning(f"Failed to read registry at {registry_path}: {exc}")
    return None


def _atomic_write(path: Path, content: str) -> None:
    """Atomic write: write to temp file, then rename."""
    path.parent.mkdir(parents=True, exist_ok=True)
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


def write_registry(project_path: str, content: str) -> bool:
    """Write content to the project registry. Creates .shellack/ dir if needed."""
    registry_dir = Path(project_path) / _REGISTRY_DIR
    registry_path = registry_dir / _REGISTRY_FILE
    try:
        _atomic_write(registry_path, content)
        return True
    except Exception as exc:
        logger.warning(f"Failed to write registry at {registry_path}: {exc}")
        return False


def ensure_registry(project_path: str) -> str:
    """Read existing registry or create initial template. Returns content."""
    content = read_registry(project_path)
    if content:
        return content
    write_registry(project_path, _INITIAL_TEMPLATE)
    return _INITIAL_TEMPLATE


def append_to_registry(project_path: str, section: str, entry: str) -> bool:
    """Append an entry to a specific section of the registry.

    Args:
        project_path: Absolute path to the project root
        section: Section header (e.g., "UI Components", "Architecture Rules")
        entry: The table row or rule text to append
    """
    content = read_registry(project_path)
    if not content:
        content = _INITIAL_TEMPLATE

    section_header = f"## {section}"
    if section_header not in content:
        # Section doesn't exist — append at end
        content = content.rstrip() + f"\n\n{section_header}\n{entry}\n"
    else:
        # Find the section and append after the last non-empty line before next section
        lines = content.split("\n")
        insert_idx = None
        in_section = False
        for i, line in enumerate(lines):
            if line.strip() == section_header:
                in_section = True
                continue
            if in_section and line.startswith("## "):
                insert_idx = i
                break
            if in_section and line.strip():
                insert_idx = i + 1

        if insert_idx is None:
            insert_idx = len(lines)

        lines.insert(insert_idx, entry)
        content = "\n".join(lines)

    return write_registry(project_path, content)
