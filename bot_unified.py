#!/usr/bin/env python3
"""
Shellack Unified Bot
Modular architecture with channel-based routing
"""

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from typing import Dict, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from anthropic import Anthropic
from dotenv import load_dotenv

from tools.cost_tracker import TurnCost, ThreadCost

# Import our modules
from orchestrator_config import (
    get_project_for_channel,
    is_orchestrator_channel,
    is_peer_review_channel,
    CHANNEL_ROUTING,
    PROJECTS,
)
from orchestrator import Orchestrator
from peer_review import PeerReviewCoordinator
from app_store_connect import AppStoreConnectClient, format_feedback_for_slack
from agents import AgentFactory
from tools.session_backend import APIBackend, MaxBackend
from tools.slack_session import SlackSession
from tools.usage_tracker import UsageTracker
from tools.config_writer import set_env_var
from tools.plugin_manager import PluginManager
from tools.thinking_indicator import ThinkingIndicator
from tools.token_cart import HaikuTokenCart, detect_correction
from tools.journal_polisher import polish_journal
from tools.github_journal import post_journal_entry
from tools.thread_observer import ThreadObserver
from tools.agent_discussion import DiscussionLog

# Load environment
load_dotenv()

# Logging
logger = logging.getLogger(__name__)

# Initialize services
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Initialize modules
orchestrator = Orchestrator()
peer_review = PeerReviewCoordinator()
agent_factory = AgentFactory(anthropic_client)

# Session management
active_sessions: Dict[str, dict] = {}
_session_lock = threading.Lock()
token_cart = HaikuTokenCart()

_SESSION_IDLE_TIMEOUT = int(os.environ.get("SESSION_IDLE_TIMEOUT", 600))  # 10 minutes
_SESSION_CHECK_INTERVAL = 60  # check every minute


def _finalize_journal(session: dict):
    """Polish journal draft and post to GitHub Discussions."""
    try:
        project_key = session.get("project_key", "")
        project = PROJECTS.get(project_key, {})
        draft = session.get("journal_draft", "")

        if not draft or not project:
            return

        polished = polish_journal(draft, project.get("name", ""))
        if not polished:
            polished = draft  # fallback to raw draft

        repo = project.get("github_repo", "")
        if repo:
            post_journal_entry(repo, "Journal", polished)
            logger.info(f"Journal posted for {project_key}")
    except Exception as exc:
        logger.warning(f"Journal finalization failed: {exc}")


def _session_cleanup_loop():
    """Background thread: finalize and remove idle sessions."""
    while True:
        time.sleep(_SESSION_CHECK_INTERVAL)
        now = time.time()
        stale = []
        with _session_lock:
            for thread_ts, session in list(active_sessions.items()):
                last_active = session.get("last_active", 0)
                if last_active and (now - last_active) > _SESSION_IDLE_TIMEOUT:
                    stale.append((thread_ts, active_sessions.pop(thread_ts)))
        # Finalize outside the lock
        for thread_ts, session in stale:
            if session.get("journal_draft"):
                _finalize_journal(session)


# run: session registry — keyed by thread_ts, cleaned up when session closes
RUN_SESSIONS: dict = {}

# Conversational output instructions appended to every run: session
_SLACK_CONVERSATIONAL_PROMPT = """
---
SLACK OUTPUT RULES (follow these strictly):
- Be brief and conversational. You are chatting in Slack, not writing a report.
- Never paste file contents directly into messages — they go to the canvas automatically.
- After editing or creating a file, say what you did in one sentence (e.g. "Updated `foo.swift` to fix the login bug.").
- Keep code snippets in messages to ≤10 lines. Larger code goes to the session canvas.
- Use bullet points for lists of changes, not wall-of-text prose.
- If you need to share long output (test results, build logs, file trees), summarise in 1-2 sentences instead.
"""

# Usage tracking — persists to usage.json, monthly auto-reset
usage_tracker = UsageTracker()

# Plugin management
plugin_manager = PluginManager()
_bot_extensions: dict = {}


def get_channel_name(channel_id: str) -> str:
    """Get channel name from ID"""
    try:
        result = app.client.conversations_info(channel=channel_id)
        return result["channel"]["name"]
    except Exception as e:
        print(f"Error getting channel name: {e}")
        return ""


# ============================================================================
# PROJECT AGENT HANDLERS (per-channel, see projects.yaml)
# ============================================================================


def _post_smart(channel_id: str, thread_ts: str, text: str) -> None:
    """Post text to a thread with canvas routing for large/code content."""
    from tools.slack_session import _md_to_mrkdwn, _CODE_FENCE_RE, _MAX_INLINE_CHARS

    text = _md_to_mrkdwn(text)
    has_code = bool(_CODE_FENCE_RE.search(text))
    is_long = len(text) > _MAX_INLINE_CHARS

    if has_code or is_long:
        # Try to route to canvas
        try:
            resp = app.client.canvases_create(
                title="🦞 Agent Output",
                document_content={"type": "markdown", "markdown": text},
            )
            canvas_id = resp.get("canvas_id") or (resp.get("canvas") or {}).get("id")
            if canvas_id:
                summary = _CODE_FENCE_RE.split(text)[0].strip()[:300]
                notice = (summary + "\n" if summary else "") + (
                    f"📄 Full output in canvas (`{canvas_id}`)"
                )
                app.client.chat_postMessage(
                    channel=channel_id, thread_ts=thread_ts, text=notice
                )
                return
        except Exception:
            pass
        # Canvas unavailable — truncate
        if is_long:
            text = text[:_MAX_INLINE_CHARS] + "… _(truncated)_"

    app.client.chat_postMessage(channel=channel_id, thread_ts=thread_ts, text=text)


def _has_security_keywords(prompt: str) -> bool:
    """Check if prompt contains auth/input/crypto keywords for security override."""
    patterns = [r"\bauth\b", r"\blogin\b", r"\btoken\b", r"\bcrypto\b", r"\bpassword\b", r"\bsession\b", r"\binjection\b"]
    lower = prompt.lower()
    return any(re.search(p, lower) for p in patterns)


def _summarize_persona_finding(slot_name: str, slot: dict) -> str:
    """Format a persona's findings for appending to the response."""
    verdict = slot.get("verdict", "")
    if slot_name == "skeptic" and verdict == "reconsider":
        assumptions = slot.get("assumptions", [])
        if assumptions:
            items = "\n".join(f"- {a.get('claim', '')}: {a.get('risk', '')}" for a in assumptions[:3])
            return f"🤨 *Skeptic:*\n{items}"
    if slot_name == "inspector" and verdict in ("gaps", "incomplete"):
        gaps = slot.get("gaps", [])
        if gaps:
            items = "\n".join(f"- {g.get('location', '')}: {g.get('type', '')}" for g in gaps[:3])
            return f"🔍 *Inspector:*\n{items}"
    if slot_name == "infosec" and verdict == "blocker":
        mitigations = slot.get("mitigations", [])
        if mitigations:
            items = "\n".join(f"- {m.get('threat', '')}: {m.get('defense', '')}" for m in mitigations[:3])
            return f"🛡️ *Infosec BLOCKER:*\n{items}"
    return ""


