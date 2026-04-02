"""Tests for tools/thread_memory.py — cross-thread persistence."""
import os
import tempfile

import pytest

from tools.thread_memory import read_thread_memory, write_thread_memory


def test_write_and_read_thread_memory():
    """Round-trip: write then read returns same content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        content = "## Persistent Context\n### Open Items\n- Fix the login bug"
        assert write_thread_memory(tmpdir, "alpha", content) is True
        result = read_thread_memory(tmpdir, "alpha")
        assert result == content


def test_read_missing_returns_none():
    """No file on disk returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        assert read_thread_memory(tmpdir, "nonexistent") is None


def test_write_creates_nested_dirs():
    """write_thread_memory creates .shellack/thread-memory/ if absent."""
    with tempfile.TemporaryDirectory() as tmpdir:
        write_thread_memory(tmpdir, "beta", "some content")
        mem_dir = os.path.join(tmpdir, ".shellack", "thread-memory")
        assert os.path.isdir(mem_dir)
        assert os.path.isfile(os.path.join(mem_dir, "beta.md"))


def test_write_overwrites_existing():
    """Subsequent writes overwrite the prior content."""
    with tempfile.TemporaryDirectory() as tmpdir:
        write_thread_memory(tmpdir, "alpha", "version 1")
        write_thread_memory(tmpdir, "alpha", "version 2")
        assert read_thread_memory(tmpdir, "alpha") == "version 2"


def test_read_invalid_path_returns_none():
    """Read from a path that can't exist returns None gracefully."""
    assert read_thread_memory("/nonexistent/path/xyz", "proj") is None


def test_write_invalid_path_returns_false():
    """Write to an invalid path returns False gracefully."""
    assert write_thread_memory("/proc/0/invalid", "proj", "data") is False
