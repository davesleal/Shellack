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
| 🐛 **GitHub issues** | Bugs and crashes auto-open issues with correct labels |
| 🔍 **Peer review** | Staged Quality / Security / Performance review in `#code-review` |
| 📔 **Journal** | Narrative `JOURNAL.md` entries written after significant work |
| 📱 **App Store Connect** | Auto-monitors reviews and TestFlight feedback |
| 🔌 **Plugin management** | Install Claude plugins, MCP servers, and bot extensions from Slack |
| ⚙️ **Live config** | Switch AI mode/model without restarting the bot |
| 🌉 **Terminal bridge** | `claude-slack` — respond to Claude Code prompts via Slack buttons on any device |

---

## 🚀 Quick start

```bash
git clone https://github.com/YOUR_ORG/Shellack.git
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
GITHUB_ORG=YOUR_ORG            # Your GitHub username or org

# Slack user ID for operator escalations (Profile → ··· → Copy member ID)
OWNER_SLACK_USER_ID=U0XXXXXXX

# Peer review channel
CODE_REVIEW_CHANNEL_ID=C0XXXXXXX

# AI mode — "api" (Anthropic API) or "max" (Claude Max subscription, zero API cost)
SESSION_BACKEND=api
SESSION_MODEL=claude-sonnet-4-6

# Project paths (defaults to ~/Repos/<Name>)
DAYIST_PROJECT_PATH=~/Repos/Dayist
TILEDOCK_PROJECT_PATH=~/Repos/TileDock
# ... see .env.example for all variables

# App Store Connect (optional)
APP_STORE_CONNECT_KEY_ID=...
APP_STORE_CONNECT_ISSUER_ID=...
APP_STORE_CONNECT_PRIVATE_KEY_PATH=~/.appstoreconnect/AuthKey_XXXXX.p8
```

### Project & channel routing

Edit `orchestrator_config.py` to register your projects and map them to Slack channels:

```python
PROJECTS = {
    "myapp": {
        "name": "MyApp",
        "path": os.environ.get("MYAPP_PROJECT_PATH", os.path.expanduser("~/Repos/MyApp")),
        "bundle_id": os.environ.get("MYAPP_BUNDLE_ID", ""),
        "primary_channel": "myapp-dev",
        "language": "swift",
        "platform": "ios",
        "github_repo": f"{_GITHUB_ORG}/MyApp",
    },
}
```

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
| `@Shellack usage` | Show this month's session and mention counts |

Mode and model changes take effect immediately — no restart required.

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

## 🔐 Security

- Tokens stored in `.env` (gitignored)
- Each channel is isolated to its configured project directory
- Bot extensions require a full Git URL — no implicit registry installs
- All destructive operations (file writes, issue creation) require an active agent task

---

## 📮 Support

- 📚 [Setup guide](./SETUP_GUIDE.md)
- 🐛 [Report issues](https://github.com/YOUR_ORG/Shellack/issues)
- 💬 [Discussions](https://github.com/YOUR_ORG/Shellack/discussions)

---

## 📝 License

MIT — see [LICENSE](LICENSE) for details.
