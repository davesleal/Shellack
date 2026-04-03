"""Tests for tools/registry.py — Project Registry subsystem."""

from tools.registry import (
    _INITIAL_TEMPLATE,
    append_to_registry,
    ensure_registry,
    read_registry,
    write_registry,
)


def test_read_registry_returns_content(tmp_path):
    registry_dir = tmp_path / ".shellack"
    registry_dir.mkdir()
    registry_file = registry_dir / "registry.md"
    registry_file.write_text("# My Registry\nSome content")

    result = read_registry(str(tmp_path))
    assert result == "# My Registry\nSome content"


def test_read_registry_returns_none_when_missing(tmp_path):
    result = read_registry(str(tmp_path))
    assert result is None


def test_write_registry_creates_dir_and_file(tmp_path):
    content = "# Test Registry"
    result = write_registry(str(tmp_path), content)

    assert result is True
    assert (tmp_path / ".shellack" / "registry.md").read_text() == content


def test_ensure_registry_creates_template(tmp_path):
    result = ensure_registry(str(tmp_path))

    assert result == _INITIAL_TEMPLATE
    assert (tmp_path / ".shellack" / "registry.md").exists()
    assert (tmp_path / ".shellack" / "registry.md").read_text() == _INITIAL_TEMPLATE


def test_ensure_registry_reads_existing(tmp_path):
    registry_dir = tmp_path / ".shellack"
    registry_dir.mkdir()
    (registry_dir / "registry.md").write_text("# Existing")

    result = ensure_registry(str(tmp_path))
    assert result == "# Existing"


def test_append_to_existing_section(tmp_path):
    write_registry(str(tmp_path), _INITIAL_TEMPLATE)

    entry = "| Button | src/Button.tsx | onClick, label | Primary CTA |"
    result = append_to_registry(str(tmp_path), "UI Components", entry)

    assert result is True
    content = read_registry(str(tmp_path))
    assert entry in content
    # Entry should be in the UI Components section (before Design Tokens)
    lines = content.split("\n")
    entry_idx = next(i for i, l in enumerate(lines) if entry in l)
    header_idx = next(i for i, l in enumerate(lines) if "## UI Components" in l)
    next_section_idx = next(
        i for i, l in enumerate(lines) if i > header_idx and l.startswith("## ")
    )
    assert header_idx < entry_idx < next_section_idx


def test_append_to_missing_section(tmp_path):
    write_registry(str(tmp_path), _INITIAL_TEMPLATE)

    entry = "| deploy | ci/deploy.sh | Runs on merge to main |"
    result = append_to_registry(str(tmp_path), "CI Pipelines", entry)

    assert result is True
    content = read_registry(str(tmp_path))
    assert "## CI Pipelines" in content
    assert entry in content


def test_append_preserves_other_sections(tmp_path):
    write_registry(str(tmp_path), _INITIAL_TEMPLATE)

    append_to_registry(
        str(tmp_path),
        "UI Components",
        "| Card | src/Card.tsx | title, body | Reusable card |",
    )

    content = read_registry(str(tmp_path))
    # All original sections must still be present
    for section in [
        "## UI Components",
        "## Design Tokens",
        "## Shared Utilities",
        "## Data Models",
        "## API Patterns",
        "## Architecture Rules",
    ]:
        assert section in content, f"Missing section: {section}"


def test_ensure_registry_nonexistent_path_no_crash():
    """ensure_registry on a path that doesn't exist returns template without crashing."""
    result = ensure_registry("/nonexistent/path/that/doesnt/exist")
    # Should return the template (even if write fails) or handle gracefully
    assert result is not None
