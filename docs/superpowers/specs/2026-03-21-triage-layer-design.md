# Triage Layer Design

**Goal:** Automatically classify every incoming Shellack request and route it to the appropriate Claude model and session type — eliminating the `run:` requirement for most users while keeping API costs proportional to task complexity.

**Architecture:** A lightweight Haiku classifier (`tools/triage.py`) runs before every `api` mode request in `handle_project_message`. It returns a `TriageResult` with tier, model, and reason. `handle_project_message` uses this to pick between `quick_reply` (single-turn via `ProjectAgent`) and `SlackSession` (streaming, multi-turn, registered in `RUN_SESSIONS`). Max mode and `run:` are unaffected.

**Tech Stack:** Python, Anthropic SDK (Haiku for triage), existing `APIBackend` / `SlackSession` infrastructure.

---

## Data Flow

`run:` prefix is handled entirely in `handle_mention` and never reaches `handle_project_message`. The diagram below covers only what happens inside `handle_project_message`, after the `if not project: return` guard.

```
handle_project_message(event, say, channel_name)
  [project resolved; early return if not found]
  [reactions_add :claude:, post ack, save ack_ts]
      │
      ▼
  api mode?
  ├── yes ──▶ triage_result = classify(prompt, project_key)
  │           [classify() always returns a TriageResult — never raises]
  │               ▼
  │           tier == complex?
  │           ├── yes ──▶ delete ack message (best-effort; failure is acceptable)
  │           │           active_sessions.pop(thread_ts, None)  ← SlackSession manages own history
  │           │           build system_prompt + cwd from project config
  │           │           SlackSession(APIBackend(triaged_model), on_close=_triage_on_close)
  │           │           RUN_SESSIONS[thread_ts] = session
  │           │           session.start(prompt, system_prompt, cwd)
  │           │           return  ← reactions_remove + record_session handled in _triage_on_close
  │           └── no  ──▶ append user turn to active_sessions
  │                       ProjectAgent.handle(prompt, context, model=triaged_model)
  │                       [sub-agent detection inside handle()]
  └── no  ──▶ append user turn to active_sessions
              ProjectAgent.handle(prompt, context)  ← max mode, no model override
```

**Important:** The existing `active_sessions[thread_ts].append({"role": "user", ...})` at line 157 of the current `handle_project_message` must be **deleted** and moved to the single-turn path only (after the complex early-return). This is a required code removal — not just an addition.

---

## Tier → Model Mapping

| Tier | Model | Examples |
|---|---|---|
| simple | claude-haiku-4-5-20251001 | Questions, lookups, explanations, status checks |
| moderate | claude-sonnet-4-6 | Code review, analysis, debugging help, single-file changes |
| complex | claude-sonnet-4-6 | Multi-file edits, refactors, long debugging, architecture work |

Complex uses Sonnet (not Opus) as the cost-conscious default. Opus can be introduced as a configurable option later.

**Known limitation:** Sub-agents (CrashInvestigator, Testing, etc.) manage their own backends internally and call `quick_reply()` without a model override. When triage selects Haiku but a sub-agent is triggered, the sub-agent will use `SESSION_MODEL` (typically Sonnet), not the triaged model. This is an accepted tradeoff — sub-agents are heavier tasks and Sonnet is appropriate for them.

**Max mode + complex request:** In max mode, triage is skipped entirely — all requests go through the single-turn `quick_reply` path via the Claude CLI, regardless of complexity. For long multi-step tasks in max mode, `run:` remains the explicit escape hatch to start an interactive `SlackSession`.

**Context continuity on complex path:** If a user has an existing quick-reply thread (history in `active_sessions`) and a follow-up message is triaged as complex, `active_sessions.pop()` discards that prior context. `SlackSession`/`APIBackend` starts a fresh history. This is an accepted limitation — triage-triggered sessions always start clean.

---

## Components

### New: `tools/triage.py`

