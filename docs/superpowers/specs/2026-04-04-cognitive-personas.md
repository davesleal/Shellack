# Cognitive Personas — Agent Team Architecture

> **Date:** 2026-04-04
> **Status:** Approved

## Overview

21 cognitive personas that model the full human thought process. Each persona is a lightweight Haiku or Sonnet call that activates conditionally based on trigger detection. The primary reasoning model (Opus/Sonnet) remains the coder — the personas sharpen its output.

## The Full Roster

| # | Persona | Emoji | Role | Model | Trigger |
|---|---------|-------|------|-------|---------|
| 1 | **Observer** | 👁️ | Tracks thread context, appends per turn | Haiku | Every turn |
| 2 | **Historian** | 📜 | Checks git history, past decisions, previous STATE.md. Prevents repeating mistakes | Haiku | When proposing changes to existing code |
| 3 | **Empathizer** | 🫂 | End-user perspective. How does the person using this feel? What's confusing? | Haiku | UI/UX changes, user-facing features |
| 4 | **Strategist** | 🎯 | Big picture planning. Sequences work, identifies dependencies, maps the path from here to shipped | Haiku | Multi-step tasks, roadmap questions |
| 5 | **Prioritizer** | ⚖️ | Impact-to-effort ratio. Which of 5 options do we pick? Prevents analysis paralysis | Haiku | When multiple options presented |
| 6 | **Monetization Coach** | 💰 | Revenue lens. Free vs premium? Conversion impact? LTV? A/B test opportunity? | Sonnet | New features, pricing, onboarding flows |
| 7 | **Architect** | 📐 | Structure, API design, data models, dependency decisions | Sonnet | New modules, schema changes, refactors |
| 8 | **Skeptic** | 🤨 | Second-guesses the approach. "Are we sure? What about X?" | Haiku | After any plan or proposal |
| 9 | **Devil's Advocate** | 👹 | Argues the opposite. "What if we should NOT do this at all?" | Haiku | Major architecture or product decisions |
| 10 | **Simplifier** | ✂️ | Fights complexity. "Can we do this in half the code?" YAGNI enforcer | Haiku | When solution seems overengineered |
| 11 | **Researcher** | 🌐 | Web lookups. API docs, library versions, best practices, compatibility | Sonnet + Web | When referencing external APIs/libraries |
| 12 | **Data Scientist** | 📊 | Scale analysis, query patterns, data modeling, metrics | Haiku | Data models, performance, analytics |
| 13 | **Rogue** | 😈 | Stress tester. "What if 10k concurrent requests? What if the payload is 50MB?" | Haiku | After implementation proposals |
| 14 | **Hacker** | 🏴‍☠️ | Red team. Injection, abuse, privilege escalation, data exfiltration, rate limit bypass | Haiku | Code changes touching auth, input, APIs |
| 15 | **Infosec** | 🛡️ | Defensive security. Input validation, secrets handling, CORS, CSRF | Sonnet | Code touching auth, crypto, user input |
| 16 | **Inspector** | 🔍 | Completeness check. Edge cases, missing returns, unclosed resources | Haiku | After code changes |
| 17 | **Tester** | 🧪 | Test coverage, assertion quality, test isolation, mocking strategy | Sonnet | After code changes |
| 18 | **Visual UX** | 🎨 | WCAG accessibility, UX laws, design system compliance, platform conventions | Sonnet | UI code changes |
| 19 | **Specialist** | 🧬 | Language/framework idioms. Knows the "right" way in Swift, React, Python. Consults registry | Haiku | All code output |
| 20 | **Connector** | 🔗 | Cross-project pattern recognition. "This is similar to how we solved X in project B" | Haiku | Novel problems, architecture decisions |
| 21 | **Reuser** | ♻️ | Holistic reuse thinker. "This already exists in utils/. We built this last week. Extract this into a shared component." Prevents redundant work, enforces DRY, and ensures adopted libraries are used consistently (SWR not useEffect+fetch, Zod not manual validation). Consults the project registry | Haiku | All code output |
| 22 | **Coach** | 💪 | Confidence. "This approach is solid because X. Ship it." Blocks over-hedging and imposter syndrome | Haiku | When agent is deferring or over-qualifying |

