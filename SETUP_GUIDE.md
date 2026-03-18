# Setup Guide: Slack Claude Code Bot

Complete guide to set up automated development workflows via Slack.

## Prerequisites

- Python 3.9+
- Slack workspace with admin access
- Claude API key
- App Store Connect API access (optional, for automation)
- Claude Code Slack plugin (for unified Claude Code ↔ Slack workflow):
  ```bash
  claude plugin install slack
  ```
  This enables Claude Code to read/write Slack directly alongside the bot, unifying the multi-agent flow.

## Step 1: Create Slack App

### Option A: Using App Manifest (Recommended - Fast & Easy!)

**This automatically configures everything for you.**

1. Go to https://api.slack.com/apps
2. Click **"Create New App"** → **"From an app manifest"**
3. Select your workspace
4. Choose **YAML** tab
5. Copy and paste the contents of `slack-app-manifest.yml` from this repo
6. Click **"Next"** → Review settings → **"Create"**
7. Done! Your app is fully configured ✨

**Now get your tokens:**

1. Go to **"OAuth & Permissions"**
   - Copy the **Bot User OAuth Token** (starts with `xoxb-`)

2. Go to **"Basic Information"** → **"App-Level Tokens"**
   - Click **"Generate Token and Scopes"**
   - Name: "Socket Token"
   - Add scope: `connections:write`
   - Click **"Generate"**
   - Copy the **App-Level Token** (starts with `xapp-`)

3. Click **"Install to Workspace"** → **"Allow"**

That's it! Skip to [Step 2](#step-2-get-claude-api-key).

---

### Option B: Manual Setup (If manifest doesn't work)

<details>
<summary>Click to expand manual instructions</summary>

#### 1.1 Create App

1. Go to https://api.slack.com/apps
2. Click "Create New App" → "From scratch"
3. Name: "SlackClaw"
4. Select your workspace

#### 1.2 Configure OAuth & Permissions

Navigate to "OAuth & Permissions" and add these **Bot Token Scopes**:

```
app_mentions:read
channels:history
channels:read
chat:write
files:read
files:write
groups:history
groups:read
im:history
im:read
mpim:history
mpim:read
users:read
```

#### 1.3 Enable Socket Mode

1. Go to "Socket Mode" in sidebar
2. Enable Socket Mode
3. Click "Generate" for app-level token
4. Name: "Socket Token"
5. Add scope: `connections:write`
6. Copy the **App-Level Token** (starts with `xapp-`)

#### 1.4 Subscribe to Events

1. Go to "Event Subscriptions"
2. Enable Events
3. Subscribe to these **bot events**:
   - `app_mention`
   - `message.channels`
   - `message.groups`
   - `message.im`
   - `message.mpim`

#### 1.5 Enable Interactivity

1. Go to "Interactivity & Shortcuts"
2. Turn on **Interactivity**
3. (Request URL not needed for Socket Mode)

#### 1.6 Install App

1. Go to "Install App" in sidebar
2. Click "Install to Workspace"
3. Click "Allow"
4. Copy the **Bot User OAuth Token** (starts with `xoxb-`)

</details>

## Step 2: Get Claude API Key

1. Go to https://console.anthropic.com/
2. Navigate to API Keys
3. Create new key
4. Copy the key (starts with `sk-ant-`)

## Step 3: App Store Connect API (Optional)

### 3.1 Create API Key

1. Go to https://appstoreconnect.apple.com/access/api
2. Click "+" to create new key
3. Name: "Claude Bot API"
4. Access: **Developer** (minimum required)
5. Download the key file (`AuthKey_XXXXX.p8`)
6. Copy the **Key ID** and **Issuer ID**

⚠️ **Important**: Save the `.p8` file securely - you can't download it again!

### 3.2 Store Key Securely

```bash
# Move key to secure location
mkdir -p ~/.appstoreconnect
mv ~/Downloads/AuthKey_*.p8 ~/.appstoreconnect/
chmod 600 ~/.appstoreconnect/AuthKey_*.p8
```

## Step 4: Install & Configure Bot

### 4.1 Install Dependencies

```bash
cd "/Users/daveleal/Repos/SlackClaw"
pip install -r requirements.txt
```

### 4.2 Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit with your credentials
nano .env
```

Fill in your credentials:

```bash
# Slack
SLACK_BOT_TOKEN=xoxb-your-token-here
SLACK_APP_TOKEN=xapp-your-token-here
SLACK_SIGNING_SECRET=your-signing-secret

# Claude
ANTHROPIC_API_KEY=sk-ant-your-key-here