```python
from __future__ import annotations
import json
import logging
from dataclasses import dataclass

import httpx
from anthropic import Anthropic

logger = logging.getLogger(__name__)

_HAIKU = "claude-haiku-4-5-20251001"
_SONNET = "claude-sonnet-4-6"

_TIER_TO_MODEL: dict[str, str] = {
    "simple": _HAIKU,
    "moderate": _SONNET,
    "complex": _SONNET,
}


@dataclass
class TriageResult:
    tier: str    # "simple" | "moderate" | "complex"
    model: str   # full model ID
    reason: str  # one sentence, for logging only


# Safe default — returned on any triage failure
_DEFAULT = TriageResult(tier="moderate", model=_SONNET, reason="triage unavailable")

_PROMPT = """Classify this developer request. Reply with JSON only, no prose.
{"tier": "simple|moderate|complex", "reason": "one sentence"}

simple   = question, explanation, lookup, read-only, status check
moderate = code review, analysis, single-file change, debugging help
complex  = multi-file edits, refactor, long debugging, architecture work

Request: """


def classify(prompt: str, project_key: str = "") -> TriageResult:
    """Classify prompt using Haiku. Always returns a TriageResult — never raises."""
    client = Anthropic(
        http_client=httpx.Client(timeout=httpx.Timeout(5.0)),
        max_retries=0,  # no retries — triage must be fast; failures use _DEFAULT
    )
    try:
        msg = client.messages.create(
            model=_HAIKU,
            max_tokens=64,
            messages=[{"role": "user", "content": _PROMPT + prompt}],
        )
        data = json.loads(msg.content[0].text)
        tier = data.get("tier", "")
        if tier not in _TIER_TO_MODEL:
            raise ValueError(f"Unknown tier: {tier!r}")
        result = TriageResult(
            tier=tier,
            model=_TIER_TO_MODEL[tier],
            reason=data.get("reason", ""),
        )
        logger.info(f"🔍 Triage: {result.tier} → {result.model} — \"{result.reason}\"")
        return result
    except Exception as exc:
        logger.warning(f"⚠️  Triage failed: {exc} — using default (moderate/sonnet)")
        return _DEFAULT
```

**Key implementation notes:**
- `TriageResult` dataclass is defined before `_DEFAULT` uses it
- `max_retries=0` prevents SDK retry logic from multiplying the 5s timeout
- `httpx.Timeout(5.0)` applies to the full round-trip
- `classify()` is documented and guaranteed to never raise — callers need no try/except

### New: `tests/test_triage.py`

Unit tests — all Anthropic client calls mocked via `unittest.mock.patch("tools.triage.Anthropic")`:

| Test | Mocked response | Expected result |
|---|---|---|
| Simple question | `{"tier": "simple", "reason": "..."}` | `tier=simple`, `model=haiku` |
| Moderate task | `{"tier": "moderate", "reason": "..."}` | `tier=moderate`, `model=sonnet` |
| Complex task | `{"tier": "complex", "reason": "..."}` | `tier=complex`, `model=sonnet` |
| API exception | raises `Exception` | `_DEFAULT` (sonnet/moderate) |
| Malformed JSON | returns `"not json"` | `_DEFAULT` |
| Unknown tier | `{"tier": "unknown", "reason": "..."}` | `_DEFAULT` |
| Timeout | raises `httpx.TimeoutException` | `_DEFAULT` |

### Modified: `tools/session_backend.py`

`quick_reply` gains an optional `model` parameter:

```python
def quick_reply(
    prompt: str,
    system_prompt: str = "",
    cwd: str = ".",
    model: str | None = None,  # overrides SESSION_MODEL env var; ignored in max mode
) -> str:
    backend_mode = os.environ.get("SESSION_BACKEND", "api")
    if backend_mode == "max" and MaxBackend.available():
        backend: SessionBackend = MaxBackend()
    else:
        resolved_model = model or os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        backend = APIBackend(model=resolved_model)
    ...
```

### Modified: `agents/project_agent.py`

`ProjectAgent.handle()` gains an optional `model` parameter:

```python
def handle(
    self,
    prompt: str,
    thread_context: list = None,
    model: str | None = None,  # triage-selected model; None = use SESSION_MODEL
) -> tuple[str, str]:
```

`model` is forwarded only to the `quick_reply` call in the non-sub-agent branch:

```python
response = quick_reply(
    full_prompt,
    system_prompt=self._system_prompt,
    cwd=self.project.get("path", "."),
    model=model,   # ← new
)
```

Sub-agent dispatches (`agent.run(prompt, thread_context)`) ignore `model` — this is the accepted tradeoff documented above.

### Modified: `bot_unified.py` — `handle_project_message`

Full structure of the modified function, showing where each piece sits:

