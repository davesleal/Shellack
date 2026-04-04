"""Tests for the Reuser persona."""

import pytest

from tools.personas.reuser import Reuser


@pytest.fixture
def persona():
    return Reuser()


def test_reuser_metadata(persona):
    assert persona.name == "reuser"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "token_cart"]
    assert persona.writes == "reuser"
    assert persona.emoji == "\u267b\ufe0f"


def test_reuser_activation(persona):
    assert persona.should_activate("moderate", {}) is True
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False
