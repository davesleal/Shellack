"""Tests for tools/voice_transcriber.py — all external calls mocked."""

from unittest.mock import MagicMock, patch
import os

from tools.voice_transcriber import (
    download_slack_file,
    transcribe_slack_file,
)


def test_download_slack_file_success():
    """Downloads file and saves to temp path."""
    mock_resp = MagicMock()
    mock_resp.content = b"fake audio data"
    mock_resp.raise_for_status = MagicMock()

    with patch("tools.voice_transcriber.requests.get", return_value=mock_resp):
        path = download_slack_file("https://files.slack.com/audio.ogg", "test-fake-token")

    assert path is not None
    assert os.path.exists(path)
    with open(path, "rb") as f:
        assert f.read() == b"fake audio data"
    os.unlink(path)


def test_download_slack_file_failure():
    """Network error returns None."""
    with patch(
        "tools.voice_transcriber.requests.get", side_effect=Exception("timeout")
    ):
        path = download_slack_file("https://files.slack.com/audio.ogg", "test-fake-token")
    assert path is None


def test_transcribe_slack_file_not_audio():
    """Non-audio file returns None without attempting download."""
    file_info = {
        "filetype": "pdf",
        "mimetype": "application/pdf",
        "url_private": "https://...",
    }
    result = transcribe_slack_file(file_info, "test-fake-token")
    assert result is None


def test_transcribe_slack_file_no_url():
    """File with no download URL returns None."""
    file_info = {"filetype": "ogg", "mimetype": "audio/ogg"}
    result = transcribe_slack_file(file_info, "test-fake-token")
    assert result is None


def test_transcribe_slack_file_success():
    """Full flow: download + transcribe returns text."""
    file_info = {
        "filetype": "ogg",
        "mimetype": "audio/ogg",
        "subtype": "slack_audio",
        "url_private_download": "https://files.slack.com/audio.ogg",
    }

    with patch(
        "tools.voice_transcriber.download_slack_file", return_value="/tmp/test.ogg"
    ), patch("tools.voice_transcriber.transcribe", return_value="Hello world"):
        result = transcribe_slack_file(file_info, "test-fake-token")

    assert result == "Hello world"


def test_transcribe_slack_file_transcription_fails():
    """Download succeeds but transcription fails — returns None."""
    file_info = {
        "filetype": "ogg",
        "mimetype": "audio/ogg",
        "url_private_download": "https://files.slack.com/audio.ogg",
    }

    with patch(
        "tools.voice_transcriber.download_slack_file", return_value="/tmp/test.ogg"
    ), patch("tools.voice_transcriber.transcribe", return_value=None):
        result = transcribe_slack_file(file_info, "test-fake-token")

    assert result is None
