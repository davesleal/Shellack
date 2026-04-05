"""Tests for the VisualUX persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.visual_ux import VisualUX


@pytest.fixture
def persona():
    return VisualUX()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_metadata(persona):
    assert persona.name == "visual_ux"
    assert persona.model == "sonnet"
    assert persona.reads == ["architect"]
    assert persona.writes == "visual_ux"
    assert persona.emoji == "\U0001f3a8"
    assert persona.max_tokens == 768


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_activates_on_complex_with_ui_files(persona):
    ctx = {"architect": {"files_affected": ["components/Button.tsx"]}}
    assert persona.should_activate("complex", ctx) is True


def test_activates_on_moderate_with_ui_files(persona):
    ctx = {"architect": {"files_affected": ["views/Settings.swift"]}}
    assert persona.should_activate("moderate", ctx) is True


def test_does_not_activate_on_complex_without_ui_files(persona):
    ctx = {"architect": {"files_affected": ["models/user.py"]}}
    assert persona.should_activate("complex", ctx) is False


def test_does_not_activate_on_simple(persona):
    ctx = {"architect": {"files_affected": ["components/Button.tsx"]}}
    assert persona.should_activate("simple", ctx) is False


def test_does_not_activate_on_deep(persona):
    ctx = {"architect": {"files_affected": ["components/Button.tsx"]}}
    assert persona.should_activate("deep", ctx) is False


def test_does_not_activate_with_empty_files(persona):
    assert persona.should_activate("complex", {}) is False


def test_activates_for_each_ui_extension(persona):
    for ext in [".tsx", ".jsx", ".vue", ".svelte", ".swift", ".css", ".html"]:
        ctx = {"architect": {"files_affected": [f"file{ext}"]}}
        assert persona.should_activate("complex", ctx) is True, f"Failed for {ext}"


# ---------------------------------------------------------------------------
# Run (mocked API)
# ---------------------------------------------------------------------------

def test_run_returns_parsed_output(monkeypatch, persona):
    output = {
        "a11y_issues": [
            {"element": "Button", "violation": "WCAG 1.4.3 contrast", "fix": "Use #333 on #fff"}
        ],
        "ux_issues": [],
        "verdict": "fixable",
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=50, output_tokens=30)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({"architect": {"proposal": "New button component"}})
    result.pop("_usage", None)
    assert result == output


def test_run_falls_back_on_bad_json(monkeypatch, persona):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text="not json")]
    mock_msg.usage = MagicMock(input_tokens=10, output_tokens=5)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({})
    result.pop("_usage", None)
    assert result == {"raw": "not json"}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_build_user_content_filters_ui_files(persona):
    inputs = {
        "architect": {
            "proposal": "Redesign dashboard",
            "files_affected": ["components/Dashboard.tsx", "models/user.py", "styles/main.css"],
        },
    }
    content = persona._build_user_content(inputs)
    assert "Redesign dashboard" in content
    assert "Dashboard.tsx" in content
    assert "main.css" in content
    assert "user.py" not in content


def test_build_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
