# Specialized Product Agents — Design Spec
**Date:** 2026-03-18
**Status:** Approved
**Author:** Dave Leal + Claude Code

---

## Overview

Upgrade SlackClaw's per-project agents from generic Claude wrappers into fully specialized, context-aware agents with lifecycle tracking, GitHub integration, staged peer review, and per-project journaling. Each agent knows its project deeply, manages its own work lifecycle, and hands off to the review pool before posting "Done."

---

## Goals

- Each project agent carries its project's `CLAUDE.md` as part of its system prompt
- Agents post structured lifecycle updates to the active Slack thread as work progresses
- Bugs and crashes auto-create GitHub issues in the correct repo; issue is closed on task completion
- After completing any task that produced a code change or GitHub issue, agents trigger staged peer review in `#code-review`
- Each project maintains a narrative `JOURNAL.md` for blog-post-ready progress tracking
- On completion: `STATE.md`, `docs/JOURNAL.md` (SlackClaw), and README (if new capability added) are updated

---

## Architecture

### Agent Lifecycle (per task)

```
User message in #project-dev
        ↓
ProjectAgent.handle(prompt, thread_context)
        ↓
1. 🔵 LifecycleNotifier.started(task_summary)
2. CLAUDE.md already prepended to system prompt at init
3. detect_sub_agent(prompt) → task type (crash/review/test/docs/general)
4. If crash/bug → GitHubClient.create_issue() → 🐛 LifecycleNotifier.issue_created(url, number)
5. Run sub-agent or main agent → 🔨 LifecycleNotifier.in_progress(detail)
6. If agent detects it is blocked → 🙋 LifecycleNotifier.needs_human(reason) → stop
7. On response complete AND (code changed OR issue created):
   a. 👀 LifecycleNotifier.pending_review()
   b. StagedPeerReview.trigger(summary, changed_files, project_key, channel_id, thread_ts)
   c. GitHubClient.close_issue() if issue was opened this session
8. ✅ LifecycleNotifier.done(summary)
9. JournalWriter.append_entry(...) — only if code changed or issue created
10. Update STATE.md + docs/JOURNAL.md (always); update README (only if new capability added)
```

**"Significant task"** = any task that resulted in a code change OR a GitHub issue being created. General questions and explanations do not trigger journal writes or peer review.

**"Code changed" detection:** Inferred from task type — `CrashInvestigatorAgent` and `TestingAgent` responses are always treated as potential code changes. `DocsAgent` and general agent responses are treated as code changes only if the Claude response contains at least one fenced code block (triple backtick). `CodeReviewAgent` does not trigger peer review (it IS a review).

**Review timing:** Stage 1 is fire-and-forget — the agent posts `pending_review`, fires the review, then immediately posts `done`. It does not block waiting for review results. If Stage 1 flags a blocking issue, `#code-review` posts `🙋 @Dave` in that thread independently.

**Failure state:** If any step throws an uncaught exception, `LifecycleNotifier.failed(error)` posts `❌ Failed: {error}` to the thread. GitHub issues created before failure remain open.

**AgentFactory cache eviction:** MVP — agents are in-memory keyed by `thread_ts`. Cache resets on bot restart. No TTL in MVP; acceptable because bots are restarted regularly and threads are naturally short-lived. Long-running deployments should add a 24h TTL in a future iteration.

---

### Task Type Detection

Uses existing `detect_sub_agent(prompt)` in `agents/sub_agents.py` — keyword matching:

| Keywords | Sub-agent | GitHub label |
|----------|-----------|--------------|
| crash, exception, signal, bug | `CrashInvestigatorAgent` | `crash`, `bug` |
| investigate | `CrashInvestigatorAgent` | `bug` (note: false positives on generic use of "investigate" are acceptable in MVP) |
| review, pr, pull request | `CodeReviewAgent` | `review` |
| test, testing, coverage | `TestingAgent` | `testing` |
| doc, document, readme, claude.md | `DocsAgent` | `documentation` |
| (none of above) | Main `ProjectAgent` | — |

