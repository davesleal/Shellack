"""Tests for the Connector persona."""

import pytest

from tools.personas.connector import Connector


@pytest.fixture
def persona():
    return Connector()


def test_connector_metadata(persona):
    assert persona.name == "connector"
    assert persona.model == "haiku"
    assert persona.reads == ["architect", "token_cart"]
    assert persona.writes == "connector"
    assert persona.emoji == "\U0001f517"


def test_connector_activation(persona):
    assert persona.should_activate("complex", {}) is True
    assert persona.should_activate("moderate", {}) is False
    assert persona.should_activate("simple", {}) is False
    assert persona.should_activate("deep", {}) is False
