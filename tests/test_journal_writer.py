import pytest
import re
from pathlib import Path
from tools.journal_writer import JournalWriter


@pytest.fixture
def tmp_project(tmp_path):
    return str(tmp_path)


def test_creates_docs_journal_if_none_exists(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry(
        "Fix crash",
        "User reported crash",
        "Investigated",
        "Fixed",
        "Guard statements matter",
    )
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    assert journal.exists()


def test_appends_to_existing_docs_journal(tmp_project):
    docs = Path(tmp_project) / "docs"
    docs.mkdir()
    journal = docs / "JOURNAL.md"
    journal.write_text("# Journal\n\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "Context", "Approach", "Outcome", "Insights")
    content = journal.read_text()
    assert content.startswith("# Journal")  # original content preserved
    assert "Task" in content
    assert "Context" in content
    assert "Insights" in content


def test_appends_to_root_journal_if_docs_missing(tmp_project):
    root_journal = Path(tmp_project) / "JOURNAL.md"
    root_journal.write_text("# Journal\n\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "Context", "Approach", "Outcome", "Insights")
    content = root_journal.read_text()
    assert "Task" in content


def test_prefers_docs_journal_over_root(tmp_project):
    docs = Path(tmp_project) / "docs"
    docs.mkdir()
    docs_journal = docs / "JOURNAL.md"
    docs_journal.write_text("# Docs Journal\n")
    root_journal = Path(tmp_project) / "JOURNAL.md"
    root_journal.write_text("# Root Journal\n")

    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "C", "A", "O", "I")
    assert "Task" in docs_journal.read_text()
    assert "Task" not in root_journal.read_text()


def test_entry_includes_issue_number_when_provided(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry(
        "Fix", "Context", "Approach", "Outcome", "Insights", issue_number=42
    )
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    assert "#42" in journal.read_text()


def test_entry_has_date_header(tmp_project):
    writer = JournalWriter(tmp_project)
    writer.append_entry("Task", "C", "A", "O", "I")
    journal = Path(tmp_project) / "docs" / "JOURNAL.md"
    content = journal.read_text()
    assert re.search(r"\d{4}-\d{2}-\d{2}", content)
