# Hybrid Approach: Minimize API Costs

Use your Claude subscription + minimal API usage for automation.

## Architecture

```
App Store Connect → Slack (API cost: ~$2/month)
                     ↓
              Human reviews in Slack
                     ↓
         Claude Code CLI (your subscription)
                     ↓
              Post results to Slack
```

## Setup

### 1. Lightweight Monitoring Bot

Create `monitor_only.py`:

```python
#!/usr/bin/env python3
"""
Lightweight bot - only monitors App Store Connect
Does NOT use Claude API - just posts to Slack
"""

import os
from slack_bolt import App
from app_store_connect import AppStoreConnectClient, format_feedback_for_slack

app = App(token=os.environ["SLACK_BOT_TOKEN"])

def start_monitoring():
    client = AppStoreConnectClient(
        key_id=os.environ["APP_STORE_CONNECT_KEY_ID"],
        issuer_id=os.environ["APP_STORE_CONNECT_ISSUER_ID"],
        private_key_path=os.environ["APP_STORE_CONNECT_PRIVATE_KEY_PATH"]
    )

    def post_to_slack(feedback):
        message = format_feedback_for_slack(feedback)

        app.client.chat_postMessage(
            channel="project-dev",
            text=message,
            blocks=[
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": message}
                },
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {"type": "plain_text", "text": "🔍 Investigate with Claude Code"},
                            "style": "primary",
                            "url": f"slack://channel?team=YOUR_TEAM&id=CHANNEL_ID"
                        }
                    ]
                }
            ]
        )

    # Monitor for new feedback
    client.poll_for_new_feedback(
        "com.example.yourapp",
        post_to_slack,
        poll_interval=600  # Every 10 minutes
    )

if __name__ == "__main__":
    print("📱 Monitoring App Store Connect...")
    print("💰 No Claude API usage - zero AI costs!")
    start_monitoring()
```

### 2. Your Workflow

When a bug is posted:

1. **Bot posts to Slack** (no AI, just formatting)
   ```
   🚨 New Review (⭐⭐)
   "App crashes on login"
   ```

2. **You investigate locally**
   ```bash
   cd /path/to/your/project
   claude code
   # Ask Claude about the issue using your subscription
   ```

3. **You post results to Slack**
   - Copy Claude's analysis
   - Post to the thread

### 3. Cost Comparison

| Approach | Monthly Cost |
|----------|-------------|
| **Full AI bot** | $20-50 |
| **Hybrid (monitoring only)** | $0 (uses subscription) |
| **Manual everything** | $0 but time-intensive |

## Advanced: Slack Shortcuts

Add shortcuts to launch Claude Code:

**In Slack app settings:**
```
Shortcut: "Investigate with Claude"
Action: Opens terminal and runs:
  cd /path/to/project && claude code --prompt "Investigate the issue in #thread"
```

## Automation Without AI Costs

You can automate these without Claude API:

### 1. Review Aggregation
```python
# Weekly digest of all reviews
weekly_summary = collect_reviews()
post_to_slack("#project-weekly", weekly_summary)
```

### 2. Priority Flagging
```python
# Flag urgent issues (no AI needed)
if rating <= 2 or "crash" in review:
    post_to_slack("#project-urgent", review)
    notify_on_call_dev()
```

### 3. TestFlight Feedback
```python
# Auto-post beta feedback
for feedback in get_beta_feedback():
    post_to_slack("#project-beta", feedback)
```

### 4. Release Reminders
```python
# Check if new version is due
if days_since_release > 14:
    post_to_slack("#project-dev", "⏰ Time to ship 1.3.0?")
```

All of these are simple scripts - no AI needed!

## Recommended Setup

**Phase 1: Free automation**
- App Store Connect monitoring
- Auto-post to Slack
- Manual investigation via Claude Code

**Phase 2: Add AI only where valuable**
- Keep most work in Claude Code (your subscription)
- Use API for specific automations like:
  - Initial crash log analysis ($1-2/month)
  - Code review summaries ($2-3/month)

**Total cost: ~$3-5/month vs $20-50/month**

## MCP Alternative (Advanced)

If you're comfortable with experimental features:

1. Use Claude Code's MCP support
2. Connect Slack as MCP resource
3. Process everything locally

This is cutting-edge but could let you use your subscription for the bot.

See: https://modelcontextprotocol.io/introduction

## Verdict

**Recommended approach:**
1. ✅ Monitor App Store Connect automatically (free/cheap)
2. ✅ Post to Slack for visibility (free)
3. ✅ Investigate with Claude Code CLI (your subscription)
4. ✅ Share findings in Slack (manual but free)

**Add paid API later** only if you find specific automations worth $20-50/month.

Most developers find the hybrid approach sufficient - you get 90% of the value at 10% of the cost!
