#!/usr/bin/env python3
"""
SlackClaw Unified Bot
Modular architecture with channel-based routing

Channels:
- Project channels (#dayist-dev, etc) → Project agents
- #slackclaw-central → Orchestrator
- #code-review → Peer review system
"""

import json
import os
import re
import threading
import uuid
from typing import Dict, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from anthropic import Anthropic
from dotenv import load_dotenv

# Import our modules
from orchestrator_config import (
    get_project_for_channel,
    is_orchestrator_channel,
    is_peer_review_channel,
    CHANNEL_ROUTING,
    PROJECTS
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

# Load environment
load_dotenv()

# Initialize services
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Initialize modules
orchestrator = Orchestrator()
peer_review = PeerReviewCoordinator()
agent_factory = AgentFactory(anthropic_client)

# Session management
active_sessions: Dict[str, list] = {}

# run: session registry — keyed by thread_ts, cleaned up when session closes
RUN_SESSIONS: dict = {}

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
# PROJECT AGENT HANDLERS (for #dayist-dev, #nova-dev, etc.)
# ============================================================================

def handle_project_message(event, say, channel_name: str):
    """Handle messages in project-specific channels using specialized project agents."""
    text = event["text"]
    thread_ts = event.get("thread_ts", event["ts"])
    channel_id = event["channel"]

    # Get project config and resolve project key
    routing = CHANNEL_ROUTING.get(channel_name)
    project_key = routing["project"] if routing else None
    project = PROJECTS.get(project_key) if project_key else None

    if not project:
        say(
            text=f"❌ Channel `{channel_name}` not configured. See orchestrator_config.py",
            thread_ts=thread_ts
        )
        return

    # Remove bot mention
    prompt = text.split(">", 1)[1].strip() if ">" in text else text

    # Initialize session
    if thread_ts not in active_sessions:
        active_sessions[thread_ts] = []
        say(
            text=f"🧵 New session\n📂 Project: `{project['name']}`",
            thread_ts=thread_ts
        )

    # Build context (exclude the last user message — agent.handle adds it)
    context = list(active_sessions[thread_ts])

    active_sessions[thread_ts].append({"role": "user", "content": prompt})

    # Dispatch to specialized project agent
    say(text="🔄 Processing...", thread_ts=thread_ts)

    agent = agent_factory.get_agent(
        project_key, project,
        app, channel_id, thread_ts
    )
    response, agent_label = agent.handle(prompt, context)

    active_sessions[thread_ts].append({"role": "assistant", "content": response})

    # Label sub-agent responses so it's clear who answered
    header = f"🤖 *{agent_label}*\n" if agent_label != project["name"] else ""
    say(text=f"{header}{response}", thread_ts=thread_ts)

    usage_tracker.record_mention(
        os.environ.get("SESSION_BACKEND", "api"),
        os.environ.get("SESSION_MODEL", "claude-sonnet-4-6"),
    )


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
                thread_ts=thread_ts
            )
        else:
            say(
                text=f"❌ Failed to sync standards",
                thread_ts=thread_ts
            )

    elif "search all" in prompt_lower:
        # Extract query
        query = prompt.split(":", 1)[1].strip() if ":" in prompt else prompt.replace("search all", "").strip()

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

`@SlackClaw update all CLAUDE.md: <rule>`
Update CLAUDE.md files across all projects

`@SlackClaw sync standards from <source> to <target>`
Sync coding standards between projects

`@SlackClaw search all: <query>`
Search across all projects

