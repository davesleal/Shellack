# Shellack Project Journal

## 2026-04-05 — The Bot That Reads Its Own Source Code

**Context:** The 25-persona pipeline shipped yesterday, but the bot couldn't answer questions about itself. Ask "how does triage work?" and it would say "run this command and paste the output" — the exact behavior the pipeline was supposed to eliminate. Toolkeeper was supposed to auto-fetch files, but Haiku kept deciding "no tools needed." Self-research existed in concept but wasn't wired. And every question — including "what's your uptime?" — ran the full pipeline for 75 seconds because the agent-manager was disabled by default, hardcoding everything to moderate.

**Approach:** Four parallel agents built the features (skeptic micro-loop fix, 14 persona unit tests, cost tracking, self-research). Then a code review agent found two critical bugs: shell injection vectors in the command safety check and Toolkeeper silently dropping `_usage` metadata. The real debugging started when we tested live in Slack and found a chain of failures: `_project_path` was filtered out by the persona reads list (Toolkeeper ran in the wrong directory), enriched context made Haiku think it already had enough info, the self-research trigger condition was inverted, and agent-manager defaulting to OFF meant no classification happened at all.

The breakthrough was accepting that Toolkeeper's single-shot Haiku decision is fundamentally unreliable — it will always say "no tools needed" when it sees any context. Instead of fighting this, self-research now fires automatically on moderate+ whenever no tool output was gathered. Its iterative loop (see the file listing, pick a file, read it, decide if more is needed) is much more reliable than a single-shot "should I use tools?" decision.

**Outcome:** Simple questions ("uptime?") now respond in ~14 seconds with no pipeline. Moderate questions ("how does triage work?") read actual source code and give accurate, specific answers. Complex questions ("trace the full lifecycle") produce comprehensive multi-phase analyses with ASCII diagrams, decision point tables, and failure zone maps — all grounded in code the bot actually read. Tables render correctly in Slack via code blocks. 715 tests passing, up from 560 at session start.

**Insights:** The most interesting failure was how enriched context creates a confidence trap for small models. Haiku sees STATE.md mentioning "triage system" and thinks it knows enough — it has no concept of "this is a summary, not the source." Removing context from Toolkeeper's view was counterintuitive but necessary. The iterative self-research loop works better because each step grounds the model in actual file contents, breaking the false confidence cycle. Sometimes the fix isn't making the model smarter — it's making it see less until it has to look for itself.

---

## 2026-04-04 — Phased Orchestrator: 25 Personas Across 9 Phases

**Context:** The flat consultant model (infosec, architect, tester, visual-ux, output-editor) fired post-hoc after every response — no ability to shape the response before it shipped, no inter-persona communication, no revision loops. The 22-persona cognitive spec was complete but only 11 were implemented.

**Approach:** Designed a phased pipeline where personas are pure functions: `(declared_input_slots) → named_output_slot`. A shared typed dict (`TurnContext`) carries state between personas. Three-tier activation — simple tasks (greetings, renames) skip cognitive phases entirely (~$0.002). Moderate tasks (bug fixes, features) get lightweight Plan + Design pre-hoc and Challenge + Quality post-hoc (~$0.005). Complex tasks (architecture, refactors) get the full 9-phase pipeline with micro-loop revision where the Skeptic can send the Architect back to revise within the same turn (~$0.008-0.014).

The key insight was that micro-loops — not persona count — are the cost lever. Moderate gets the same personas as complex but in advisory mode (post-hoc, no revision loops). Complex enables pre-hoc revision where assumptions get challenged before the response ships.

Built via subagent-driven development: one fresh agent per task, spec compliance review + code quality review after each. 10 implementation commits, 25 persona files, pipeline core, and bot_unified integration.

**Outcome:** 549 tests (up from 467). 25 cognitive personas + 4 infrastructure agents across 9 phases. Seven self-healing feedback loops from immediate intra-turn revision to permanent CLAUDE.md rules. The pipeline is feature-gated (`pipeline: true` in projects.yaml) with the old consultant code as fallback. Full roster: Strategist, Historian, Researcher, Architect, Specialist, Data Scientist, Empathizer, Connector, Reuser, Dreamer, Insights, Growth Coach, Skeptic, Devil's Advocate, Simplifier, Prioritizer, Rogue, Hacker, Infosec, Inspector, Tester, Visual UX, Learner, Coach, Output Editor.

