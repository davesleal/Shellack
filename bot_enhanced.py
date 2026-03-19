#!/usr/bin/env python3
"""
Enhanced Slack Claude Code Bot with App Store Connect Integration
"""

import os
import json
import threading
from typing import Dict, Optional
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from anthropic import Anthropic
from dotenv import load_dotenv
from app_store_connect import AppStoreConnectClient, format_feedback_for_slack

# Load environment variables
load_dotenv()

# Initialize Slack app
app = App(token=os.environ.get("SLACK_BOT_TOKEN"))
anthropic_client = Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

# Session management
active_sessions: Dict[str, list] = {}

# Channel to project mapping
CHANNEL_PROJECTS = {
    "dayist-dev": {
        "path": os.environ.get("DAYIST_PROJECT_PATH"),
        "bundle_id": "com.daveleal.Dayist",
        "auto_investigate": True,  # Auto-dispatch agents for bugs
    }
}


def get_project_config(channel_name: str) -> Optional[Dict]:
    """Get project configuration for a channel"""
    return CHANNEL_PROJECTS.get(channel_name)


def execute_claude_task(
    project_path: str, task: str, thread_context: list = None
) -> str:
    """
    Execute a task using Claude with full context

    In production, this would use Claude Agent SDK for tool access
    """
    try:
        # Build messages with context
        messages = thread_context or []
        messages.append({"role": "user", "content": task})

        # Call Claude API with context about the project
        system_prompt = f"""You are a senior iOS developer working on a project located at: {project_path}

You have access to:
- Read and write files
- Run git commands
- Execute xcodebuild
- Run tests
- Analyze crash logs

The project is a SwiftUI iOS app called Dayist. Target iOS 26+.

When responding:
1. Be concise but thorough
2. Show code changes as diffs when relevant
3. Run tests to verify changes
4. Commit changes with clear messages
"""

        response = anthropic_client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            system=system_prompt,
            messages=messages,
        )

        return response.content[0].text

    except Exception as e:
        return f"Error: {str(e)}"


def create_autonomous_agent(
    project_path: str, task: str, thread_ts: str, channel_id: str, context: list = None
):
    """
    Create autonomous agent to handle a task

    Runs in background, posts progress updates
    """
    try:
        # Initial status
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text="🤖 Starting autonomous investigation...",
        )

        # Execute task
        result = execute_claude_task(project_path, task, context)

        # Post result with formatting
        app.client.chat_postMessage(
            channel=channel_id,
            thread_ts=thread_ts,
            text=f"✅ *Investigation Complete*\n\n{result}",
            blocks=[
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"✅ *Investigation Complete*\n\n{result}",
                    },
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Apply Fix"},
                            "style": "primary",
                            "value": "apply_fix",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Run Tests"},
                            "value": "run_tests",
                        },
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "Create PR"},
                            "value": "create_pr",
                        },
                    ],
                },
            ],
        )

    except Exception as e:
        app.client.chat_postMessage(
            channel=channel_id, thread_ts=thread_ts, text=f"❌ Error: {str(e)}"
        )


@app.event("app_mention")
def handle_mention(event, say):
    """Handle @claude mentions"""
    channel_id = event["channel"]
    thread_ts = event.get("thread_ts", event["ts"])
    text = event["text"]

    # Get channel info
    channel_info = app.client.conversations_info(channel=channel_id)
    channel_name = channel_info["channel"]["name"]

    config = get_project_config(channel_name)

    if not config:
        say(
            text=f"❌ Channel not configured. Available: {', '.join(CHANNEL_PROJECTS.keys())}",
            thread_ts=thread_ts,
        )
        return

    # Extract prompt (remove mention)
    prompt = text.split(">", 1)[1].strip() if ">" in text else text

    # Initialize session if new
    if thread_ts not in active_sessions:
        active_sessions[thread_ts] = []
        say(text=f"🧵 New session\n📂 Project: `{config['path']}`", thread_ts=thread_ts)

    # Add to history
    active_sessions[thread_ts].append({"role": "user", "content": prompt})

    # Check for autonomous mode
    if prompt.lower().startswith("auto:") or prompt.lower().startswith("investigate:"):
        task = prompt.split(":", 1)[1].strip()

        say(text="🚀 Dispatching autonomous agent...", thread_ts=thread_ts)

        thread = threading.Thread(
            target=create_autonomous_agent,
            args=(
                config["path"],
                task,
                thread_ts,
                channel_id,
                active_sessions[thread_ts],
            ),
        )
        thread.daemon = True
        thread.start()
        return

    # Regular interaction
    say(text="🔄 Processing...", thread_ts=thread_ts)

    response = execute_claude_task(config["path"], prompt, active_sessions[thread_ts])

    active_sessions[thread_ts].append({"role": "assistant", "content": response})

    say(text=response, thread_ts=thread_ts)


