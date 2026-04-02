"""Voice transcription — converts Slack audio messages to text using faster-whisper."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

import requests

logger = logging.getLogger(__name__)

_MODEL_SIZE = os.environ.get("WHISPER_MODEL", "base")
_transcriber = None


def _get_transcriber():
    """Lazy-load the whisper model."""
    global _transcriber
    if _transcriber is None:
        try:
            from faster_whisper import WhisperModel

            _transcriber = WhisperModel(
                _MODEL_SIZE,
                device="cpu",
                compute_type="int8",
            )
            logger.info(f"Whisper model '{_MODEL_SIZE}' loaded")
        except ImportError:
            logger.warning(
                "faster-whisper not installed — voice transcription unavailable"
            )
            return None
        except Exception as exc:
            logger.warning(f"Failed to load Whisper model: {exc}")
            return None
    return _transcriber


def download_slack_file(url: str, token: str) -> Optional[str]:
    """Download a Slack file to a temp path. Returns path or None."""
    try:
        resp = requests.get(
            url,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30,
        )
        resp.raise_for_status()
        suffix = ".ogg"  # Slack voice messages are typically ogg/opus
        if "mp4" in url:
            suffix = ".mp4"
        elif "webm" in url:
            suffix = ".webm"
        elif "m4a" in url:
            suffix = ".m4a"

        fd, path = tempfile.mkstemp(suffix=suffix)
        with os.fdopen(fd, "wb") as f:
            f.write(resp.content)
        return path
    except Exception as exc:
        logger.warning(f"Failed to download Slack file: {exc}")
        return None


def transcribe(audio_path: str) -> Optional[str]:
    """Transcribe an audio file. Returns transcript text or None."""
    model = _get_transcriber()
    if model is None:
        return None

    try:
        segments, info = model.transcribe(
            audio_path,
            beam_size=5,
            language=None,  # auto-detect
        )
        text = " ".join(seg.text.strip() for seg in segments)
        return text.strip() if text.strip() else None
    except Exception as exc:
        logger.warning(f"Transcription failed: {exc}")
        return None
    finally:
        try:
            os.unlink(audio_path)
        except OSError:
            pass


def transcribe_slack_file(file_info: dict, token: str) -> Optional[str]:
    """Download and transcribe a Slack audio file.

    Args:
        file_info: Slack file object from the event
        token: Slack bot token for authenticated download

    Returns: transcript text or None
    """
    url = file_info.get("url_private_download") or file_info.get("url_private")
    if not url:
        logger.warning("No download URL in file info")
        return None

    # Check if it's an audio file
    filetype = file_info.get("filetype", "")
    mimetype = file_info.get("mimetype", "")
    if not (
        filetype in ("mp4", "webm", "ogg", "m4a", "aac", "wav", "mp3")
        or "audio" in mimetype
        or file_info.get("subtype") == "slack_audio"
    ):
        return None  # not an audio file

    path = download_slack_file(url, token)
    if not path:
        return None

    return transcribe(path)
