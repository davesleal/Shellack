"""Tests for the Specialist persona."""

import pytest

from tools.personas.specialist import Specialist


@pytest.fixture
def persona():
    return Specialist()


def test_specialist_metadata(persona):
    assert persona.name == "specialist"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "token_cart"]
    assert persona.writes == "specialist"
    assert persona.emoji == "\U0001f9ec"


def test_specialist_activation(persona):
    assert persona.should_activate("moderate", {}) is True
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False
