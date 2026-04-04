"""Tests for the DataScientist persona."""

import pytest

from tools.personas.data_scientist import DataScientist


@pytest.fixture
def persona():
    return DataScientist()


def test_data_scientist_metadata(persona):
    assert persona.name == "data_scientist"
    assert persona.model == "haiku"
    assert persona.reads == ["architect"]
    assert persona.writes == "data_scientist"
    assert persona.emoji == "\U0001f4ca"


def test_data_scientist_activation(persona):
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("moderate", {}) is False
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False