```python
def handle_project_message(event, say, channel_name: str):
    text = event["text"]
    msg_ts = event["ts"]
    thread_ts = event.get("thread_ts", msg_ts)
    channel_id = event["channel"]

    routing = CHANNEL_ROUTING.get(channel_name)
    project_key = routing["project"] if routing else None
    project = PROJECTS.get(project_key) if project_key else None

    if not project:
        ...return

    prompt = text.split(">", 1)[1].strip() if ">" in text else text

    # Initialise session context (do NOT append yet — complex path skips this)
    if thread_ts not in active_sessions:
        active_sessions[thread_ts] = []
    context = list(active_sessions[thread_ts])

    # React + ack (unchanged)
    try:
        app.client.reactions_add(channel=channel_id, name="claude", timestamp=msg_ts)
    except Exception:
        pass
    try:
        ack = app.client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text="_On it..._")
        ack_ts = ack["ts"]
    except Exception:
        ack_ts = None

    # Triage
    backend_mode = os.environ.get("SESSION_BACKEND", "api")

    if backend_mode == "api":
        triage_result = classify(prompt, project_key)   # always returns TriageResult
    else:
        triage_result = None  # max mode: no triage

    if triage_result and triage_result.tier == "complex":
        # Delete ack before streaming begins (failure is acceptable — streaming output follows)
        if ack_ts:
            try:
                app.client.chat_delete(channel=channel_id, ts=ack_ts)
            except Exception:
                pass

        # SlackSession manages its own history — remove any stale active_sessions entry
        active_sessions.pop(thread_ts, None)

        # Derive system_prompt and cwd from project config
        cwd = project.get("path", ".")
        # Build a minimal system prompt inline (same fields ProjectAgent would use)
        system_prompt = f"You are a senior developer working on {project['name']}."

        triaged_model = triage_result.model

        def _triage_on_close(
            _mode=backend_mode,       # capture by value — avoids late-binding if env changes
            _model=triaged_model,
            _channel=channel_id,
            _msg_ts=msg_ts,
        ):
            RUN_SESSIONS.pop(thread_ts, None)
            usage_tracker.record_session(_mode, _model)
            try:
                app.client.reactions_remove(channel=_channel, name="claude", timestamp=_msg_ts)
            except Exception:
                pass

        session = SlackSession(
            thread_ts=thread_ts,
            channel_id=channel_id,
            client=app.client,
            backend=APIBackend(model=triaged_model),
            on_close=_triage_on_close,
        )
        RUN_SESSIONS[thread_ts] = session
        session.start(prompt, system_prompt, cwd)
        return

    # Single-turn path — append user turn now
    active_sessions[thread_ts].append({"role": "user", "content": prompt})

    # triaged_model is None in max mode (triage_result is None)
    triaged_model = triage_result.model if triage_result is not None else None

    try:
        agent = agent_factory.get_agent(project_key, project, app, channel_id, thread_ts)
        response, agent_label = agent.handle(prompt, context, model=triaged_model)
    except Exception as exc:
        ...

    active_sessions[thread_ts].append({"role": "assistant", "content": response})

    # [existing: ack update/delete, _post_smart, reactions_remove]

    actual_model = triaged_model or os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
    usage_tracker.record_mention(backend_mode, actual_model)
```

**Key notes:**
- `active_sessions` append at current line 157 must be **deleted** and moved to the single-turn path only — this is a removal, not just an addition
- `_triage_on_close` uses default-argument capture (`_mode=backend_mode`, etc.) to avoid late-binding, matching the existing `_on_run_close` pattern in `handle_mention`
- `_triage_on_close` calls `record_session` (streaming path); `record_mention` is called at the bottom of the single-turn path. These are different usage tracker methods — both are correct, neither is missing
- Ack delete failure on the complex path is acceptable — streaming output follows immediately
- `system_prompt` on the complex path is intentionally minimal. This is a known simplification — a follow-up can inject the full `ProjectAgent` system prompt if needed
- `triage_result is not None` used (not `if triage_result`) for clarity, since `TriageResult` is always truthy

---

## What Does Not Change

- `handle_mention` — `run:` prefix handling is entirely here; untouched
- Max mode — `triage_result = None`; `ProjectAgent.handle()` called without model override
- Sub-agent detection — lives inside `ProjectAgent.handle()`; not duplicated in `bot_unified.py`
- `SlackSession` constructor signature — unchanged
- Canvas routing, lifecycle posts, peer review, journal writing — untouched

---

## Testing Strategy

**`tests/test_triage.py`** — 7 unit tests (see table above)

**`tests/test_project_agent.py`** — add:
- `test_handle_passes_model_to_quick_reply`: call `handle(prompt, model="claude-haiku-4-5-20251001")`, mock `quick_reply`, assert it is called with `model="claude-haiku-4-5-20251001"`

**`tests/test_usage_integration.py`** — update `test_project_message_records_mention`:
- Patch `bot_unified.classify` to return `TriageResult(tier="simple", model="claude-haiku-4-5-20251001", reason="test")`
- Assert `record_mention` is called with `("api", "claude-haiku-4-5-20251001")`

**`tests/test_bot_run_trigger.py`** — add:
- `test_simple_triage_uses_quick_reply`: patch `classify` returning `tier=simple`; assert `SlackSession` is NOT created; assert `agent.handle()` is called with `model="claude-haiku-4-5-20251001"`
- `test_complex_triage_starts_slack_session`: patch `classify` returning `tier=complex`; mock `SlackSession` to capture kwargs (including `on_close`); assert `SlackSession` is created, registered in `RUN_SESSIONS[thread_ts]`, and `session.start()` is called; assert `active_sessions` does NOT contain `thread_ts` after the call
- `test_complex_triage_on_close_records_session`: from the mock in the above test, retrieve the `on_close` kwarg passed to `SlackSession.__init__`; call it directly; assert `usage_tracker.record_session` is called with `("api", "claude-sonnet-4-6")`
