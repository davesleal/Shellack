#!/usr/bin/env python3
"""
Slack Claude Code Bot - Bridges Slack conversations to Claude Code sessions
"""

import os
import json
from typing import Dict, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from anthropic import Anthropic
import subprocess
from pathlib import Path

# Initialize Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Session management: thread_ts -> conversation history
active_sessions: Dict[str, list] = {}

# Channel to project directory mapping
CHANNEL_PROJECTS = {
    "dayist-dev": "/path/to/your/project"  # Update with your project path,
    # Add more channels/projects here
}


def get_project_path(channel_name: str) -> Optional[str]:
    """Get the project directory for a channel"""
    return CHANNEL_PROJECTS.get(channel_name)


def execute_claude_code_command(project_path: str, prompt: str) -> str:
    """
    Execute a Claude Code command in the project directory

    This uses subprocess to invoke claude-code CLI directly
    """
    try:
        # Change to project directory and run claude command
        result = subprocess.run(
            ["claude", "code", "--prompt", prompt],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        if result.returncode == 0:
            return result.stdout
        else:
            return f"Error: {result.stderr}"

    except subprocess.TimeoutExpired:
        return "Command timed out after 5 minutes"
    except Exception as e:
        return f"Error executing command: {str(e)}"


def create_autonomous_agent(
    project_path: str, task: str, thread_ts: str, channel_id: str
):
    """
    Create an autonomous agent to handle a task

    This runs in the background and posts updates to the Slack thread
    """
    # Post initial message
    app.client.chat_postMessage(
        channel=channel_id,
        thread_ts=thread_ts,
        text=f"🤖 Starting autonomous agent for: {task}",
    )

    # Execute the task using Claude Code
    result = execute_claude_code_command(project_path, task)

    # Post result
    app.client.chat_postMessage(
        channel=channel_id, thread_ts=thread_ts, text=f"✅ Task complete:\n\n{result}"
    )


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @mentions of the bot"""
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    text = event["text"]
    user = event["user"]

    # Get channel info to determine project
    channel_info = app.client.conversations_info(channel=channel_id)
    channel_name = channel_info["channel"]["name"]

    project_path = get_project_path(channel_name)

    if not project_path:
        say(
            text=f"❌ This channel is not configured for Claude Code. Available channels: {', '.join(CHANNEL_PROJECTS.keys())}",
            thread_ts=thread_ts,
        )
        return

    # Remove bot mention from text
    prompt = text.split(">", 1)[1].strip() if ">" in text else text

    # Check if this is a new session or continuation
    if thread_ts not in active_sessions:
        active_sessions[thread_ts] = []
        say(
            text=f"🧵 Starting new session in {channel_name}\n📂 Project: `{project_path}`",
            thread_ts=thread_ts,
        )

    # Add to conversation history
    active_sessions[thread_ts].append({"role": "user", "content": prompt})

    # Check for autonomous mode
    if prompt.lower().startswith("auto:"):
        task = prompt[5:].strip()
        say(text=f"🚀 Dispatching autonomous agent...", thread_ts=thread_ts)

        # Run agent in background (in production, use a task queue)
        import threading

        agent_thread = threading.Thread(
            target=create_autonomous_agent,
            args=(project_path, task, thread_ts, channel_id),
        )
        agent_thread.start()
        return

    # Execute command via Claude Code
    say(text="🔄 Processing...", thread_ts=thread_ts)

    response = execute_claude_code_command(project_path, prompt)

    # Add response to history
    active_sessions[thread_ts].append({"role": "assistant", "content": response})

    # Post response
    say(text=response, thread_ts=thread_ts)


@app.event("message")
def handle_message(event, say):
    """Handle messages in threads where bot was mentioned"""
    # Only respond to threaded messages in active sessions
    thread_ts = event.get("thread_ts")

    if thread_ts and thread_ts in active_sessions:
        # This is a follow-up in an existing session
        handle_mention(event, say)


# Webhook endpoint for App Store Connect
@app.command("/bug-report")
def handle_bug_report(ack, command, say):
    """
    Handle bug reports from App Store Connect

    Usage: /bug-report {"app": "Dayist", "crash_log": "...", "user_feedback": "..."}
    """
    ack()

    try:
        data = json.loads(command["text"])
        app_name = data.get("app", "Unknown")
        crash_log = data.get("crash_log", "")
        feedback = data.get("user_feedback", "")

        channel_name = f"{app_name.lower()}-dev"

        # Post initial bug report
        result = say(
            channel=channel_name,
            text=f"🚨 *New Bug Report from App Store Connect*\n\n"
            f"*App:* {app_name}\n"
            f"*Feedback:* {feedback}\n\n"
            f"```\n{crash_log[:500]}...\n```",
        )

        thread_ts = result["ts"]

        # Auto-dispatch investigation agent
        project_path = get_project_path(channel_name)
        if project_path:
            task = f"Investigate this crash and propose a fix:\n\nUser feedback: {feedback}\n\nCrash log:\n{crash_log}"

            import threading

            agent_thread = threading.Thread(
                target=create_autonomous_agent,
                args=(project_path, task, thread_ts, result["channel"]),
            )
            agent_thread.start()

    except Exception as e:
        say(text=f"Error processing bug report: {str(e)}")


if __name__ == "__main__":
    # Run in Socket Mode (easier for development, no public URL needed)
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))
    print("🚀 Slack Claude Code Bot is running!")
    handler.start()
