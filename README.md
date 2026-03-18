# SlackClaw 🦞

> Bridge your Slack workspace with Claude AI for automated development workflows

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Slack API](https://img.shields.io/badge/Slack-API-4A154B?logo=slack)](https://api.slack.com/)
[![Claude](https://img.shields.io/badge/Claude-AI-5B4CFF)](https://www.anthropic.com/)

Interact with Claude Code directly from Slack, enabling natural conversations about your codebase, autonomous bug investigations, and automated App Store Connect monitoring.

## ✨ Features

- 💬 **Natural Conversations** - Ask Claude about your code from Slack
- 🧵 **Thread-based Sessions** - Each thread maintains full conversation context
- 🤖 **Autonomous Agents** - Auto-investigate and fix bugs
- 📱 **App Store Connect** - Auto-monitor reviews and TestFlight feedback
- 💰 **Zero-Cost Option** - Monitor-only mode uses your Claude subscription
- 🔐 **Secure** - Channel-isolated workspaces with permission controls
- 🧠 **Project-Aware Agents** — each agent loads its project's `CLAUDE.md` for deep context
- 🐛 **GitHub Issue Auto-Creation** — bugs and crashes auto-open issues in the correct repo with labels
- 📋 **Lifecycle Visibility** — structured 🔵🐛🔨👀✅ status posts in thread; high-signal events cross-post top-level to the project channel
- 🔍 **Staged Peer Review** — automated Quality/Security/Performance review + cross-project agent review in `#code-review`
- 📔 **Project Journaling** — narrative `JOURNAL.md` entries after significant work, written for blog-post readability

## 🚀 Quick Start

```bash
git clone https://github.com/davesleal/SlackClaw.git
cd SlackClaw
./setup.sh
```

The setup script will:
1. Create virtual environment
2. Install dependencies
3. Guide you through configuration
4. Start the bot

## 📖 Table of Contents

- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Zero-Cost Mode](#zero-cost-mode)
- [Advanced Features](#advanced-features)
- [Deployment](#deployment)
- [Contributing](#contributing)

## 📦 Installation

### Prerequisites

- Python 3.9+
- Slack workspace with admin access
- Claude API key (or Claude Max subscription for zero-cost mode)
- App Store Connect API access (optional)
- Claude Code CLI with Slack plugin:
  ```bash
  claude plugin install slack
  ```

### Setup

```bash
# Clone the repository
git clone https://github.com/davesleal/SlackClaw.git
cd SlackClaw

# Run automated setup
./setup.sh

# Or manual setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
nano .env
```

## ⚙️ Configuration

### 1. Create Slack App

**Quick method (recommended):**
1. Go to https://api.slack.com/apps
2. Click "Create New App" → **"From an app manifest"**
3. Paste contents from `slack-app-manifest.yml`
4. Get your tokens and install

**Manual method:** See [SETUP_GUIDE.md](./SETUP_GUIDE.md#option-b-manual-setup)

### 2. Configure Environment

```bash
# .env file
SLACK_BOT_TOKEN=xoxb-your-token
SLACK_APP_TOKEN=xapp-your-token
ANTHROPIC_API_KEY=sk-ant-your-key  # Optional if using zero-cost mode
APP_STORE_CONNECT_KEY_ID=your-key   # Optional
```

### 3. Map Channels to Projects

Edit `bot_enhanced.py`:

```python
CHANNEL_PROJECTS = {
    "myapp-dev": {
        "path": "/path/to/your/app",
        "bundle_id": "com.example.app",
        "auto_investigate": True
    }
}
```

See [SETUP_GUIDE.md](./SETUP_GUIDE.md) for detailed instructions.

## 💡 Usage

### Basic Commands

```
@SlackClaw what files are in the Settings view?
@SlackClaw explain how authentication works
@SlackClaw show recent commits
```

### Autonomous Mode

```
@SlackClaw auto: analyze performance bottlenecks
@SlackClaw investigate: users report app crashes on login
```

### Thread-based Sessions

Each thread maintains conversation context:

```
User: @SlackClaw review the subscription code
Bot: [Analysis of subscription implementation]

User: Can you suggest improvements?
Bot: [Suggestions with context from previous message]

User: Apply those changes
Bot: [Applies changes and commits]
```

## 💰 Zero-Cost Mode

Don't want to pay for Claude API? Use your existing Claude subscription:

```bash
# Run the monitoring-only bot (no AI costs)
python monitor_only.py
```

This mode:
- ✅ Monitors App Store Connect
- ✅ Posts reviews/feedback to Slack
- ✅ Adds action buttons
- ❌ **No Claude API usage** ($0/month)

Investigate locally with Claude Code CLI:
```bash
cd /path/to/project
claude code
# Ask Claude about issues using your subscription
```

See [HYBRID_APPROACH.md](./HYBRID_APPROACH.md) for details.

## 🎯 Real-World Example

**Autonomous Bug Investigation:**

```
[Auto-posted by SlackClaw]
🚨 New App Store Review

Rating: ⭐⭐ (2/5)
Title: "App crashes on launch"
Review: Every time I open the app it crashes. iPhone 15 Pro, iOS 18.1

---

🤖 Starting autonomous investigation...

✅ Investigation Complete

Found crash in LoginView.swift:42
Issue: Force unwrapping nil user data during launch
Fix: Added guard statement and fallback

Affected versions: 1.2.0+
Priority: High
Files changed: 1

[Apply Fix] [Run Tests] [Create PR]
```

## 🚀 Advanced Features

### Custom Agents

```python
AGENTS = {
    "crash_investigator": {
        "system_prompt": "Expert at analyzing iOS crash logs...",
        "triggers": ["crash", "exception"]
    }
}
```

### Workflow Automation

```
@SlackClaw deploy to testflight
→ Runs tests
→ Updates version
→ Creates build
→ Submits
→ Posts confirmation
```

### Multi-step Tasks

```
@SlackClaw auto: prepare release 1.3.0
```

Bot handles:
- Running all tests
- Updating version numbers
- Generating changelog
- Creating release notes
- Building archive
- Submitting to TestFlight

## 📊 Cost Comparison

| Mode | Monthly Cost | Features |
|------|-------------|----------|
| **Full AI** | $20-50 | Fully autonomous, auto-investigates |
| **Zero-cost** | $0 | Monitoring + manual investigation |
| **Hybrid** | $5-10 | Selective automation |

## 🌐 Deployment

### Local (Development)

```bash
python bot_enhanced.py
```

### macOS Service

```bash
# Copy launch agent
cp com.daveleal.slackclaw.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.daveleal.slackclaw.plist
```

### Cloud Deployment

**Railway:**
```bash
railway up
```

**Fly.io:**
```bash
fly deploy
```

**DigitalOcean:**
```bash
doctl apps create --spec app.yaml
```

See [SETUP_GUIDE.md](./SETUP_GUIDE.md#production-deployment) for details.

## 🗂️ Project Structure

```
SlackClaw/
├── bot_enhanced.py         # Full-featured bot with AI
├── monitor_only.py         # Zero-cost monitoring bot
├── app_store_connect.py    # App Store Connect API client
├── setup.sh               # Automated setup script
├── requirements.txt       # Python dependencies
├── .env.example          # Environment template
├── README.md             # This file
├── SETUP_GUIDE.md        # Detailed setup instructions
└── HYBRID_APPROACH.md    # Zero-cost mode guide
```

## 🔐 Security

- ✅ Tokens stored in `.env` (gitignored)
- ✅ Bot only accesses configured channels
- ✅ Each channel isolated to specific directory
- ✅ Destructive operations require approval
- ✅ All API calls logged

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing`)
5. Open a Pull Request

## 📝 License

MIT License - see [LICENSE](LICENSE) for details.

## 🙏 Acknowledgments

- Built with [Anthropic's Claude API](https://www.anthropic.com/)
- Powered by [Slack Bolt](https://slack.dev/bolt-python/)
- Inspired by the need for better development workflows

## 📮 Support

- 📚 [Documentation](./SETUP_GUIDE.md)
- 🐛 [Report Issues](https://github.com/davesleal/SlackClaw/issues)
- 💬 [Discussions](https://github.com/davesleal/SlackClaw/discussions)

## 🎯 Roadmap

- [ ] MCP server integration
- [ ] GitHub Actions integration
- [ ] Crash log analysis (CrashReporter integration)
- [ ] Multi-language support (beyond iOS/Swift)
- [ ] Custom agent marketplace
- [ ] Web dashboard for monitoring

---

**Built for developers who want to ship faster** 🚢

Made with ❤️ by [Dave Leal](https://github.com/davesleal)

[⭐ Star this repo](https://github.com/davesleal/SlackClaw) if you find it useful!