@app.action("apply_fix")
def handle_apply_fix(ack, action, say):
    """Handle 'Apply Fix' button click"""
    ack()
    say("🔨 Applying fix...")
    # TODO: Implement fix application logic


@app.action("run_tests")
def handle_run_tests(ack, action, say):
    """Handle 'Run Tests' button click"""
    ack()
    say("🧪 Running tests...")
    # TODO: Implement test execution


@app.action("create_pr")
def handle_create_pr(ack, action, say):
    """Handle 'Create PR' button click"""
    ack()
    say("📝 Creating pull request...")
    # TODO: Implement PR creation


def start_app_store_connect_monitoring():
    """Start monitoring App Store Connect for feedback"""
    try:
        client = AppStoreConnectClient(
            key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
            issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
            private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"],
        )

        def handle_feedback(feedback: Dict):
            """Handle new feedback from App Store Connect"""
            bundle_id = feedback["bundle_id"]

            # Find channel for this app
            channel_name = None
            config = None

            for ch_name, ch_config in CHANNEL_PROJECTS.items():
                if ch_config.get("bundle_id") == bundle_id:
                    channel_name = ch_name
                    config = ch_config
                    break

            if not channel_name:
                print(f"No channel configured for {bundle_id}")
                return

            # Format and post to Slack
            message = format_feedback_for_slack(feedback)

            result = app.client.chat_postMessage(channel=channel_name, text=message)

            thread_ts = result["ts"]

            # Auto-investigate if enabled and it's a low rating or contains keywords
            if config.get("auto_investigate"):
                should_investigate = False

                if feedback["type"] == "review" and feedback["rating"] <= 3:
                    should_investigate = True

                if feedback["type"] == "beta_feedback":
                    keywords = ["crash", "bug", "broken", "error", "doesn't work"]
                    comment = feedback.get("comment", "").lower()
                    if any(kw in comment for kw in keywords):
                        should_investigate = True

                if should_investigate:
                    task = f"Investigate this user feedback and identify potential issues:\n\n{message}"

                    thread = threading.Thread(
                        target=create_autonomous_agent,
                        args=(config["path"], task, thread_ts, result["channel"]),
                    )
                    thread.daemon = True
                    thread.start()

        # Start polling (runs in background thread)
        for channel_name, config in CHANNEL_PROJECTS.items():
            bundle_id = config.get("bundle_id")
            if bundle_id:
                thread = threading.Thread(
                    target=client.poll_for_new_feedback,
                    args=(bundle_id, handle_feedback),
                    kwargs={"poll_interval": 300},  # Check every 5 minutes
                )
                thread.daemon = True
                thread.start()
                print(f"🔍 Monitoring App Store Connect for {bundle_id}")

    except Exception as e:
        print(f"❌ Error starting App Store Connect monitoring: {str(e)}")


if __name__ == "__main__":
    print("🚀 Starting Slack Claude Code Bot...")

    # Start App Store Connect monitoring
    if all(
        [
            os.environ.get("APP_STORE_CONNECT_KEY_ID"),
            os.environ.get("APP_STORE_CONNECT_ISSUER_ID"),
            os.environ.get("APP_STORE_CONNECT_PRIVATE_KEY_PATH"),
        ]
    ):
        start_app_store_connect_monitoring()
    else:
        print("⚠️  App Store Connect credentials not configured")

    # Start Slack bot
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))

    print("✅ Bot is running!")
    print(f"📱 Monitoring channels: {', '.join(CHANNEL_PROJECTS.keys())}")

    handler.start()
