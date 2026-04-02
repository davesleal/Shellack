# tests/test_consultants.py
"""Unit tests for tools/consultants.py — all Anthropic calls mocked."""
import pytest
from unittest.mock import MagicMock, patch

from tools.consultants import detect_triggers, consult


# ---------------------------------------------------------------------------
# detect_triggers
# ---------------------------------------------------------------------------

def test_detect_triggers_infosec():
    """Auth/login/token keywords trigger infosec."""
    assert "infosec" in detect_triggers("We need to validate the auth token")
    assert "infosec" in detect_triggers("Check the login flow for CSRF")
    assert "infosec" in detect_triggers("Password hashing uses bcrypt")


def test_detect_triggers_architect():
    """New module/refactor keywords trigger architect."""
    assert "architect" in detect_triggers("Created a new module for payments")
    assert "architect" in detect_triggers("We should refactor the handler")
    assert "architect" in detect_triggers("Added a dependency on redis")


def test_detect_triggers_none():
    """Normal response with no signals returns empty list."""
    assert detect_triggers("The build succeeded and tests pass.") == []
    assert detect_triggers("Updated the README with examples.") == []


def test_detect_triggers_both():
    """Response with both security and architecture signals returns both roles."""
    roles = detect_triggers("Refactor the auth module into a new file")
    assert "infosec" in roles
    assert "architect" in roles


# ---------------------------------------------------------------------------
# consult (mocked API)
# ---------------------------------------------------------------------------

def _make_mock_response(text: str) -> MagicMock:
    """Build a mock Anthropic message response."""
    content_block = MagicMock()
    content_block.text = text
    msg = MagicMock()
    msg.content = [content_block]
    return msg


@patch("tools.consultants.Anthropic")
def test_consult_infosec_returns_finding(mock_anthropic_cls):
    """Infosec consultant returns a finding string."""
    finding = "\ud83d\udd34 SECURITY: Input not sanitized in parse_query()"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(finding)
    mock_anthropic_cls.return_value = mock_client

    result = consult(role="infosec", response="We added a new login endpoint")
    assert result == finding


@patch("tools.consultants.Anthropic")
def test_consult_infosec_no_issues_returns_none(mock_anthropic_cls):
    """When consultant says no issues, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 No security concerns."
    )
    mock_anthropic_cls.return_value = mock_client

    result = consult(role="infosec", response="We added a new login endpoint")
    assert result is None


@patch("tools.consultants.Anthropic")
def test_consult_architect_returns_finding(mock_anthropic_cls):
    """Architect consultant returns a concern string."""
    concern = "\ud83d\udcd0 ARCHITECTURE: Handler is mixing persistence and routing"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(concern)
    mock_anthropic_cls.return_value = mock_client

    result = consult(role="architect", response="Created a new module for payments")
    assert result == concern


@patch("tools.consultants.Anthropic")
def test_consult_architect_no_issues_returns_none(mock_anthropic_cls):
    """When architect says no issues, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 Architecture looks sound."
    )
    mock_anthropic_cls.return_value = mock_client

    result = consult(role="architect", response="Created a new module")
    assert result is None


@patch("tools.consultants.Anthropic")
def test_consult_api_failure_returns_none(mock_anthropic_cls):
    """API exception returns None (never blocks)."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("timeout")
    mock_anthropic_cls.return_value = mock_client

    result = consult(role="infosec", response="Check auth token")
    assert result is None


def test_consult_unknown_role_returns_none():
    """Unknown role returns None without calling API."""
    result = consult(role="unicorn", response="anything")
    assert result is None