`@SlackClaw help`
Show this help""",
            thread_ts=thread_ts
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
            "diff": text  # Simplified - would get actual diff
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
            thread_ts=thread_ts
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

    # add plugin <name>
    if lower.startswith("add plugin "):
        name = clean_text[11:].strip()
        result = plugin_manager.install_plugin(name)
        _handle_result(result, f"✅ Plugin `{name}` installed. Restart any active `run:` session to use it.")
        return True

    # remove plugin <name>
    if lower.startswith("remove plugin "):
        name = clean_text[14:].strip()
        result = plugin_manager.uninstall_plugin(name)
        _handle_result(result, f"✅ Plugin `{name}` removed.")
        return True

    # add mcp <name> <command>
    if lower.startswith("add mcp "):
        rest = clean_text[8:].strip()
        parts = rest.split(None, 1)
        if len(parts) < 2:
            _post_error("Usage: `@SlackClaw add mcp <name> <command>`")
            return True
        mcp_name, command = parts
        result = plugin_manager.add_mcp(mcp_name, command)
        _handle_result(result, f"✅ MCP server `{mcp_name}` added.")
        return True

    # remove mcp <name>
    if lower.startswith("remove mcp "):
        name = clean_text[11:].strip()
        result = plugin_manager.remove_mcp(name)
        _handle_result(result, f"✅ MCP server `{name}` removed.")
        return True

    # add bot-plugin <name_or_url>
    if lower.startswith("add bot-plugin "):
        name_or_url = clean_text[15:].strip()
        result = plugin_manager.add_bot_plugin(name_or_url, registry=_bot_extensions)
        installed_name = result.get("name", name_or_url)
        _handle_result(result, f"✅ Bot extension `{installed_name}` installed and loaded.")
        return True

    # remove bot-plugin <name>
    if lower.startswith("remove bot-plugin "):
        name = clean_text[18:].strip()
        result = plugin_manager.remove_bot_plugin(name, registry=_bot_extensions)
        _handle_result(result, f"✅ Bot extension `{name}` removed.")
        return True

    return False


def _handle_config_command(clean_text: str, say, thread_ts: str) -> bool:
    """Handle config commands. Returns True if the command was consumed."""
    lower = clean_text.lower()

    # set mode max|api
    if lower.startswith("set mode "):
        mode = lower[9:].strip()
        if mode in ("max", "api"):
            set_env_var("SESSION_BACKEND", mode)
            say(text=f"✅ Mode set to `{mode}`. No restart required.", thread_ts=thread_ts)
        else:
            say(text="Usage: `@SlackClaw set mode max|api`", thread_ts=thread_ts)
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
            say(text="Usage: `@SlackClaw set model opus|sonnet|haiku`", thread_ts=thread_ts)
        return True

    # usage
    if lower == "usage":
        say(text=usage_tracker.format_usage_message(), thread_ts=thread_ts)
        return True

    # config
    if lower == "config":
        mode = os.environ.get("SESSION_BACKEND", "api")
        model = os.environ.get("SESSION_MODEL", "claude-sonnet-4-6")
        onboarding = os.environ.get("ONBOARDING_COMPLETE", "false")
        lines = [
            "🦞 *SlackClaw — Config*",
            f"Backend: `{mode}`",
            f"Model: `{model}`",
            f"Onboarding: {'complete ✓' if onboarding == 'true' else 'pending'}",
        ]
        say(text="\n".join(lines), thread_ts=thread_ts)
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
    if _handle_config_command(clean_text, say, thread_ts):
        return

    # --- plugin management commands ---
    user_id = event.get("user", "")
    if _handle_plugin_command(clean_text, say, user_id, channel_id, thread_ts):
        return

    # --- run: session trigger (top-level mentions only) ---
    is_top_level = (thread_ts == ts)
    if is_top_level and clean_text.lower().startswith("run:"):
        task = clean_text[4:].strip()
        if not task:
            say(text="Usage: `@SlackClaw run: <task description>`", thread_ts=thread_ts)
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

        def _on_run_close(
            _mode=os.environ.get("SESSION_BACKEND", "api"),
            _model=os.environ.get("SESSION_MODEL", "claude-sonnet-4-6"),
            _ts=thread_ts,
        ):
            usage_tracker.record_session(_mode, _model)
            RUN_SESSIONS.pop(_ts, None)

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

    # Fall through to existing behavior for active_sessions (quick reply threads)
    if thread_ts and thread_ts in active_sessions:
        handle_mention(event, say)


# ============================================================================
# APP STORE CONNECT MONITORING
# ============================================================================

def start_app_store_connect_monitoring():
    """Monitor App Store Connect for all configured projects"""
    if not all([
        os.environ.get("APP_STORE_CONNECT_KEY_ID"),
        os.environ.get("APP_STORE_CONNECT_ISSUER_ID"),
        os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY_PATH")
    ]):
        print("⚠️  App Store Connect not configured")
        return

    try:
        client = AppStoreConnectClient(
            key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
            issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
            private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"]
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

            app.client.chat_postMessage(
                channel=channel,
                text=message
            )

        # Monitor each project with bundle_id
        for project in PROJECTS.values():
            bundle_id = project.get("bundle_id")
            if bundle_id:
                thread = threading.Thread(
                    target=client.poll_for_new_feedback,
                    args=(bundle_id, handle_feedback),
                    kwargs={"poll_interval": 600},
                    daemon=True
                )
                thread.start()
                print(f"📱 Monitoring {project['name']}")

    except Exception as e:
        print(f"❌ App Store Connect error: {e}")


# ============================================================================
# ONBOARDING
# ============================================================================

def check_and_post_onboarding() -> None:
    """Post onboarding message to #slackclaw-dev if not already complete."""
    if os.environ.get("ONBOARDING_COMPLETE") == "true":
        return

    # Find the slackclaw-dev channel ID
    channel_id = None
    try:
        result = app.client.conversations_list(types="public_channel,private_channel", limit=200)
        for ch in result.get("channels", []):
            if ch["name"] == "slackclaw-dev":
                channel_id = ch["id"]
                break
    except Exception as e:
        print(f"⚠️  Could not list channels for onboarding: {e}")
        return

    if not channel_id:
        print("⚠️  Could not find #slackclaw-dev for onboarding. Skipping.")
        return

    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "👋 *Welcome to SlackClaw!* Let's get you set up.\n\n"
                    "How would you like to power AI sessions?"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "⚡ Claude Max subscription"},
                    "action_id": "onboarding_mode_select",
                    "value": "max",
                    "style": "primary",
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "🔑 Anthropic API key"},
                    "action_id": "onboarding_mode_select",
                    "value": "api",
                },
            ],
        },
    ]
    try:
        app.client.chat_postMessage(
            channel=channel_id,
            text="👋 Welcome to SlackClaw! Choose your AI backend.",
            blocks=blocks,
        )
        print("📋 Onboarding message posted to #slackclaw-dev")
    except Exception as e:
        print(f"⚠️  Could not post onboarding: {e}")


