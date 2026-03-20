# SlackClaw Project Journal

## 2026-03-18 — Slack↔Terminal Bridge

**Context:** The operator wanted to respond to Claude Code prompts from any device (phone, tablet, another machine) without switching to the terminal to type `1`, `2`, `3`. The idea: Claude Code posts Block Kit button messages to the project's Slack channel; clicking a button feeds the answer back to Claude's stdin through a named pipe.

**Approach:** Designed around a session-scoped named pipe. The `claude-slack` wrapper creates a FIFO at `/tmp/claude_bridge/<uuid>`, writes a session JSON file, then launches `claude` with the pipe read-end as stdin. The key technical challenge was the pipe lifecycle: opening a named pipe blocks until both ends are open. We solved this with the keep-alive write-end pattern — open `O_WRONLY|O_NONBLOCK` first (unblocks the open call), then open `O_RDONLY|O_NONBLOCK`, then clear `O_NONBLOCK` from the read-end via `fcntl` so the subprocess's stdin blocks normally. A new `tools/slack_bridge.py` module handles Block Kit formatting and project channel detection (git remote URL → `PROJECTS` match → `CHANNEL_ROUTING` lookup). A new `@app.action("claude_bridge_input")` handler in `bot_unified.py` receives button clicks, writes the answer to the pipe, and updates the Slack message to show confirmation.

**Outcome:** `claude-slack` is installed at `/usr/local/bin/claude-slack` as a drop-in replacement for `claude`. Running it from any repo posts a 🟢 session-start to the correct project channel and enables Slack-button-based responses. 48 tests pass. The bridge handles concurrent sessions cleanly (session UUID in button values prevents cross-contamination), and all failure modes (stale sessions, dead pipes, missing channels) produce ephemeral errors to the operator only.

**Insights:** Named pipes have a subtle lifecycle that trips up most implementations. The double-open trick (write-end first non-blocking, read-end second, then clear non-blocking) is the correct POSIX pattern but isn't well-documented for Python. Worth writing up: the `O_NONBLOCK` flag exists to prevent the `open()` call from hanging, but once both ends are open you need to clear it from the read-end or the subprocess will get `EAGAIN` on every read instead of blocking. The `os.fdopen(read_fd, "rb")` wrapper is also critical — passing a raw integer fd to `subprocess.Popen` with default `close_fds=True` would close the fd before the child can inherit it. Two small details, one correct bridge.

---

## 2026-03-18 - Multi-Agent Development System Foundation

### Major Milestone: Architecture Complete

**Context:** Built SlackClaw from scratch as a Slack bot integrated with Claude AI for development workflows across multiple projects.

### Architecture Decisions

#### 1. Modular Unified Architecture (Option C)
**Decision:** Single bot process with channel-based routing
**Alternatives Considered:**
- Option A: Separate bot per project (too many processes)
- Option B: Single monolithic bot (no separation of concerns)

**Rationale:**
- One deployment, easy maintenance
- Modular code with clear separation
- Scalable - add projects without code changes
- Three core modules: Project Agents, Orchestrator, Peer Review

**Implementation:**
- `bot_unified.py` - Main routing engine
- `orchestrator_config.py` - Project registry and channel mapping
- `orchestrator.py` - Cross-project operations
- `peer_review.py` - Autonomous code review system

#### 2. Multi-Project Support
**Projects Configured:**
- **iOS:** Dayist, NOVA, Nudge
- **macOS:** TileDock, Atmos Universal, SidePlane
- **Meta:** SlackClaw itself

**Channel Routing:**
- Dedicated channels: `#dayist-dev`, `#nova-dev`, `#nudge-dev`, `#tiledock-dev`, `#atmos-dev`, `#sideplane-dev`
- Orchestrator: `#slackclaw-central` (cross-project coordination)
- Peer Review: `#code-review` (autonomous review agents)

#### 3. App Store Connect Integration
**Feature:** Automated monitoring of App Store reviews and TestFlight feedback
**Implementation:**
- `app_store_connect.py` - API client with JWT authentication
- 10-minute polling interval for new feedback
- Auto-posts to appropriate project channels
- Configured for: Dayist (iOS), TileDock (macOS), SidePlane (macOS)

**Challenge:** Bundle ID case sensitivity
**Solution:** Updated config to use lowercase bundle ID matching App Store Connect

### Multi-Agent Vision (Emerging)

**The Trinity Architecture:**
```
Developer
    ↓
Claude (Official App) - Orchestrator/Brain
    ↓                    ↓
SlackClaw              GitHub App
(Code Execution)       (Version Control)
```

**Key Insight:** Token-efficient delegation
- Claude handles conversation intelligence and decision-making
- SlackClaw executes code operations (file access, changes, tests)
- GitHub App manages PR workflow and CI/CD
- Claude delegates to SlackClaw instead of reading full files directly

