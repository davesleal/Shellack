"""Tests for tools/skill_mapper.py."""

from unittest.mock import patch
from tools.skill_mapper import (
    detect_stack,
    get_skills_for_project,
    format_skill_manifest,
    GLOBAL_SKILLS,
)


def test_detect_stack_python(tmp_path):
    (tmp_path / "requirements.txt").write_text("flask\n")
    stacks = detect_stack(str(tmp_path))
    assert "python" in stacks


def test_detect_stack_swift(tmp_path):
    (tmp_path / "Package.swift").write_text("// swift-tools-version:5.9\n")
    stacks = detect_stack(str(tmp_path))
    assert "swift" in stacks


def test_detect_stack_nextjs(tmp_path):
    (tmp_path / "package.json").write_text("{}\n")
    (tmp_path / "next.config.js").write_text("module.exports = {}\n")
    stacks = detect_stack(str(tmp_path))
    assert "web" in stacks
    assert "nextjs" in stacks


def test_detect_stack_empty(tmp_path):
    stacks = detect_stack(str(tmp_path))
    assert stacks == []


def test_detect_stack_invalid_path():
    stacks = detect_stack("/nonexistent/path")
    assert stacks == []


def test_global_skills_always_included(tmp_path):
    with patch(
        "tools.skill_mapper._get_installed_skills", return_value=set(GLOBAL_SKILLS)
    ):
        skills = get_skills_for_project(str(tmp_path))
    for g in GLOBAL_SKILLS:
        assert g in skills


def test_web_project_gets_frontend_skills(tmp_path):
    (tmp_path / "package.json").write_text("{}\n")
    all_skills = set(GLOBAL_SKILLS) | {
        "frontend-design",
        "baseline-ui",
        "animate",
        "colorize",
        "overdrive",
        "typeset",
        "arrange",
        "delight",
        "adapt",
        "fixing-motion-performance",
        "fixing-metadata",
    }
    with patch("tools.skill_mapper._get_installed_skills", return_value=all_skills):
        skills = get_skills_for_project(str(tmp_path))
    assert "frontend-design" in skills
    assert "animate" in skills
    assert "colorize" in skills


def test_swift_project_does_not_get_web_skills(tmp_path):
    (tmp_path / "Package.swift").write_text("// swift\n")
    all_skills = set(GLOBAL_SKILLS) | {
        "polish",
        "critique",
        "adapt",
        "normalize",
        "distill",
        "frontend-design",
        "animate",
    }
    with patch("tools.skill_mapper._get_installed_skills", return_value=all_skills):
        skills = get_skills_for_project(str(tmp_path), language="swift", platform="ios")
    assert "polish" in skills
    assert "frontend-design" not in skills
    assert "animate" not in skills


def test_language_config_adds_stack(tmp_path):
    all_skills = set(GLOBAL_SKILLS) | {"normalize", "distill", "extract", "onboard"}
    with patch("tools.skill_mapper._get_installed_skills", return_value=all_skills):
        skills = get_skills_for_project(str(tmp_path), language="python")
    assert "normalize" in skills


def test_only_installed_skills_returned(tmp_path):
    """Skills not installed on disk are filtered out."""
    with patch(
        "tools.skill_mapper._get_installed_skills", return_value={"audit", "harden"}
    ):
        skills = get_skills_for_project(str(tmp_path))
    assert "audit" in skills
    assert "fixing-accessibility" not in skills  # not installed


def test_format_skill_manifest():
    manifest = format_skill_manifest(["audit", "harden", "optimize"])
    assert "/audit" in manifest
    assert "/harden" in manifest
    assert "Available Skills" in manifest


def test_format_skill_manifest_empty():
    assert format_skill_manifest([]) == ""
