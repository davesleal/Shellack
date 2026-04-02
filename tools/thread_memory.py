"""Thread memory — cross-thread persistence via .shellack/thread-memory/."""
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_MEMORY_DIR = ".shellack/thread-memory"


def read_thread_memory(project_path: str, project_key: str) -> Optional[str]:
    """Read persistent thread memory for a project."""
    mem_path = Path(project_path) / _MEMORY_DIR / f"{project_key}.md"
    if mem_path.exists():
        try:
            return mem_path.read_text()
        except Exception as exc:
            logger.warning(f"Failed to read thread memory: {exc}")
    return None


def write_thread_memory(project_path: str, project_key: str, content: str) -> bool:
    """Write persistent thread memory."""
    mem_dir = Path(project_path) / _MEMORY_DIR
    mem_path = mem_dir / f"{project_key}.md"
    try:
        mem_dir.mkdir(parents=True, exist_ok=True)
        mem_path.write_text(content)
        return True
    except Exception as exc:
        logger.warning(f"Failed to write thread memory: {exc}")
        return False