def handle_project_message(event, say, channel_name: str):
    """Handle messages in project-specific channels using specialized project agents."""
    text = event["text"]
    msg_ts = event["ts"]
    thread_ts = event.get("thread_ts", msg_ts)
    channel_id = event["channel"]

    # Get project config and resolve project key
    routing = CHANNEL_ROUTING.get(channel_name)
    project_key = routing["project"] if routing else None
    project = PROJECTS.get(project_key) if project_key else None

    if not project:
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"❌ Channel `{channel_name}` not configured. See orchestrator_config.py",
        )
        return

    # Remove bot mention
    prompt = text.split(">", 1)[1].strip() if ">" in text else text

    # React :claude: IMMEDIATELY — before any processing
    try:
        app.client.reactions_add(channel=channel_id, name="claude", timestamp=msg_ts)
    except Exception:
        pass

    # Handle empty prompt — try voice transcription if audio file present
    if not prompt.strip():
        audio_files = [
            f
            for f in event.get("files", [])
            if f.get("subtype") == "slack_audio"
            or "audio" in f.get("mimetype", "")
            or f.get("filetype", "")
            in ("mp4", "webm", "ogg", "m4a", "aac", "wav", "mp3")
        ]
        if audio_files:
            try:
                from tools.voice_transcriber import transcribe_slack_file

                transcript = transcribe_slack_file(
                    audio_files[0],
                    os.environ.get("SLACK_BOT_TOKEN", ""),
                )
                if transcript:
                    prompt = transcript
                    app.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"\U0001f399\ufe0f *Heard:* {transcript}",
                    )
                else:
                    app.client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text="\U0001f399\ufe0f Couldn't transcribe the voice message. Try again or type your message.",
                    )
                    return
            except Exception as exc:
                logger.warning(f"Voice transcription failed: {exc}")
                app.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="\U0001f399\ufe0f Voice transcription isn't available. Type your message instead.",
                )
                return
        elif event.get("files"):
            app.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="\U0001f4ce File-only messages aren't supported \u2014 add some text with your file.",
            )
            return
        else:
            app.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text="\u2753 Empty message received. Try again with some text.",
            )
            return

    # Initialise session context
    with _session_lock:
        if thread_ts not in active_sessions:
            active_sessions[thread_ts] = {
                "handoff": None,
                "journal_draft": "",
                "turn_count": 0,
                "project_key": project_key,
                "cost": ThreadCost(),
                "last_active": time.time(),
                "skills": [],  # populated on first turn
                "observer": ThreadObserver(),
                "project_structure": "",  # cached on first use
            }
        session = active_sessions[thread_ts]
        session["last_active"] = time.time()

    # Create discussion log for this turn
    discussion = DiscussionLog()

    # Thread observer: append user message
    observer = session.get("observer")
    if observer is None:
        observer = ThreadObserver()
        session["observer"] = observer
    observer.observe("user", prompt)
    discussion.add("observer", f"User: {prompt[:80]}")

    # File fetcher: identify and read needed files
    file_context = ""
    needed_files = []
    use_token_cart = project.get("features", {}).get("token-cart", True)
    if use_token_cart:
        try:
            from tools.file_fetcher import (
                fetch_files_for_context,
                scan_project_structure,
            )

            # Cache project structure on first use
            if not session.get("project_structure"):
                session["project_structure"] = scan_project_structure(
                    project.get("path", "")
                )

            needed_files = observer.identify_needed_files(
                prompt, session["project_structure"]
            )
            if needed_files:
                file_context = fetch_files_for_context(
                    project.get("path", ""), needed_files
                )
                logger.info(f"File fetcher loaded: {needed_files}")
                discussion.add("file_fetcher", f"Loaded {', '.join(needed_files)}")
        except Exception:
            pass

    # Estimate input token count for the indicator
    handoff_chars = len(session.get("handoff") or "")
    estimated_tokens = (len(prompt) + handoff_chars) // 3

    backend_mode = os.environ.get("SESSION_BACKEND", "api")

    # 4. Single-turn path

    model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")

    # 6. Start animated thinking indicator (posts clay-colored message, cycles verbs)
    indicator = ThinkingIndicator(app.client, channel_id, thread_ts)
    indicator.start(input_tokens=estimated_tokens)

    # Pre-call: enrich context via Token Cart (skip if feature-gated off)
    use_external_handoff = project.get("features", {}).get("external-handoff", True)
    registry_content = None  # initialized before conditional for downstream use
    if use_token_cart:
        # Read project registry for context enrichment (feature-gated)
        if project.get("features", {}).get("registry", True):
            from tools.registry import ensure_registry

            registry_content = ensure_registry(project.get("path", ""))

        # Cross-thread persistence: load prior thread memory for new threads
        effective_handoff = session["handoff"]
        if use_external_handoff and not effective_handoff:
            try:
                from tools.thread_memory import read_thread_memory

                effective_handoff = read_thread_memory(
                    project.get("path", ""), project_key
                )
            except Exception:
                pass

        # Combine registry + file context
        full_registry = registry_content or ""
        if file_context:
            full_registry = (
                f"{full_registry}\n\n## Fetched Files\n{file_context}"
                if full_registry
                else f"## Fetched Files\n{file_context}"
            )

        try:
            enriched_context = token_cart.pre_call(
                handoff=effective_handoff,
                prompt=prompt,
                registry=full_registry or None,
            )
        except Exception as exc:
            logger.warning(f"Token cart pre-call failed: {exc}")
            enriched_context = prompt
        discussion.add(
            "token_cart",
            "Context enriched"
            + (f" with {len(needed_files)} files" if needed_files else ""),
        )
    else:
        enriched_context = prompt

    # Agent Manager: intelligent model selection (opt-in, default OFF)
    use_agent_manager = project.get("features", {}).get("agent-manager", False)
    if use_agent_manager and use_token_cart:
        try:
            from tools.agent_manager import classify_complexity, select_model

            complexity = classify_complexity(prompt, handoff=session.get("handoff"))
            model = select_model(complexity)
            logger.info(f"Agent manager: {complexity} → {model}")
        except Exception:
            pass  # fall through to default model

    # 6b. Pre-hoc Toolkeeper: auto-execute safe commands to gather context
    use_pipeline = project.get("features", {}).get("pipeline", True)
    if use_pipeline and use_token_cart:
        current_complexity = complexity if use_agent_manager else "moderate"
        if current_complexity != "simple":
            try:
                from tools.pipeline import TurnContext, run_pipeline

                pre_ctx = TurnContext()
                pre_ctx["agent_manager"] = {
                    "complexity": current_complexity,
                    "model": model,
                    "security_override": _has_security_keywords(prompt),
                }
                pre_ctx["observer"] = {
                    "summary": observer.context if observer else prompt[:200],
                    "turn": session.get("turn_count", 1),
                }
                pre_ctx["token_cart"] = {
                    "enriched_prompt": enriched_context if isinstance(enriched_context, str) else prompt,
                    "handoff": session.get("handoff", "") or "",
                    "registry": registry_content or "",
                    "file_context": file_context or "",
                }
                pre_ctx["_project_path"] = project.get("path", ".")

                # Run pre-hoc phases (toolkeeper + plan + design on complex)
                pre_results, _ = run_pipeline(pre_ctx, current_complexity, pre_hoc=True)

                for phase_name, entries in pre_results:
                    phase_emoji = {
                        "toolkeeper": "🔧",
                        "plan": "🎯",
                        "design": "📐",
                        "vision": "🔮",
                        "challenge": "🤨",
                        "security": "🛡️",
                        "quality": "✅",
                    }.get(phase_name, "📋")
                    discussion.add_phase_entries(phase_name, phase_emoji, entries)

                # If Toolkeeper gathered context, inject it into the enriched prompt
                toolkeeper_output = pre_ctx.get("toolkeeper", {})
                if toolkeeper_output.get("needs_tools") and toolkeeper_output.get("output"):
                    tool_context = toolkeeper_output["output"]
                    enriched_context = f"{enriched_context}\n\n## Auto-Fetched Context\n{tool_context}"
                    logger.info(f"Toolkeeper injected {len(tool_context)} chars of context")

                # 6c. Self-research: multi-step investigation for complex questions
                # Triggers when Toolkeeper didn't gather enough or complexity warrants it
                _needs_research = (
                    current_complexity in ("moderate", "complex")
                    and (
                        not toolkeeper_output.get("needs_tools")
                        or not toolkeeper_output.get("output", "").strip()
                    )
                )
                if _needs_research:
                    try:
                        from tools.self_research import run_research

                        research = run_research(
                            question=prompt,
                            project_path=project.get("path", "."),
                            client=anthropic_client,
                        )
                        if research["findings"]:
                            enriched_context = (
                                f"{enriched_context}\n\n"
                                f"## Self-Research Findings ({research['steps']} steps)\n"
                                f"{research['findings']}"
                            )
                            logger.info(
                                f"Self-research: {research['steps']} steps, "
                                f"{len(research['findings'])} chars, "
                                f"commands: {research['commands_run']}"
                            )
                    except Exception as exc:
                        logger.warning(f"Self-research failed: {exc}")

            except Exception as exc:
                logger.warning(f"Pre-hoc pipeline failed: {exc}")

    # 7. Run the agent
    try:
        agent = agent_factory.get_agent(
            project_key, project, app, channel_id, thread_ts
        )
        if not session.get("skills"):
            from tools.skill_mapper import get_skills_for_project

            session["skills"] = get_skills_for_project(
                project.get("path", ""),
                language=project.get("language", ""),
                platform=project.get("platform", ""),
            )
        response, agent_label = agent.handle(prompt, enriched_context, model=model)
    except Exception as exc:
        indicator.done()
        logger.exception(f"Agent error in {channel_name}")
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"❌ An error occurred while processing your request. Please try again.",
        )
        try:
            app.client.reactions_remove(
                channel=channel_id, name="claude", timestamp=msg_ts
            )
        except Exception:
            pass
        return

    # Thread observer: append agent response
    if observer:
        observer.observe("agent", response[:1000])

    # 8. Estimate turn cost
    if project.get("features", {}).get("cost-observability", True):
        model_used = model or os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        est_input = (
            len(prompt)
            + len(enriched_context if isinstance(enriched_context, str) else "")
        ) // 4
        est_output = len(response) // 4
        turn_cost = TurnCost(
            input_tokens=est_input, output_tokens=est_output, model=model_used
        )
        if "cost" not in session:
            session["cost"] = ThreadCost()
        session["cost"].add_turn(turn_cost)

    # 8b. Run post-hoc cognitive pipeline (replaces gut check + consultants)
    use_pipeline = project.get("features", {}).get("pipeline", True)
    if use_pipeline and use_token_cart:
        try:
            from tools.pipeline import TurnContext, run_pipeline

            # Build TurnContext from session state
            turn_ctx = TurnContext()
            turn_ctx["agent_manager"] = {
                "complexity": complexity if use_agent_manager else "moderate",
                "model": model,
                "security_override": _has_security_keywords(prompt),
            }
            turn_ctx["observer"] = {
                "summary": observer.context if observer else prompt[:200],
                "turn": session.get("turn_count", 1),
            }
            turn_ctx["token_cart"] = {
                "enriched_prompt": enriched_context if isinstance(enriched_context, str) else prompt,
                "handoff": session.get("handoff", "") or "",
                "registry": registry_content or "",
            }
            # For post-hoc: inject the agent's response as the "architect" slot
            turn_ctx["architect"] = {
                "proposal": response[:2000],
                "data_model": "",
                "api_surface": "",
                "files_affected": [],
            }
            turn_ctx["strategist"] = {"tasks": [], "sequence": []}
            turn_ctx["historian"] = {"prior_decisions": [], "conflicts": []}

            # Determine complexity
            current_complexity = complexity if use_agent_manager else "moderate"

            # Run post-hoc phases
            phase_results, _ = run_pipeline(turn_ctx, current_complexity, pre_hoc=False)

            for phase_name, entries in phase_results:
                phase_emoji = {
                    "challenge": "🤨",
                    "quality": "✅",
                    "security": "🛡️",
                    "synthesis": "🧠",
                }.get(phase_name, "📋")
                discussion.add_phase_entries(phase_name, phase_emoji, entries)

            # Check for blocker verdicts
            for slot_name in ("infosec", "visual_ux"):
                slot = turn_ctx.get(slot_name, {})
                if slot.get("verdict") == "blocker":
                    response += f"\n\n🔴 **{slot_name.replace('_', ' ').upper()} BLOCKER:** Response held for review."

            # Append persona findings to response
            for slot_name in ("skeptic", "inspector", "infosec"):
                slot = turn_ctx.get(slot_name, {})
                if slot.get("verdict") not in (None, "proceed", "complete", "covered", "accessible", "clear", "secure", "resilient"):
                    summary = _summarize_persona_finding(slot_name, slot)
                    if summary:
                        response += f"\n\n{summary}"

            # Wire Learner persistence (Feedback Loops 5-7)
            learner_output = turn_ctx.get("learner")
            if learner_output and isinstance(learner_output, dict):
                for lesson in learner_output.get("lessons", []):
                    persistence = lesson.get("persistence", "thread")
                    insight = lesson.get("insight", "")
                    if not insight:
                        continue
                    try:
                        if persistence == "thread":
                            from tools.thread_memory import write_thread_memory
                            # Append lesson to thread memory
                            existing = session.get("handoff", "") or ""
                            updated = f"{existing}\n\n### Learned\n- {insight}" if existing else f"### Learned\n- {insight}"
                            write_thread_memory(project.get("path", ""), project_key, updated)
                        elif persistence == "project":
                            from tools.registry import append_to_registry
                            append_to_registry(project.get("path", ""), "Architecture Rules", f"| {insight[:50]} | learned | auto-extracted |")
                        elif persistence == "permanent":
                            from tools.self_improver import reflect_and_update
                            reflect_and_update(prompt=insight, response="", project_path=project.get("path", "."))
                    except Exception:
                        pass  # best-effort persistence

        except Exception as exc:
            logger.warning(f"Pipeline failed: {exc}")  # log but never block
    elif use_token_cart:
        # Fallback: legacy gut check + consultant dispatch
        use_gut_check = project.get("features", {}).get("gut-check", True)
        if use_gut_check:
            try:
                concern = token_cart.gut_check(
                    response=response,
                    registry=registry_content,
                    handoff=session["handoff"],
                )
                if concern:
                    response += f"\n\n⚠️ *Gut check:* {concern}"
                    logger.info(f"Gut check flagged: {concern}")
                    discussion.add("gut_check", f"CONCERN: {concern}")
                else:
                    discussion.add("gut_check", "PROCEED")
            except Exception:
                pass  # never block on gut check

        use_consultants = project.get("features", {}).get("consultants", True)
        if use_consultants:
            try:
                from tools.consultants import detect_triggers, consult

                triggered_roles = detect_triggers(response)
                for role in triggered_roles:
                    feedback = consult(
                        role=role,
                        response=response,
                        handoff=session.get("handoff"),
                        registry=registry_content,
                    )
                    if feedback:
                        response += f"\n\n{feedback}"
                        logger.info(f"Consultant {role} flagged findings")
                        discussion.add(role, f"Flagged: {feedback[:60]}")
            except Exception:
                pass  # never block on consultants

    # 9. Parse response tags and render
    from tools.response_parser import parse_response, split_message
    from tools.slack_session import _md_to_mrkdwn

    parsed = parse_response(response)

    # Fallback: if no [reply] tag but [think] has content, post think as reply
    if not parsed.reply and parsed.think:
        parsed.reply = parsed.think
        parsed.think = ""  # don't show in churned block since it's the reply now

    # Cost string for the churned block (API mode only — Max is $0)
    cost_str = ""
    if (
        backend_mode == "api"
        and project.get("features", {}).get("cost-observability", True)
        and session.get("cost")
    ):
        last_turn = session["cost"].turns[-1] if session["cost"].turns else None
        if last_turn:
            cost_str = session["cost"].format_turn_summary(last_turn)

    # Order: churned+reasoning → discussion → reply → buttons → remove emoji
    # 1. Update indicator to churned (with reasoning)
    indicator.done(think_block=parsed.think, cost_summary=cost_str)

    # 1b. Post agent discussion log
    if not discussion.is_empty():
        try:
            app.client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                text=discussion.format(),
            )
        except Exception:
            pass

    # 2. Post [reply] as separate message(s)
    if parsed.reply:
        formatted_reply = _md_to_mrkdwn(parsed.reply)
        chunks = split_message(formatted_reply, max_chars=3500)
        for chunk in chunks:
            try:
                app.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text=chunk,
                )
            except Exception:
                pass

        # 3. Post action buttons if reply contains numbered options
        from tools.action_buttons import detect_options, format_buttons

        options = detect_options(parsed.reply)
        if options:
            blocks = format_buttons(options, thread_ts)
            try:
                app.client.chat_postMessage(
                    channel=channel_id,
                    thread_ts=thread_ts,
                    text="Pick an option:",
                    blocks=blocks,
                )
            except Exception:
                pass

    # 4. Remove :claude: reaction LAST — only after everything is posted
    try:
        app.client.reactions_remove(channel=channel_id, name="claude", timestamp=msg_ts)
    except Exception:
        pass

    # Post-call: compact via Token Cart — async, never blocks the user
    if use_token_cart:

        def _post_call_async():
            try:
                cart_result = token_cart.post_call(
                    handoff=session["handoff"],
                    prompt=prompt,
                    response=response,
                )
                with _session_lock:
                    if thread_ts in active_sessions:
                        session["handoff"] = cart_result["handoff"]
                        session["journal_draft"] = cart_result["journal_draft"]
                        session["turn_count"] += 1

                        # Inline code review: surface issues for next turn
                        review = cart_result.get("review", "")
                        if review and review.strip() != "CLEAN" and review.strip():
                            logger.info(f"Token cart code review: {review}")
                            # Store for next turn's handoff context
                            if session["handoff"]:
                                session[
                                    "handoff"
                                ] += f"\n\n### Code Review Flags\n{review}"

                # Cross-thread persistence: save latest handoff for future threads
                # File I/O — outside the lock
                if use_external_handoff and cart_result["handoff"]:
                    try:
                        from tools.thread_memory import write_thread_memory

                        write_thread_memory(
                            project.get("path", ""), project_key, cart_result["handoff"]
                        )
                    except Exception:
                        pass  # never block on persistence

                # Append key learnings to context manifest
                if observer and observer.context:
                    try:
                        from tools.context_manifest import append_learned

                        # Extract decisions from observer context
                        for line in observer.context.split("\n"):
                            if "DECIDED:" in line or "FACT:" in line:
                                append_learned(project.get("path", ""), line.strip())
                    except Exception:
                        pass
            except Exception as exc:
                logger.warning(f"Token cart post-call failed: {exc}")

        threading.Thread(target=_post_call_async, daemon=True).start()

    # Correction feedback: detect and update registry (async)
    if use_token_cart and project.get("features", {}).get("registry", True):
        if detect_correction(prompt):

            def _correction_async():
                try:
                    correction = token_cart.extract_correction(prompt, response)
                    if correction:
                        from tools.registry import append_to_registry

                        append_to_registry(
                            project.get("path", ""),
                            correction["section"],
                            correction["entry"],
                        )
                        logger.info(
                            f"Registry updated with correction: {correction['section']}"
                        )
                except Exception:
                    pass

            threading.Thread(target=_correction_async, daemon=True).start()

    usage_tracker.record_mention(backend_mode, model)


