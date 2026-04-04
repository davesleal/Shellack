"""Tests for the Empathizer persona."""

import pytest

from tools.personas.empathizer import Empathizer


@pytest.fixture
def persona():
    return Empathizer()


def test_empathizer_metadata(persona):
    assert persona.name == "empathizer"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "observer"]
    assert persona.writes == "empathizer"
    assert persona.emoji == "\U0001fac2"


def test_empathizer_activation(persona):
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("moderate", {}) is False
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False