# GitHub integration (issue auto-creation)
GITHUB_TOKEN=ghp_your_token_here      # Needs 'repo' scope — github.com/settings/tokens
DAVE_SLACK_USER_ID=U0XXXXXXX          # Your Slack user ID (Profile → ··· → Copy member ID)
CODE_REVIEW_CHANNEL_ID=code-review    # Channel name for staged peer review posts

# App Store Connect (optional)
APP_STORE_CONNECT_KEY_ID=YOUR_KEY_ID
APP_STORE_CONNECT_ISSUER_ID=YOUR_ISSUER_ID
APP_STORE_CONNECT_PRIVATE_KEY_PATH=/Users/daveleal/.appstoreconnect/AuthKey_XXXXX.p8

# Projects
DAYIST_PROJECT_PATH=/path/to/your/project
```

### 4.3 Configure Channels

Edit `bot_enhanced.py` to map your channels:

```python
CHANNEL_PROJECTS = {
    "dayist-dev": {
        "path": "/path/to/your/project",
        "bundle_id": "com.daveleal.Dayist",
        "auto_investigate": True
    },
    # Add more projects:
    # "another-app": {
    #     "path": "/path/to/another/app",
    #     "bundle_id": "com.example.app",
    #     "auto_investigate": False
    # }
}
```

## Step 5: Create Slack Channels

Create these channels in your workspace:

```
#dayist-dev       - Development discussions
#dayist-bugs      - Auto-posted bugs from App Store Connect
#dayist-releases  - Release notifications
```

Invite the bot to each channel:
```
/invite @Claude Code Bot
```

## Step 6: Test the Bot

### 6.1 Start Bot

```bash
python bot_enhanced.py
```

You should see:
```
🚀 Starting Slack Claude Code Bot...
🔍 Monitoring App Store Connect for com.daveleal.Dayist
✅ Bot is running!
📱 Monitoring channels: dayist-dev
```

### 6.2 Test in Slack

In `#dayist-dev` channel:

**Basic request:**
```
@Claude Code Bot what files are in the Views/Settings directory?
```

**Autonomous mode:**
```
@Claude Code Bot auto: analyze the subscription tracking feature and suggest improvements
```

**Investigate mode:**
```
@Claude Code Bot investigate: users are reporting the app crashes when logging in
```

## Step 7: Production Deployment

### Option A: Run as Service (macOS)

Create `~/Library/LaunchAgents/com.daveleal.claude-bot.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.daveleal.claude-bot</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/local/bin/python3</string>
        <string>/Users/daveleal/Repos/SlackClaw/bot_enhanced.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/daveleal/Repos/SlackClaw</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>/tmp/claude-bot.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/claude-bot.error.log</string>
</dict>
</plist>
```

Load the service:
```bash
launchctl load ~/Library/LaunchAgents/com.daveleal.claude-bot.plist
```

### Option B: Run in tmux/screen

```bash
# Create persistent session
tmux new -s claude-bot

# Run bot
cd "/Users/daveleal/Repos/SlackClaw"
python bot_enhanced.py

# Detach: Ctrl+B, then D
# Re-attach: tmux attach -t claude-bot
```

### Option C: Deploy to Server

For 24/7 operation, deploy to:
- **Railway**: https://railway.app
- **Fly.io**: https://fly.io
- **DigitalOcean**: App Platform
- **AWS**: ECS or Lambda

## Usage Examples

### Thread-based Sessions

Each Slack thread = isolated session with conversation context:

```
User: @Claude fix the login bug
Bot: 🧵 New session
     📂 Project: /path/to/your/project

     I'll analyze the login code...
     [Analysis results]

User: Can you also check the password validation?
Bot: [Continues in same context]

User: Apply the fix
Bot: ✅ Changes applied
     📝 Committed: "fix(auth): improve login error handling"
```

### Autonomous Investigations

Bot automatically investigates low-rated reviews:

```
[Auto-posted by bot]
🚨 New App Store Review

Rating: ⭐⭐ (2/5)
Title: App crashes on launch
Review: Every time I open the app it crashes immediately. iPhone 15 Pro, iOS 18.1
Reviewer: frustrated_user
Date: 2026-03-18T10:30:00Z

---

🤖 Starting autonomous investigation...

✅ Investigation Complete

Found crash in LoginView.swift:42
Issue: Force unwrapping nil user data during launch
Fix: Added guard statement and fallback

Affected versions: 1.2.0+
Suggested priority: High

[Apply Fix] [Run Tests] [Create PR]
```

### Multi-step Workflows

```
@Claude auto: prepare release 1.3.0
```