# ============================================================================
# ORCHESTRATOR HANDLERS (for #slackclaw-central)
# ============================================================================


def handle_orchestrator_message(event, say):
    """Handle messages in orchestrator channel"""
    text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])

    # Remove bot mention
    prompt = text.split(">", 1)[1].strip() if ">" in text else text
    prompt_lower = prompt.lower()

    say(text="🎯 Orchestrator processing...", thread_ts=thread_ts)

    # Route to orchestrator commands
    if "update all claude.md" in prompt_lower or "update all CLAUDE.md" in prompt_lower:
        # Extract rule
        rule = prompt.split(":", 1)[1].strip() if ":" in prompt else prompt
        results = orchestrator.update_all_claude_md(rule)

        response = "## ✅ Updated CLAUDE.md Files\n\n"
        for project, success in results.items():
            emoji = "✅" if success else "❌"
            response += f"{emoji} {project}\n"

        say(text=response, thread_ts=thread_ts)

    elif "sync standards" in prompt_lower:
        # Extract source and target
        parts = prompt.lower().split("from")[1].split("to")
        source = parts[0].strip()
        target = parts[1].strip() if len(parts) > 1 else ""

        success = orchestrator.sync_standards(source, target)

        if success:
            say(
                text=f"✅ Synced standards from {source} to {target}",
                thread_ts=thread_ts,
            )
        else:
            say(text=f"❌ Failed to sync standards", thread_ts=thread_ts)

    elif "search all" in prompt_lower:
        # Extract query
        query = (
            prompt.split(":", 1)[1].strip()
            if ":" in prompt
            else prompt.replace("search all", "").strip()
        )

        results = orchestrator.search_all_projects(query)

        response = f"## 🔍 Search Results for: `{query}`\n\n"
        for project, files in results.items():
            if files:
                response += f"**{project}** ({len(files)} matches)\n"
                for f in files[:5]:  # Show first 5
                    response += f"- {f}\n"
                if len(files) > 5:
                    response += f"- ... and {len(files) - 5} more\n"
                response += "\n"

        if not any(results.values()):
            response += "No matches found across any project."

        say(text=response, thread_ts=thread_ts)

    else:
        # Generic orchestrator help
        say(
            text="""**Orchestrator Commands:**

`@Shellack update all CLAUDE.md: <rule>`
Update CLAUDE.md files across all projects

`@Shellack sync standards from <source> to <target>`
Sync coding standards between projects

`@Shellack search all: <query>`
Search across all projects

`@Shellack help`
Show this help""",
            thread_ts=thread_ts,
        )


