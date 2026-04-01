#!/bin/bash

# Slack Claude Code Bot - Quick Setup Script

set -e

echo "🚀 Slack Claude Code Bot Setup"
echo "================================"
echo ""

# Check Python version
echo "📌 Checking Python version..."
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.9 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo "✅ Python $PYTHON_VERSION detected"
echo ""

# Check if we're in the right directory
if [ ! -f "requirements.txt" ]; then
    echo "❌ requirements.txt not found. Are you in the slack-claude-bot directory?"
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "ℹ️  Virtual environment already exists"
fi
echo ""

# Activate virtual environment
echo "🔌 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install --upgrade pip -q
pip install -r requirements.txt -q
echo "✅ Dependencies installed"
echo ""

# Create .env file if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file..."
    cp .env.example .env
    echo "✅ .env file created"
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file with your credentials:"
    echo "   - SLACK_BOT_TOKEN"
    echo "   - SLACK_APP_TOKEN"
    echo "   - ANTHROPIC_API_KEY"
    echo ""
    read -p "Press Enter to open .env in nano (Ctrl+X to save)..."
    nano .env
else
    echo "ℹ️  .env file already exists"
fi
echo ""

# Verify .env has required variables
echo "🔍 Checking environment configuration..."
source .env

if [ -z "$SLACK_BOT_TOKEN" ] || [ "$SLACK_BOT_TOKEN" = "xoxb-your-bot-token-here" ]; then
    echo "❌ SLACK_BOT_TOKEN not configured in .env"
    exit 1
fi

if [ -z "$SLACK_APP_TOKEN" ] || [ "$SLACK_APP_TOKEN" = "xapp-your-app-token-here" ]; then
    echo "❌ SLACK_APP_TOKEN not configured in .env"
    exit 1
fi

if [ -z "$ANTHROPIC_API_KEY" ] || [ "$ANTHROPIC_API_KEY" = "sk-ant-api03-your-key-here" ]; then
    echo "❌ ANTHROPIC_API_KEY not configured in .env"
    exit 1
fi

echo "✅ Environment configuration looks good"
echo ""

# Test App Store Connect (optional)
if [ -n "$APP_STORE_CONNECT_KEY_ID" ] && [ "$APP_STORE_CONNECT_KEY_ID" != "your-key-id" ]; then
    echo "🍎 Testing App Store Connect API..."
    python3 app_store_connect.py
    echo ""
else
    echo "ℹ️  App Store Connect not configured (optional)"
    echo ""
fi

# Summary
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Create Slack channels (e.g., #project-dev)"
echo "2. Invite the bot: /invite @Claude Code Bot"
echo "3. Start the bot: python bot_enhanced.py"
echo "4. Test with: @Claude Code Bot hello"
echo ""
echo "For production deployment, see SETUP_GUIDE.md"
echo ""

# Ask if user wants to start the bot now
read -p "Start the bot now? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo ""
    echo "🚀 Starting bot..."
    echo "   Press Ctrl+C to stop"
    echo ""
    python3 bot_enhanced.py
fi
