# Shellack 🦞

> A Claude-powered Slack bot for multi-project development automation

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Slack Bolt](https://img.shields.io/badge/Slack-Bolt-4A154B?logo=slack)](https://slack.dev/bolt-python/)
[![Claude](https://img.shields.io/badge/Claude-AI-5B4CFF)](https://www.anthropic.com/)

Shellack connects your Slack workspace to Claude AI, giving each project channel its own intelligent agent. Ask questions, start full coding sessions, manage plugins, and track usage — all from Slack.

---

## ✨ What it does

| Capability | Description |
|---|---|
| 💬 **Quick chat** | `@Shellack <question>` — project-aware answers with thread context |
| 🖥️ **Full sessions** | `@Shellack run: <task>` — interactive Claude Code session in a thread |
| 🎨 **Canvas output** | Code blocks route to a Slack Canvas instead of flooding the thread |
| 🤖 **Project agents** | Each channel gets a dedicated agent loaded with `CLAUDE.md` context |
| 🧠 **Token Cart** | Haiku-powered context compaction — replaces full-history replay, ~57% token savings |
| 🛡️ **Agent teams** | Infosec + architect consultants review responses when triggered |
| ✅ **Gut check** | Sanity check against project registry before posting responses |
| 📋 **Project registry** | Auto-maintained index of reusable components, patterns, and rules |
| 🔄 **Cross-thread memory** | Handoffs persist across threads via `.shellack/thread-memory/` |
| 🐛 **GitHub issues** | Bugs and crashes auto-open issues with correct labels |
| 🔍 **Peer review** | Staged Quality / Security / Performance review in `#code-review` |
| 📔 **Journal** | Narrative journal entries via GitHub Discussions (weekly threads) |
| 📱 **App Store Connect** | Auto-monitors reviews and TestFlight feedback |
| 🔌 **Plugin management** | Install Claude plugins, MCP servers, and bot extensions from Slack |
| ⚙️ **Live config** | Switch AI mode/model/features without restarting the bot |
| 💰 **Cost tracking** | Per-turn token spend displayed in the Churned block |
| 🌉 **Terminal bridge** | `claude-slack` — respond to Claude Code prompts via Slack buttons on any device |

---

## 🚀 Quick start

```bash
git clone https://github.com/your-org/Shellack.git
cd Shellack
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python bot_unified.py
```

---

## ⚙️ Configuration

### Slack app

1. Go to [api.slack.com/apps](https://api.slack.com/apps) → **Create New App → From a manifest**
2. Paste `slack-app-manifest.yml` — this sets all scopes and event subscriptions automatically
3. Install to workspace and copy `SLACK_BOT_TOKEN` + `SLACK_APP_TOKEN`

### Environment variables

```bash
# .env
SLACK_BOT_TOKEN=xoxb-...
SLACK_APP_TOKEN=xapp-...
ANTHROPIC_API_KEY=sk-ant-...

# GitHub integration — enables issue auto-creation
GITHUB_TOKEN=ghp_...
GITHUB_ORG=your-org            # Your GitHub username or org

# Slack user ID for operator escalations (Profile → ··· → Copy member ID)
OWNER_SLACK_USER_ID=U0XXXXXXX

# Peer review channel
CODE_REVIEW_CHANNEL_ID=C0XXXXXXX

# AI mode — "api" (Anthropic API) or "max" (Claude Max subscription, zero API cost)
SESSION_BACKEND=api
SESSION_MODEL=claude-sonnet-4-6

# Project paths (defaults to ~/Repos/<Name>)
# MY_PROJECT_PROJECT_PATH=~/Repos/MyProject
# ... see .env.example for all variables

# App Store Connect (optional)
APP_STORE_CONNECT_KEY_ID=...
APP_STORE_CONNECT_ISSUER_ID=...
APP_STORE_CONNECT_PRIVATE_KEY_PATH=~/.appstoreconnect/AuthKey_XXXXX.p8
```

### Project & channel routing

Copy `projects.example.yaml` to `projects.yaml` and fill in your projects:

```bash
cp projects.example.yaml projects.yaml
# Edit projects.yaml with your channels, paths, and repos
```

```yaml
# projects.yaml (gitignored — your config, not committed)
github_org: your-org
projects:
  myapp:
    name: MyApp
    primary_channel: myapp-dev
    language: swift
    platform: ios
    github_repo: your-org/MyApp
    path: ~/Repos/MyApp
    # Optional: Token Cart feature flags
    features:
      token-cart: true        # context compaction (default: on)
      gut-check: true         # sanity check (default: on)
      consultants: true       # infosec + architect (default: on)
      registry: true          # pattern index (default: on)
      agent-manager: false    # model selection (default: off)
```

See `projects.example.yaml` for the full schema with all options.

---

## 💡 Usage

### Quick chat — `@Shellack <question>`

Ask anything about the project in its channel. The bot uses the project's `CLAUDE.md` as context and maintains conversation history per thread.

```
@Shellack what does the NetworkClient class do?
@Shellack why might login fail on iOS 17?
@Shellack show me recent commits touching the auth flow
```

The `:claude:` emoji appears on your message while the bot is thinking, and disappears when it replies.

---

### Full session — `@Shellack run: <task>`

Starts an interactive Claude Code session in the thread. Claude can read files, write code, run tests, and commit — just like the CLI. Output is streamed back to Slack in real time; code blocks go to a session Canvas.

```
@Shellack run: fix the crash in LoginView
@Shellack run: add unit tests for the cart total calculation
@Shellack run: refactor NetworkClient to use async/await
```

Continue the session by replying in the thread (no `@mention` needed). Stop it with `stop` or `cancel`.

Sessions time out after 30 minutes of inactivity (warned at 15 and 25 minutes).

---

### Config commands

These work in any channel, any context:

| Command | Effect |
|---|---|
| `@Shellack set mode max` | Switch to Claude Max subscription (zero API cost) |
| `@Shellack set mode api` | Switch to Anthropic API |
| `@Shellack set model opus` | Use claude-opus-4-6 |
| `@Shellack set model sonnet` | Use claude-sonnet-4-6 (default) |
| `@Shellack set model haiku` | Use claude-haiku-4-5 |
| `@Shellack config` | Show current mode, model, and onboarding status |
| `@Shellack config show` | Show all Token Cart feature flags for this channel |
| `@Shellack config <feature> on/off` | Toggle a feature at runtime (e.g., `config gut-check off`) |
| `@Shellack usage` | Show this month's session and mention counts |

All changes take effect immediately — no restart required.

**Configurable features:** `token-cart`, `gut-check`, `registry`, `consultants`, `external-handoff`, `cost-observability`, `code-review`, `agent-manager`

---

### Plugin management

| Command | Effect |
|---|---|
| `@Shellack plugins` | List all installed Claude plugins, MCP servers, and bot extensions |
| `@Shellack add plugin <name>` | Install a Claude Code plugin |
| `@Shellack remove plugin <name>` | Uninstall a Claude Code plugin |
| `@Shellack add mcp <name> <command>` | Register an MCP server |
| `@Shellack remove mcp <name>` | Remove an MCP server |
| `@Shellack add bot-plugin <git-url>` | Install and hot-reload a bot extension |
| `@Shellack remove bot-plugin <name>` | Uninstall a bot extension |

---

### Peer review

Triggers automatically when an agent edits or creates files, or opens a GitHub issue. Posts to `#code-review`:

1. **Stage 1** — Quality, Security, and Performance agents review in parallel
2. **Stage 2** — Maestro selects ≤2 peer agents from projects sharing the same platform/language

Blocking findings tag the operator in the thread.

---

### GitHub issues

When a crash or bug is detected, the agent automatically:
- Opens an issue in the correct repo with appropriate labels (`crash`, `bug`, `p0`, `p1`)
- Posts the issue link in the Slack thread and top-level in the project channel
- Closes the issue when the fix is confirmed

---

## 🌉 Terminal bridge (`claude-slack`)

Run `claude-slack` instead of `claude` from any project repo. Claude Code posts Block Kit button messages to the project's Slack channel when it needs input — click a button on your phone, tablet, or any device to feed the answer back.

```bash
# From any project repo
claude-slack

# Claude Code runs as normal, but prompts appear in Slack
```

Sessions are UUID-scoped so concurrent sessions never cross-contaminate. Stale button clicks show an ephemeral error only to you.

---

## 📊 AI cost modes

| Mode | Set with | Monthly cost | Notes |
|---|---|---|---|
| **API** | `set mode api` | Pay-per-token | Anthropic API, full control |
| **Max** | `set mode max` | $0 extra | Uses your Claude Max subscription via CLI |

Both modes route through the same backend — switching affects quick replies and `run:` sessions alike.

---

## 🗂️ Project structure

```
Shellack/
├── bot_unified.py          # Main bot — entry point
├── orchestrator_config.py  # Project registry & channel routing
├── orchestrator.py         # Cross-project operations
├── peer_review.py          # Staged peer review system
├── agents/
│   ├── project_agent.py    # Per-project agent with CLAUDE.md context
│   └── sub_agents.py       # Crash / Testing / Review / Docs sub-agents
├── tools/
│   ├── token_cart.py       # Haiku-powered context compaction + gut check
│   ├── registry.py         # .shellack/registry.md management
│   ├── thread_memory.py    # Cross-thread persistence
│   ├── cost_tracker.py     # Per-turn/thread cost tracking
│   ├── consultants.py      # Infosec + architect consultants
│   ├── agent_manager.py    # Complexity-based model selection
│   ├── github_journal.py   # GitHub Discussions journal posting
│   ├── journal_polisher.py # Sonnet journal polish
│   ├── session_backend.py  # APIBackend + MaxBackend + quick_reply()
│   ├── slack_session.py    # run: session lifecycle, canvas routing
│   ├── lifecycle.py        # Structured Slack status posts
│   ├── github_client.py    # Issue creation & management
│   ├── plugin_manager.py   # Claude plugins, MCP, bot extensions
│   ├── config_writer.py    # Live .env updates
│   ├── usage_tracker.py    # Monthly usage counters
│   └── journal_writer.py   # JOURNAL.md entries
├── app_store_connect.py    # App Store Connect monitoring
├── claude-slack            # Terminal bridge wrapper script
├── .env.example            # All supported env vars with docs
├── slack-app-manifest.yml  # Slack app manifest (scopes + events)
└── SETUP_GUIDE.md          # Detailed setup walkthrough
```

---

## 🧠 Token Cart — Multi-Agent Architecture

Shellack uses a three-tier model hierarchy to minimize costs while maximizing quality:

| Model | Role | Cost |
|---|---|---|
| **Haiku 4.5** | Token Cart — context compaction, gut checks, correction detection | $0.25/MTok |
| **Sonnet 4.6** | Consultants (infosec, architect), journal polish, output editing | $3/MTok |
| **Opus 4.6** | Primary reasoning — main agent work | $15/MTok |

Instead of replaying full conversation history (quadratic token cost), the Token Cart compacts each turn into a structured handoff. By turn 10, this saves ~57% on tokens.

**How it works per turn:**
1. Haiku enriches context from prior handoff + project registry
2. Reasoning model (Opus/Sonnet) handles the task
3. Gut check verifies response against registry
4. Consultants review if security/architecture triggers detected
5. Haiku compacts the turn into a new handoff (async, non-blocking)
6. Corrections auto-update the project registry

All features are independently toggleable via `@Shellack config <feature> on/off`.

---

## 🔐 Security

- Tokens stored in `.env` (gitignored)
- Pre-commit hook scans for 16 secret patterns (Slack tokens, API keys, AWS, GitHub, private keys)
- Owner-only gates on plugin/MCP/config commands (fail-closed when `OWNER_SLACK_USER_ID` is unset)
- Each channel is isolated to its configured project directory
- Bot extensions require a full Git URL — no implicit registry installs
- All destructive operations (file writes, issue creation) require an active agent task
- Error messages sanitized — no exception details leak to Slack
- Triage separates system prompts from user input (prompt injection prevention)

---

## 📮 Support

- 📚 [Setup guide](./SETUP_GUIDE.md)
- 🐛 [Report issues](https://github.com/davesleal/Shellack/issues)
- 💬 [Discussions](https://github.com/davesleal/Shellack/discussions)

---

## 📝 License

MIT — see [LICENSE](LICENSE) for details.
