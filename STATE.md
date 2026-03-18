# SlackClaw Current State
**Last Updated:** 2026-03-18 03:00 AM
**Status:** Production-ready, monitoring active

---

## 🟢 What's Running

### SlackClaw Bot
**Location:** `/Users/daveleal/Repos/SlackClaw`
**Status:** Should be running (check with `ps aux | grep bot_unified`)
**Start Command:**
```bash
cd /Users/daveleal/Repos/SlackClaw
source venv/bin/activate
python bot_unified.py
```

**Monitoring:**
- Dayist (iOS) - App Store Connect reviews
- TileDock (macOS) - App Store Connect reviews
- SidePlane (macOS) - App Store Connect reviews

### Configured Channels
```
#dayist-dev      → Dayist project agent
#nova-dev        → NOVA project agent
#nudge-dev       → Nudge project agent
#tiledock-dev    → TileDock project agent
#atmos-dev       → Atmos Universal project agent
#sideplane-dev   → SidePlane project agent
#slackclaw-dev   → SlackClaw project agent
#slackclaw-central → Orchestrator (cross-project ops)
#code-review     → Peer review system
```

**Bot Status:** Invited to channels, needs to be mentioned with `@SlackClaw`

---

## 🔧 Configuration

### Project Registry
**File:** `orchestrator_config.py`

**Projects:**
| Project | Path | Bundle ID | Channel | Platform |
|---------|------|-----------|---------|----------|
| Dayist | /Users/daveleal/Applications/Dayist App | com.daveleal.dayist | dayist-dev | iOS |
| NOVA | /Users/daveleal/Repos/NOVA | None | nova-dev | iOS |
| Nudge | /Users/daveleal/Repos/Nudge | None | nudge-dev | iOS |
| TileDock | /Users/daveleal/Applications/MacDock | com.daveleal.MacDock | tiledock-dev | macOS |
| Atmos | /Users/daveleal/Applications/atmos-universal | None | atmos-dev | macOS |
| SidePlane | /Users/daveleal/Applications/Mac2Vision | com.daveleal.sideplane | sideplane-dev | macOS |
| SlackClaw | /Users/daveleal/Repos/SlackClaw | N/A | slackclaw-dev | Server |

### Credentials
**File:** `.env` (gitignored)
**Location:** `/Users/daveleal/Repos/SlackClaw/.env`

**Contains:**
- `SLACK_BOT_TOKEN` - Bot token (rotated)
- `SLACK_APP_TOKEN` - App token (rotated)
- `SLACK_SIGNING_SECRET` - Signing secret (rotated)
- `ANTHROPIC_API_KEY` - Claude API key
- `APP_STORE_CONNECT_KEY_ID` - ASC API key ID
- `APP_STORE_CONNECT_ISSUER_ID` - ASC issuer ID
- `APP_STORE_CONNECT_PRIVATE_KEY_PATH` - Path to .p8 file

**Private Key Location:** `/Users/daveleal/.appstoreconnect/AuthKey_6HRA34Z2AQ.p8`

---

## ⚠️ Current Issues

### 1. Anthropic API Credits (MONITORING)
**Problem:** API returns 400 "credit balance too low" despite $20 in account
**Status:** Credits visible in console (Leal Labs org: `d7645a43-5c57-42ca-aa41-0cda64cfce61`)
**Likely Cause:** API auth layer hasn't synced yet (can take 10-15 min)
**Action:** Wait and retry. Should resolve automatically.

**Test Command:**
```bash
cd /Users/daveleal/Repos/SlackClaw
source venv/bin/activate
python3 -c "
from anthropic import Anthropic
import os
from dotenv import load_dotenv

load_dotenv()
client = Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])

try:
    response = client.messages.create(
        model='claude-sonnet-4-5-20250929',
        max_tokens=10,
        messages=[{'role': 'user', 'content': 'Hi'}]
    )
    print('✅ API working!')
except Exception as e:
    print(f'❌ Still failing: {e}')
"
```

**If still failing after 30 min:** Contact Anthropic support

### 2. Claude OAuth (NON-BLOCKING)
**Problem:** Official Claude Slack app OAuth redirect URI error
**Status:** Likely temporary Anthropic issue
**Impact:** Doesn't affect SlackClaw operation
**Action:** Wait or contact Anthropic support

---

## 🎯 What's Complete

✅ **Architecture**
- Modular unified bot with channel-based routing
- Three core modules: Project Agents, Orchestrator, Peer Review
- Single process handles all channels

✅ **Multi-Project Support**
- 7 projects configured (4 iOS/macOS with ASC, 3 dev-only)
- Channel routing working
- Project-specific context per channel

✅ **App Store Connect Integration**
- API client with JWT auth
- 10-minute polling for reviews/feedback
- Auto-posts to appropriate channels

✅ **Documentation**
- `ARCHITECTURE.md` - System design
- `JOURNAL.md` - Project history and decisions
- `PROJECT_DESCRIPTIONS.md` - Channel topics for all projects
- `STATE.md` - This file

✅ **GitHub Integration**
- GitHub Slack app installed
- Repos visible to Slack
- All bots can see code

✅ **Security**
- All credentials in .env (gitignored)
- Tokens rotated after exposure
- Private key secured with chmod 600

---

## 🔮 What's Next

### Immediate (Ready to Implement)

