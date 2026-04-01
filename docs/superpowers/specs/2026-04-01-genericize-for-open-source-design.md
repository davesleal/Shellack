# Genericize Shellack for Open-Source Forks

**Date:** 2026-04-01
**Status:** Design
**Goal:** Make the repo forkable with zero personal project leakage. All project-specific config lives in a gitignored file. Tracked files contain only generic bot infrastructure.

---

## 1. Config extraction: `projects.yaml`

### What

A single YAML file holds all project definitions, channel routing, and per-project context. Gitignored. Ships with `projects.example.yaml` (tracked) showing the full schema with two placeholder projects.

### Schema

```yaml
github_org: "your-org"

projects:
  webapp:
    name: "Web App"
    path: "~/Repos/WebApp"            # overridable via WEBAPP_PROJECT_PATH env var
    bundle_id: ""                       # optional, for App Store Connect
    language: python
    platform: web
    github_repo: "your-org/WebApp"
    primary_channel: "webapp-dev"
    context:                            # optional, enriches agent system prompt
      description: "Next.js dashboard"
      purpose: "Internal analytics tool"
      tech: "Next.js, PostgreSQL"
      patterns:
        - "Server components for data fetching"
      watch_out:
        - "Don't expose raw SQL in API routes"

  mobile:
    name: "Mobile App"
    path: "~/Repos/MobileApp"
    bundle_id: "com.example.mobile"
    language: swift
    platform: ios
    github_repo: "your-org/MobileApp"
    primary_channel: "mobile-dev"
    context:
      description: "iOS companion app"
      purpose: "Mobile client for the web dashboard"
      tech: "SwiftUI, SwiftData"
      patterns: []
      watch_out: []

channels:
  webapp-dev:
    project: webapp
    mode: dedicated
    channel_id: "C0123456789"           # from Slack channel settings
  mobile-dev:
    project: mobile
    mode: dedicated
    channel_id: "C9876543210"
  central:
    mode: orchestrator
    access: all_projects
    channel_id: ""                      # optional, create when ready
  code-review:
    mode: peer_review
    access: all_projects
    channel_id: ""
    review_agents: ["code-quality", "security", "performance"]
    approval_required: true
    auto_merge: false

# Global coding standards applied across all projects
standards:
  swift:
    style_guide: "Swift API Design Guidelines"
    conventions:
      - "Use descriptive variable names"
      - "Prefer composition over inheritance"
    required_tests: true
    min_coverage: 80
  python:
    style_guide: "PEP 8"
    conventions:
      - "Use type hints"
      - "Maximum line length: 100"
    required_tests: true
    min_coverage: 80

# Orchestrator commands — examples auto-adapt to your project names
orchestrator_commands:
  update_all_claude_md:
    syntax: "@Shellack update all CLAUDE.md: <rule>"
  sync_standards:
    syntax: "@Shellack sync standards from <source> to <target>"
  global_search:
    syntax: "@Shellack search all: <query>"
  coordinate_change:
    syntax: "@Shellack coordinate: <change>"
```

### Loading

`orchestrator_config.py` becomes a thin loader:

```python
import yaml, os

_CONFIG_PATH = os.environ.get(
    "SHELLACK_CONFIG", os.path.join(os.path.dirname(__file__), "projects.yaml")
)

def _load_config():
    with open(_CONFIG_PATH) as f:
        return yaml.safe_load(f)

_cfg = _load_config()

GITHUB_ORG = _cfg.get("github_org", "your-org")
PROJECTS = _cfg.get("projects", {})
CHANNEL_ROUTING = _cfg.get("channels", {})
GLOBAL_STANDARDS = _cfg.get("standards", {})
ORCHESTRATOR_COMMANDS = _cfg.get("orchestrator_commands", {})
```

- Env var overrides for paths: `{PROJECT_KEY.upper()}_PROJECT_PATH`
- Env var overrides for bundle IDs: `{PROJECT_KEY.upper()}_BUNDLE_ID`
- `SHELLACK_CONFIG` env var overrides the config file path

`agents/project_agent.py` reads `context` from the loaded `PROJECTS` dict instead of maintaining a separate `PROJECT_CONTEXT`.

### Startup validation