# ============================================================================
# PEER REVIEW HANDLERS (for #code-review)
# ============================================================================


def handle_peer_review_message(event, say):
    """Handle messages in peer review channel"""
    text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])

    # Check if this is a review request
    if "ready for review" in text.lower() or "pr" in text.lower():
        say(text="🔍 Starting peer review...", thread_ts=thread_ts)

        # Extract PR info (simplified - would parse from message)
        pr_data = {
            "description": "Code changes ready for review",
            "files": ["example.swift"],  # Would extract from message
            "diff": text,  # Simplified - would get actual diff
        }

        # Run peer review
        reviews = peer_review.review_pr(pr_data)
        summary = peer_review.format_review_summary(reviews)

        say(text=summary, thread_ts=thread_ts)

    else:
        say(
            text="""**Code Review Channel**

Post your PR for autonomous review:
`🤖 PR #123 ready for review
Files: file1.swift, file2.swift
Description: Fixed bug in login flow`

The review bots will analyze and provide feedback!""",
            thread_ts=thread_ts,
        )


# ============================================================================
# MAIN MESSAGE HANDLER - Routes to appropriate module
# ============================================================================


def _handle_plugin_command(
    clean_text: str,
    say,
    user_id: str,
    channel_id: str,
    thread_ts: str,
) -> bool:
    """Handle plugin management commands. Returns True if the command was consumed."""
    lower = clean_text.lower()

    def _post_error(error_text: str) -> None:
        app.client.chat_postEphemeral(
            channel=channel_id,
            user=user_id,
            text=f"❌ {error_text}",
        )

    def _post_success(text: str) -> None:
        say(text=text, thread_ts=thread_ts)

    def _handle_result(result: dict, success_text: str) -> None:
        if result.get("ok"):
            _post_success(success_text)
        else:
            _post_error(result.get("error", "Unknown error"))

    # plugins — list all
    if lower == "plugins":
        result = plugin_manager.list_all(registry=_bot_extensions)
        lines = ["🔌 *Installed plugins:*"]
        lines.append(f"*Claude Code plugins:* {', '.join(result['plugins']) or 'none'}")
        lines.append(f"*MCP servers:* {', '.join(result['mcps']) or 'none'}")
        lines.append(f"*Bot extensions:* {', '.join(result['bot_plugins']) or 'none'}")
        _post_success("\n".join(lines))
        return True

    # --- Owner-only gate for mutating commands ---
    def _require_owner() -> bool:
        """Return True if user is the owner, False otherwise (posts error).

        Fail-closed: if OWNER_SLACK_USER_ID is not set, deny all mutating commands.
        """
        owner = os.environ.get("OWNER_SLACK_USER_ID", "")
        if not owner:
            _post_error(
                "OWNER_SLACK_USER_ID is not configured. Plugin management is disabled."
            )
            return False
        if user_id != owner:
            _post_error("Plugin management is restricted to the workspace owner.")
            return False
        return True

    # add plugin <name>
    if lower.startswith("add plugin "):
        if not _require_owner():
            return True
        name = clean_text[11:].strip()
        result = plugin_manager.install_plugin(name)
        _handle_result(
            result,
            f"✅ Plugin `{name}` installed. Restart any active `run:` session to use it.",
        )
        return True

    # remove plugin <name>
    if lower.startswith("remove plugin "):
        if not _require_owner():
            return True
        name = clean_text[14:].strip()
        result = plugin_manager.uninstall_plugin(name)
        _handle_result(result, f"✅ Plugin `{name}` removed.")
        return True

    # add mcp <name> <command>
    if lower.startswith("add mcp "):
        if not _require_owner():
            return True
        rest = clean_text[8:].strip()
        parts = rest.split(None, 1)
        if len(parts) < 2:
            _post_error("Usage: `@Shellack add mcp <name> <command>`")
            return True
        mcp_name, command = parts
        result = plugin_manager.add_mcp(mcp_name, command)
        _handle_result(result, f"✅ MCP server `{mcp_name}` added.")
        return True

    # remove mcp <name>
    if lower.startswith("remove mcp "):
        if not _require_owner():
            return True
        name = clean_text[11:].strip()
        result = plugin_manager.remove_mcp(name)
        _handle_result(result, f"✅ MCP server `{name}` removed.")
        return True

    # add bot-plugin <name_or_url>
    if lower.startswith("add bot-plugin "):
        if not _require_owner():
            return True
        name_or_url = clean_text[15:].strip()
        result = plugin_manager.add_bot_plugin(name_or_url, registry=_bot_extensions)
        installed_name = result.get("name", name_or_url)
        _handle_result(
            result, f"✅ Bot extension `{installed_name}` installed and loaded."
        )
        return True

    # remove bot-plugin <name>
    if lower.startswith("remove bot-plugin "):
        if not _require_owner():
            return True
        name = clean_text[18:].strip()
        result = plugin_manager.remove_bot_plugin(name, registry=_bot_extensions)
        _handle_result(result, f"✅ Bot extension `{name}` removed.")
        return True

    return False


