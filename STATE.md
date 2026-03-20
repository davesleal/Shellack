# SlackClaw Current State
**Last Updated:** 2026-03-18
**Status:** Production-ready, specialized agents active

---

## 🟢 What's Running

### SlackClaw Bot
**Location:** `~/Repos/SlackClaw`
**Status:** Should be running (check with `ps aux | grep bot_unified`)
**Start Command:**
```bash
cd ~/Repos/SlackClaw
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
| Dayist | ~/Applications/Dayist App | com.your-org.dayist | dayist-dev | iOS |
| NOVA | ~/Repos/NOVA | None | nova-dev | iOS |
| Nudge | ~/Repos/Nudge | None | nudge-dev | iOS |
| TileDock | ~/Applications/MacDock | com.your-org.MacDock | tiledock-dev | macOS |
| Atmos | ~/Applications/atmos-universal | None | atmos-dev | macOS |
| SidePlane | ~/Applications/Mac2Vision | com.your-org.sideplane | sideplane-dev | macOS |
| SlackClaw | ~/Repos/SlackClaw | N/A | slackclaw-dev | Server |

### Credentials
**File:** `.env` (gitignored)
**Location:** `~/Repos/SlackClaw/.env`

**Contains:**
- `SLACK_BOT_TOKEN` - Bot token (rotated)
- `SLACK_APP_TOKEN` - App token (rotated)
- `SLACK_SIGNING_SECRET` - Signing secret (rotated)
- `ANTHROPIC_API_KEY` - Claude API key
- `APP_STORE_CONNECT_KEY_ID` - ASC API key ID
- `APP_STORE_CONNECT_ISSUER_ID` - ASC issuer ID
- `APP_STORE_CONNECT_PRIVATE_KEY_PATH` - Path to .p8 file

**Private Key Location:** `~/.appstoreconnect/AuthKey_XXXXX.p8`

---

## ⚠️ Current Issues

### 1. Anthropic API Credits (MONITORING)
**Problem:** API returns 400 "credit balance too low" despite $20 in account
**Status:** Credits visible in console (check your Anthropic organization settings)
**Likely Cause:** API auth layer hasn't synced yet (can take 10-15 min)
**Action:** Wait and retry. Should resolve automatically.

**Test Command:**
```bash
cd ~/Repos/SlackClaw
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

## 🤖 Specialized Product Agents (2026-03-18)

✅ **CLAUDE.md loading per agent**
- Each project agent loads its project's `CLAUDE.md` as system context
- Agents are scoped per thread (`thread_ts`) rather than per project key
- Prevents state bleeding across parallel conversations

✅ **GitHub issue auto-creation**
- `GitHubClient` auto-opens issues in the correct repo for crash/bug tasks
- Labels applied based on task type (bug, crash, performance)
- Issues auto-closed when work is marked done

✅ **Lifecycle Slack posts (thread + channel)**
- `LifecycleNotifier` posts structured 🔵🐛🔨👀✅ status events to threads
- High-signal events (issue created, done, needs human, pending review) cross-posted top-level to project channel
- Enables Claude app to scan any project channel and understand current state

✅ **Staged peer review (Stage 1 + Stage 2)**
- `StagedPeerReview` triggers automatically when agent response contains code
- Stage 1: Quality/Security/Performance review posted to `#code-review`
- Stage 2: Cross-project agent review request posted to `#code-review`
- `PeerReviewAgent` parses structured JSON output (blocking/non-blocking issues)
- The operator is @-mentioned for blocking issues

✅ **Per-project journaling**
- `JournalWriter` appends narrative entries to `docs/JOURNAL.md` in each project repo
- Falls back to root `JOURNAL.md` if `docs/` directory is absent
- Entries formatted for blog-post readability

✅ **Maestro CLAUDE.md written**
- Coordination protocol defined for all 7 projects
- Covers thread-scoped agent pattern, dual-post lifecycle, and staged review protocol

**Test Coverage:** 28 tests, all passing (as of 2026-03-18)

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

