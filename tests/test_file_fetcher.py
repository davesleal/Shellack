"""Tests for tools/file_fetcher.py."""

from tools.file_fetcher import read_file, fetch_files_for_context


def test_read_file_exists(tmp_path):
    (tmp_path / "test.txt").write_text("hello world")
    result = read_file(str(tmp_path), "test.txt")
    assert result == "hello world"


def test_read_file_missing(tmp_path):
    result = read_file(str(tmp_path), "nope.txt")
    assert result is None


def test_read_file_path_traversal(tmp_path):
    result = read_file(str(tmp_path), "../../etc/passwd")
    assert result is None


def test_read_file_truncates(tmp_path):
    (tmp_path / "big.txt").write_text("x" * 10000)
    result = read_file(str(tmp_path), "big.txt")
    assert len(result) < 5000
    assert "truncated" in result


def test_fetch_multiple_files(tmp_path):
    (tmp_path / "a.ts").write_text("const a = 1;")
    (tmp_path / "b.ts").write_text("const b = 2;")
    result = fetch_files_for_context(str(tmp_path), ["a.ts", "b.ts"])
    assert "const a" in result
    assert "const b" in result


def test_fetch_missing_file(tmp_path):
    result = fetch_files_for_context(str(tmp_path), ["nope.ts"])
    assert "not found" in result
