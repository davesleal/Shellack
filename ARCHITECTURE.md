# Shellack Architecture

Modular unified bot with channel-based routing and a multi-tier agent system.

## System Overview

```
Shellack Unified Bot (single process)
│
├─ Token Cart (Haiku — always on)
│  ├─ Pre-call context enrichment
│  ├─ Post-call compaction (async)
│  ├─ Gut check before posting
│  ├─ Correction detection → registry updates
│  └─ Cross-thread persistence
│
├─ Project Agents (per channel)
│  ├─ #project-a-dev → Agent + team
│  │  ├─ Primary: Opus (reasoning)
│  │  ├─ Token Cart: Haiku (context)
│  │  ├─ Infosec: Sonnet (security review)
│  │  └─ Architect: Sonnet (structure review)
│  └─ .shellack/registry.md (patterns + rules)
│
├─ Agent Manager (opt-in)
│  └─ Classifies complexity → selects model tier
│
├─ Orchestrator
│  └─ #shellack-central (cross-project coordination)
│
└─ Peer Review
   └─ #code-review (staged review agents)
```

## Three-Tier Model Hierarchy

| Model | Role | Cost (per MTok) |
|---|---|---|
| **Haiku 4.5** | Token Cart — compaction, enrichment, gut check, corrections | $0.25 / $1.25 |
| **Sonnet 4.6** | Consultants, journal polish, output editing | $3 / $15 |
| **Opus 4.6** | Primary reasoning — main agent work | $15 / $75 |

## Turn Lifecycle

```
1. User @mentions Shellack in a project channel
2. :claude: reaction added
3. ThinkingIndicator posts (clay-colored, cycling verbs)
4. Token Cart pre-call: enriches context from handoff + registry
5. Agent Manager: classifies complexity, selects model (opt-in)
6. ProjectAgent.handle(): runs reasoning model
7. Gut check: Haiku sanity-checks against registry
8. Consultants: infosec/architect review if triggered
9. ThinkingIndicator.done(): gray block with "Churned for Xs · $cost"
10. :claude: reaction removed
11. Post-call (async): Haiku compacts → handoff, journal, thread memory
12. Correction detection (async): updates registry if operator corrected agent
```

## Channel Routing

Configured in `projects.yaml` (gitignored). The bot routes based on channel name:

```
if channel == "shellack-central"  → orchestrator.handle()
elif channel == "code-review"     → peer_review.handle()
elif channel in CHANNEL_ROUTING   → handle_project_message()
```

## Token Cart Flow

```
Turn N:
  handoff_N-1 + prompt + registry
      ↓
  Haiku pre-call → enriched context (relevant context only)
      ↓
  Reasoning model (Opus/Sonnet) → response
      ↓
  Haiku gut check → PROCEED or CONCERN
      ↓
  Sonnet consultants → security/architecture findings (if triggered)
      ↓
  Response posted to Slack
      ↓
  Haiku post-call (async) → handoff_N + journal draft
      ↓
  Thread memory persisted to .shellack/thread-memory/
```

## Feature Configuration

All features opt-in via `projects.yaml` or runtime `@Shellack config`:

| Feature | Default | Description |
|---|---|---|
| `token-cart` | on | Context compaction between turns |
| `external-handoff` | on | Cross-thread persistence |
| `gut-check` | on | Sanity check before posting |
| `consultants` | on | Infosec + architect review |
| `registry` | on | Auto-maintained pattern index |
| `cost-observability` | on | Token spend tracking |
| `code-review` | on | Inline self-healing review |
| `agent-manager` | **off** | Complexity-based model selection |

## Key Files

```
Shellack/
├── bot_unified.py              # Main bot — entry point, routing, wiring
├── orchestrator_config.py      # YAML loader for projects.yaml
├── projects.yaml               # YOUR config (gitignored)
├── projects.example.yaml       # Template with full schema
├── agents/
│   ├── agent_factory.py        # Per-channel agent cache + warmup
│   ├── project_agent.py        # ProjectAgent with CLAUDE.md context
│   └── sub_agents.py           # Crash / Testing / Review / Docs
├── tools/
│   ├── token_cart.py           # Haiku context compaction + gut check
│   ├── registry.py             # .shellack/registry.md management
│   ├── thread_memory.py        # Cross-thread persistence
│   ├── cost_tracker.py         # Per-turn/thread cost tracking
│   ├── consultants.py          # Infosec + architect consultants
│   ├── agent_manager.py        # Complexity classification + model selection
│   ├── github_journal.py       # GitHub Discussions journal posting
│   ├── journal_polisher.py     # Sonnet journal polish
│   ├── session_backend.py      # APIBackend + MaxBackend + quick_reply()
│   ├── slack_session.py        # run: session lifecycle + canvas routing
│   ├── thinking_indicator.py   # Animated Slack indicator
│   ├── lifecycle.py            # Structured Slack status posts
│   ├── github_client.py        # Issue creation & management
│   └── self_improver.py        # Auto-update CLAUDE.md on recovered blocks
├── hooks/pre-commit            # Secret scanning (16 patterns)
└── tests/                      # 373 tests
```

## Adding New Projects

1. Edit `projects.yaml`:
```yaml
projects:
  myapp:
    name: MyApp
    primary_channel: myapp-dev
    language: swift
    platform: ios
    github_repo: your-org/MyApp
    path: ~/Repos/MyApp
```

2. Create and invite:
```
/create #myapp-dev
/invite @Shellack
```

3. Restart the bot. The agent bootstraps automatically.

## Persistence

| Data | Storage | Lifespan |
|---|---|---|
| Internal handoffs | In-memory (`active_sessions`) | Thread lifetime |
| External handoffs | `.shellack/thread-memory/` | Across threads |
| Project registry | `.shellack/registry.md` | Permanent |
| Journal drafts | In-memory → GitHub Discussions | Session → permanent |
| Usage stats | `usage.json` | Monthly reset |

## Security

- Pre-commit hook: 16 secret patterns (Slack tokens, API keys, AWS, GitHub, private keys)
- Owner-only gates: plugin/MCP/config commands fail-closed when `OWNER_SLACK_USER_ID` is unset
- Triage: system prompts separated from user input
- Error messages: sanitized, no exception details leak to Slack
- Self-improver: opt-in, rules sanitized (length cap, suspicious patterns, non-ASCII rejection)
