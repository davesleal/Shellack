"""Tests for the Architect persona."""

import json
from unittest.mock import MagicMock

import pytest

from tools.personas.architect import Architect


@pytest.fixture
def persona():
    return Architect()


# ---------------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------------

def test_architect_metadata(persona):
    assert persona.name == "architect"
    assert persona.model == "sonnet"
    assert persona.reads == ["strategist", "historian", "token_cart"]
    assert persona.writes == "architect"
    assert persona.emoji == "\U0001f4d0"


# ---------------------------------------------------------------------------
# Activation
# ---------------------------------------------------------------------------

def test_architect_activates_moderate_and_complex(persona):
    assert persona.should_activate("moderate", {}) is True
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False


# ---------------------------------------------------------------------------
# Run (mocked API)
# ---------------------------------------------------------------------------

def test_architect_run(monkeypatch, persona):
    output = {
        "proposal": "Use a layered architecture with clear separation of concerns.",
        "data_model": "User(id, name, email), Project(id, owner_id, name)",
        "api_surface": "create_user(name, email) -> User; create_project(owner_id, name) -> Project",
        "files_affected": ["tools/user.py", "tools/project.py"],
    }
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=json.dumps(output))]
    mock_msg.usage = MagicMock(input_tokens=80, output_tokens=60)
    monkeypatch.setattr(persona, "_call_api", lambda s, u, m, mt: mock_msg)

    result = persona.run({
        "strategist": {"tasks": ["Design user model", "Design project model"]},
        "historian": {"prior_decisions": ["Use SQLite for storage"]},
    })
    usage = result.pop("_usage")
    assert result == output
    assert usage == {"input_tokens": 80, "output_tokens": 60}


# ---------------------------------------------------------------------------
# User content
# ---------------------------------------------------------------------------

def test_architect_builds_user_content_includes_strategist_tasks(persona):
    inputs = {
        "strategist": {
            "tasks": ["Design the data model", "Create API endpoints"],
            "estimated_complexity": "moderate",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Design the data model" in content
    assert "Create API endpoints" in content


def test_architect_builds_user_content_includes_historian_decisions(persona):
    inputs = {
        "strategist": {"tasks": ["Build something"]},
        "historian": {"prior_decisions": ["Always use async functions"]},
    }
    content = persona._build_user_content(inputs)
    assert "Always use async functions" in content


def test_architect_builds_user_content_includes_token_cart(persona):
    inputs = {
        "token_cart": {
            "enriched_prompt": "Build a caching layer",
            "registry": "existing_cache: tools/cache.py",
        },
    }
    content = persona._build_user_content(inputs)
    assert "Build a caching layer" in content
    assert "existing_cache" in content


def test_architect_builds_user_content_empty_fallback(persona):
    content = persona._build_user_content({})
    assert content == "No context available."