**Plus the infrastructure agents:**

| Agent | Emoji | Role |
|-------|-------|------|
| File Fetcher | 📂 | Reads project files on demand |
| Token Cart | 🛒 | Context compaction and enrichment |
| Output Editor | ✍️ | Polish for external outputs (GitHub, docs, journals) |
| Agent Manager | 📋 | Complexity classification, model selection |

## Cognitive Flow

```
Stimulus arrives
  👁️  Observe — what's happening, track context
  📜  Remember — have we been here before?
  🫂  Empathize — how does the user feel about this?
  🎯  Strategize — what's the plan, what's the sequence?
  ⚖️  Prioritize — what matters most right now?
  💰  Monetize — how does this make/save money?
  📐  Architect — how should this be built?
  🤨  Question — are we sure about this?
  👹  Challenge — should we even do this?
  ✂️  Simplify — can we do less?
  🌐  Research — what do the docs/web say?
  📊  Analyze — will this scale? what do numbers say?
  🧬  Specialize — what's the idiomatic way?
  😈  Stress — what breaks under load?
  🏴‍☠️ Attack — how would a bad actor exploit this?
  🛡️  Defend — how do we protect against that?
  🔍  Inspect — did we miss anything?
  🧪  Test — is this covered?
  🎨  Design — is this accessible and well-designed?
  🔗  Connect — where have we seen this pattern?
  ♻️  Reuse — does this already exist? extract and share
  💪  Commit — this is solid, ship it
  ✍️  Polish — clean for humans
```

## Activation Rules

Not every persona fires on every turn. The Token Cart / Observer detects which are relevant:

- **Always active:** Observer, Token Cart, File Fetcher
- **Every code change:** Inspector, Specialist, Tester
- **Every proposal:** Skeptic, Simplifier, Coach
- **Conditionally:** all others based on trigger patterns

Maximum personas per turn: **4** (plus always-active). Prevents latency explosion.

## Cost Model

- 15 Haiku personas × ~$0.0005/call = $0.0075 if ALL fired (they won't)
- 6 Sonnet personas × ~$0.005/call = $0.03 if ALL fired (they won't)
- Typical turn: 2-3 personas fire = ~$0.002
- Always-active (observer, cart): ~$0.002/turn

## Implementation Status

### Implemented
- 👁️ Observer (thread_observer.py)
- 📂 File Fetcher (file_fetcher.py)
- 🛒 Token Cart (token_cart.py)
- ✅ Gut Check (token_cart.py — becoming Skeptic + Inspector)
- 🛡️ Infosec (consultants.py)
- 📐 Architect (consultants.py)
- 🧪 Tester (consultants.py)
- 🎨 Visual UX (consultants.py)
- ✍️ Output Editor (consultants.py)
- 📋 Agent Manager (agent_manager.py)
- 💪 Coach (partially — in system prompt)

### To Implement
- 📜 Historian
- 🫂 Empathizer
- 🎯 Strategist
- ⚖️ Prioritizer
- 💰 Monetization Coach
- 🤨 Skeptic (upgrade from gut check)
- 👹 Devil's Advocate
- ✂️ Simplifier
- 🌐 Researcher
- 📊 Data Scientist
- 😈 Rogue
- 🏴‍☠️ Hacker
- 🔍 Inspector
- 🧬 Specialist
- 🔗 Connector

## Discussion Transparency

All persona activations appear in the Agent Discussion block:

```
💬 Agent Discussion
👁️ User asking about Phase 3 migration
📂 Loaded socialService.ts, followService.ts
📜 Last migration (Phase 2) took 3 commits, no rollback issues
🤨 Schema proposal looks solid but check Firestore subcollection paths
🧬 In Supabase, use RLS policies not application-level auth checks
💪 Migration plan is complete. Ship the schema file.
```
