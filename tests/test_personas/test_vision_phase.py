"""
Integration tests for the vision phase persona composition.

Verifies activation rules and that insights correctly receives dreamer output.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.dreamer import Dreamer
from tools.personas.insights import Insights
from tools.personas.growth_coach import GrowthCoach
from tools.pipeline import Phase, TurnContext, run_phase


def _make_mock_msg(output: dict):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=20, output_tokens=15)
    return mock_msg


def _patch_all(monkeypatch, personas: list, output: dict):
    for persona in personas:
        monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt, _o=output: _make_mock_msg(_o))


@pytest.fixture
def vision_personas():
    return [Dreamer(), Insights(), GrowthCoach()]


def test_vision_only_on_complex(monkeypatch, vision_personas):
    """None of the vision personas fire on moderate; all 3 fire on complex."""
    output = {
        "vision": "A unified platform for all teams",
        "next_step": "Add webhook support",
        "platform_potential": "Enterprise SaaS",
        "time_horizon": "quarter",
        "success_criteria": ["10% DAU increase"],
        "metrics": ["daily_active_users"],
        "instrumentation": ["log webhook calls"],
        "verdict": "measurable",
        "funnel_impact": "Activation: users onboard faster",
        "conversion_risk": "Low discoverability",
        "ab_test_opportunity": "Test onboarding flow A vs B",
    }
    _patch_all(monkeypatch, vision_personas, output)

    phase = Phase(name="vision", emoji="\U0001f52e", personas=vision_personas)
    ctx = TurnContext()
    ctx["architect"] = {"proposal": "Add webhook integration", "data_model": "", "api_surface": "", "files_affected": []}
    ctx["token_cart"] = {}

    # Moderate — none should fire
    discussion_moderate, _ = run_phase(phase, ctx, "moderate")
    assert discussion_moderate == [], f"Expected no personas to fire on moderate, got: {discussion_moderate}"

    # Complex — all 3 should fire
    # Add dreamer output to ctx so insights can read it
    ctx["dreamer"] = {
        "vision": output["vision"],
        "next_step": output["next_step"],
        "platform_potential": output["platform_potential"],
        "time_horizon": output["time_horizon"],
    }
    ctx["insights"] = {
        "success_criteria": output["success_criteria"],
        "metrics": output["metrics"],
        "instrumentation": output["instrumentation"],
        "verdict": output["verdict"],
    }

    discussion_complex, _ = run_phase(phase, ctx, "complex")
    fired_names = [e.split(":")[0].split(" ")[-1] for e in discussion_complex]

    assert "dreamer" in fired_names
    assert "insights" in fired_names
    assert "growth_coach" in fired_names
    assert len(fired_names) == 3


def test_insights_reads_dreamer(monkeypatch):
    """Insights receives dreamer output in its inputs when context contains dreamer slot."""
    dreamer_output = {
        "vision": "Become the default dev tool for teams",
        "next_step": "Ship real-time collaboration",
        "platform_potential": "SMB market",
        "time_horizon": "quarter",
    }
    insights_output = {
        "success_criteria": ["30% retention after 7 days"],
        "metrics": ["d7_retention"],
        "instrumentation": ["track feature_used events"],
        "verdict": "measurable",
    }

    insights = Insights()

    captured_inputs: dict = {}

    def fake_call_api(system, user, model, max_tokens):
        captured_inputs["user"] = user
        return _make_mock_msg(insights_output)

    monkeypatch.setattr(insights, "_call_api", fake_call_api)

    # Simulate TurnContext with architect + dreamer populated
    ctx = TurnContext()
    ctx["architect"] = {"proposal": "Build real-time collab layer", "data_model": "session table", "api_surface": "WS endpoint"}
    ctx["dreamer"] = dreamer_output

    inputs = {slot: ctx[slot] for slot in insights.reads if slot in ctx}
    result = insights.run(inputs)

    # Dreamer vision should appear in the user content sent to insights
    assert dreamer_output["vision"] in captured_inputs["user"], (
        "Insights did not receive dreamer vision in its user content"
    )
    assert result["verdict"] == "measurable"
    assert "d7_retention" in result["metrics"]
