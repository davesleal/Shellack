# Genericize Shellack for Open-Source Forks — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the repo forkable with zero personal project leakage — all project-specific config in a gitignored `projects.yaml`, tracked files contain only generic bot infrastructure, pre-commit hook blocks secret leaks.

**Architecture:** `orchestrator_config.py` becomes a thin YAML loader. `PROJECT_KNOWLEDGE` in `project_agent.py` is replaced by the `context` key in `projects.yaml`. All docs, tests, and scripts use generic placeholder names.

**Tech Stack:** Python, PyYAML, shell (pre-commit hook)

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `projects.example.yaml` | Example config with full commented schema, two placeholder projects |
| Create | `projects.yaml` | User's real config (gitignored) — copied from example |
| Create | `hooks/pre-commit` | Secret scanning shell script |
| Create | `tests/test_config_loader.py` | Tests for the YAML loader |
| Rewrite | `orchestrator_config.py` | Thin YAML loader, env var overrides, startup validation |
| Modify | `agents/project_agent.py` | Read context from config instead of `PROJECT_KNOWLEDGE` |
| Modify | `tools/triage.py` | Fix `_DEFAULT` stale import-time evaluation |
| Modify | `tools/slack_bridge.py` | Fallback channel from env, not hardcoded |
| Modify | `bot_unified.py` | Startup validation, strip project references from comments |
| Modify | `.gitignore` | Add `projects.yaml` |
| Modify | `requirements.txt` | Add `PyYAML` |
| Modify | All test files | Generic fixture names (`alpha`, `beta`, `C_ALPHA`, etc.) |
| Modify | All doc/script files | Strip personal project names, use generic placeholders |

---

### Task 1: Add PyYAML dependency

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: Add PyYAML to requirements.txt**

Add `PyYAML>=6.0` after the existing `PyJWT` line:

```
PyYAML>=6.0
```

- [ ] **Step 2: Verify it's already installed**

Run: `source venv/bin/activate && python -c "import yaml; print(yaml.__version__)"`
Expected: version number (already installed in venv)

- [ ] **Step 3: Commit**

```bash
git add requirements.txt
git commit -m "chore: add PyYAML to requirements.txt"
```

---

### Task 2: Create `projects.example.yaml` and gitignore `projects.yaml`

**Files:**
- Create: `projects.example.yaml`
- Modify: `.gitignore`

- [ ] **Step 1: Write `projects.example.yaml`**

