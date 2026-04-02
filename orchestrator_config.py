#!/usr/bin/env python3
"""
Shellack Orchestrator Configuration — YAML Loader

Loads all project configuration from projects.yaml (or the path in
SHELLACK_CONFIG env var).  Exports the same module-level names that the
rest of the codebase expects:

    PROJECTS, CHANNEL_ROUTING, GLOBAL_STANDARDS,
    ORCHESTRATOR_COMMANDS, PEER_REVIEW_CONFIG, GITHUB_ORG

Plus helper functions:
    get_project_for_channel, get_all_projects,
    is_orchestrator_channel, is_peer_review_channel, validate_config
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_KNOWN_TOP_LEVEL_KEYS = {
    "github_org", "projects", "channels", "standards",
    "orchestrator_commands", "peer_review",
}

# ---------------------------------------------------------------------------
# Internal loader
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "projects.yaml")


def _load_yaml(path: Optional[str] = None) -> dict:
    """Load and return raw YAML config dict."""
    config_path = path or os.environ.get("SHELLACK_CONFIG", _DEFAULT_CONFIG_PATH)
    config_path = os.path.expanduser(str(config_path))

    if not os.path.isfile(config_path):
        raise FileNotFoundError(
            f"Shellack config not found at {config_path}. "
            "Copy projects.example.yaml to projects.yaml and fill in your details:\n"
            "  cp projects.example.yaml projects.yaml"
        )

    with open(config_path, "r") as f:
        return yaml.safe_load(f) or {}


def _build_projects(raw: dict, github_org: str) -> Dict[str, dict]:
    """Build the PROJECTS dict from raw YAML, applying env var overrides."""
    projects: Dict[str, dict] = {}
    for key, proj in (raw.get("projects") or {}).items():
        env_key = key.upper()

        path = os.environ.get(
            f"{env_key}_PROJECT_PATH",
            proj.get("path", ""),
        )
        path = os.path.expanduser(path)

        bundle_id_default = proj.get("bundle_id")
        bundle_id = os.environ.get(f"{env_key}_BUNDLE_ID", bundle_id_default)

        github_repo = proj.get("github_repo", f"{github_org}/{key}")

        projects[key] = {
            "name": proj.get("name", key),
            "path": path,
            "bundle_id": bundle_id,
            "primary_channel": proj.get("primary_channel", ""),
            "language": proj.get("language", ""),
            "platform": proj.get("platform", ""),
            "github_repo": github_repo,
        }
        # Carry through optional context block for agent prompts
        if "context" in proj:
            projects[key]["context"] = proj["context"]
        # Token Cart feature flags and model overrides
        if "features" in proj:
            projects[key]["features"] = proj["features"]
        else:
            projects[key]["features"] = {}
        if "team" in proj:
            projects[key]["team"] = proj["team"]
        else:
            projects[key]["team"] = {}

    return projects


def _build_channel_routing(raw: dict) -> Dict[str, dict]:
    """Build CHANNEL_ROUTING from raw YAML channels section."""
    routing: Dict[str, dict] = {}
    for name, ch in (raw.get("channels") or {}).items():
        entry: dict = dict(ch)  # shallow copy
        routing[name] = entry
    return routing


def load_config(path: Optional[str] = None) -> dict:
    """Load config from YAML and return a dict of all top-level exports.

    This is the main entry point; the module-level globals are populated
    by calling this at import time.
    """
    raw = _load_yaml(path)

    # Warn on empty config
    if not raw.get("projects"):
        logger.warning(
            "projects.yaml has no 'projects' section — bot will have no project agents"
        )

    # Warn on unrecognized top-level keys (likely typos)
    unknown = set(raw.keys()) - _KNOWN_TOP_LEVEL_KEYS
    if unknown:
        logger.warning(
            f"projects.yaml has unrecognized top-level keys: {unknown} — "
            "these will be ignored (check for typos)"
        )

    github_org = os.environ.get("GITHUB_ORG", raw.get("github_org", "YOUR_ORG"))
    projects = _build_projects(raw, github_org)
    channel_routing = _build_channel_routing(raw)
    global_standards = raw.get("standards") or {}
    orchestrator_commands = raw.get("orchestrator_commands") or {}
    peer_review_config = raw.get("peer_review") or {}

    return {
        "GITHUB_ORG": github_org,
        "PROJECTS": projects,
        "CHANNEL_ROUTING": channel_routing,
        "GLOBAL_STANDARDS": global_standards,
        "ORCHESTRATOR_COMMANDS": orchestrator_commands,
        "PEER_REVIEW_CONFIG": peer_review_config,
    }


# ---------------------------------------------------------------------------
# Module-level exports — populated at import time
# ---------------------------------------------------------------------------

_config = load_config()

GITHUB_ORG: str = _config["GITHUB_ORG"]
PROJECTS: Dict[str, dict] = _config["PROJECTS"]
CHANNEL_ROUTING: Dict[str, dict] = _config["CHANNEL_ROUTING"]
GLOBAL_STANDARDS: Dict[str, dict] = _config["GLOBAL_STANDARDS"]
ORCHESTRATOR_COMMANDS: Dict[str, dict] = _config["ORCHESTRATOR_COMMANDS"]
PEER_REVIEW_CONFIG: Dict[str, dict] = _config["PEER_REVIEW_CONFIG"]


# ---------------------------------------------------------------------------
# Helper functions — same signatures as the original hardcoded version
# ---------------------------------------------------------------------------


def get_project_for_channel(channel_name: str) -> Optional[Dict]:
    """Get project configuration for a channel."""
    routing = CHANNEL_ROUTING.get(channel_name)
    if not routing:
        return None

    if routing.get("mode") == "dedicated":
        project_key = routing.get("project")
        return PROJECTS.get(project_key)

    # Orchestrator and peer-review channels have access to all
    return None


def get_all_projects() -> List[Dict]:
    """Get all registered projects."""
    return list(PROJECTS.values())


def is_orchestrator_channel(channel_name: str) -> bool:
    """Check if channel is the orchestrator."""
    routing = CHANNEL_ROUTING.get(channel_name)
    return bool(routing and routing.get("mode") == "orchestrator")


def is_peer_review_channel(channel_name: str) -> bool:
    """Check if channel is for peer review."""
    routing = CHANNEL_ROUTING.get(channel_name)
    return bool(routing and routing.get("mode") == "peer_review")


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_config() -> List[str]:
    """Return a list of warning strings about the current config.

    Checks:
    - Channel routing references a project key that doesn't exist in PROJECTS
    - Dedicated channels with empty channel_id
    """
    warnings: List[str] = []

    for ch_name, ch in CHANNEL_ROUTING.items():
        # Check project references
        if ch.get("mode") == "dedicated":
            proj_key = ch.get("project", "")
            if proj_key and proj_key not in PROJECTS:
                warnings.append(
                    f"Channel '{ch_name}' references unknown project '{proj_key}'"
                )

        # Check empty channel_ids on dedicated channels
        if ch.get("mode") == "dedicated" and not ch.get("channel_id"):
            warnings.append(
                f"Channel '{ch_name}' has no channel_id set"
            )

    return warnings
