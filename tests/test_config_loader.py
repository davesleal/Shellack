"""Tests for orchestrator_config YAML loader."""

import os
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

# We import the loader function directly rather than the module-level globals,
# so each test can point at its own temp YAML without side effects.
from orchestrator_config import (
    load_config,
    get_project_for_channel,
    get_all_projects,
    is_orchestrator_channel,
    is_peer_review_channel,
    validate_config,
    PROJECTS,
    CHANNEL_ROUTING,
    GLOBAL_STANDARDS,
    ORCHESTRATOR_COMMANDS,
    PEER_REVIEW_CONFIG,
    GITHUB_ORG,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MINIMAL_YAML = textwrap.dedent("""\
    github_org: "test-org"

    projects:
      myapp:
        name: "My App"
        path: "~/Repos/MyApp"
        bundle_id: "com.test.myapp"
        language: swift
        platform: ios
        github_repo: "test-org/MyApp"
        primary_channel: "myapp-dev"

    channels:
      myapp-dev:
        project: myapp
        mode: dedicated
        channel_id: "C12345"
      ops-central:
        mode: orchestrator
        access: all_projects
        channel_id: ""
      code-review:
        mode: peer_review
        access: all_projects
        channel_id: ""

    standards:
      swift:
        style_guide: "Swift API Design Guidelines"
        conventions: ["Use guard"]
        required_tests: true
        min_coverage: 80

    orchestrator_commands:
      global_search:
        description: "Search everywhere"
        syntax: "@Bot search: <query>"

    peer_review:
      reviewers:
        code-quality:
          focus: ["readability"]
          blocking: true
      approval_threshold: 1
      auto_merge_on_approval: false
      required_checks: ["tests_passing"]
""")


@pytest.fixture
def yaml_file(tmp_path):
    """Write minimal YAML to a temp file and return its path."""
    p = tmp_path / "projects.yaml"
    p.write_text(MINIMAL_YAML)
    return str(p)


# ---------------------------------------------------------------------------
# Loading from YAML
# ---------------------------------------------------------------------------


class TestLoadConfig:
    def test_loads_projects(self, yaml_file):
        cfg = load_config(yaml_file)
        assert "myapp" in cfg["PROJECTS"]
        proj = cfg["PROJECTS"]["myapp"]
        assert proj["name"] == "My App"
        assert proj["language"] == "swift"
        assert proj["platform"] == "ios"
        assert proj["github_repo"] == "test-org/MyApp"
        assert proj["primary_channel"] == "myapp-dev"

    def test_expands_tilde_in_path(self, yaml_file):
        cfg = load_config(yaml_file)
        proj = cfg["PROJECTS"]["myapp"]
        assert "~" not in proj["path"]
        assert proj["path"].endswith("/Repos/MyApp")

    def test_loads_channel_routing(self, yaml_file):
        cfg = load_config(yaml_file)
        assert "myapp-dev" in cfg["CHANNEL_ROUTING"]
        assert cfg["CHANNEL_ROUTING"]["myapp-dev"]["mode"] == "dedicated"
        assert cfg["CHANNEL_ROUTING"]["myapp-dev"]["channel_id"] == "C12345"

    def test_loads_standards(self, yaml_file):
        cfg = load_config(yaml_file)
        assert "swift" in cfg["GLOBAL_STANDARDS"]
        assert cfg["GLOBAL_STANDARDS"]["swift"]["min_coverage"] == 80

    def test_loads_orchestrator_commands(self, yaml_file):
        cfg = load_config(yaml_file)
        assert "global_search" in cfg["ORCHESTRATOR_COMMANDS"]

    def test_loads_peer_review(self, yaml_file):
        cfg = load_config(yaml_file)
        assert cfg["PEER_REVIEW_CONFIG"]["approval_threshold"] == 1

    def test_loads_github_org(self, yaml_file):
        cfg = load_config(yaml_file)
        assert cfg["GITHUB_ORG"] == "test-org"

    def test_context_block_carried_through(self, tmp_path):
        y = textwrap.dedent("""\
            github_org: "org"
            projects:
              app:
                name: "App"
                path: "/tmp/app"
                primary_channel: "app-dev"
                context:
                  description: "A test app"
                  patterns: ["MVVM"]
            channels: {}
        """)
        p = tmp_path / "projects.yaml"
        p.write_text(y)
        cfg = load_config(str(p))
        assert cfg["PROJECTS"]["app"]["context"]["description"] == "A test app"


# ---------------------------------------------------------------------------
# Env var overrides
# ---------------------------------------------------------------------------


class TestEnvVarOverrides:
    def test_project_path_override(self, yaml_file):
        with patch.dict(os.environ, {"MYAPP_PROJECT_PATH": "/custom/path"}):
            cfg = load_config(yaml_file)
            assert cfg["PROJECTS"]["myapp"]["path"] == "/custom/path"

    def test_bundle_id_override(self, yaml_file):
        with patch.dict(os.environ, {"MYAPP_BUNDLE_ID": "com.override.id"}):
            cfg = load_config(yaml_file)
            assert cfg["PROJECTS"]["myapp"]["bundle_id"] == "com.override.id"

    def test_github_org_env_override(self, yaml_file):
        with patch.dict(os.environ, {"GITHUB_ORG": "env-org"}):
            cfg = load_config(yaml_file)
            assert cfg["GITHUB_ORG"] == "env-org"

    def test_shellack_config_env_var(self, yaml_file):
        with patch.dict(os.environ, {"SHELLACK_CONFIG": yaml_file}):
            # Pass no explicit path — should pick up from env
            cfg = load_config()
            assert "myapp" in cfg["PROJECTS"]


# ---------------------------------------------------------------------------
# Missing config
# ---------------------------------------------------------------------------


class TestMissingConfig:
    def test_raises_file_not_found(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent.yaml")
        with pytest.raises(FileNotFoundError, match="Shellack config not found"):
            load_config(bad_path)

    def test_error_message_includes_path(self, tmp_path):
        bad_path = str(tmp_path / "gone.yaml")
        with pytest.raises(FileNotFoundError, match="gone.yaml"):
            load_config(bad_path)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_get_project_for_channel_dedicated(self):
        """Uses module-level globals loaded from real projects.yaml."""
        # Find any dedicated channel from the live config
        for ch_name, ch in CHANNEL_ROUTING.items():
            if ch.get("mode") == "dedicated":
                result = get_project_for_channel(ch_name)
                assert result is not None
                assert "name" in result
                break

    def test_get_project_for_channel_unknown(self):
        assert get_project_for_channel("nonexistent-channel") is None

    def test_get_project_for_channel_orchestrator_returns_none(self):
        for ch_name, ch in CHANNEL_ROUTING.items():
            if ch.get("mode") == "orchestrator":
                assert get_project_for_channel(ch_name) is None
                break

    def test_get_all_projects_returns_list(self):
        result = get_all_projects()
        assert isinstance(result, list)
        assert len(result) == len(PROJECTS)

    def test_is_orchestrator_channel(self):
        for ch_name, ch in CHANNEL_ROUTING.items():
            if ch.get("mode") == "orchestrator":
                assert is_orchestrator_channel(ch_name) is True
                break

    def test_is_orchestrator_channel_false(self):
        assert is_orchestrator_channel("nonexistent") is False

    def test_is_peer_review_channel(self):
        for ch_name, ch in CHANNEL_ROUTING.items():
            if ch.get("mode") == "peer_review":
                assert is_peer_review_channel(ch_name) is True
                break

    def test_is_peer_review_channel_false(self):
        assert is_peer_review_channel("nonexistent") is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidateConfig:
    def test_warns_on_bad_project_ref(self, yaml_file, monkeypatch):
        import orchestrator_config as oc

        # Inject a channel that references a nonexistent project
        monkeypatch.setitem(
            oc.CHANNEL_ROUTING,
            "ghost-dev",
            {"project": "ghost", "mode": "dedicated", "channel_id": "C999"},
        )
        warnings = validate_config()
        assert any("ghost" in w for w in warnings)

    def test_warns_on_empty_channel_id(self, yaml_file, monkeypatch):
        import orchestrator_config as oc

        monkeypatch.setitem(
            oc.CHANNEL_ROUTING,
            "empty-dev",
            {"project": "myapp", "mode": "dedicated", "channel_id": ""},
        )
        warnings = validate_config()
        assert any("empty-dev" in w for w in warnings)

    def test_no_warnings_on_clean_config(self, yaml_file):
        # The real projects.yaml should be clean
        warnings = validate_config()
        # Filter to only dedicated-channel warnings (orchestrator/review may lack IDs)
        dedicated_warnings = [
            w for w in warnings
            if "unknown project" in w
        ]
        assert dedicated_warnings == []


# ---------------------------------------------------------------------------
# Module-level globals sanity
# ---------------------------------------------------------------------------


class TestModuleLevelExports:
    """Verify the module-level globals are populated and have the right types."""

    def test_projects_is_dict(self):
        assert isinstance(PROJECTS, dict)
        assert len(PROJECTS) > 0

    def test_channel_routing_is_dict(self):
        assert isinstance(CHANNEL_ROUTING, dict)

    def test_global_standards_is_dict(self):
        assert isinstance(GLOBAL_STANDARDS, dict)

    def test_orchestrator_commands_is_dict(self):
        assert isinstance(ORCHESTRATOR_COMMANDS, dict)

    def test_peer_review_config_is_dict(self):
        assert isinstance(PEER_REVIEW_CONFIG, dict)

    def test_github_org_is_string(self):
        assert isinstance(GITHUB_ORG, str)
        assert len(GITHUB_ORG) > 0