```yaml
# Shellack Project Configuration
# Copy this file to projects.yaml and fill in your details:
#   cp projects.example.yaml projects.yaml
#
# projects.yaml is gitignored — your project names, paths, and channel IDs
# never leave your machine.

# Your GitHub org or username — used for issue creation and repo links
github_org: "your-org"

# ─── Projects ───────────────────────────────────────────────────────────
# Each key is a short slug used internally (e.g., "webapp", "mobile").
# All fields except 'name' and 'primary_channel' are optional.
projects:
  webapp:
    name: "Web App"                         # display name in Slack messages
    path: "~/Repos/WebApp"                  # local checkout (overridable via WEBAPP_PROJECT_PATH env var)
    bundle_id: ""                           # optional — App Store Connect bundle ID for review monitoring
    language: python                        # used for coding conventions in agent prompt
    platform: web                           # ios | macos | web | server | visionos
    github_repo: "your-org/WebApp"          # owner/repo for issue creation
    primary_channel: "webapp-dev"           # Slack channel name (without #)
    context:                                # optional — enriches the agent's system prompt
      description: "Next.js analytics dashboard"
      purpose: "Internal tool for visualizing product metrics"
      tech: "Next.js 15, PostgreSQL, Tailwind CSS"
      patterns:
        - "Server components for data fetching"
        - "Drizzle ORM for database queries"
      watch_out:
        - "Don't expose raw SQL in API routes"
        - "Always validate user input at API boundaries"

  mobile:
    name: "Mobile App"
    path: "~/Repos/MobileApp"
    bundle_id: "com.example.mobile"
    language: swift
    platform: ios
    github_repo: "your-org/MobileApp"
    primary_channel: "mobile-dev"
    context:
      description: "iOS companion app for the web dashboard"
      purpose: "View metrics and receive push notifications on the go"
      tech: "SwiftUI, SwiftData, CloudKit"
      patterns:
        - "MVVM with @Observable"
        - "SwiftData for local persistence"
      watch_out:
        - "Never force-unwrap optionals from network responses"
        - "HealthKit queries must be async — don't block main thread"

# ─── Channel Routing ────────────────────────────────────────────────────
# Maps Slack channel names to projects or special modes.
# channel_id: find this in Slack → channel settings → copy channel ID
channels:
  webapp-dev:
    project: webapp                         # must match a key in 'projects' above
    mode: dedicated
    channel_id: ""                          # paste your Slack channel ID here
  mobile-dev:
    project: mobile
    mode: dedicated
    channel_id: ""
  # Orchestrator — cross-project commands (update all CLAUDE.md, sync standards, etc.)
  central:
    mode: orchestrator
    access: all_projects
    channel_id: ""
  # Peer review — autonomous code review with specialized agents
  code-review:
    mode: peer_review
    access: all_projects
    channel_id: ""
    review_agents: ["code-quality", "security", "performance"]
    approval_required: true
    auto_merge: false

# ─── Global Standards ───────────────────────────────────────────────────
# Coding conventions applied to all projects using that language.
standards:
  swift:
    style_guide: "Swift API Design Guidelines"
    conventions:
      - "Use descriptive variable names"
      - "Prefer composition over inheritance"
      - "Use guard statements for early returns"
      - "Avoid force unwrapping unless guaranteed safe"
    required_tests: true
    min_coverage: 80
  python:
    style_guide: "PEP 8"
    conventions:
      - "Use type hints"
      - "Docstrings for all public functions"
      - "Maximum line length: 100"
      - "Use black for formatting"
    required_tests: true
    min_coverage: 80
  javascript:
    style_guide: "Airbnb JavaScript Style Guide"
    conventions:
      - "Use const by default, let when needed"
      - "Prefer arrow functions for callbacks"
      - "Use async/await over .then() chains"
    required_tests: true
    min_coverage: 70

# ─── Orchestrator Commands ──────────────────────────────────────────────
# Available in the orchestrator channel. Examples auto-adapt to your project names.
orchestrator_commands:
  update_all_claude_md:
    description: "Update CLAUDE.md in all projects"
    syntax: "@Shellack update all CLAUDE.md: <rule>"
    example: "@Shellack update all CLAUDE.md: prefer async/await over callbacks"
  sync_standards:
    description: "Sync coding standards between projects"
    syntax: "@Shellack sync standards from <source> to <target>"
    example: "@Shellack sync standards from webapp to mobile"
  global_search:
    description: "Search across all projects"
    syntax: "@Shellack search all: <query>"
    example: "@Shellack search all: deprecated API usage"
  coordinate_change:
    description: "Make coordinated change across projects"
    syntax: "@Shellack coordinate: <change>"
    example: "@Shellack coordinate: update linting rules"

# ─── Peer Review ────────────────────────────────────────────────────────
peer_review:
  reviewers:
    code-quality:
      focus: ["readability", "maintainability", "best_practices"]
      blocking: true
    security:
      focus: ["vulnerabilities", "data_exposure", "authentication"]
      blocking: true
    performance:
      focus: ["memory_leaks", "inefficient_algorithms", "n_plus_one"]
      blocking: false    # advisory only
  approval_threshold: 2
  auto_merge_on_approval: false
  required_checks: ["tests_passing", "no_merge_conflicts"]
```

- [ ] **Step 2: Add `projects.yaml` to `.gitignore`**

Add after the existing `.env` line at the top of `.gitignore`:

```
projects.yaml
```

- [ ] **Step 3: Copy example to create local projects.yaml**

```bash
cp projects.example.yaml projects.yaml
```

Then verify it's ignored:

```bash
git status --short projects.yaml
```

Expected: no output (file is ignored)

- [ ] **Step 4: Commit**

```bash
git add projects.example.yaml .gitignore
git commit -m "feat: add projects.example.yaml and gitignore projects.yaml"
```

---

### Task 3: Rewrite `orchestrator_config.py` as YAML loader

**Files:**
- Rewrite: `orchestrator_config.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Write failing tests for the config loader**

Create `tests/test_config_loader.py`:

```python
"""Tests for orchestrator_config YAML loader."""
import os
import tempfile
import textwrap
from unittest.mock import patch

import pytest
import yaml


MINIMAL_CONFIG = {
    "github_org": "test-org",
    "projects": {
        "alpha": {
            "name": "Alpha",
            "path": "~/Repos/Alpha",
            "language": "python",
            "platform": "server",
            "github_repo": "test-org/Alpha",
            "primary_channel": "alpha-dev",
        }
    },
    "channels": {
        "alpha-dev": {
            "project": "alpha",
            "mode": "dedicated",
            "channel_id": "C_ALPHA",
        }
    },
}


