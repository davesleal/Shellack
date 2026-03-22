#!/usr/bin/env python3
"""
Shellack Orchestrator Configuration
Multi-project coordination and peer review system
"""

import os
from typing import Dict, List, Optional

# GitHub org/user — override with GITHUB_ORG env var
_GITHUB_ORG = os.environ.get("GITHUB_ORG", "YOUR_ORG")

# Project Registry
# All projects that Shellack can access.
# Override paths via env vars; see .env.example for all supported variables.
PROJECTS = {
    "dayist": {
        "name": "Dayist",
        "path": os.environ.get(
            "DAYIST_PROJECT_PATH", os.path.expanduser("~/Repos/Dayist")
        ),
        "bundle_id": os.environ.get("DAYIST_BUNDLE_ID", ""),
        "primary_channel": "dayist-dev",
        "language": "swift",
        "platform": "ios",
        "github_repo": f"{_GITHUB_ORG}/Dayist",
    },
    "nova": {
        "name": "NOVA",
        "path": os.environ.get("NOVA_PROJECT_PATH", os.path.expanduser("~/Repos/NOVA")),
        "bundle_id": os.environ.get("NOVA_BUNDLE_ID", None),
        "primary_channel": "nova-dev",
        "language": "swift",
        "platform": "ios",
        "github_repo": f"{_GITHUB_ORG}/NOVA",
    },
    "nudge": {
        "name": "Nudge",
        "path": os.environ.get(
            "NUDGE_PROJECT_PATH", os.path.expanduser("~/Repos/Nudge")
        ),
        "bundle_id": os.environ.get("NUDGE_BUNDLE_ID", None),
        "primary_channel": "nudge-dev",
        "language": "swift",
        "platform": "ios",
        "github_repo": f"{_GITHUB_ORG}/Nudge",
    },
    "slackclaw": {
        "name": "Shellack",
        "path": os.environ.get(
            "SLACKCLAW_PROJECT_PATH", os.path.expanduser("~/Repos/SlackClaw")
        ),
        "bundle_id": None,
        "primary_channel": "slackclaw-dev",
        "language": "python",
        "platform": "server",
        "github_repo": f"{_GITHUB_ORG}/Shellack",
    },
    "tiledock": {
        "name": "TileDock",
        "path": os.environ.get(
            "TILEDOCK_PROJECT_PATH", os.path.expanduser("~/Repos/TileDock")
        ),
        "bundle_id": os.environ.get("TILEDOCK_BUNDLE_ID", ""),
        "primary_channel": "tiledock-dev",
        "language": "swift",
        "platform": "macos",
        "github_repo": f"{_GITHUB_ORG}/TileDock",
    },
    "atmosuniversal": {
        "name": "Atmos",
        "path": os.environ.get(
            "ATMOS_PROJECT_PATH", os.path.expanduser("~/Repos/Atmos")
        ),
        "bundle_id": os.environ.get("ATMOS_BUNDLE_ID", None),
        "primary_channel": "atmos-dev",
        "language": "swift",
        "platform": "macos",
        "github_repo": f"{_GITHUB_ORG}/atmos-universal",
    },
    "sideplane": {
        "name": "SidePlane",
        "path": os.environ.get(
            "SIDEPLANE_PROJECT_PATH", os.path.expanduser("~/Repos/SidePlane")
        ),
        "bundle_id": os.environ.get("SIDEPLANE_BUNDLE_ID", ""),
        "primary_channel": "sideplane-dev",
        "language": "swift",
        "platform": "macos",
        "github_repo": f"{_GITHUB_ORG}/SidePlane",
    },
}