**Insights:** The communication model debate (message bus vs. event bus vs. pipeline) resolved cleanly: a for-loop with a dict beats pub/sub when phase ordering is already defined and max active personas per phase is 4-6. The operator's insight — "personas don't talk, they write 80-200 token JSON into named slots" — eliminated prose overhead and made the system debuggable. The Discussion Log in Slack now shows phase-grouped persona output, which is dramatically more readable than the flat list.

---

## 2026-04-02 — Token Cart complete: 393 tests, full agent team, journal wiring

**Context:** After the core Token Cart implementation (9 subsystems, 373 tests), three gaps remained from observer review: missing consultant roles, journal draft never consumed, and the visual UX story. Also needed to address inline code review in the post-call prompt, monthly Discussion rollups, and consultant client performance.

**Approach:** Dispatched parallel agents for non-conflicting work. Added tester and output-editor consultant roles with a singleton Anthropic client (previously creating a new client per call). Added visual UX/accessibility consultant that checks WCAG 2.x compliance, UX laws (Fitts's, Hick's, Miller's, Jakob's), and design system consistency via the project registry. Added inline code review to the post-call Haiku prompt (new `---REVIEW---` section marker). Added monthly Discussion rollup function. Wired journal posting to session lifecycle — a background cleanup thread detects idle sessions (10 minutes), polishes the accumulated journal draft via Sonnet, and posts to GitHub Discussions as weekly threads.

**Outcome:** 393 tests (up from 373). All observer findings addressed. The full Token Cart system is now wired end to end: context flows in (pre-call enrichment), gets compacted (post-call), persists across threads (external handoffs), corrections feed back to the registry, costs are tracked, consultants review when triggered, and journals get polished and posted when sessions end. Six consultant roles active: infosec, architect, tester, output-editor, visual-ux, plus gut check.