@pytest.fixture
def config_file(tmp_path):
    """Write a minimal projects.yaml and return its path."""
    p = tmp_path / "projects.yaml"
    p.write_text(yaml.dump(MINIMAL_CONFIG))
    return str(p)


def _load_with_path(config_path):
    """Import orchestrator_config with a custom config path."""
    import importlib
    with patch.dict(os.environ, {"SHELLACK_CONFIG": config_path}):
        import orchestrator_config
        importlib.reload(orchestrator_config)
        return orchestrator_config


def test_loads_projects_from_yaml(config_file):
    mod = _load_with_path(config_file)
    assert "alpha" in mod.PROJECTS
    assert mod.PROJECTS["alpha"]["name"] == "Alpha"


def test_loads_channels_from_yaml(config_file):
    mod = _load_with_path(config_file)
    assert "alpha-dev" in mod.CHANNEL_ROUTING
    assert mod.CHANNEL_ROUTING["alpha-dev"]["project"] == "alpha"


def test_github_org_from_yaml(config_file):
    mod = _load_with_path(config_file)
    assert mod.GITHUB_ORG == "test-org"


def test_env_var_overrides_path(config_file):
    mod = _load_with_path(config_file)
    with patch.dict(os.environ, {"ALPHA_PROJECT_PATH": "/custom/path"}):
        importlib.reload(mod) if hasattr(mod, '__loader__') else None
        # Re-import to pick up env override
        import importlib as il
        with patch.dict(os.environ, {"SHELLACK_CONFIG": config_file,
                                      "ALPHA_PROJECT_PATH": "/custom/path"}):
            il.reload(mod)
            assert mod.PROJECTS["alpha"]["path"] == "/custom/path"


def test_missing_config_raises_with_helpful_message():
    with patch.dict(os.environ, {"SHELLACK_CONFIG": "/nonexistent/projects.yaml"}):
        import importlib
        import orchestrator_config
        with pytest.raises(FileNotFoundError, match="projects.yaml"):
            importlib.reload(orchestrator_config)


def test_get_project_for_channel(config_file):
    mod = _load_with_path(config_file)
    proj = mod.get_project_for_channel("alpha-dev")
    assert proj is not None
    assert proj["name"] == "Alpha"


def test_get_project_for_unknown_channel(config_file):
    mod = _load_with_path(config_file)
    assert mod.get_project_for_channel("nonexistent") is None


def test_empty_channel_id_is_valid(tmp_path):
    """Channels with empty channel_id should load without error."""
    cfg = {
        "projects": {"beta": {"name": "Beta", "primary_channel": "beta-dev"}},
        "channels": {"beta-dev": {"project": "beta", "mode": "dedicated", "channel_id": ""}},
    }
    p = tmp_path / "projects.yaml"
    p.write_text(yaml.dump(cfg))
    mod = _load_with_path(str(p))
    assert mod.CHANNEL_ROUTING["beta-dev"]["channel_id"] == ""


def test_validate_channels_warns_on_bad_project(config_file, capsys):
    """validate_config should warn if a channel references a nonexistent project."""
    cfg = dict(MINIMAL_CONFIG)
    cfg["channels"] = {"bad-dev": {"project": "nonexistent", "mode": "dedicated", "channel_id": ""}}
    import tempfile as tf
    with tf.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(cfg, f)
        f.flush()
        mod = _load_with_path(f.name)
        warnings = mod.validate_config()
        assert any("nonexistent" in w for w in warnings)
    os.unlink(f.name)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `source venv/bin/activate && python -m pytest tests/test_config_loader.py -v 2>&1 | tail -20`