General/question tasks (no keyword match) → main agent, no GitHub issue, no journal entry.

---

### Staged Peer Review

**Artifact posted to `#code-review`:** Agent summary (what was done, why, key decisions) + list of changed files. The original project thread posts a link to the `#code-review` thread.

**Stage 1 (immediate, automatic):**
- `StagedPeerReview` (new class in `peer_review.py`) wraps `PeerReviewCoordinator`
- Calls `PeerReviewCoordinator.review_pr(pr_data)` — extended to enforce structured JSON output via system prompt so blocking detection is reliable (not brittle regex)
- Posts results as replies in a new `#code-review` thread
- If any reviewer marks a finding as blocking → posts `🙋 @Dave` in the `#code-review` thread

**Stage 2 (async, immediately after Stage 1):**
- Maestro identifies agents with tech overlap (same `platform` or `language` from `orchestrator_config.py`)
- Posts a message to `#code-review` @mentioning the SlackClaw bot with a routing prefix indicating which project agent should respond (e.g., `[dayist-review] @SlackClaw please review...`). The existing channel-based dispatch in `bot_unified.py` picks this up and routes to the correct project agent.
- Tags up to 2 relevant project agents this way
- No timeout — Stage 2 is best-effort

**Note on "tagging an agent":** Project agents are not separate Slack users — they are all the same SlackClaw bot. Stage 2 works by posting a prefixed message in `#code-review` that the bot's dispatcher recognises and routes to the correct `ProjectAgent` instance.

**Escalation:**
- Stage 1 blocking finding → `🙋 @Dave` in `#code-review` thread
- Agent stuck mid-task → `🙋 @Dave` in the original project thread

---

### Channel-Level Visibility (Cross-posting)

For each significant event, the agent posts a **top-level message to the project channel** (not in the thread). This keeps threads for detailed work and channels for scannable status — so Claude app can read any project channel and immediately understand what's happening across the workspace.

**Events that surface to the channel:**

| Event | Top-level post format |
|-------|----------------------|
| Issue created | `🐛 [Dayist] Issue #42 opened: "Login crash on iPhone 15" → <thread link> <github link>` |
| Peer review triggered | `👀 [Dayist] Peer review requested → <thread link> \| #code-review` |
| Escalation | `🙋 [Dayist] @Dave — input needed → <thread link>` |
| Task done | `✅ [Dayist] Done: login crash fixed, issue #42 closed → <thread link>` |

**What does NOT get a channel post:** `started`, `in_progress` — these stay in-thread only.

`LifecycleNotifier` handles both the thread post and the channel-level post for each qualifying event. The channel-level post uses the same `channel_id` but with `thread_ts=None` (top-level).

---

### CLAUDE.md Loading

At `ProjectAgent.__init__()`:
1. Resolve path: `{project_path}/CLAUDE.md`
2. If file exists: read contents, prepend to system prompt under `## Project Rules (from CLAUDE.md)`
3. If file missing: log warning `"CLAUDE.md not found for {project_name}"`, continue without it — no Slack notification

---

### Project Journals

**Location resolution (in order):**
1. If `{project_path}/docs/JOURNAL.md` exists → append there
2. If `{project_path}/JOURNAL.md` exists → append there
3. Neither exists → create `{project_path}/docs/JOURNAL.md` (create `docs/` dir if needed)

**Entry format:**
```markdown
## YYYY-MM-DD — {Task Title}

**Context:** What was reported / what triggered this task.

**Approach:** How the agent investigated or implemented.

**Outcome:** What was resolved or built. GitHub issue #N if applicable.

**Insights:** Anything interesting, surprising, or worth sharing — suitable for a blog post.

---
```

---

## Components

### New Files

#### `tools/__init__.py`
Empty — makes `tools/` a Python package, required for imports.

#### `tools/github_client.py`

