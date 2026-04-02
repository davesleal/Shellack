# Message UX Redesign

> **Date:** 2026-04-02
> **Status:** Approved

## Goal

Separate the thinking indicator from the response. Agent responses use structured `[think]/[action]/[reply]` tags. Reasoning renders as a collapsible block. The answer lands as a clean separate message. ThinkingIndicator updates every 1s. Long responses split across multiple messages.

## Problem

Currently `ThinkingIndicator.done(response=formatted)` stuffs "Churned for Xs" + reasoning + answer into one gray Slack attachment. Issues:
- Everything in one styled block — reasoning and answer mixed together
- Long responses hit Slack's ~4000 char limit with no splitting
- Indicator updates every 5s (sluggish feel)
- XML can leak through streaming chunk boundaries

## Tag System

Agent system prompts mandate structured prefixes in responses:

| Tag | Purpose | Rendering |
|---|---|---|
| `[think]` | Reasoning, internal deliberation | Collapsible code block in the Churned message |
| `[action]` | Status updates ("Reading files...", "Running tests...") | Inline in ThinkingIndicator during cycling |
| `[reply]` | Final answer for the operator | Clean separate plain-text message |
| No tag | Backward compatible fallback | Treated as `[reply]` |

An agent response may contain multiple sections:
```
[think] Let me read the relevant files to understand the auth system.
Found 3 files: auth.py, session.py, middleware.py.
The session module uses a deprecated pattern.

[reply] The auth system uses OAuth2 with refresh tokens. The session middleware
at `auth/middleware.py:42` has a deprecated pattern — it stores tokens in
cookies without the `SameSite` attribute. Here's how to fix it...
```

## Message Flow

```
1. User @mentions Shellack
2. Bot adds :claude: reaction to user's message
3. Bot posts ThinkingIndicator (clay-colored, cycling verbs every 1s)
4. Agent returns response
5. Parse tags → split into think/action/reply sections
6. Update ThinkingIndicator to gray:
   ✻ Churned for 12s · $0.014 (↑2.1k ↓890)
   
   💭 Reasoning
   ┄┄┄┄┄┄┄┄┄┄
   Let me read the relevant files...
   Found 3 files needing updates.
   The auth module uses a deprecated pattern.
   
7. Post [reply] content as separate plain-text message
8. If reply > 3500 chars, split across multiple messages
9. Remove :claude: reaction
```

## Collapsible Reasoning

The `[think]` block renders as a fenced code block in the Churned attachment. Slack auto-collapses code blocks over ~5 lines with a "Show more/less" toggle.

Format:
```
💭 Reasoning
┄┄┄┄┄┄┄┄┄┄┄┄┄┄
{think content here}
```

If `[think]` is absent or empty, the Churned block shows only the header line.

## Message Splitting

Slack caps messages at ~4000 characters. When `[reply]` content exceeds 3500 chars:

1. Never split inside a fenced code block (``` ... ```) — keep the entire block in one chunk
2. Split on paragraph boundaries (`\n\n`) where possible
3. If a single paragraph exceeds 3500, split on sentence boundaries (`. `)
4. If a code block alone exceeds 3500, post it as-is (Slack will truncate with "Show more")
5. Each chunk posted as a separate thread reply
6. No "continued..." markers — just clean consecutive messages

## ThinkingIndicator Changes

| Setting | Current | New |
|---|---|---|
| `_UPDATE_INTERVAL` | 5.0s | 1.0s |
| `done()` signature | `done(response, cost_summary)` | `done(think_block, cost_summary)` |
| Response in attachment | Full response crammed in | Only Churned header + think block |

The `done()` method no longer receives the full response. It receives only the optional `[think]` content to render as a collapsible block.

## Response Parser

New module `tools/response_parser.py` — parses tag-prefixed responses.

```python
@dataclass
class ParsedResponse:
    think: str       # [think] content (may be empty)
    actions: list    # [action] lines (may be empty)
    reply: str       # [reply] content (the answer)
```

Parsing rules:
- Scan for `[think]`, `[action]`, `[reply]` at start of line or after newline
- Content after a tag belongs to that section until the next tag
- If no tags found, entire text is `reply` (backward compatible)
- Multiple `[action]` lines are collected into a list
- `[think]` and `[reply]` take the last occurrence if duplicated

## System Prompt Update

Add to `ProjectAgent._build_system_prompt()`:

```
## Response Format
Structure your response with these tags:

[think] Your reasoning process — what you're considering, files you're reading,
decisions you're making. This is shown to the operator in a collapsible block.
Keep it concise — key observations only, not a stream of consciousness.

[reply] Your final answer to the operator. This is the main response they see.
Always include a [reply] section. Be direct and actionable.

If the task is simple and needs no reasoning, skip [think] and just use [reply].
```

## Streaming Path (run: sessions)

The `run:` path via `SlackSession` is **not changed** in this spec. The tag system applies only to the single-turn path (`handle_project_message → ProjectAgent.handle → quick_reply`).

The streaming path's XML leak fix (cross-chunk boundaries) is tracked separately.

## Files Changed

| File | Change |
|---|---|
| Create: `tools/response_parser.py` | `ParsedResponse` dataclass + `parse_response()` function |
| Modify: `tools/thinking_indicator.py` | `_UPDATE_INTERVAL` 5→1, `done()` takes `think_block` not `response` |
| Modify: `bot_unified.py` | Parse response tags, post reply separately, split long messages |
| Modify: `agents/project_agent.py` | Add tag instructions to system prompt |
| Create: `tests/test_response_parser.py` | Parser unit tests |
| Modify: `tests/test_thinking_indicator.py` | Updated done() signature tests |

## Fallback Behavior

- No tags in response → entire text is `[reply]` → posted as separate message
- `[think]` only, no `[reply]` → think goes in Churned block, no separate message
- `[reply]` only → no collapsible block, just the answer
- Tag parsing failure → treat as no-tag fallback

## Feature Gate

No feature gate — this is a rendering change, not an optional feature. All projects get the improved UX.
