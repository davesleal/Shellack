#!/usr/bin/env python3
"""Appends narrative journal entries to per-project JOURNAL.md files."""

import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class JournalWriter:
    def __init__(self, project_path: str):
        self.project_path = Path(project_path)

    def _resolve_journal_path(self) -> Path:
        docs_journal = self.project_path / "docs" / "JOURNAL.md"
        root_journal = self.project_path / "JOURNAL.md"

        if docs_journal.exists():
            return docs_journal
        if root_journal.exists():
            return root_journal

        # Neither exists — create docs/JOURNAL.md
        docs_journal.parent.mkdir(parents=True, exist_ok=True)
        docs_journal.write_text("# Project Journal\n\n")
        return docs_journal

    def append_entry(self, title: str, context: str, approach: str,
                     outcome: str, insights: str,
                     issue_number: Optional[int] = None):
        """Append a dated narrative entry to the project journal."""
        today = date.today().isoformat()
        issue_line = f"\n\n**GitHub Issue:** #{issue_number}" if issue_number else ""

        entry = f"""
## {today} — {title}

**Context:** {context}

**Approach:** {approach}

**Outcome:** {outcome}{issue_line}

**Insights:** {insights}

---
"""
        try:
            journal_path = self._resolve_journal_path()
            with open(journal_path, "a") as f:
                f.write(entry)
            logger.info(f"Journal entry written to {journal_path}")
        except Exception as e:
            logger.error(f"Failed to write journal entry: {e}")