Bot will:
1. Run all tests
2. Update version numbers
3. Generate changelog from commits
4. Create release notes
5. Build archive
6. Submit to TestFlight
7. Post confirmation to #releases

## Advanced Features

### Custom Agents

Create specialized agents for specific tasks:

```python
# In bot_enhanced.py
AGENTS = {
    "crash_investigator": {
        "system_prompt": "You are an expert at analyzing iOS crash logs...",
        "triggers": ["crash", "exception", "signal"]
    },
    "code_reviewer": {
        "system_prompt": "You are a senior iOS developer reviewing code...",
        "triggers": ["review", "PR", "pull request"]
    }
}
```

### Workflow Automation

Set up automatic workflows:

```python
# Auto-create PR when fix is applied
@app.action("apply_fix")
def handle_apply_fix(ack, action, context):
    # Apply changes
    # Run tests
    # Create PR
    # Post to #reviews channel
```

### Integration with CI/CD

Trigger builds from Slack:

```
@Claude deploy to testflight
@Claude run performance tests
@Claude check memory leaks
```

## Monitoring & Logs

View logs:
```bash
# If using launchd
tail -f /tmp/claude-bot.log

# If using tmux
tmux attach -t claude-bot
```

## Troubleshooting

### Bot Not Responding

1. Check bot is running: `ps aux | grep bot_enhanced.py`
2. Check Slack tokens are valid
3. Verify bot is in channel: `/invite @Claude Code Bot`
4. Check logs for errors

### App Store Connect Not Working

1. Verify API key is valid: `ls -la ~/.appstoreconnect/`
2. Check key permissions: `chmod 600 ~/.appstoreconnect/AuthKey_*.p8`
3. Test API access: `python app_store_connect.py`

### Rate Limits

Claude API limits:
- Rate: 50 requests/min
- Adjust poll intervals if hitting limits

Slack API limits:
- Tier 3: 50+ messages/sec (sufficient for most use cases)

## Security Best Practices

1. **Never commit `.env` file**
   ```bash
   echo ".env" >> .gitignore
   ```

2. **Rotate API keys regularly**
   - Slack: Every 90 days
   - Claude: Every 90 days
   - App Store Connect: Yearly

3. **Limit bot permissions**
   - Only add to necessary channels
   - Use minimal Slack scopes
   - Restrict App Store Connect access

4. **Audit bot activity**
   - Review Slack messages regularly
   - Check git commits made by bot
   - Monitor API usage

## Cost Estimates

**Claude API:**
- ~$0.015 per 1K input tokens
- ~$0.075 per 1K output tokens
- Estimated: $20-50/month for moderate use

**App Store Connect API:**
- Free (included with Apple Developer Program)

**Infrastructure:**
- Free: Run locally
- Railway: ~$5/month
- DigitalOcean: ~$5/month

## Next Steps

1. ✅ Set up basic bot
2. Test manual commands
3. Enable App Store Connect monitoring
4. Configure autonomous agents
5. Set up workflows
6. Deploy to production

## Support

Issues? Check:
- Slack API docs: https://api.slack.com/docs
- Claude API docs: https://docs.anthropic.com
- App Store Connect API: https://developer.apple.com/documentation/appstoreconnectapi

Happy automating! 🚀

## Step 8: Install claude-slack Bridge (Optional)

The `claude-slack` script lets you respond to Claude Code prompts via Slack
buttons on any device, instead of switching to the terminal.

### Install

```bash
cd /Users/daveleal/Repos/SlackClaw
chmod +x claude-slack
ln -sf "$(pwd)/claude-slack" /usr/local/bin/claude-slack
```

### Usage — drop-in replacement for `claude`

```bash
claude-slack               # start new session
claude-slack --continue    # resume last session
claude-slack -p "do X"    # non-interactive prompt
```

### How it works

1. `claude-slack` detects the current project from the git remote URL and
   routes the session to the correct `#project-dev` channel.
2. A 🟢 session-start message is posted to that channel.
3. When Claude Code needs input, post a Block Kit message using
   `tools/slack_bridge.py::format_bridge_blocks` via the Slack MCP.
4. Dave clicks a button on any device → the answer feeds back to Claude's stdin.

### Prerequisite

`CHANNEL_ROUTING` in `orchestrator_config.py` must have `channel_id` filled
in for every project's `primary_channel` entry. Run the bridge implementation
plan's Task 2 if this hasn't been done yet.

### Smoke test

```bash
# From SlackClaw repo root:
claude-slack --version
# Expected: 🟢 session-start appears in the project channel, script exits cleanly.
```