```python
class GitHubClient:
    def __init__(self, token: str)
    def create_issue(self, project_key: str, title: str, body: str, task_type: str) -> dict
        # Routes to correct repo via PROJECTS[project_key]["github_repo"]
        # Returns {"number": int, "url": str}
        # Error handling: logs + returns None on auth/rate limit failure
        # No duplicate detection in MVP — that's a future concern
    def close_issue(self, project_key: str, issue_number: int) -> bool
```

**Label taxonomy:**

| Task type | Labels applied |
|-----------|---------------|
| crash | `crash`, `bug`, `{platform}` |
| bug/investigate | `bug`, `{platform}` |
| review | `review` |
| test | `testing` |
| docs | `documentation` |

Platform labels: `ios`, `macos`, `server`

**Error handling:** On any GitHub API error (auth, rate limit, network), log the error and return `None`. Lifecycle continues — the agent does not halt if issue creation fails. Post a note to the thread: `⚠️ Could not create GitHub issue: {reason}`.

#### `tools/lifecycle.py`

```python
class LifecycleNotifier:
    def __init__(self, app: App, channel_id: str, thread_ts: str,
                 project_name: str, dave_user_id: str)
    # Thread-only (no channel post):
    def started(self, summary: str)        # 🔵 Started: {summary}
    def in_progress(self, detail: str)     # 🔨 {detail}
    def failed(self, error: str)           # ❌ Failed: {error}
    # Thread + top-level channel post:
    def issue_created(self, url: str, number: int)   # 🐛 thread + channel
    def pending_review(self, thread_link: str)        # 👀 thread + channel
    def done(self, summary: str, issue_number: int = None)  # ✅ thread + channel
    def needs_human(self, reason: str)     # 🙋 thread + channel (@Dave)
```

`project_name` used in channel-level post prefix (e.g. `[Dayist]`).
`dave_user_id` sourced from `DAVE_SLACK_USER_ID` env var, used in `needs_human()`.
Channel-level posts use `channel_id` with `thread_ts=None` (top-level).

#### `tools/journal_writer.py`

```python
class JournalWriter:
    def __init__(self, project_path: str)
    def append_entry(self, title: str, context: str, approach: str,
                     outcome: str, insights: str, issue_number: int = None)
    # Resolves journal path (see location resolution above)
    # Creates dirs as needed
    # Appends formatted entry with today's date
```

### Modified Files

#### `orchestrator_config.py`
Add `github_repo` to each project entry:
```python
"dayist":       {"github_repo": "davesleal/Dayist", ...},
"nova":         {"github_repo": "davesleal/NOVA", ...},
"nudge":        {"github_repo": "davesleal/Nudge", ...},
"tiledock":     {"github_repo": "davesleal/TileDock", ...},
"atmosuniversal": {"github_repo": "davesleal/atmos-universal", ...},
"sideplane":    {"github_repo": "davesleal/SidePlane", ...},
"slackclaw":    {"github_repo": "davesleal/SlackClaw", ...},
```

#### `agents/project_agent.py`
Constructor signature:
```python
def __init__(self, project_key: str, project_config: dict, client: Anthropic,
             app: App, channel_id: str, thread_ts: str)
```
- Loads `CLAUDE.md` and prepends to system prompt
- Constructs `LifecycleNotifier(app, channel_id, thread_ts, dave_user_id)`
- Constructs `GitHubClient(github_token)`
- Constructs `JournalWriter(project_config["path"])`
- `handle()` orchestrates full lifecycle per spec above

#### `agents/agent_factory.py`
`get_agent(project_key, project_config, app, channel_id, thread_ts)` — note agents are now per-thread (not per-project), since `channel_id` and `thread_ts` vary per conversation.

#### `bot_unified.py`
Pass `app`, `channel_id`, `thread_ts` when calling `agent_factory.get_agent()`.

### New Config

#### `SlackClaw/CLAUDE.md` (Maestro instructions)

