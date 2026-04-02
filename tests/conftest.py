"""
Root test conftest — ensures a projects.yaml config exists before any
test module is collected (and therefore before orchestrator_config is
imported at module level).

On a fresh clone where projects.yaml is gitignored and absent, this
writes a minimal temporary config and points SHELLACK_CONFIG at it.
When the real projects.yaml exists, this is a no-op.
"""

import os
import tempfile

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REAL_CONFIG = os.path.join(_REPO_ROOT, "projects.yaml")

_FALLBACK_CONFIG = """\
github_org: "test-org"
projects:
  alpha:
    name: "Alpha"
    path: "/tmp/alpha"
    language: python
    platform: server
    github_repo: "test-org/Alpha"
    primary_channel: "alpha-dev"
    context:
      description: "Test project"
      purpose: "Unit testing"
      tech: "Python"
      patterns: []
      watch_out: []
  beta:
    name: "Beta"
    path: "/tmp/beta"
    language: swift
    platform: ios
    github_repo: "test-org/Beta"
    primary_channel: "beta-dev"
channels:
  alpha-dev:
    project: alpha
    mode: dedicated
    channel_id: "C_ALPHA"
  beta-dev:
    project: beta
    mode: dedicated
    channel_id: "C_BETA"
  shellack-central:
    mode: orchestrator
    access: all_projects
    channel_id: ""
  code-review:
    mode: peer_review
    access: all_projects
    channel_id: ""
standards:
  python:
    style_guide: "PEP 8"
    conventions: ["Use type hints"]
    required_tests: true
    min_coverage: 80
"""

# Keep a reference so the temp file isn't garbage-collected mid-session.
_tmp_file = None


def pytest_configure(config):
    """Runs before collection — guarantees SHELLACK_CONFIG points at a valid file."""
    global _tmp_file

    if os.path.isfile(_REAL_CONFIG):
        return  # real config exists, nothing to do

    if os.environ.get("SHELLACK_CONFIG") and os.path.isfile(
        os.environ["SHELLACK_CONFIG"]
    ):
        return  # caller already set a valid override

    _tmp_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".yaml",
        prefix="shellack_test_",
        delete=False,
    )
    _tmp_file.write(_FALLBACK_CONFIG)
    _tmp_file.flush()
    os.environ["SHELLACK_CONFIG"] = _tmp_file.name


def pytest_unconfigure(config):
    """Clean up the temp file when the session ends."""
    global _tmp_file
    if _tmp_file is not None:
        path = _tmp_file.name
        _tmp_file.close()
        try:
            os.unlink(path)
        except OSError:
            pass
        _tmp_file = None