**Benefits:**
- Reduces Claude API token consumption
- Clear separation of concerns
- Each agent does what it does best
- Maintains conversation context across tools

### Technical Challenges Resolved

#### 1. API Billing Issue
**Problem:** Anthropic API returning 400 "credit balance too low" despite $20 added
**Root Cause:** Timing - credits visible in console but API auth layer not synced
**Solution:** Wait 10-15 minutes for Anthropic systems to sync
**Status:** Monitoring, should resolve automatically

#### 2. OAuth Redirect Error
**Problem:** Claude Slack app OAuth failing with redirect URI error
**Status:** Likely temporary Anthropic service issue, non-blocking for SlackClaw

#### 3. Private Key Configuration
**Problem:** User initially put private key contents in .env instead of file path
**Solution:** Moved `.p8` file to `~/.appstoreconnect/` with `chmod 600`, updated .env to file path

### Security Practices

**Secrets Management:**
- All credentials in `.env` (gitignored)
- API keys, tokens, signing secrets isolated
- Private keys in secure directory with restricted permissions
- User rotated all Slack tokens after accidental exposure

**Permissions:**
- App Store Connect: Read-only access to reviews/feedback
- Slack: Bot scope limited to necessary permissions
- File system: SlackClaw has direct access to configured project paths

### Next Steps

**Immediate:**
1. ✅ Create project descriptions for Slack channels
2. ⚠️ Develop Claude ↔ SlackClaw delegation protocol
3. ⚠️ Implement project journal automation
4. ⚠️ Test multi-agent workflows

**Future:**
- GitHub integration for PR automation
- Custom review agents for different code areas
- Metrics dashboard for bot activity
- Cross-project pattern detection

### Files Structure
```
SlackClaw/
├── bot_unified.py              # Main unified bot
├── orchestrator_config.py      # Project registry
├── orchestrator.py             # Cross-project ops
├── peer_review.py              # Autonomous review
├── app_store_connect.py        # ASC integration
├── .env                        # Credentials (gitignored)
├── slack-app-manifest.yml      # Slack app config
├── ARCHITECTURE.md             # Architecture docs
├── README.md                   # Project overview
└── docs/
    └── JOURNAL.md              # This file
```

### Lessons Learned

1. **Start with architecture** - The modular unified approach saved us from having to manage 7+ separate bot processes

2. **Configuration over code** - `orchestrator_config.py` makes adding projects trivial without touching core bot logic

3. **Separation of concerns** - Three distinct modules (Project Agents, Orchestrator, Peer Review) keeps code clean and purposeful

4. **Security from day one** - Gitignoring .env and properly managing secrets prevents credential leaks

5. **Documentation as you build** - Created ARCHITECTURE.md and README.md during development, not after

6. **Multi-agent thinking** - Combining official Claude + SlackClaw + GitHub creates more than sum of parts

### Resources
- Repository: https://github.com/YOUR_ORG/SlackClaw

---

## Archive

### 2026-03-18 - Session Summary
**Duration:** ~2 hours
**Focus:** Complete SlackClaw setup from concept to running bot
**Key Achievement:** Multi-project Slack bot with AI integration, orchestration, and peer review capabilities
**Status:** Production-ready, monitoring App Store Connect for 3 apps
**Next Session:** Multi-agent synergy implementation

---

## 2026-03-18 — Specialized Product Agents

**Context:** The operator wanted each project agent to be truly specialized — carrying its project's CLAUDE.md as system context, auto-creating GitHub issues for bugs, posting structured lifecycle updates to Slack, triggering staged peer review before completing significant work, and maintaining a per-project narrative journal.

**Approach:** Built three new tool classes (GitHubClient, LifecycleNotifier, JournalWriter), refactored PeerReviewAgent to use structured JSON output, added StagedPeerReview for two-stage autonomous review, rewrote ProjectAgent to own the full task lifecycle, updated AgentFactory to scope agents per thread rather than per project, and wired everything through bot_unified.py. Wrote a Maestro CLAUDE.md defining coordination protocol across all 7 projects. Full TDD throughout — 28 tests covering all new modules.

**Outcome:** Each project agent now carries its project's CLAUDE.md context, automatically creates and closes GitHub issues for crash tasks, posts 🔵🐛🔨👀✅ lifecycle events to Slack threads with high-signal events cross-posted top-level to the project channel for Claude app visibility, triggers staged peer review in #code-review before marking work done, and appends narrative JOURNAL.md entries. The system is designed for the operator to ping Claude app for workspace-wide status from any project channel.

**Insights:** The "thread-scoped agent" pattern (keying AgentFactory by thread_ts rather than project_key) was a key architectural decision — it means each conversation carries its own lifecycle context, preventing state from bleeding across parallel conversations. The dual-post pattern (thread for detail, channel for signal) lets Claude app scan any project channel and immediately understand what's happening, without needing a central "status channel" — the project channels become their own status boards.

---