Contents to be written covering:
- **Role:** Orchestrator across all Leal Labs projects — Dayist, NOVA, Nudge, TileDock, Atmos, SidePlane, SlackClaw
- **Channel routing:** which channel maps to which project and agent
- **GitHub standards:** issue title format `[Type] Brief description`, label taxonomy, severity (crash = P0, bug = P1, feature = P2)
- **Escalation rules:** when to tag @Dave (blocking peer review finding, ambiguous scope, security issue, task failure)
- **Peer review protocol:** always trigger after code changes; Stage 1 auto, Stage 2 tag agents with same platform
- **Journal standards:** narrative tone, entry must include insights suitable for a blog post
- **Completion checklist:** STATE.md → docs/JOURNAL.md → README (if new capability)

---

## Environment Additions

`.env` / `.env.example`:
```
GITHUB_TOKEN=ghp_your_token_here      # Needs 'repo' scope for issue creation
DAVE_SLACK_USER_ID=<your-slack-user-id>  # Used in @mention escalations; find via Slack profile
```

---

## Interface Contracts

| Class | Constructed by | Receives at init |
|-------|---------------|------------------|
| `LifecycleNotifier` | `ProjectAgent.__init__` | `app`, `channel_id`, `thread_ts`, `dave_user_id` |
| `GitHubClient` | `ProjectAgent.__init__` | `GITHUB_TOKEN` from env |
| `JournalWriter` | `ProjectAgent.__init__` | `project_path` |
| `StagedPeerReview` | `ProjectAgent.__init__` | `app`, `code_review_channel_id` (from env or hardcoded `"code-review"`) |

`StagedPeerReview.trigger(summary, changed_files, project_key, origin_thread_ts)` — called from `ProjectAgent.handle` when review is warranted.

`AgentFactory.get_agent()` creates a new `ProjectAgent` per thread (keyed by `thread_ts`), not per project, since lifecycle context is thread-scoped. MVP: cache is in-memory and clears on restart. No TTL required for MVP.

---

## Sub-agent → GitHub Label Mapping

```
detect_sub_agent(prompt) → sub-agent class → label(s)
CrashInvestigatorAgent → ["crash", "bug", platform]   # also triggers peer review
CodeReviewAgent        → ["review"]                    # does NOT trigger peer review (it is review)
TestingAgent           → ["testing"]                   # also triggers peer review
DocsAgent              → ["documentation"]             # triggers peer review only if response contains code block
None (general)         → no issue created              # triggers peer review only if response contains code block
```

#### `peer_review.py` (modified)
- Add `StagedPeerReview` class wrapping `PeerReviewCoordinator`
- Extend `PeerReviewCoordinator` reviewers to output structured JSON (enforce via system prompt) so blocking detection is reliable
- `StagedPeerReview.trigger()` orchestrates Stage 1 + Stage 2 and posts to `#code-review`

---

## Out of Scope (Backlog)

- Slack Canvas board echoing GitHub issue state (#11)
- Slack Lists / Tasks tab API integration
- Automatic PR creation from agent fixes
- Duplicate GitHub issue detection
- Cross-project pattern detection

---

## Success Criteria

- [ ] Each project agent's system prompt includes `CLAUDE.md` content (or logs warning if missing)
- [ ] Bug/crash messages auto-create a GitHub issue with correct repo, labels, and platform tag
- [ ] GitHub issue is closed when agent posts `done`
- [ ] Lifecycle posts (`🔵 🐛 🔨 👀 ✅ / 🙋 / ❌`) appear in Slack thread at each stage
- [ ] High-signal events (`🐛 👀 ✅ 🙋`) also post top-level to project channel for Claude app visibility
- [ ] Tasks producing code changes or issues trigger Stage 1 peer review in `#code-review`
- [ ] Maestro tags ≤2 relevant project agents for Stage 2 review based on platform/language overlap
- [ ] `@Dave` tagged in project thread when blocked; in `#code-review` when review is blocking
- [ ] Project `JOURNAL.md` gets a narrative entry after significant work (code change or issue created)
- [ ] `STATE.md` and `docs/JOURNAL.md` updated on every task completion
- [ ] `SlackClaw/CLAUDE.md` written with full maestro coordination protocol
