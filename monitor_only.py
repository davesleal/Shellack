#!/usr/bin/env python3
"""
Lightweight App Store Connect Monitor
Posts to Slack without using Claude API - zero AI costs!
"""

import os
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from dotenv import load_dotenv
from app_store_connect import AppStoreConnectClient, format_feedback_for_slack
import threading

load_dotenv()

app = App(token=os.environ.get("SLACK_BOT_TOKEN"))

# Configuration
CHANNEL = os.environ.get("MONITOR_CHANNEL", "project-dev")  # Your project channel
BUNDLE_ID = os.environ.get("MONITOR_BUNDLE_ID", "com.example.yourapp")  # Your app bundle ID
CHECK_INTERVAL = 600  # 10 minutes


def start_monitoring():
    """Monitor App Store Connect and post to Slack"""
    try:
        client = AppStoreConnectClient(
            key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
            issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
            private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"],
        )

        def handle_feedback(feedback):
            """Post feedback to Slack with action buttons"""
            message = format_feedback_for_slack(feedback)

            # Determine priority
            is_urgent = False
            if feedback["type"] == "review":
                is_urgent = feedback["rating"] <= 2
            elif feedback["type"] == "beta_feedback":
                urgent_keywords = ["crash", "bug", "broken", "error", "doesn't work"]
                comment = feedback.get("comment", "").lower()
                is_urgent = any(kw in comment for kw in urgent_keywords)

            # Add priority emoji
            if is_urgent:
                message = f"🚨 **URGENT** {message}"

            try:
                result = app.client.chat_postMessage(
                    channel=CHANNEL,
                    text=message,
                    blocks=[
                        {
                            "type": "section",
                            "text": {"type": "mrkdwn", "text": message},
                        },
                        {
                            "type": "context",
                            "elements": [
                                {
                                    "type": "mrkdwn",
                                    "text": "💡 *To investigate:* Run `claude code` locally and ask about this issue",
                                }
                            ],
                        },
                        {
                            "type": "actions",
                            "elements": [
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "📝 Add to Backlog",
                                    },
                                    "value": "add_backlog",
                                    "action_id": "add_backlog",
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "🔍 Investigating",
                                    },
                                    "value": "investigating",
                                    "action_id": "investigating",
                                },
                                {
                                    "type": "button",
                                    "text": {
                                        "type": "plain_text",
                                        "text": "✅ Resolved",
                                    },
                                    "style": "primary",
                                    "value": "resolved",
                                    "action_id": "resolved",
                                },
                            ],
                        },
                    ],
                )

                print(f"✅ Posted feedback to Slack (thread: {result['ts']})")

            except Exception as e:
                print(f"❌ Error posting to Slack: {str(e)}")

        # Start polling
        print(f"🔍 Monitoring {BUNDLE_ID}")
        print(f"📢 Posting to #{CHANNEL}")
        print(f"⏱️  Checking every {CHECK_INTERVAL // 60} minutes")
        print(f"💰 No AI costs - using Slack + App Store Connect only\n")

        client.poll_for_new_feedback(
            BUNDLE_ID, handle_feedback, poll_interval=CHECK_INTERVAL
        )

    except Exception as e:
        print(f"❌ Error starting monitoring: {str(e)}")


@app.action("add_backlog")
def handle_add_backlog(ack, action, say):
    """Mark as added to backlog"""
    ack()
    say(text="📝 Added to backlog", thread_ts=action["message"]["ts"])


@app.action("investigating")
def handle_investigating(ack, action, say):
    """Mark as investigating"""
    ack()
    say(text="🔍 Investigation started", thread_ts=action["message"]["ts"])


@app.action("resolved")
def handle_resolved(ack, action, say):
    """Mark as resolved"""
    ack()
    say(text="✅ Marked as resolved", thread_ts=action["message"]["ts"])


@app.command("/check-reviews")
def handle_check_reviews(ack, command, say):
    """Manual command to check for new reviews"""
    ack()
    say("🔍 Checking for new reviews...")
    # This would trigger a manual check
    # For now, just acknowledge


if __name__ == "__main__":
    print("🚀 Starting App Store Connect Monitor")
    print("=" * 50)
    print()

    # Start monitoring in background thread
    monitor_thread = threading.Thread(target=start_monitoring, daemon=True)
    monitor_thread.start()

    # Start Slack bot
    handler = SocketModeHandler(app, os.environ.get("SLACK_APP_TOKEN"))

    print("✅ Monitor is running!")
    print()
    print("This bot does NOT use Claude API - zero AI costs!")
    print("Reviews and feedback will be posted to Slack.")
    print("Use Claude Code locally to investigate.")
    print()
    print("Press Ctrl+C to stop")
    print()

    handler.start()
