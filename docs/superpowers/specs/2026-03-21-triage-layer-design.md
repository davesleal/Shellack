# Triage Layer Design

**Goal:** Automatically classify every incoming Shellack request and route it to the appropriate Claude model and session type — eliminating the `run:` requirement for most users while keeping API costs proportional to task complexity.

**Architecture:** A lightweight Haiku classifier (`tools/triage.py`) runs before every `api` mode request. It returns a `TriageResult` with tier, model, and reason. `handle_project_message` uses this to pick between `quick_reply` (single-turn) and `SlackSession` (streaming, multi-turn). Max mode is unaffected.

**Tech Stack:** Python, Anthropic SDK (Haiku for triage), existing `APIBackend` / `SlackSession` infrastructure.

---

## Data Flow

```
Incoming message
      │
      ▼
  run: prefix? ──yes──▶ SlackSession (skip triage, existing behavior)
      │ no
      ▼
  api mode?
  ├── yes ──▶ triage.classify(prompt, project_key)
  │               │ TriageResult{tier, model, reason}
  │               ▼
  │           tier == complex?
  │           ├── yes ──▶ SlackSession(APIBackend(model=triaged_model))
  │           └── no  ──▶ quick_reply(model=triaged_model)
  └── no  ──▶ existing max behavior (quick_reply via CLI, triage skipped)
```

---

## Tier → Model Mapping

| Tier | Model | Examples |
|---|---|---|
| simple | claude-haiku-4-5-20251001 | Questions, lookups, explanations, status checks |
| moderate | claude-sonnet-4-6 | Code review, analysis, debugging help, single-file changes |
| complex | claude-sonnet-4-6 | Multi-file edits, refactors, long debugging, architecture work |

Complex tasks use Sonnet (not Opus) as the cost-conscious default. Opus can be introduced as a configurable option later.

---

## Components

### New: `tools/triage.py`

Single public function:

```python
@dataclass
class TriageResult:
    tier: str    # "simple" | "moderate" | "complex"
    model: str   # full model ID
    reason: str  # one sentence, for logging only

def classify(prompt: str, project_key: str = "") -> TriageResult:
    ...
```

Calls Haiku directly via Anthropic SDK (not through `quick_reply` to avoid backend confusion).

**Triage prompt:**
```
Classify this developer request. Reply with JSON only, no prose.
{"tier": "simple|moderate|complex", "reason": "one sentence"}

simple   = question, explanation, lookup, read-only, status check
moderate = code review, analysis, single-file change, debugging help
complex  = multi-file edits, refactor, long debugging, architecture work

Request: {prompt}
```

**Error handling:** Any failure (API error, malformed JSON, timeout) silently returns a safe default — `moderate / claude-sonnet-4-6` — so the bot always responds.

**Logging:** Triage result printed to terminal only:
```
🔍 Triage: complex → claude-sonnet-4-6 — "multi-file auth refactor"
```

### New: `tests/test_triage.py`

Unit tests covering:
- Simple request → haiku
- Moderate request → sonnet
- Complex request → sonnet + complex tier
- API error → safe default (sonnet/moderate)
- Malformed JSON → safe default

All tests mock the Anthropic client — no real API calls.

### Modified: `tools/session_backend.py`

`quick_reply` gains an optional `model` parameter:

```python
def quick_reply(
    prompt: str,
    system_prompt: str = "",
    cwd: str = ".",
    model: str | None = None,   # ← new, overrides SESSION_MODEL env var
) -> str:
```

Falls back to `SESSION_MODEL` env var when `None`. No other changes.

### Modified: `bot_unified.py` — `handle_project_message`

Routing logic added after the `run:` check (which remains in `handle_mention`, untouched):

```python
backend_mode = os.environ.get("SESSION_BACKEND", "api")
triage_result = None

if backend_mode == "api":
    triage_result = classify(prompt, project_key)
    print(f"🔍 Triage: {triage_result.tier} → {triage_result.model} — \"{triage_result.reason}\"")

if triage_result and triage_result.tier == "complex":
    # Start interactive session with triaged model
    backend = APIBackend(model=triage_result.model)
    session = SlackSession(...)
    session.start(prompt, system_prompt, cwd)
    return

model = triage_result.model if triage_result else None
response, label = agent.handle(prompt, context, model=model)
```

The rest of `handle_project_message` (ack message, `:claude:` reaction, canvas routing, lifecycle) is unchanged.

---

## Error Handling

| Failure | Behaviour |
|---|---|
| Triage API error | Log warning, use `moderate/sonnet` default |
| Malformed JSON from Haiku | Log warning, use `moderate/sonnet` default |
| Triage timeout | Log warning, use `moderate/sonnet` default |

Triage failures are never surfaced to Slack — the request always proceeds.

---

## What Does Not Change

- `run:` prefix in `handle_mention` — still forces `SlackSession`, no triage
- Max mode — triage skipped entirely, CLI handles everything
- All lifecycle posts, canvas routing, reactions — untouched
- `ProjectAgent.handle()` interface — unchanged except optional `model` passthrough

---

## Testing Strategy

- `test_triage.py` — unit tests, all Anthropic calls mocked
- `test_project_agent.py` — verify `model` kwarg flows through correctly
- `test_usage_integration.py` — verify triage is called in api mode, skipped in max mode
- No integration tests requiring real API calls