_VALID_FEATURES = {
    "token-cart",
    "internal-handoff",
    "external-handoff",
    "gut-check",
    "code-review",
    "consultants",
    "pipeline",
    "registry",
    "cost-observability",
    "agent-manager",
}


def _handle_config_command(clean_text: str, say, thread_ts: str, event: Dict) -> bool:
    """Handle config commands. Returns True if the command was consumed."""
    lower = clean_text.lower()

    # Check if this is a config command that requires owner
    is_config_command = (
        lower.startswith("set mode ")
        or lower.startswith("set model ")
        or lower == "usage"
        or lower.startswith("set triage ")
        or lower == "config"
        or lower.startswith("config ")
    )

    if is_config_command:
        owner = os.environ.get("OWNER_SLACK_USER_ID", "")
        if not owner:
            say(
                "OWNER_SLACK_USER_ID is not configured. Config commands are disabled.",
                thread_ts=thread_ts,
            )
            return True
        if event.get("user") != owner:
            say(
                "Configuration changes are restricted to the workspace owner.",
                thread_ts=thread_ts,
            )
            return True

    # set mode max|api
    if lower.startswith("set mode "):
        mode = lower[9:].strip()
        if mode == "max":
            if not shutil.which("claude"):
                say(
                    text="❌ `claude` CLI not found. Install Claude Code first: https://claude.ai/code",
                    thread_ts=thread_ts,
                )
                return True
            set_env_var("SESSION_BACKEND", "max")
            say(text="✅ Mode set to `max`. No restart required.", thread_ts=thread_ts)
        elif mode == "api":
            set_env_var("SESSION_BACKEND", mode)
            say(
                text=f"✅ Mode set to `{mode}`. No restart required.",
                thread_ts=thread_ts,
            )
        else:
            say(text="Usage: `@Shellack set mode max|api`", thread_ts=thread_ts)
        return True

    # set model opus|sonnet|haiku
    if lower.startswith("set model "):
        alias = lower[10:].strip()
        model_map = {
            "opus": "claude-opus-4-6",
            "sonnet": "claude-sonnet-4-6",
            "haiku": "claude-haiku-4-5-20251001",
        }
        model = model_map.get(alias)
        if model:
            set_env_var("SESSION_MODEL", model)
            say(text=f"✅ Model set to `{model}`.", thread_ts=thread_ts)
        else:
            say(
                text="Usage: `@Shellack set model opus|sonnet|haiku`",
                thread_ts=thread_ts,
            )
        return True

    # usage
    if lower == "usage":
        say(text=usage_tracker.format_usage_message(), thread_ts=thread_ts)
        return True

    # set triage on|off
    if lower.startswith("set triage "):
        state = lower[11:].strip()
        if state == "on":
            set_env_var("TRIAGE_ENABLED", "true")
            say(
                text="✅ Triage enabled. Requests will be auto-routed to haiku/sonnet.",
                thread_ts=thread_ts,
            )
        elif state == "off":
            set_env_var("TRIAGE_ENABLED", "false")
            say(
                text="✅ Triage disabled. All requests use SESSION_MODEL.",
                thread_ts=thread_ts,
            )
        else:
            say(text="Usage: `@Shellack set triage on|off`", thread_ts=thread_ts)
        return True

    # config (global settings summary)
    if lower == "config":
        mode = os.environ.get("SESSION_BACKEND", "api")
        model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        onboarding = os.environ.get("ONBOARDING_COMPLETE", "false")
        triage_enabled = os.environ.get("TRIAGE_ENABLED", "true").lower() != "false"
        lines = [
            "🦞 *Shellack — Config*",
            f"Backend: `{mode}`",
            f"Model: `{model}`",
            f"Triage: {'on ✓' if triage_enabled else 'off'} (api mode only)",
            f"Onboarding: {'complete ✓' if onboarding == 'true' else 'pending'}",
        ]
        say(text="\n".join(lines), thread_ts=thread_ts)
        return True

    # config show — list feature flags for the current project
    if lower == "config show":
        channel_id = event.get("channel", "")
        channel_name = get_channel_name(channel_id)
        routing = CHANNEL_ROUTING.get(channel_name, {})
        project_key = routing.get("project")
        project = PROJECTS.get(project_key) if project_key else None
        if not project:
            say(text="❌ No project mapped to this channel.", thread_ts=thread_ts)
            return True
        features = project.get("features", {})
        project_name = project.get("name", project_key)
        lines = [f"🦞 *Feature flags — {project_name}*"]
        for feat in sorted(_VALID_FEATURES):
            enabled = features.get(feat, False)
            lines.append(f"  `{feat}`: {'on ✓' if enabled else 'off'}")
        say(text="\n".join(lines), thread_ts=thread_ts)
        return True

    # config <feature> on|off — toggle a feature flag for the current project
    if lower.startswith("config "):
        parts = lower[7:].split()
        if len(parts) == 2:
            feature_name, toggle = parts
            if feature_name not in _VALID_FEATURES:
                valid_list = ", ".join(f"`{f}`" for f in sorted(_VALID_FEATURES))
                say(
                    text=f"❌ Unknown feature `{feature_name}`. Valid features: {valid_list}",
                    thread_ts=thread_ts,
                )
                return True
            if toggle not in ("on", "off"):
                say(
                    text=f"Usage: `@Shellack config {feature_name} on|off`",
                    thread_ts=thread_ts,
                )
                return True
            channel_id = event.get("channel", "")
            channel_name = get_channel_name(channel_id)
            routing = CHANNEL_ROUTING.get(channel_name, {})
            project_key = routing.get("project")
            project = PROJECTS.get(project_key) if project_key else None
            if not project:
                say(text="❌ No project mapped to this channel.", thread_ts=thread_ts)
                return True
            if "features" not in project:
                project["features"] = {}
            project["features"][feature_name] = toggle == "on"
            project_name = project.get("name", project_key)
            state = "on" if toggle == "on" else "off"
            say(
                text=f"✅ `{feature_name}` is now *{state}* for {project_name}",
                thread_ts=thread_ts,
            )
            return True

    return False