@app.action("onboarding_mode_select")
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
            "Change anytime: `@SlackClaw set mode api`"
        )
        if channel and message_ts:
            client.chat_update(channel=channel, ts=message_ts, text=text, blocks=[
                {"type": "section", "text": {"type": "mrkdwn", "text": text}}
            ])
    else:
        # API mode: ask for model selection
        set_env_var("SESSION_BACKEND", "api")
        model_blocks = [
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": "Which model would you like to use?"},
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
                        "text": {"type": "plain_text", "text": "Sonnet 4.6 ✓ recommended · ~$3/Mtok"},
                        "action_id": "onboarding_model_select",
                        "value": "claude-sonnet-4-6",
                        "style": "primary",
                    },
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Haiku 4.5 · ~$0.25/Mtok"},
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
        "Change anytime: `@SlackClaw set model opus|sonnet|haiku`"
    )
    if channel and message_ts:
        client.chat_update(channel=channel, ts=message_ts, text=text, blocks=[
            {"type": "section", "text": {"type": "mrkdwn", "text": text}}
        ])


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
        client.chat_postEphemeral(
            channel=channel,
            user=user,
            text=f"⚠️ Could not load session: {e}",
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
        return  # leave buttons active so Dave can retry

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
    print("🦞 SlackClaw Unified Bot")
    print("=" * 60)
    print()
    print("📡 Modules loaded:")
    print("  ✅ Project Agents (dedicated channels)")
    print("  ✅ Orchestrator (#slackclaw-central)")
    print("  ✅ Peer Review (#code-review)")
    print()

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
