# Shellack Project Journal

## 2026-04-01 — Genericized for Open Source

**Context:** Shellack was built as a personal dev automation bot, but the architecture is general-purpose — any team could use it. The problem: project names, channel IDs, bundle IDs, and personal paths were hardcoded across 40+ files. Anyone forking would inherit someone else's project config baked into the code.

**Approach:** Extracted all project-specific config into a single `projects.yaml` file (gitignored), with a fully commented `projects.example.yaml` as the template. Rewrote `orchestrator_config.py` from a 200-line hardcoded dict into a 140-line YAML loader with env var overrides, tilde expansion, and startup validation. Removed the `PROJECT_KNOWLEDGE` dict from `project_agent.py` — agents now read their context from the `context` block in the YAML. Genericized every test fixture (alpha/beta instead of real names), stripped personal references from all docs and scripts, and added a pre-commit hook that scans for 12 secret patterns in staged files.

**Outcome:** 14 commits, 218 tests passing, zero personal identifiers in tracked files. A fresh fork gets: copy the example yaml, fill in your projects, run the bot. The pre-commit hook catches accidental secret commits before they happen. Closed 4 GitHub issues that were already implemented (#5 multi-language, #8 test suite, #11 reverse chat, #12 bridge). Created follow-up issue #13 for remaining polish (conftest fixture for fresh clones, CONTRIBUTING.md).

**Insights:** The hardest part wasn't the config extraction — it was finding every reference. Personal identifiers were woven through comments, docstrings, test fixtures, wrapper scripts, setup guides, and architecture docs. The systematic grep-audit-fix-verify cycle was essential. The YAML loader ended up simpler than the original hardcoded config because it eliminated 5 project entries × 8 fields each of repetitive Python dict literals. The pre-commit hook is the kind of thing you wish you'd added on day one — a 66-line bash script that removes an entire class of "oh no" moments.

**Security hardening (same session):** An infosec review surfaced 10 findings. Two HIGH: plugin manager allowed arbitrary git clone + import from any Slack user (RCE), and the self-improver could poison CLAUDE.md via second-order prompt injection. Both fixed with owner-only gates (fail-closed when `OWNER_SLACK_USER_ID` is unset) and rule sanitization (length cap, suspicious pattern blocklist, non-ASCII rejection, opt-in via env var). Four MEDIUM: pre-commit hook expanded to 16 patterns, triage classifier now separates system prompt from user input, ripgrep search uses fixed-strings to prevent ReDoS, Slack manifest scopes documented. Four LOW: untracked leaked metadata files, config commands gated to owner, error messages sanitized to prevent path leakage. 255 tests total, 37 specifically verifying security controls.

---

## 2026-03-18 — Slack↔Terminal Bridge

**Context:** The operator wanted to respond to Claude Code prompts from any device (phone, tablet, another machine) without switching to the terminal to type `1`, `2`, `3`. The idea: Claude Code posts Block Kit button messages to the project's Slack channel; clicking a button feeds the answer back to Claude's stdin through a named pipe.

**Approach:** Designed around a session-scoped named pipe. The `claude-slack` wrapper creates a FIFO at `/tmp/claude_bridge/<uuid>`, writes a session JSON file, then launches `claude` with the pipe read-end as stdin. The key technical challenge was the pipe lifecycle: opening a named pipe blocks until both ends are open. We solved this with the keep-alive write-end pattern — open `O_WRONLY|O_NONBLOCK` first (unblocks the open call), then open `O_RDONLY|O_NONBLOCK`, then clear `O_NONBLOCK` from the read-end via `fcntl` so the subprocess's stdin blocks normally. A new `tools/slack_bridge.py` module handles Block Kit formatting and project channel detection (git remote URL → `PROJECTS` match → `CHANNEL_ROUTING` lookup). A new `@app.action("claude_bridge_input")` handler in `bot_unified.py` receives button clicks, writes the answer to the pipe, and updates the Slack message to show confirmation.

**Outcome:** `claude-slack` is installed at `/usr/local/bin/claude-slack` as a drop-in replacement for `claude`. Running it from any repo posts a 🟢 session-start to the correct project channel and enables Slack-button-based responses. 48 tests pass. The bridge handles concurrent sessions cleanly (session UUID in button values prevents cross-contamination), and all failure modes (stale sessions, dead pipes, missing channels) produce ephemeral errors to the operator only.

**Insights:** Named pipes have a subtle lifecycle that trips up most implementations. The double-open trick (write-end first non-blocking, read-end second, then clear non-blocking) is the correct POSIX pattern but isn't well-documented for Python. Worth writing up: the `O_NONBLOCK` flag exists to prevent the `open()` call from hanging, but once both ends are open you need to clear it from the read-end or the subprocess will get `EAGAIN` on every read instead of blocking. The `os.fdopen(read_fd, "rb")` wrapper is also critical — passing a raw integer fd to `subprocess.Popen` with default `close_fds=True` would close the fd before the child can inherit it. Two small details, one correct bridge.

---

## 2026-03-18 - Multi-Agent Development System Foundation

### Major Milestone: Architecture Complete

**Context:** Built Shellack from scratch as a Slack bot integrated with Claude AI for development workflows across multiple projects.

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
**Projects Configured:** Multiple projects across iOS and macOS platforms, plus Shellack itself.

**Channel Routing:**
- Dedicated channels: one `#<project>-dev` channel per project
- Orchestrator: `#shellack-central` (cross-project coordination)
- Peer Review: `#code-review` (autonomous review agents)

#### 3. App Store Connect Integration
**Feature:** Automated monitoring of App Store reviews and TestFlight feedback
**Implementation:**
- `app_store_connect.py` - API client with JWT authentication
- 10-minute polling interval for new feedback
- Auto-posts to appropriate project channels
- Configured for: all projects with bundle IDs in `projects.yaml`

**Challenge:** Bundle ID case sensitivity
**Solution:** Updated config to use lowercase bundle ID matching App Store Connect

### Multi-Agent Vision (Emerging)

**The Trinity Architecture:**
```
Developer
    ↓
Claude (Official App) - Orchestrator/Brain
    ↓                    ↓
Shellack              GitHub App
(Code Execution)       (Version Control)
```

**Key Insight:** Token-efficient delegation
- Claude handles conversation intelligence and decision-making
- Shellack executes code operations (file access, changes, tests)
- GitHub App manages PR workflow and CI/CD
- Claude delegates to Shellack instead of reading full files directly

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
**Status:** Likely temporary Anthropic service issue, non-blocking for Shellack

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
- File system: Shellack has direct access to configured project paths

### Next Steps

**Immediate:**
1. ✅ Create project descriptions for Slack channels
2. ⚠️ Develop Claude ↔ Shellack delegation protocol
3. ⚠️ Implement project journal automation
4. ⚠️ Test multi-agent workflows

**Future:**
- GitHub integration for PR automation
- Custom review agents for different code areas
- Metrics dashboard for bot activity
- Cross-project pattern detection

### Files Structure
```
Shellack/
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

6. **Multi-agent thinking** - Combining official Claude + Shellack + GitHub creates more than sum of parts

### Resources
- Repository: https://github.com/your-org/Shellack

---

## Archive

### 2026-03-18 - Session Summary
**Duration:** ~2 hours
**Focus:** Complete Shellack setup from concept to running bot
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

---

## 2026-03-26 — Bot polish: triage killed, deduplication fixed, agents pre-warmed

**Context:** Several UX issues had crept in during the previous session's rapid iteration: duplicate messages (plain text showing above the colored attachment), a noisy "Created agent" log on first message, triage failures polluting logs, and leaked `<function_calls>` XML in responses.

**Approach:** Tackled each root cause rather than papering over symptoms. The duplicate message was `text` and `attachments[].text` both rendering — Slack does this when both are non-empty. Fix: `text=""` everywhere in ThinkingIndicator; the attachment `fallback` field handles notification previews. Agent pre-warming required shifting the AgentFactory cache key from `thread_ts` to `channel_id`, adding `warmup_all()` called at startup, and updating `thread_ts`/`channel_id` on the agent before each `handle()` call. Triage was removed entirely — it had been routing all tiers to the same `SESSION_MODEL` anyway, so the extra Haiku round-trip was pure overhead with failure modes. Code block formatting instructions were added to the system prompt so agents use proper fenced blocks with language tags and close them before resuming prose. `_md_to_mrkdwn` got an auto-close guard for dangling fences. Three new test files cover the new contracts: 182 tests total.

**Outcome:** ThinkingIndicator shows only the clay/gray bar — no duplicate text. Agents are alive at startup, no creation lag. Test suite expanded from 161 to 182 with coverage for AgentFactory caching/warmup, ThinkingIndicator text="" contract, and _md_to_mrkdwn edge cases.

**Insights:** Slack's message structure is a gotcha: `text` is always rendered as plain text above attachments, even when attachments carry the same content. Setting `text=""` and relying on `fallback` (used only for notifications) is the correct pattern for attachment-only messages. It's easy to miss because local testing often doesn't trigger notification previews. The agent pre-warming change is also a good example of a cache key that looks right (thread is unique, no collisions) but is wrong for the use case (we want agent identity to survive across threads on the same channel, not reset per conversation).