Expected: FAIL (orchestrator_config doesn't load YAML yet)

- [ ] **Step 3: Rewrite `orchestrator_config.py`**

Replace the entire contents of `orchestrator_config.py` with:

```python
#!/usr/bin/env python3
"""
Shellack Orchestrator Configuration
Loads project definitions, channel routing, and standards from projects.yaml.
"""

import logging
import os
import sys
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.environ.get(
    "SHELLACK_CONFIG",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "projects.yaml"),
)


def _load_config() -> dict:
    """Load and return the projects.yaml config, applying env var overrides."""
    if not os.path.exists(_CONFIG_PATH):
        raise FileNotFoundError(
            f"projects.yaml not found at {_CONFIG_PATH}\n"
            "Copy the example and fill in your details:\n"
            "  cp projects.example.yaml projects.yaml"
        )
    with open(_CONFIG_PATH) as f:
        cfg = yaml.safe_load(f) or {}

    # Apply env var overrides for project paths and bundle IDs
    for key, project in cfg.get("projects", {}).items():
        env_prefix = key.upper()
        path_override = os.environ.get(f"{env_prefix}_PROJECT_PATH")
        if path_override:
            project["path"] = path_override
        bundle_override = os.environ.get(f"{env_prefix}_BUNDLE_ID")
        if bundle_override:
            project["bundle_id"] = bundle_override
        # Expand ~ in paths
        if "path" in project:
            project["path"] = os.path.expanduser(project["path"])

    return cfg


_cfg = _load_config()

GITHUB_ORG: str = _cfg.get("github_org", "your-org")
PROJECTS: Dict[str, dict] = _cfg.get("projects", {})
CHANNEL_ROUTING: Dict[str, dict] = _cfg.get("channels", {})
GLOBAL_STANDARDS: Dict[str, dict] = _cfg.get("standards", {})
ORCHESTRATOR_COMMANDS: Dict[str, dict] = _cfg.get("orchestrator_commands", {})
PEER_REVIEW_CONFIG: dict = _cfg.get("peer_review", {})


def validate_config() -> List[str]:
    """Validate config consistency. Returns list of warning strings."""
    warnings = []
    for ch_name, routing in CHANNEL_ROUTING.items():
        if routing.get("mode") == "dedicated":
            proj_key = routing.get("project", "")
            if proj_key not in PROJECTS:
                warnings.append(
                    f"Channel '{ch_name}' references project '{proj_key}' "
                    f"which is not defined in projects"
                )
        if not routing.get("channel_id"):
            logger.info(f"Channel '{ch_name}' has no channel_id — will not be pre-warmed")
    return warnings


def get_project_for_channel(channel_name: str) -> Optional[Dict]:
    """Get project configuration for a channel."""
    routing = CHANNEL_ROUTING.get(channel_name)
    if not routing:
        return None
    if routing.get("mode") == "dedicated":
        project_key = routing.get("project", "")
        return PROJECTS.get(project_key)
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
```

- [ ] **Step 4: Create your local `projects.yaml` with your real project data**

Copy `projects.example.yaml` to `projects.yaml` and fill in your actual project names, paths, and channel IDs. This file is gitignored.

- [ ] **Step 5: Run config loader tests**

Run: `source venv/bin/activate && python -m pytest tests/test_config_loader.py -v`
Expected: all pass

- [ ] **Step 6: Run full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q`
Expected: all pass (existing tests still work because `orchestrator_config` exports the same names)

- [ ] **Step 7: Commit**

```bash
git add orchestrator_config.py tests/test_config_loader.py
git commit -m "feat: rewrite orchestrator_config as YAML loader

Reads projects, channels, standards from projects.yaml (gitignored).
Env var overrides for paths and bundle IDs. Startup validation with
clear error when config is missing."
```

---

### Task 4: Remove `PROJECT_KNOWLEDGE` from `project_agent.py` — read from config

**Files:**
- Modify: `agents/project_agent.py`
- Modify: `tests/test_project_agent.py`

- [ ] **Step 1: Update test to use config-sourced context**

In `tests/test_project_agent.py`, update the project config fixture to include a `context` key instead of relying on `PROJECT_KNOWLEDGE`:

```python
FAKE_PROJECT = {
    "name": "Alpha",
    "path": "/tmp/alpha",
    "language": "python",
    "platform": "server",
    "github_repo": "test-org/Alpha",
    "primary_channel": "alpha-dev",
    "context": {
        "description": "Test project for unit tests",
        "purpose": "Validate agent behavior",
        "tech": "Python, pytest",
        "patterns": ["TDD workflow"],
        "watch_out": ["Don't mock too broadly"],
    },
}
```

Update the `project_key` from `"dayist"` to `"alpha"` in all test calls.

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_project_agent.py -v`
Expected: tests still pass (PROJECT_KNOWLEDGE has a fallback) or fail if key not found

- [ ] **Step 3: Modify `project_agent.py` to read context from config**

Remove the entire `PROJECT_KNOWLEDGE` dict (lines 45-125). Update `_build_system_prompt` to read from `self.project.get("context", {})` instead of `PROJECT_KNOWLEDGE.get(self.project_key, {})`:

Replace:
```python
knowledge = PROJECT_KNOWLEDGE.get(self.project_key, {})
```

With:
```python
knowledge = self.project.get("context", {})
```

This is the only line that references `PROJECT_KNOWLEDGE`. After changing it, delete the entire `PROJECT_KNOWLEDGE` dict.

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_project_agent.py -v`
Expected: all pass

- [ ] **Step 5: Run full suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add agents/project_agent.py tests/test_project_agent.py
git commit -m "refactor: remove PROJECT_KNOWLEDGE — agent reads context from projects.yaml"
```

---

### Task 5: Fix `_DEFAULT` stale evaluation in `triage.py`

**Files:**
- Modify: `tools/triage.py`
- Modify: `tests/test_triage.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_triage.py`:

```python
def test_default_fallback_uses_current_session_model(monkeypatch):
    """_DEFAULT must reflect SESSION_MODEL at call time, not import time."""
    monkeypatch.setenv("SESSION_MODEL", "claude-opus-4-6")
    # Force re-evaluation by calling classify with a mock that raises
    with patch("tools.triage.Anthropic") as MockClient:
        MockClient.return_value.messages.create.side_effect = RuntimeError("boom")
        result = classify("anything")
    assert result.model == "claude-opus-4-6"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `source venv/bin/activate && python -m pytest tests/test_triage.py::test_default_fallback_uses_current_session_model -v`
Expected: FAIL — `_DEFAULT.model` was set at import time

- [ ] **Step 3: Fix `triage.py`**

Replace the module-level `_DEFAULT` with a lazy fallback inside `classify()`:

```python
# Remove this line:
_DEFAULT = TriageResult(tier="moderate", model=_configured_model(), reason="triage unavailable")

# In the except block of classify(), replace `return _DEFAULT` with:
        return TriageResult(
            tier="moderate",
            model=_configured_model(),
            reason="triage unavailable",
        )
```

- [ ] **Step 4: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_triage.py -v`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tools/triage.py tests/test_triage.py
git commit -m "fix: triage _DEFAULT now evaluates SESSION_MODEL at call time, not import"
```

---

### Task 6: Add ThinkingIndicator fallback test

**Files:**
- Modify: `tests/test_thinking_indicator.py`

- [ ] **Step 1: Add fallback tests**

Append to `tests/test_thinking_indicator.py`:

```python
def test_done_fallback_posts_response_separately_on_update_failure():
    """If chat_update fails with response text, fallback posts response as separate message."""
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.0"}
    # First chat_update (in _cycle) succeeds; done()'s chat_update fails
    client.chat_update.side_effect = [None, Exception("update failed"), None]

    ind = ThinkingIndicator(client, "C1", "T1")
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    ind.done(response="The answer is 42")

    # Should have tried to post response separately
    post_calls = [c for c in client.chat_postMessage.call_args_list
                  if c.kwargs.get("text") == "The answer is 42"]
    assert len(post_calls) == 1


def test_done_total_failure_does_not_crash():
    """If everything fails, done() must not raise."""
    client = MagicMock()
    client.chat_postMessage.return_value = {"ts": "1.0"}
    client.chat_update.side_effect = Exception("total failure")
    client.chat_postMessage.side_effect = [{"ts": "1.0"}, Exception("post also fails")]

    ind = ThinkingIndicator(client, "C1", "T1")
    ind._ts = "1.0"
    ind._start = time.monotonic() - 5
    ind._stop = threading.Event()
    ind._stop.set()
    ind._bg = None

    # Must not raise
    ind.done(response="some text")
```

- [ ] **Step 2: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_thinking_indicator.py -v`
Expected: all pass (the fallback code already exists, we're just proving it works)

- [ ] **Step 3: Commit**

```bash
git add tests/test_thinking_indicator.py
git commit -m "test: add ThinkingIndicator fallback coverage for done() failure paths"
```

---

### Task 7: Create pre-commit secret scanning hook

**Files:**
- Create: `hooks/pre-commit`

- [ ] **Step 1: Create the hooks directory and script**

```bash
#!/usr/bin/env bash
# Pre-commit hook: block commits containing secrets or credentials.
# Setup: git config core.hooksPath hooks
set -euo pipefail

PATTERNS=(
    'xoxb-[a-zA-Z0-9]'             # Slack bot token
    'xoxp-[a-zA-Z0-9]'             # Slack user token
    'xoxs-[a-zA-Z0-9]'             # Slack session token
    'xoxa-[a-zA-Z0-9]'             # Slack app token
    'sk-ant-[a-zA-Z0-9]'           # Anthropic API key
    'sk-live[a-zA-Z0-9]'           # Stripe live key
    'AKIA[0-9A-Z]{16}'             # AWS access key ID
    '-----BEGIN.*PRIVATE KEY'       # Private keys
    'AIza[0-9A-Za-z_-]{35}'        # Google API key
    'ghp_[0-9a-zA-Z]{36}'          # GitHub personal access token
    'ghs_[0-9a-zA-Z]{36}'          # GitHub server token
)

# Build combined regex
COMBINED=""
for p in "${PATTERNS[@]}"; do
    if [ -n "$COMBINED" ]; then
        COMBINED="$COMBINED|$p"
    else
        COMBINED="$p"
    fi
done

# Get staged files (skip binary, skip excluded paths)
STAGED=$(git diff --cached --name-only --diff-filter=ACMR)
if [ -z "$STAGED" ]; then
    exit 0
fi

FAILED=0
while IFS= read -r file; do
    # Skip exclusions
    case "$file" in
        *.example*|hooks/pre-commit) continue ;;
        docs/superpowers/specs/*|docs/superpowers/plans/*) continue ;;
    esac

    # Skip binary files
    if file --brief --mime "$file" 2>/dev/null | grep -q "charset=binary"; then
        continue
    fi

    # Scan for secrets
    MATCHES=$(git diff --cached -U0 -- "$file" | grep -nE "^\+" | grep -E "$COMBINED" || true)
    if [ -n "$MATCHES" ]; then
        echo "🚨 Potential secret in: $file"
        echo "$MATCHES"
        echo ""
        FAILED=1
    fi
done <<< "$STAGED"

if [ "$FAILED" -eq 1 ]; then
    echo "❌ Commit blocked — secrets detected in staged files."
    echo "   If this is a false positive (e.g., documentation), use:"
    echo "   git commit --no-verify"
    exit 1
fi

exit 0
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x hooks/pre-commit
```

- [ ] **Step 3: Configure git to use the hooks directory**

```bash
git config core.hooksPath hooks
```

- [ ] **Step 4: Test the hook**

Create a temp file with a fake secret, stage it, try to commit:

```bash
echo "SLACK_BOT_TOKEN=xoxb-fake-token-here" > /tmp/test_secret.txt
cp /tmp/test_secret.txt test_secret_temp.txt
git add test_secret_temp.txt
git commit -m "test" 2>&1 || true
git reset HEAD test_secret_temp.txt
rm test_secret_temp.txt
```

Expected: commit blocked with "Potential secret" message

- [ ] **Step 5: Commit the hook**

```bash
git add hooks/pre-commit
git commit -m "feat: add pre-commit hook for secret scanning

Scans staged files for Slack tokens, API keys, AWS credentials,
private keys, and GitHub tokens. Zero dependencies — pure bash."
```

---

### Task 8: Strip personal references from `tools/slack_bridge.py`

**Files:**
- Modify: `tools/slack_bridge.py`
- Modify: `tests/test_slack_bridge.py`

- [ ] **Step 1: Fix fallback channel ID**

In `tools/slack_bridge.py`, replace the hardcoded fallback:

```python
# Replace:
_FALLBACK_CHANNEL_ID = "C0AMEEP7EFL"  # #claude-code

# With:
_FALLBACK_CHANNEL_ID = os.environ.get("FALLBACK_CHANNEL_ID", "")
```

- [ ] **Step 2: Update test fixtures**

In `tests/test_slack_bridge.py`, replace all project-specific references:
- `"slackclaw"` → `"alpha"`
- `"Shellack"` → `"Alpha"`
- `"YOUR_ORG/Shellack"` → `"test-org/Alpha"`
- `"C0AMEEP7EFL"` → `"C_FALLBACK"` (and set env var in tests)
- Channel configs: use `"alpha-dev"` with `"C_ALPHA"`

- [ ] **Step 3: Run tests**

Run: `source venv/bin/activate && python -m pytest tests/test_slack_bridge.py -v`
Expected: all pass

- [ ] **Step 4: Commit**

```bash
git add tools/slack_bridge.py tests/test_slack_bridge.py
git commit -m "refactor: remove hardcoded channel IDs from slack_bridge, genericize tests"
```

---

### Task 9: Genericize all remaining test fixtures

**Files:**
- Modify: `tests/test_github_client.py`
- Modify: `tests/test_staged_peer_review.py`
- Modify: `tests/test_bot_run_trigger.py`
- Modify: `tests/test_bot_plugin_commands.py`
- Modify: `tests/test_onboarding.py`
- Modify: `tests/test_bot_config_commands.py`
- Modify: `tests/test_usage_integration.py`
- Modify: `tests/test_agent_factory.py`
- Modify: `tests/test_lifecycle.py`

- [ ] **Step 1: Replace project-specific names across all test files**

Apply these substitutions in every test file:

| Old | New |
|-----|-----|
| `"dayist"` | `"alpha"` |
| `"Dayist"` | `"Alpha"` |
| `"DayistAgent"` | `"AlphaAgent"` |
| `"dayist-dev"` | `"alpha-dev"` |
| `"C0AM872QM8E"` | `"C_ALPHA"` |
| `"tiledock"` | `"beta"` |
| `"TileDock"` | `"Beta"` |
| `"tiledock-dev"` | `"beta-dev"` |
| `"C0AHTQU2CQ2"` | `"C_BETA"` |
| `"slackclaw-dev"` | `"alpha-dev"` (or `"shellack-dev"` where it refers to the bot's own channel) |
| `"slackclaw"` | `"shellack"` (as project key) |
| `"YOUR_ORG/Dayist"` | `"test-org/Alpha"` |
| `"YOUR_ORG/Shellack"` | `"test-org/Shellack"` |
| `project_name="Dayist"` | `project_name="Alpha"` |
| `project_key="dayist"` | `project_key="alpha"` |
| `"C_DAYIST"` | `"C_ALPHA"` |
| `[tiledock-review]` | `[beta-review]` |

- [ ] **Step 2: Run full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 3: Commit**

```bash
git add tests/
git commit -m "refactor: genericize all test fixtures — no project-specific names"
```

---

### Task 10: Strip personal references from docs and scripts

**Files:**
- Modify: `CLAUDE.md`
- Modify: `ARCHITECTURE.md`
- Modify: `STATE.md`
- Modify: `README.md`
- Modify: `SETUP_GUIDE.md`
- Modify: `HYBRID_APPROACH.md`
- Modify: `docs/PROJECT_DESCRIPTIONS.md`
- Modify: `docs/JOURNAL.md`
- Modify: `bot_unified.py` (docstring only)
- Modify: `bot.py`, `bot_enhanced.py`, `monitor_only.py` (legacy files)
- Modify: `claude-slack` (wrapper script)
- Modify: `setup.sh`
- Modify: `.env.example`

- [ ] **Step 1: Clean `CLAUDE.md`**

Remove the project table entirely. Keep only the generic Shellack bot operating instructions (peer review protocol, journal standards, completion checklist, channel visibility rules, Claude-Slack bridge docs). Replace any remaining channel-specific examples with generic ones (`#project-a-dev`, `@Shellack sync standards from projectA to projectB`).

- [ ] **Step 2: Clean `ARCHITECTURE.md`**

Replace project-specific channel names with generic ones:
- `#dayist-dev → Dayist project` → `#<project>-dev → Project agent`
- `#slackclaw-central` → `#central`
- Example commands: use `projectA`, `projectB`

- [ ] **Step 3: Reset `STATE.md` to a clean template**

Replace with a generic template:

```markdown
# Shellack Current State
**Last Updated:** YYYY-MM-DD
**Status:** [status]

## Running
- Start: `source venv/bin/activate && python bot_unified.py`
- Config: `projects.yaml` (see `projects.example.yaml`)

## Configured Channels
Loaded from `projects.yaml` at startup.

## Open Items
- [ ] ...

## How to Resume
\`\`\`bash
cd /path/to/shellack && source venv/bin/activate && python bot_unified.py
venv/bin/pytest -q
\`\`\`
```

- [ ] **Step 4: Clean `README.md`**

Replace `DAYIST_PROJECT_PATH` and `TILEDOCK_PROJECT_PATH` with generic `PROJECT_NAME_PROJECT_PATH`. Ensure the clone URL uses generic org.

- [ ] **Step 5: Clean `SETUP_GUIDE.md`**

Replace all `dayist` references with `<your-project>`, `DAYIST_PROJECT_PATH` with `<PROJECT>_PROJECT_PATH`, bundle IDs with `com.example.yourapp`, channel names with `#<project>-dev`.

- [ ] **Step 6: Clean `HYBRID_APPROACH.md`**

Replace `dayist-dev` with `project-dev`, `com.example.Dayist` with `com.example.yourapp`, channel variants with generic names.

- [ ] **Step 7: Clean `docs/PROJECT_DESCRIPTIONS.md`**

Convert to a template document showing the format with placeholder projects. Remove all real project entries.

- [ ] **Step 8: Clean `docs/JOURNAL.md`**

In the "Multi-Project Support" section (lines 41-50), replace project names with generic descriptions. Keep the dated structure but strip identifiers.

- [ ] **Step 9: Clean `bot_unified.py` docstring**

Replace lines 6-9:
```python
"""
Shellack Unified Bot
Modular architecture with channel-based routing
"""
```

- [ ] **Step 10: Clean legacy files**

- `bot.py`: Replace `"dayist-dev"` with a config lookup or generic placeholder
- `bot_enhanced.py`: Replace Dayist channel config, `com.daveleal.Dayist` bundle ID
- `monitor_only.py`: Replace `CHANNEL = "dayist-dev"` and `BUNDLE_ID = "com.daveleal.Dayist"` with env var reads
- `claude-slack`: Replace hardcoded `/Users/daveleal/Repos/SlackClaw` with `$(dirname "$0")` or `SCRIPT_DIR`
- `setup.sh`: Replace `#dayist-dev` reference with generic example
- `.env.example`: Replace `DAYIST_PROJECT_PATH` with generic `# PROJECT_NAME_PROJECT_PATH=/path/to/project`

- [ ] **Step 11: Run full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 12: Commit**

```bash
git add CLAUDE.md ARCHITECTURE.md STATE.md README.md SETUP_GUIDE.md \
       HYBRID_APPROACH.md docs/PROJECT_DESCRIPTIONS.md docs/JOURNAL.md \
       bot_unified.py bot.py bot_enhanced.py monitor_only.py \
       claude-slack setup.sh .env.example
git commit -m "chore: strip all personal project references from tracked files

All docs, scripts, and legacy files now use generic placeholders.
Real project config lives in projects.yaml (gitignored)."
```

---

### Task 11: Validation sweep

**Files:** None (read-only verification)

- [ ] **Step 1: Grep for leaked identifiers**

Run each of these — all should return zero results (excluding `docs/superpowers/specs/` and `docs/superpowers/plans/`):

```bash
grep -rI --include="*.py" --include="*.md" --include="*.sh" --include="*.yaml" --include="*.json" \
  -E "Dayist|TileDock|MacDock|GridBoard|gridboard|SidePlane|Mac2Vision|SlackClaw" \
  --exclude-dir=docs/superpowers/specs --exclude-dir=docs/superpowers/plans \
  --exclude="projects.yaml" .
```

```bash
grep -rI --include="*.py" --include="*.md" --include="*.sh" \
  -E "davesleal|com\.daveleal|Leal Labs" \
  --exclude-dir=docs/superpowers/specs --exclude-dir=docs/superpowers/plans .
```

```bash
grep -rI --include="*.py" \
  -E "C0AM872QM8E|C0AHTQU2CQ2|C0AMDU1939A|C0AM3UT7XL3|C0AN4JQACKS|C0AMEEP7EFL" .
```

Expected: zero matches for all three commands.

- [ ] **Step 2: Run full test suite**

Run: `source venv/bin/activate && python -m pytest tests/ -q`
Expected: all pass

- [ ] **Step 3: Run pre-commit hook**

```bash
git diff --cached --name-only  # should be empty (all committed)
```

- [ ] **Step 4: Verify bot starts with example config**

```bash
cp projects.example.yaml /tmp/shellack_test_config.yaml
SHELLACK_CONFIG=/tmp/shellack_test_config.yaml python -c "
import orchestrator_config as oc
print(f'Projects: {list(oc.PROJECTS.keys())}')
print(f'Channels: {list(oc.CHANNEL_ROUTING.keys())}')
print(f'Warnings: {oc.validate_config()}')
print('Config loads OK')
"
```

Expected: prints project/channel keys from example, no errors

- [ ] **Step 5: Final commit if any fixups needed**

```bash
# Only if Step 1 found stragglers
git add -A && git commit -m "fix: remove remaining personal references found in validation sweep"
```

---

### Task 12: Push

- [ ] **Step 1: Review commit log**

```bash
git log --oneline HEAD~10..HEAD
```

Verify clean logical progression.

- [ ] **Step 2: Push**

```bash
git push
```