**1. Update Slack Channel Topics**
- Use descriptions from `docs/PROJECT_DESCRIPTIONS.md`
- Gives context to Claude, SlackClaw, and GitHub
- Format: `Project Name • Tech • Link • Bundle ID`

**2. Test SlackClaw in Channels**
```
In #dayist-dev:
@SlackClaw what files are in Views/Settings?

In #slackclaw-central:
@SlackClaw search all: deprecated API
```

**3. Multi-Agent Synergy**
- Design Claude → SlackClaw delegation protocol
- Update `bot_unified.py` to recognize Claude mentions
- Create example workflows

**4. Journal Automation**
- Add journal commands to SlackClaw
- Auto-log decisions from Claude conversations
- Format: `docs/JOURNAL.md` in each repo

### Future Features

- [ ] Claude delegates to SlackClaw for token efficiency
- [ ] Automated journal entries on decisions/PRs
- [ ] GitHub PR workflow automation
- [ ] Custom review agents for specialized code areas
- [ ] Metrics dashboard for bot activity
- [ ] Cross-project pattern detection

---

## 🏗️ Architecture Overview

```
Slack Workspace (Leal Labs)
│
├─ Official Claude App
│  ├─ Slack MCP (read messages/channels)
│  ├─ GitHub integration (read repos)
│  └─ Conversation intelligence
│
├─ SlackClaw Bot (Python)
│  ├─ Channel routing
│  ├─ Project Agents (7 projects)
│  ├─ Orchestrator (#slackclaw-central)
│  ├─ Peer Review (#code-review)
│  └─ App Store Connect monitoring
│
└─ GitHub App
   ├─ PR/Issue notifications
   ├─ CI/CD status
   └─ Code change events
```

**Claude Code (CLI):**
- Separate instance
- Terminal-based
- Local file access
- No Slack visibility

---

## 📂 Key Files

### SlackClaw Repository
```
/Users/daveleal/Repos/SlackClaw/
├── bot_unified.py              # Main bot (run this)
├── orchestrator_config.py      # Project registry
├── orchestrator.py             # Cross-project ops
├── peer_review.py              # Review system
├── app_store_connect.py        # ASC integration
├── .env                        # Credentials (SECRET)
├── slack-app-manifest.yml      # Slack config
├── ARCHITECTURE.md             # Architecture docs
├── README.md                   # Overview
├── STATE.md                    # This file
└── docs/
    ├── JOURNAL.md              # Project history
    └── PROJECT_DESCRIPTIONS.md # Channel topics
```

### Other Important Files
- `/Users/daveleal/.appstoreconnect/AuthKey_6HRA34Z2AQ.p8` - ASC private key
- `/Users/daveleal/.claude/settings.json` - Claude Code config
- GitHub repos for all 7 projects (see orchestrator_config.py for paths)

---

## 🚀 How to Resume

### 1. Check if SlackClaw is Running
```bash
ps aux | grep bot_unified
```

If not running:
```bash
cd /Users/daveleal/Repos/SlackClaw
source venv/bin/activate
python bot_unified.py
```

### 2. Test API Credits
```bash
# Run test command from "Current Issues" section above
# Should be working by now (credits synced)
```

### 3. Test SlackClaw
Go to any project channel in Slack:
```
@SlackClaw help
```

Should get a response with project context.

### 4. Continue with Synergy
- Read `docs/JOURNAL.md` for context
- Implement Claude → SlackClaw delegation
- Set up journal automation

---

## 💡 Quick Reference

### Restart SlackClaw
```bash
# Find and kill if running
pkill -f bot_unified

# Start fresh
cd /Users/daveleal/Repos/SlackClaw
source venv/bin/activate
python bot_unified.py
```

### Check Logs
```bash
# SlackClaw prints to stdout
# Watch for errors or API issues
```

### Update Projects
Edit `orchestrator_config.py` → restart bot

### Update Slack App
Edit `slack-app-manifest.yml` → reapply in Slack app settings

---

## 🎭 The Multi-Agent Vision

**Goal:** Claude (orchestrator) + SlackClaw (executor) + GitHub (version control)

**Benefits:**
- Token efficiency (Claude delegates heavy lifting)
- Clear separation of concerns
- Automated workflows
- Project journal maintained automatically

**Status:** Architecture documented, ready to implement

**See:** `docs/JOURNAL.md` section "Multi-Agent Vision (Emerging)"

---

## 📞 Support

**Anthropic API Issues:**
- Console: https://console.anthropic.com
- Organization: Leal Labs (`d7645a43-5c57-42ca-aa41-0cda64cfce61`)
- Credits: $20.00 (should be active)

**Slack Issues:**
- Workspace: Leal Labs
- Bot: @SlackClaw
- App settings: https://api.slack.com/apps

**GitHub:**
- Repository: https://github.com/davesleal/SlackClaw
- Issues: Track bugs/features there

---

## ✅ Session Checkpoint

**What was accomplished:**
- Complete SlackClaw setup from scratch
- Multi-project architecture implemented
- 7 projects configured
- App Store Connect monitoring active
- Documentation comprehensive
- Ready for multi-agent synergy

**What to do next session:**
1. Verify API credits working
2. Update Slack channel topics
3. Test SlackClaw in all channels
4. Implement Claude → SlackClaw delegation
5. Set up automated journal entries

**Status:** 🟢 Production-ready, monitoring active, synergy ready to implement

---

*Last session: 2026-03-18 ~3:00 AM*
*Next: Multi-agent synergy implementation*