@app.event("app_mention")
def handle_mention(event, say):
    """Route messages to the appropriate handler based on channel."""
    channel_id = event["channel"]
    channel_name = get_channel_name(channel_id)
    ts = event.get("ts", "")
    thread_ts = event.get("thread_ts", ts)

    # If this is a thread reply and the thread has an active run: session,
    # defer to handle_message — both handlers fire for @mentions in threads
    if thread_ts != ts and thread_ts in RUN_SESSIONS:
        return

    # Strip bot mention to get clean text
    raw_text = event.get("text", "")
    clean_text = re.sub(r"<@[A-Z0-9]+>", "", raw_text).strip()

    # --- config commands (any channel, any context) ---
    if _handle_config_command(clean_text, say, thread_ts, event):
        return

    # --- plugin management commands ---
    user_id = event.get("user", "")
    if _handle_plugin_command(clean_text, say, user_id, channel_id, thread_ts):
        return

    # --- run: session trigger (top-level mentions only) ---
    is_top_level = thread_ts == ts
    if is_top_level and clean_text.lower().startswith("run:"):
        task = clean_text[4:].strip()
        if not task:
            say(text="Usage: `@Shellack run: <task description>`", thread_ts=thread_ts)
            return

        # Pick backend
        backend_mode = os.environ.get("SESSION_BACKEND", "api")
        if backend_mode == "max" and MaxBackend.available():
            backend = MaxBackend()
        else:
            model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
            backend = APIBackend(model=model)

        # Get project context from channel
        routing = CHANNEL_ROUTING.get(channel_name, {})
        project_key = routing.get("project")
        system_prompt = ""
        cwd = "."
        if project_key:
            project = PROJECTS.get(project_key, {})
            cwd = project.get("path", ".")
            claude_md_path = os.path.join(cwd, "CLAUDE.md")
            if os.path.exists(claude_md_path):
                try:
                    with open(claude_md_path) as f:
                        system_prompt = f.read()
                except OSError:
                    pass

        # Append Slack-specific output rules to every run: session
        system_prompt = (system_prompt or "") + _SLACK_CONVERSATIONAL_PROMPT

        try:
            app.client.reactions_add(channel=channel_id, name="claude", timestamp=ts)
        except Exception:
            pass

        def _on_run_close(
            _mode=os.environ.get("SESSION_BACKEND", "api"),
            _model=os.environ.get("SESSION_MODEL", "claude-sonnet-4-6"),
            _ts=thread_ts,
            _channel=channel_id,
            _msg_ts=ts,
        ):
            usage_tracker.record_session(_mode, _model)
            RUN_SESSIONS.pop(_ts, None)
            try:
                app.client.reactions_remove(
                    channel=_channel, name="claude", timestamp=_msg_ts
                )
            except Exception:
                pass

        session = SlackSession(
            thread_ts=thread_ts,
            channel_id=channel_id,
            client=app.client,
            backend=backend,
            on_close=_on_run_close,
        )
        RUN_SESSIONS[thread_ts] = session
        session.start(task, system_prompt, cwd)
        print(f"🚀 run: session started in #{channel_name} thread {thread_ts}")
        return

    # --- existing routing ---
    print(f"📬 Message in #{channel_name}")

    # Route to appropriate handler
    if is_orchestrator_channel(channel_name):
        print(f"🎯 Routing to orchestrator")
        handle_orchestrator_message(event, say)

    elif is_peer_review_channel(channel_name):
        print(f"🤝 Routing to peer review")
        handle_peer_review_message(event, say)

    else:
        print(f"🤖 Routing to project agent")
        handle_project_message(event, say, channel_name)