**Insights:** The journal wiring was the missing piece that closes the loop — without it, the journal draft accumulated in memory and evaporated when the session ended. The idle-timeout approach (10min, checked every 60s) is simple and reliable. The visual UX consultant is interesting because it bridges code review and design review — it reads the same project registry as other consultants but checks for entirely different things (contrast ratios, touch targets, platform conventions). Created three forward-looking issues: Computer Use (#15), Visual UX screenshots (#16), and Log Access (#17) — together these give agents eyes on code + UI + runtime.

---

## 2026-04-02 — Token Cart multi-agent system: spec to implementation in one session

**Context:** The bot replayed full conversation history on every API call — token consumption grew quadratically. Agents created duplicate components because they had no inventory of what existed. Corrections in one thread were forgotten by the next. The operator wanted a multi-tier agent system where cheap models handle structured work (compaction, review, classification) and expensive models focus on reasoning.

**Approach:** Designed and implemented a complete multi-agent system in a single session using subagent-driven development. Wrote the architecture spec first (1150 lines, Mermaid diagrams), then an implementation plan, then dispatched fresh implementer agents per subsystem with an observer agent reviewing quality between tasks. Nine subsystems built: Token Cart Core (Haiku pre/post enrichment replacing full-history replay), Project Registry (auto-populated `.shellack/registry.md`), Cross-Thread Persistence (handoffs survive thread death), Correction Feedback Loop (operator corrections auto-update registry), Cost Observability (per-turn spend in Churned block), Gut Check Agent (sanity check before posting), Channel Agent Teams (infosec + architect Sonnet consultants), Agent Manager (Haiku classifies complexity → selects Haiku/Sonnet/Opus per task), and Feature Configuration (runtime toggles via `@Shellack config`). Also built GitHub Discussions journal modules and Sonnet polisher (not yet wired to session lifecycle).

**Outcome:** 373 tests (up from 263), all passing. Every feature is opt-in and configurable per project via `projects.yaml` or runtime `@Shellack config` commands. Estimated 57%+ token savings on 10-turn threads. All Haiku/Sonnet API calls wrapped in try/except with graceful fallbacks — failures never block the main agent. Three-tier model hierarchy operational: Haiku ($0.25/MTok) for structured work, Sonnet ($3/MTok) for consultants and polish, Opus ($15/MTok) for reasoning.

**Insights:** The subagent-driven development pattern worked well for this — each subsystem was independent enough to dispatch as a self-contained task. The observer agent caught three issues the implementers missed (unused import, missing warning log, type hint mismatch). The correction feedback loop is deceptively powerful: a single "don't create custom CSS" from the operator propagates to every future thread via the registry. The key architectural decision was making everything bidirectional — agents consult each other freely, not in a pipeline. The gut check alone would have caught dozens of "agent creates a Modal when one exists" incidents from past sessions.

---

## 2026-04-02 — Haiku Token Cart architecture spec

**Context:** The bot replays full conversation history on every API call — token consumption grows quadratically. By turn 10, you're re-sending turns 1-9 every time. Additionally, agents create duplicate components because they don't have a reliable inventory of what exists, and corrections made in one thread are forgotten by the next.

**Approach:** Designed a multi-tier agent architecture around a persistent Haiku "Token Cart" — an always-on cheap model ($0.25/MTok) that tracks context, enriches reasoning model inputs, and maintains a living project registry. The system is bidirectional: agents consult each other freely, not in a waterfall pipeline. Key components: pre/post call enrichment, cross-thread external handoffs, auto-populated project registry (components, patterns, design tokens, architecture rules), correction feedback loop that auto-updates the registry, channel agent teams with core roles (infosec, architect, editor) and discoverable roles (tester, linter) bootstrapped from the project structure, a gut check agent for sanity checking before significant actions, an agent manager for intelligent parallel task dispatch across model tiers, and full cost observability.

**Outcome:** Spec complete at `docs/superpowers/specs/2026-04-02-haiku-sidecar-design.md` — 1150 lines covering architecture, handoff format, system prompts, cost analysis, configuration, and Mermaid diagrams. All features opt-in and configurable per project. Estimated 57%+ token savings on a 10-turn thread, increasing with longer conversations. Also created davesleal/Shellack#14 tracking LLM-driven agent transitions (research from a Salesforce AI Research repo).

**Insights:** The biggest design decision was making the communication model explicitly bidirectional. Early drafts had a pipeline feel — enrich → reason → compact. But the real value of cheap agents is that they can be consulted constantly, mid-turn, by anyone. "Consultation is cheap, mistakes are expensive" became the guiding principle. The project registry solves a problem that's hard to see from the code side — agents don't just need to know what files exist, they need to know what's *reusable* and what the *rules* are. A grep can find a Modal component; only the registry knows "always use this Modal, never create a custom one." Also: Slack free plan's 90-day history limit makes it unviable for persistent journaling. GitHub is the only reliable target.

---

## 2026-04-01 — XML leak fix + genericization cleanup

**Context:** Two loose ends from the genericization session. First, `run:` sessions via MaxBackend leaked raw `<function_calls>` XML into Slack messages — the streaming path had no filter while the single-turn path did. Second, the historical design and plan docs in `docs/superpowers/` still contained personal project names, paths, and identifiers across 9 files.

**Approach:** For the XML leak: moved the `_TOOL_XML_RE` regex into `slack_session.py` as a shared `_strip_tool_xml()`, applied in `_post_chunk()` before `_md_to_mrkdwn()` conversion. `project_agent.py` now imports from there instead of duplicating. Pure-XML chunks are silently dropped. For the docs cleanup: bulk sed across all specs and plans — project names genericized (Dayist→Alpha, TileDock→Beta, etc.), personal paths replaced, operator references neutralized. Added `automation` and `multi-agent` repo topics.

**Outcome:** Both output paths strip tool XML. 8 new tests for the XML filter, 263 total. All 9 superpowers docs cleaned — zero personal identifiers in any tracked file. GitHub issue #13 closed with all items resolved. Repo topics updated for discoverability.

**Insights:** The XML leak was a classic "two code paths, one got the fix" bug. The streaming path was added later and nobody thought to apply the same sanitization. The superpowers docs cleanup was pure mechanical grep-and-replace — the kind of thing that's boring but matters for anyone forking the repo. Historical design docs are the first thing a new contributor reads to understand *why* things are built the way they are, and seeing someone else's project names everywhere is disorienting.

---

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

