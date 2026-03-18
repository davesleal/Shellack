"""
Tests for the claude_bridge_input Bolt action handler.

We test the handler function directly by importing it and calling it with
mock ack/body/action/client arguments.
"""
import errno
import json
import os
import uuid
import pytest
from unittest.mock import MagicMock, patch


def _make_handler():
    from bot_unified import handle_bridge_input
    return handle_bridge_input


def _body(channel="C1", user="U1", ts="123.456"):
    return {
        "channel": {"id": channel},
        "user": {"id": user},
        "message": {"ts": ts},
    }


_VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"


def _action(value=f"{_VALID_UUID}|AnswerA"):
    return {"value": value}


def _client():
    c = MagicMock()
    c.chat_postEphemeral = MagicMock()
    c.chat_update = MagicMock()
    return c


def test_handle_malformed_value_is_ignored():
    """Values without '|' must be silently discarded after ack."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()
    handler(ack=ack, body=_body(), action={"value": "no-pipe-char"}, client=client)
    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
    client.chat_update.assert_not_called()


def test_handle_session_file_not_found(tmp_path):
    """Missing session file → ephemeral 'session expired' to user only."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in str(path):
            raise FileNotFoundError
        return open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        handler(ack=ack, body=_body(), action=_action(f"{_VALID_UUID}|X"), client=client)

    ack.assert_called_once()
    client.chat_postEphemeral.assert_called_once()
    call_kwargs = client.chat_postEphemeral.call_args.kwargs
    assert call_kwargs["user"] == "U1"
    assert "expired" in call_kwargs["text"].lower()
    client.chat_update.assert_not_called()


def test_handle_pipe_enxio_shows_ephemeral_leaves_buttons(tmp_path):
    """ENXIO (no reader on pipe) → ephemeral error, chat_update NOT called."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "dead_pipe")
    os.mkfifo(pipe_path)
    session_data = {"pipe": pipe_path}
    session_id_enxio = str(uuid.uuid4())
    session_file = str(tmp_path / f"{session_id_enxio}.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    real_open = open
    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in str(path):
            return real_open(session_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    enxio = OSError(errno.ENXIO, "No such device or address")
    with patch("builtins.open", side_effect=patched_open), \
         patch("os.open", side_effect=enxio):
        handler(ack=ack, body=_body(), action=_action(f"{session_id_enxio}|X"), client=client)

    client.chat_postEphemeral.assert_called_once()
    client.chat_update.assert_not_called()


def test_handle_missing_message_ts_skips_chat_update(tmp_path):
    """When body has no 'message' key, pipe write succeeds but chat_update is skipped."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "pipe_nots")
    os.mkfifo(pipe_path)
    read_fd  = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)
    write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)

    session_data = {"pipe": pipe_path}
    session_id_nots = str(uuid.uuid4())
    session_file = str(tmp_path / f"{session_id_nots}.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    body_no_ts = {"channel": {"id": "C1"}, "user": {"id": "U1"}}

    real_open = open
    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in str(path):
            return real_open(session_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        handler(ack=ack, body=body_no_ts, action=_action(f"{session_id_nots}|Y"), client=client)

    ack.assert_called_once()
    client.chat_update.assert_not_called()
    client.chat_postEphemeral.assert_not_called()

    os.close(write_fd)
    os.close(read_fd)


def test_handle_missing_channel_returns_early():
    """Body with no channel → early return, nothing posted."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()
    body_no_channel = {"user": {"id": "U1"}, "message": {"ts": "1.2"}}
    handler(ack=ack, body=body_no_channel, action=_action("s|X"), client=client)
    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
    client.chat_update.assert_not_called()


def test_handle_happy_path(tmp_path):
    """Pipe write succeeds → chat_update called with confirmation, no ephemeral."""
    handler = _make_handler()
    ack = MagicMock()
    client = _client()

    pipe_path = str(tmp_path / "test_pipe")
    os.mkfifo(pipe_path)
    # Open read end first (POSIX), then write end (keep-alive)
    read_fd  = os.open(pipe_path, os.O_RDONLY | os.O_NONBLOCK)
    write_fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)

    session_data = {"pipe": pipe_path}
    # Use a valid UUID as session_id
    import uuid as _uuid
    session_id = str(_uuid.uuid4())
    session_file = str(tmp_path / f"{session_id}.json")
    with open(session_file, "w") as f:
        json.dump(session_data, f)

    real_open = open
    def patched_open(path, *args, **kwargs):
        if "claude_bridge" in str(path):
            return real_open(session_file, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=patched_open):
        handler(
            ack=ack,
            body=_body(channel="C1", user="U1", ts="123.456"),
            action={"value": f"{session_id}|AnswerB"},
            client=client,
        )

    ack.assert_called_once()
    client.chat_postEphemeral.assert_not_called()
    client.chat_update.assert_called_once()
    update_kwargs = client.chat_update.call_args.kwargs
    assert update_kwargs["channel"] == "C1"
    assert update_kwargs["ts"] == "123.456"
    assert "✅" in update_kwargs["text"]
    assert "AnswerB" in update_kwargs["text"]

    os.close(write_fd)
    os.close(read_fd)