@app.event("message")
def handle_message(event, say):
    """Handle threaded messages — route to active run: session or fall through."""
    # Ignore bot messages to prevent echo loops
    if event.get("subtype") == "bot_message" or event.get("bot_id"):
        return

    thread_ts = event.get("thread_ts")

    # Route to active run: session first
    if thread_ts and thread_ts in RUN_SESSIONS:
        session = RUN_SESSIONS[thread_ts]
        if not session._closed:
            text = re.sub(r"<@[A-Z0-9]+>", "", event.get("text", "")).strip()
            if text:
                session.feed_input(text)
            return
        # Session closed but not yet popped — clean up and fall through
        RUN_SESSIONS.pop(thread_ts, None)

    # Continue conversation in any thread where the bot has previously replied —
    # ONLY for messages without a bot @mention (those are handled by app_mention).
    if thread_ts:
        raw_text = event.get("text", "")
        if not re.search(r"<@[A-Z0-9]+>", raw_text):
            # Check if this is a thread the bot participated in
            if thread_ts in active_sessions:
                handle_mention(event, say)
            else:
                # Session expired — recreate it and continue
                channel_id = event.get("channel", "")
                channel_name = get_channel_name(channel_id)
                if channel_name and channel_name in CHANNEL_ROUTING:
                    routing = CHANNEL_ROUTING[channel_name]
                    project_key = routing.get("project")
                    if project_key:
                        with _session_lock:
                            active_sessions[thread_ts] = {
                                "handoff": None,
                                "journal_draft": "",
                                "turn_count": 0,
                                "project_key": project_key,
                                "cost": ThreadCost(),
                                "last_active": time.time(),
                            }
                        handle_mention(event, say)


# ============================================================================
# APP STORE CONNECT MONITORING
# ============================================================================


def start_app_store_connect_monitoring():
    """Monitor App Store Connect for all configured projects"""
    if not all(
        [
            os.environ.get("APP_STORE_CONNECT_KEY_ID"),
            os.environ.get("APP_STORE_CONNECT_ISSUER_ID"),
            os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY_PATH"),
        ]
    ):
        print("⚠️  App Store Connect not configured")
        return

    try:
        client = AppStoreConnectClient(
            key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
            issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
            private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"],
        )

        def handle_feedback(feedback: Dict):
            """Post feedback to appropriate channel"""
            bundle_id = feedback["bundle_id"]

            # Find project
            project = None
            for p in PROJECTS.values():
                if p.get("bundle_id") == bundle_id:
                    project = p
                    break

            if not project:
                return

            channel = project.get("primary_channel")
            if not channel:
                return

            # Format and post
            message = format_feedback_for_slack(feedback)

            app.client.chat_postMessage(channel=channel, text=message)

        # Monitor each project with bundle_id
        for project in PROJECTS.values():
            bundle_id = project.get("bundle_id")
            if bundle_id:
                thread = threading.Thread(
                    target=client.poll_for_new_feedback,
                    args=(bundle_id, handle_feedback),
                    kwargs={"poll_interval": 600},
                    daemon=True,
                )
                thread.start()
                print(f"📱 Monitoring {project['name']}")

    except Exception as e:
        print(f"❌ App Store Connect error: {e}")


# ============================================================================
# ONBOARDING
# ============================================================================


def check_and_post_onboarding() -> None:
    """Post onboarding message to the bot's own dev channel if not already complete."""
    if os.environ.get("ONBOARDING_COMPLETE") == "true":
        return

    # Find the bot's own channel from config (first project with platform=server,
    # or fall back to ONBOARDING_CHANNEL env var)
    onboarding_channel = os.environ.get("ONBOARDING_CHANNEL", "")
    if not onboarding_channel:
        for _ch_name, routing in CHANNEL_ROUTING.items():
            if (
                routing.get("mode") == "dedicated"
                and routing.get("project") == "shellack"
            ):
                onboarding_channel = _ch_name
                break
        if not onboarding_channel:
            # Fall back to first dedicated channel
            for _ch_name, routing in CHANNEL_ROUTING.items():
                if routing.get("mode") == "dedicated":
                    onboarding_channel = _ch_name
                    break

    channel_id = None
    try:
        result = app.client.conversations_list(
            types="public_channel,private_channel", limit=200
        )
        for ch in result.get("channels", []):
            if ch["name"] == onboarding_channel:
                channel_id = ch["id"]
                break
    except Exception as e:
        print(f"⚠️  Could not list channels for onboarding: {e}")
        return

    if not channel_id:
        print(f"⚠️  Could not find #{onboarding_channel} for onboarding. Skipping.")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👋 *Welcome to Shellack!* Let's get you set up.\n\n"
                    "How would you like to power AI sessions?"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "⚡ Claude Max subscription",
                    },
                    "action_id": "onboarding_mode_max",
                    "value": "max",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔑 Anthropic API key"},
                    "action_id": "onboarding_mode_api",
                    "value": "api",
                },
            ],
        },
    ]
    try:
        app.client.chat_postMessage(
            channel=channel_id,
            text="👋 Welcome to Shellack! Choose your AI backend.",
            blocks=blocks,
        )
        print(f"📋 Onboarding message posted to #{onboarding_channel}")
    except Exception as e:
        print(f"⚠️  Could not post onboarding: {e}")


