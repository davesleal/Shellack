# tools/config_writer.py
"""Write or update KEY=VALUE in .env without requiring a bot restart."""
from __future__ import annotations

import os
import re

_ENV_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")


def set_env_var(key: str, value: str, env_path: str = _ENV_PATH) -> None:
    """Write or update KEY=VALUE in the .env file, then update os.environ."""
    try:
        with open(env_path) as f:
            lines = f.readlines()
    except FileNotFoundError:
        lines = []

    pattern = re.compile(rf"^{re.escape(key)}\s*=")
    replaced = False
    new_lines = []
    for line in lines:
        if pattern.match(line):
            new_lines.append(f"{key}={value}\n")
            replaced = True
        else:
            new_lines.append(line)

    if not replaced:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines[-1] += "\n"
        new_lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(new_lines)

    os.environ[key] = value