# Channel Routing
CHANNEL_ROUTING = {
    # iOS Project Channels
    "dayist-dev": {
        "project": "dayist",
        "mode": "dedicated",
        "channel_id": "C0AM872QM8E",
    },
    "nova-dev": {
        "project": "nova",
        "mode": "dedicated",
        "channel_id": "",
    },  # channel not yet created
    "nudge-dev": {
        "project": "nudge",
        "mode": "dedicated",
        "channel_id": "",
    },  # channel not yet created
    # macOS Project Channels
    "tiledock-dev": {
        "project": "tiledock",
        "mode": "dedicated",
        "channel_id": "C0AHTQU2CQ2",
    },
    "atmos-dev": {
        "project": "atmosuniversal",
        "mode": "dedicated",
        "channel_id": "C0AMDU1939A",
    },
    "sideplane-dev": {
        "project": "sideplane",
        "mode": "dedicated",
        "channel_id": "C0AM3UT7XL3",
    },
    # Meta
    "slackclaw-dev": {
        "project": "slackclaw",
        "mode": "dedicated",
        "channel_id": "C0AN4JQACKS",
    },
    # Special channels
    "slackclaw-central": {
        "mode": "orchestrator",
        "access": "all_projects",
        "channel_id": "",  # channel not yet created
        "capabilities": [
            "update_claude_md",
            "set_global_rules",
            "cross_project_search",
            "coordinate_changes",
            "sync_standards",
        ],
    },
    "code-review": {
        "mode": "peer_review",
        "access": "all_projects",
        "channel_id": "",  # channel not yet created
        "review_agents": ["code-quality", "security", "performance"],
        "approval_required": True,
        "auto_merge": False,
    },
}

# Global Standards
# These apply across all projects
GLOBAL_STANDARDS = {
    "swift": {
        "style_guide": "Swift API Design Guidelines",
        "conventions": [
            "Use descriptive variable names",
            "Prefer composition over inheritance",
            "Use guard statements for early returns",
            "Avoid force unwrapping unless guaranteed safe",
        ],
        "required_tests": True,
        "min_coverage": 80,
    },
    "python": {
        "style_guide": "PEP 8",
        "conventions": [
            "Use type hints",
            "Docstrings for all public functions",
            "Maximum line length: 100",
            "Use black for formatting",
        ],
        "required_tests": True,
        "min_coverage": 80,
    },
}

# Orchestrator Commands
ORCHESTRATOR_COMMANDS = {
    "update_all_claude_md": {
        "description": "Update CLAUDE.md in all projects",
        "syntax": "@Shellack update all CLAUDE.md: <rule>",
        "example": "@Shellack update all CLAUDE.md: prefer async/await over callbacks",
    },
    "sync_standards": {
        "description": "Sync coding standards between projects",
        "syntax": "@Shellack sync standards from <source> to <target>",
        "example": "@Shellack sync standards from dayist to nova",
    },
    "global_search": {
        "description": "Search across all projects",
        "syntax": "@Shellack search all: <query>",
        "example": "@Shellack search all: deprecated API usage",
    },
    "coordinate_change": {
        "description": "Make coordinated change across projects",
        "syntax": "@Shellack coordinate: <change>",
        "example": "@Shellack coordinate: update to Swift 6 concurrency",
    },
}

# Peer Review Configuration
PEER_REVIEW_CONFIG = {
    "reviewers": {
        "code-quality": {
            "focus": ["readability", "maintainability", "best_practices"],
            "blocking": True,
        },
        "security": {
            "focus": ["vulnerabilities", "data_exposure", "authentication"],
            "blocking": True,
        },
        "performance": {
            "focus": ["memory_leaks", "inefficient_algorithms", "n_plus_one"],
            "blocking": False,  # Advisory only
        },
    },
    "approval_threshold": 2,  # Need 2 approvals minimum
    "auto_merge_on_approval": False,  # Always require human confirmation
    "required_checks": ["tests_passing", "no_merge_conflicts", "ci_passing"],
}


def get_project_for_channel(channel_name: str) -> Optional[Dict]:
    """Get project configuration for a channel"""
    routing = CHANNEL_ROUTING.get(channel_name)
    if not routing:
        return None

    if routing["mode"] == "dedicated":
        project_key = routing["project"]
        return PROJECTS.get(project_key)

    # Orchestrator and peer-review channels have access to all
    return None


def get_all_projects() -> List[Dict]:
    """Get all registered projects"""
    return list(PROJECTS.values())


def is_orchestrator_channel(channel_name: str) -> bool:
    """Check if channel is the orchestrator"""
    routing = CHANNEL_ROUTING.get(channel_name)
    return routing and routing.get("mode") == "orchestrator"


def is_peer_review_channel(channel_name: str) -> bool:
    """Check if channel is for peer review"""
    routing = CHANNEL_ROUTING.get(channel_name)
    return routing and routing.get("mode") == "peer_review"
