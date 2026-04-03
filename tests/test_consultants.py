# tests/test_consultants.py
"""Unit tests for tools/consultants.py — all Anthropic calls mocked."""

import pytest
from unittest.mock import MagicMock, patch

import tools.consultants as consultants_mod
from tools.consultants import detect_triggers, consult, _get_client

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


@patch("tools.consultants._get_client")
def test_consult_infosec_returns_finding(mock_get_client):
    """Infosec consultant returns a finding string."""
    finding = "\ud83d\udd34 SECURITY: Input not sanitized in parse_query()"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(finding)
    mock_get_client.return_value = mock_client

    result = consult(role="infosec", response="We added a new login endpoint")
    assert result == finding


@patch("tools.consultants._get_client")
def test_consult_infosec_no_issues_returns_none(mock_get_client):
    """When consultant says no issues, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 No security concerns."
    )
    mock_get_client.return_value = mock_client

    result = consult(role="infosec", response="We added a new login endpoint")
    assert result is None


@patch("tools.consultants._get_client")
def test_consult_architect_returns_finding(mock_get_client):
    """Architect consultant returns a concern string."""
    concern = "\ud83d\udcd0 ARCHITECTURE: Handler is mixing persistence and routing"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(concern)
    mock_get_client.return_value = mock_client

    result = consult(role="architect", response="Created a new module for payments")
    assert result == concern


@patch("tools.consultants._get_client")
def test_consult_architect_no_issues_returns_none(mock_get_client):
    """When architect says no issues, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 Architecture looks sound."
    )
    mock_get_client.return_value = mock_client

    result = consult(role="architect", response="Created a new module")
    assert result is None


@patch("tools.consultants._get_client")
def test_consult_api_failure_returns_none(mock_get_client):
    """API exception returns None (never blocks)."""
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("timeout")
    mock_get_client.return_value = mock_client

    result = consult(role="infosec", response="Check auth token")
    assert result is None


def test_consult_unknown_role_returns_none():
    """Unknown role returns None without calling API."""
    result = consult(role="unicorn", response="anything")
    assert result is None


# ---------------------------------------------------------------------------
# Tester consultant
# ---------------------------------------------------------------------------


def test_detect_triggers_tester():
    """Test-related keywords trigger tester."""
    assert "tester" in detect_triggers("We need to add a test for the parser")
    assert "tester" in detect_triggers("Run pytest with coverage enabled")
    assert "tester" in detect_triggers("Add a mock for the HTTP client")
    assert "tester" in detect_triggers("The fixture needs updating")


@patch("tools.consultants._get_client")
def test_consult_tester_returns_finding(mock_get_client):
    """Tester consultant returns a gap finding."""
    finding = "\ud83e\uddea TESTING: No edge-case tests for empty input"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(finding)
    mock_get_client.return_value = mock_client

    result = consult(role="tester", response="Added parse_query() function")
    assert result == finding


@patch("tools.consultants._get_client")
def test_consult_tester_no_issues(mock_get_client):
    """When tester says coverage is good, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 Test coverage looks good."
    )
    mock_get_client.return_value = mock_client

    result = consult(role="tester", response="Added tests for parse_query()")
    assert result is None


# ---------------------------------------------------------------------------
# Output editor consultant
# ---------------------------------------------------------------------------


@patch("tools.consultants._get_client")
def test_consult_output_editor(mock_get_client):
    """Output editor returns polished text."""
    polished = "## Bug Report\n\nThe login endpoint returns 500 on invalid input."
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(polished)
    mock_get_client.return_value = mock_client

    result = consult(role="output_editor", response="login endpoint 500 bad input")
    assert result == polished


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Visual UX consultant
# ---------------------------------------------------------------------------


def test_detect_triggers_visual_ux():
    """UI keywords trigger visual-ux."""
    assert "visual-ux" in detect_triggers("Updated the button component styles")
    assert "visual-ux" in detect_triggers("Changed the layout and padding")
    assert "visual-ux" in detect_triggers("New SwiftUI view for settings")
    assert "visual-ux" in detect_triggers("Added a modal with custom color tokens")


def test_detect_triggers_visual_ux_accessibility():
    """Accessibility keywords trigger visual-ux."""
    assert "visual-ux" in detect_triggers("Check WCAG compliance on the form")
    assert "visual-ux" in detect_triggers("Added a11y labels to all icons")
    assert "visual-ux" in detect_triggers("VoiceOver reads the wrong element")


@patch("tools.consultants._get_client")
def test_consult_visual_ux_returns_finding(mock_get_client):
    """Visual UX consultant returns a finding about contrast."""
    finding = "\U0001f3a8 UX/A11Y: Button text contrast is 3.1:1 — needs 4.5:1 minimum"
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(finding)
    mock_get_client.return_value = mock_client

    result = consult(
        role="visual-ux", response="Added a new button with light gray text"
    )
    assert result == finding


@patch("tools.consultants._get_client")
def test_consult_visual_ux_no_issues(mock_get_client):
    """When visual-ux says UI looks accessible, returns None."""
    mock_client = MagicMock()
    mock_client.messages.create.return_value = _make_mock_response(
        "\u2705 UI looks accessible and consistent."
    )
    mock_get_client.return_value = mock_client

    result = consult(role="visual-ux", response="Updated button colors")
    assert result is None


# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------


def test_detect_triggers_returns_max_two():
    """At most 2 consultants triggered per response to limit latency."""
    text = "I'll refactor the auth module with new tests and update the CSS layout"
    # This could trigger infosec (auth), architect (refactor), tester (tests), visual-ux (CSS)
    result = detect_triggers(text)
    assert len(result) <= 2


@patch("tools.consultants.Anthropic")
def test_singleton_client_reused(mock_anthropic_cls):
    """_get_client() returns the same instance on repeated calls."""
    # Reset module-level singleton
    consultants_mod._client = None
    mock_anthropic_cls.return_value = MagicMock()

    try:
        c1 = _get_client()
        c2 = _get_client()
        assert c1 is c2
        assert mock_anthropic_cls.call_count == 1
    finally:
        # Clean up so other tests aren't affected
        consultants_mod._client = None