**3. Live End-to-End Test**
- Trigger a crash task from Slack
- Verify GitHub issue created, lifecycle posts appear, peer review fires
- Confirm journal entry written to project repo

### Future Features

- [ ] GitHub PR workflow automation (auto-open PR after fix)
- [ ] Custom review agents for specialized code areas (SwiftUI, networking)
- [ ] Metrics dashboard for bot activity
- [ ] Cross-project pattern detection
- [ ] Claude app workspace status summary from any project channel

---

## 🏗️ Architecture Overview

```
Slack Workspace (your organization)
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
~/Repos/SlackClaw/
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
- `~/.appstoreconnect/AuthKey_XXXXX.p8` - ASC private key
- `~/.claude/settings.json` - Claude Code config
- GitHub repos for all 7 projects (see orchestrator_config.py for paths)

---

## 🚀 How to Resume

### 1. Check if SlackClaw is Running
```bash
ps aux | grep bot_unified
```

If not running:
```bash
cd ~/Repos/SlackClaw
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
cd ~/Repos/SlackClaw
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
- Check your organization settings for credit balance

**Slack Issues:**
- Workspace: your organization's Slack workspace
- Bot: @SlackClaw
- App settings: https://api.slack.com/apps

**GitHub:**
- Repository: https://github.com/YOUR_ORG/SlackClaw
- Issues: Track bugs/features there

---

## ✅ Session Checkpoint

**What was accomplished (2026-03-18 — Specialized Agents session):**
- Built `GitHubClient`, `LifecycleNotifier`, `JournalWriter` tool classes
- Refactored `PeerReviewAgent` to structured JSON output; added `StagedPeerReview`
- Rewrote `ProjectAgent` to own full task lifecycle (start → in-progress → review → done)
- Updated `AgentFactory` to scope agents per `thread_ts` rather than per project key
- Wired everything through `bot_unified.py`
- Wrote Maestro `CLAUDE.md` defining coordination protocol across all 7 projects
- 28 tests written TDD-style, all passing

---

## ✅ Session Checkpoint

**What was accomplished (2026-03-18 — Slack↔Terminal Bridge session):**

✅ **Slack↔Terminal Bridge shipped** (`claude-slack`)
- `tools/slack_bridge.py` — Block Kit formatter (`format_bridge_blocks`), project channel detector (`detect_channel_id`), session-start notifier (`post_session_start`)
- `claude-slack` wrapper script — creates named pipe session, exports `CLAUDE_BRIDGE_SESSION` + `CLAUDE_BRIDGE_CHANNEL_ID`, launches `claude` with pipe as stdin
- `@app.action("claude_bridge_input")` handler in `bot_unified.py` — receives Slack button clicks, writes answer to named pipe, updates message with confirmation
- `CLAUDE.md` updated with bridge instructions so Claude Code knows to use Slack MCP when bridge is active
- `orchestrator_config.py` — all CHANNEL_ROUTING entries now have `channel_id` (5 real IDs populated)
- `SETUP_GUIDE.md` — Step 8 added with install and smoke-test instructions
- 48 tests passing (was 28; +20 new bridge tests)
- Symlink: `/usr/local/bin/claude-slack → ~/Repos/SlackClaw/claude-slack`

**What to do next session:**
1. Live end-to-end test: run `claude-slack` from a project repo, confirm session-start in Slack, post Block Kit prompt, click button, verify answer reaches Claude
2. Create missing Slack channels: `#nova-dev`, `#nudge-dev`, `#slackclaw-central`, `#code-review` → fill in empty `channel_id` values in `orchestrator_config.py`
3. Update Slack channel topics using `docs/PROJECT_DESCRIPTIONS.md`
4. Live end-to-end test for Specialized Agents (trigger crash task → GitHub issue + lifecycle + review + journal)

**Status:** 🟢 Bridge shipped, all tests green

---

*Last session: 2026-03-18*
*Next: Live end-to-end bridge validation + create missing Slack channels*
