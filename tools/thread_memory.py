"""Thread memory — cross-thread persistence via .shellack/thread-memory/."""

import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MEMORY_DIR = ".shellack/thread-memory"


def read_thread_memory(project_path: str, project_key: str, ttl_hours: int = 24) -> Optional[str]:
    """Read persistent thread memory. Returns None if missing or expired."""
    mem_path = Path(project_path) / _MEMORY_DIR / f"{project_key}.md"
    if mem_path.exists():
        try:
            # Check TTL — expire stale memory
            age_hours = (time.time() - mem_path.stat().st_mtime) / 3600
            if age_hours > ttl_hours:
                logger.info(f"Thread memory expired ({age_hours:.1f}h old), discarding: {mem_path}")
                mem_path.unlink()
                return None
            return mem_path.read_text()
        except Exception as exc:
            logger.warning(f"Failed to read thread memory: {exc}")
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


def write_thread_memory(project_path: str, project_key: str, content: str) -> bool:
    """Write persistent thread memory."""
    mem_dir = Path(project_path) / _MEMORY_DIR
    mem_path = mem_dir / f"{project_key}.md"
    try:
        _atomic_write(mem_path, content)
        return True
    except Exception as exc:
        logger.warning(f"Failed to write thread memory: {exc}")
        return False
