# tests/test_config_writer.py
import os
import pytest


def test_set_env_var_writes_new_key(tmp_path):
    from tools.config_writer import set_env_var

    env_file = tmp_path / ".env"
    env_file.write_text("EXISTING=value\n")
    set_env_var("NEW_KEY", "new_val", env_path=str(env_file))
    assert 'NEW_KEY="new_val"' in env_file.read_text()
    assert os.environ.get("NEW_KEY") == "new_val"


def test_set_env_var_replaces_existing_key(tmp_path):
    from tools.config_writer import set_env_var

    env_file = tmp_path / ".env"
    env_file.write_text("SESSION_BACKEND=api\n")
    set_env_var("SESSION_BACKEND", "max", env_path=str(env_file))
    content = env_file.read_text()
    assert content.count("SESSION_BACKEND") == 1
    assert 'SESSION_BACKEND="max"' in content


def test_set_env_var_creates_file_if_missing(tmp_path):
    from tools.config_writer import set_env_var

    env_file = tmp_path / ".env"
    set_env_var("FRESH_KEY", "fresh_val", env_path=str(env_file))
    assert 'FRESH_KEY="fresh_val"' in env_file.read_text()