@app.action(re.compile("onboarding_mode_(max|api)"))
def handle_onboarding_mode_select(ack, body, action, client):
    """Handle Max vs API mode selection during onboarding."""
    ack()
    mode = action.get("value", "api")
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")

    if mode == "max":
        set_env_var("SESSION_BACKEND", "max")
        set_env_var("ONBOARDING_COMPLETE", "true")
        text = (
            "✅ *Mode set to Claude Max.* All AI calls will use your Max subscription.\n\n"
            "Change anytime: `@Shellack set mode api`"
        )
        if channel and message_ts:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                text=text,
                blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
            )
    else:
        # API mode: ask for model selection
        set_env_var("SESSION_BACKEND", "api")
        model_blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "Which model would you like to use?",
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Opus 4.6 · ~$15/Mtok"},
                        "action_id": "onboarding_model_select",
                        "value": "claude-opus-4-6",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Sonnet 4.6 ✓ recommended · ~$3/Mtok",
                        },
                        "action_id": "onboarding_model_select",
                        "value": "claude-sonnet-4-6",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {
                            "type": "plain_text",
                            "text": "Haiku 4.5 · ~$0.25/Mtok",
                        },
                        "action_id": "onboarding_model_select",
                        "value": "claude-haiku-4-5-20251001",
                    },
                ],
            },
        ]
        if channel and message_ts:
            client.chat_update(
                channel=channel,
                ts=message_ts,
                text="Which model would you like to use?",
                blocks=model_blocks,
            )


@app.action("onboarding_model_select")
def handle_onboarding_model_select(ack, body, action, client):
    """Handle model selection during API mode onboarding."""
    ack()
    model = action.get("value", "claude-sonnet-4-6")
    channel = body.get("channel", {}).get("id", "")
    message_ts = body.get("message", {}).get("ts", "")

    set_env_var("SESSION_MODEL", model)
    set_env_var("ONBOARDING_COMPLETE", "true")
    text = (
        f"✅ *Model set to `{model}`.* Ready to go!\n\n"
        "Change anytime: `@Shellack set model opus|sonnet|haiku`"
    )
    if channel and message_ts:
        client.chat_update(
            channel=channel,
            ts=message_ts,
            text=text,
            blocks=[{"type": "section", "text": {"type": "mrkdwn", "text": text}}],
        )


# ============================================================================
# ACTION BUTTON HANDLER — numbered option buttons
# ============================================================================


@app.action(re.compile(r"shellack_option_\d+"))
def handle_option_click(ack, body, client):
    """Handle option button clicks — send selection as thread reply."""
    ack()
    action = body["actions"][0]
    value = action["value"]  # "thread_ts|number|label"
    parts = value.split("|", 2)
    if len(parts) < 3:
        return

    thread_ts = parts[0]
    label = parts[2]
    channel_id = body["channel"]["id"]

    # Post the selection as a message in the thread
    try:
        client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"Let's go with: {label}",
        )
    except Exception:
        pass

    # Remove the buttons (update the message to remove blocks)
    try:
        msg_ts = body["message"]["ts"]
        client.chat_update(
            channel=channel_id,
            ts=msg_ts,
            text=f"Selected: {label}",
            blocks=[],
        )
    except Exception:
        pass


# ============================================================================
# CLAUDE-SLACK BRIDGE HANDLER
# ============================================================================


@app.action("claude_bridge_input")
def handle_bridge_input(ack, body, action, client):
    """Handle button clicks from claude-slack Block Kit messages.

    Parses session_id and answer from the button value, writes the answer
    to the named pipe so Claude's stdin unblocks, then updates the Slack
    message to replace buttons with a confirmation.
    """
    ack()

    raw_value = action.get("value", "")
    parts = raw_value.split("|", 1)
    if len(parts) != 2:
        return  # malformed, ignore

    session_id, answer = parts
    # Validate session_id is a UUID to prevent path traversal
    try:
        uuid.UUID(session_id)
    except ValueError:
        return  # not a valid UUID, ignore silently
    session_file = f"/tmp/claude_bridge/{session_id}.json"
    channel = body.get("channel", {}).get("id", "")
    user = body.get("user", {}).get("id", "")
    if not channel or not user:
        return  # can't send ephemeral without both; already acked

    message_ts = body.get("message", {}).get("ts", "")
    # message_ts absent for modal/ephemeral actions — still write to pipe
    # but skip the chat_update

    # Load session
    try:
        with open(session_file) as f:
            session = json.load(f)
    except FileNotFoundError:
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text="⚠️ Session expired — the terminal session may have ended.",
        )
        return
    except Exception as e:
        logger.exception("Could not load bridge session")
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text="⚠️ Could not load session. The terminal session may have ended.",
        )
        return

    # Write answer to named pipe
    pipe_path = session.get("pipe")
    if not pipe_path:
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text="⚠️ Session data is corrupted — missing pipe path.",
        )
        return
    try:
        fd = os.open(pipe_path, os.O_WRONLY | os.O_NONBLOCK)
        try:
            os.write(fd, (answer + "\n").encode())
        finally:
            os.close(fd)
    except OSError as e:
        # ENXIO: no reader (claude-slack exited); EPIPE: broken pipe
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text=(
                f"⚠️ Could not reach terminal session — it may have exited. "
                f"({e.strerror})"
            ),
        )
        return  # leave buttons active so the user can retry

    # Update message: replace buttons with confirmation text
    # (Slack has no native disabled state; replacement is the correct approach)
    if not message_ts:
        return
    client.chat_update(
        channel=channel,
        ts=message_ts,
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"✅ *You chose:* {answer}"},
            }
        ],
        text=f"✅ You chose: {answer}",
    )


# ============================================================================
# STARTUP
# ============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("🦞 Shellack Unified Bot")
    print("=" * 60)
    print()
    print("📡 Modules loaded:")
    print("  ✅ Project Agents (dedicated channels)")
    print("  ✅ Orchestrator (#slackclaw-central)")
    print("  ✅ Peer Review (#code-review)")
    print()

    # Auto-join all configured channels
    print("📥 Joining configured channels...")
    for ch_name, config in CHANNEL_ROUTING.items():
        channel_id = config.get("channel_id")
        if not channel_id:
            continue
        try:
            app.client.conversations_join(channel=channel_id)
            print(f"  ✅ #{ch_name}")
        except Exception as e:
            print(f"  ⚠️  #{ch_name}: {e}")
    print()

    # Pre-warm one agent per configured channel (no delay on first message)
    print("🤖 Warming up project agents...")
    agent_factory.warmup_all(PROJECTS, CHANNEL_ROUTING, app)
    print(f"  ✅ {len(agent_factory.list_agents())} agents ready")
    print()

    # Start session cleanup thread (journal finalization on idle)
    threading.Thread(target=_session_cleanup_loop, daemon=True).start()

    # Start App Store Connect monitoring
    start_app_store_connect_monitoring()

    # Start bot
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))

    # Post onboarding if first run
    check_and_post_onboarding()

    print("✅ Bot is running!")
    print()
    print("Channels:")
    for channel, config in CHANNEL_ROUTING.items():
        mode = config.get("mode", "dedicated")
        print(f"  • #{channel} → {mode}")
    print()

    handler.start()
