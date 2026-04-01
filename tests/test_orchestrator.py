# tests/test_orchestrator.py
"""Security tests for orchestrator.py — search uses fixed strings."""
import subprocess
from unittest.mock import patch, MagicMock

from orchestrator import Orchestrator


def test_search_all_projects_uses_fixed_strings_flag():
    """rg call must include -F to treat query as literal, preventing regex injection."""
    fake_projects = [
        {"name": "Alpha", "path": "/tmp/alpha"},
    ]

    with patch("orchestrator.get_all_projects", return_value=fake_projects), \
         patch("orchestrator.Path") as mock_path_cls, \
         patch("subprocess.run") as mock_run:
        mock_path_cls.return_value.exists.return_value = True
        mock_run.return_value = MagicMock(returncode=1, stdout="")

        orch = Orchestrator()
        orch.search_all_projects(".*malicious regex.*")

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "-F" in cmd, f"rg command must include -F flag, got: {cmd}"
    # -F must come before the query
    f_index = cmd.index("-F")
    query_index = cmd.index(".*malicious regex.*")
    assert f_index < query_index