`bot_unified.py` validates on startup:
- `projects.yaml` exists (clear error message pointing to `projects.example.yaml` if missing)
- Each channel in `channels:` references a valid project key (for `dedicated` mode)
- Warn (don't crash) if `channel_id` is empty — those channels just won't be pre-warmed

---

## 2. Secret scanning: pre-commit hook

### What

A standalone shell script at `hooks/pre-commit` that blocks commits containing secrets.

### Patterns scanned

```
xoxb-                       # Slack bot token
xoxp-                       # Slack user token
xoxs-                       # Slack session token
xoxa-                       # Slack app token
sk-ant-                     # Anthropic API key
sk-live                     # Stripe live key
AKIA[0-9A-Z]{16}            # AWS access key ID
-----BEGIN.*PRIVATE KEY     # Private keys
AIza[0-9A-Za-z_-]{35}      # Google API key
ghp_[0-9a-zA-Z]{36}        # GitHub personal access token
ghs_[0-9a-zA-Z]{36}        # GitHub server token
```

### Behavior

- Scans only staged files (`git diff --cached`)
- Skips binary files
- Skips `*.example*`, `hooks/pre-commit` itself, and `*.md` in `docs/superpowers/specs/` and `docs/superpowers/plans/`
- On match: prints file, line number, matched pattern. Blocks commit.
- Exit 0 (allow) if no matches.

### Setup

```bash
git config core.hooksPath hooks
```

Documented in README and `SETUP_GUIDE.md`. One command, no dependencies.

### .gitignore additions

```
projects.yaml
```

---

## 3. Strip personal references from tracked files

### Scope

Every tracked file outside `docs/superpowers/specs/` and `docs/superpowers/plans/` (historical records). The following must be removed or replaced with generic equivalents:

### Identifiers to strip

| Category | Examples | Replacement |
|----------|----------|-------------|
| Project names | Alpha, Beta, Echo, Foxtrot | Generic placeholders or removed entirely |
| Old repo name | SlackClaw | "Shellack" (the bot's actual name) |
| GitHub org/user | your-org, YOUR_ORG | `your-org` in examples |
| Bundle IDs | com.example.Alpha | `com.example.myapp` |
| Slack channel IDs | C0AM872QM8E, C0AHTQU2CQ2, etc. | Empty strings or `C0EXAMPLE123` |
| Channel names | #alpha-dev, #beta-dev | `#project-a-dev`, `#project-b-dev` |
| Fallback channel ID | C0AMEEP7EFL | Empty string, loaded from env/config |

### Files requiring changes

**Active code:**
- `orchestrator_config.py` — replaced entirely by yaml loader (Section 1)
- `agents/project_agent.py` — `PROJECT_CONTEXT` removed, reads from config
- `bot_unified.py` — strip channel name references from comments
- `bot.py`, `bot_enhanced.py`, `monitor_only.py` — legacy files, strip or add deprecation note
- `tools/slack_bridge.py` — fallback channel ID from env/config, not hardcoded

**Docs:**
- `CLAUDE.md` — generic bot instructions only, project table removed
- `ARCHITECTURE.md` — generic channel examples
- `STATE.md` — reset to clean template
- `README.md` — generic setup instructions
- `SETUP_GUIDE.md` — generic examples
- `HYBRID_APPROACH.md` — generic examples
- `docs/PROJECT_DESCRIPTIONS.md` — becomes a template showing the format
- `docs/JOURNAL.md` — strip project names from "current state" sections; dated entries are historical

**Tests:**
- All test fixtures use generic names: `"alpha"`, `"beta"`, `"projecta"`, `"projectb"`
- Mock channel names: `"alpha-dev"`, `"beta-dev"`
- Mock channel IDs: `"C_ALPHA"`, `"C_BETA"`
- Files affected: `test_github_client.py`, `test_staged_peer_review.py`, `test_project_agent.py`, `test_bot_run_trigger.py`, `test_bot_plugin_commands.py`, `test_onboarding.py`, `test_bot_config_commands.py`, `test_slack_bridge.py`, `test_usage_integration.py`, `test_agent_factory.py`, `test_lifecycle.py`

**Scripts:**
- `claude-slack` wrapper — use generic paths, document how to customize
- `setup.sh` — generic channel examples
- `.env.example` — generic project path vars

---

## 4. Preset example config

### What

`projects.example.yaml` ships with useful defaults beyond just project placeholders:

- Two example projects (different platforms) showing full schema
- Standard channel routing patterns (dedicated, orchestrator, peer review)
- Default coding standards for common languages (Swift, Python, JavaScript)
- Orchestrator command examples with placeholder project names
- Comments explaining every field

### Peer review config

Included in the example with sensible defaults:
- Three review agents: code-quality (blocking), security (blocking), performance (advisory)
- 2 approvals required
- No auto-merge

---

## 5. Additional fixes from code review

### `_DEFAULT` in `triage.py` evaluated at import time

`_configured_model()` is called once at module load. If `SESSION_MODEL` changes after import, `_DEFAULT.model` is stale.

**Fix:** Make the fallback lazy — call `_configured_model()` inside `classify()` when building the default result, not at module level.

### ThinkingIndicator fallback lacks test coverage

The `done(response=...)` fallback path (lines 120-135) has multiple `except Exception: pass` blocks that could silently swallow responses.

**Fix:** Add a test that simulates `chat_update` failure and verifies the fallback `chat_postMessage` fires. Add a test for total failure to verify it doesn't crash.

---

## 6. What stays unchanged

- `.env` / `.env.example` — existing secrets pattern, already gitignored
- `bot_unified.py` core event handling — doesn't hardcode projects in logic, only in comments
- All tool modules (`thinking_indicator`, `slack_session`, `session_backend`, `lifecycle`)
- Historical design specs and plans in `docs/superpowers/`
- Bot name "Shellack" — this is the product name, not personal info

---

## 7. Validation plan

After all changes:
1. `grep -rI` for every identifier in the strip list across tracked files (excluding historical docs)
2. Run full test suite — all tests must pass
3. Run `hooks/pre-commit` against the repo to verify no secrets in tracked files
4. Clone to a temp directory, copy `projects.example.yaml` to `projects.yaml`, verify bot starts without errors
5. `git log --diff-filter=D` — confirm no accidental file deletions
