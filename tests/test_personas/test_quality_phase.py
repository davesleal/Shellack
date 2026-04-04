"""
Integration tests for the quality phase persona composition.

Verifies VisualUX activation logic and Inspector → Tester data flow.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.inspector import Inspector
from tools.personas.tester import Tester
from tools.personas.visual_ux import VisualUX
from tools.pipeline import Phase, TurnContext, run_phase


def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=20, output_tokens=15)
    return mock_msg


def _patch_all(monkeypatch, personas: list, output: dict):
    for persona in personas:
        monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt, _o=output: _make_mock_msg(_o))


def test_visual_ux_only_activates_on_ui_files(monkeypatch):
    """VisualUX fires when architect.files_affected has UI extensions; skips for .py files."""
    visual_ux = VisualUX()

    # Patch _call_api to avoid real API calls
    mock_output = {"a11y_issues": [], "ux_issues": [], "verdict": "accessible"}
    monkeypatch.setattr(visual_ux, "_call_api", lambda s, u, m, mt: _make_mock_msg(mock_output))

    # Context with .tsx file — should activate
    ctx_ui = TurnContext()
    ctx_ui["architect"] = {
        "proposal": "Build a React form",
        "files_affected": ["src/components/LoginForm.tsx", "api/auth.py"],
    }
    assert visual_ux.should_activate("moderate", ctx_ui) is True
    assert visual_ux.should_activate("complex", ctx_ui) is True

    # Context with only .py files — should NOT activate
    ctx_backend = TurnContext()
    ctx_backend["architect"] = {
        "proposal": "Build an auth service",
        "files_affected": ["auth/service.py", "auth/models.py"],
    }
    assert visual_ux.should_activate("moderate", ctx_backend) is False
    assert visual_ux.should_activate("complex", ctx_backend) is False

    # Simple complexity — should never activate regardless of files
    assert visual_ux.should_activate("simple", ctx_ui) is False


def test_quality_gate_inspector_feeds_tester(monkeypatch):
    """Inspector gaps appear in Tester's inputs via TurnContext slot 'inspector'."""
    inspector = Inspector()
    tester = Tester()

    inspector_output = {
        "gaps": [
            {"type": "edge_case", "location": "auth/service.py", "severity": "high"},
            {"type": "missing_return", "location": "auth/models.py", "severity": "medium"},
        ],
        "verdict": "gaps",
    }
    tester_output = {
        "test_cases": [
            {"name": "test_empty_password_raises", "type": "unit", "assertion": "ValueError raised on empty password"},
            {"name": "test_user_model_returns_id", "type": "unit", "assertion": "save() returns integer ID"},
        ],
        "coverage_gaps": [],
        "verdict": "covered",
    }

    monkeypatch.setattr(inspector, "_call_api", lambda s, u, m, mt: _make_mock_msg(inspector_output))
    monkeypatch.setattr(tester, "_call_api", lambda s, u, m, mt: _make_mock_msg(tester_output))

    # Visual UX won't fire — no UI files in context
    visual_ux = VisualUX()

    phase = Phase(name="quality", emoji="\u2705", personas=[inspector, tester, visual_ux])
    ctx = TurnContext()
    ctx["architect"] = {
        "proposal": "Build an auth service",
        "data_model": "User with hashed password",
        "api_surface": "POST /login",
        "files_affected": ["auth/service.py", "auth/models.py"],
    }

    discussion, costs = run_phase(phase, ctx, "moderate")

    # Inspector and Tester should have fired; VisualUX should not
    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion]
    assert "inspector" in fired_names
    assert "tester" in fired_names
    assert "visual_ux" not in fired_names

    # Inspector output should be in context and available to Tester
    assert "inspector" in ctx
    assert ctx["inspector"]["verdict"] == "gaps"
    assert len(ctx["inspector"]["gaps"]) == 2

    # Tester output should reflect its strategy
    assert "tester" in ctx
    assert ctx["tester"]["verdict"] == "covered"
    assert len(ctx["tester"]["test_cases"]) == 2
