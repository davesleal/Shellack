# Shellack Architecture

Modular unified bot with channel-based routing.

## Architecture Overview

```
Shellack Unified Bot (single process)
│
├─ Project Agents
│  ├─ #dayist-dev    → Dayist project
│  ├─ #nova-dev      → NOVA project
│  └─ #nudge-dev     → Nudge project
│
├─ Orchestrator
│  └─ #slackclaw-central
│     ├─ Update all CLAUDE.md files
│     ├─ Sync standards between projects
│     ├─ Cross-project search
│     └─ Global governance
│
└─ Peer Review
   └─ #code-review
      ├─ Code Quality Agent
      ├─ Security Agent
      └─ Performance Agent
```

## Channel Routing

The bot automatically routes to the right module based on channel name:

```python
if channel == "slackclaw-central":
    → orchestrator.handle()
elif channel == "code-review":
    → peer_review.handle()
else:
    → project_agent.handle()
```

## Modules

### 1. Project Agents (`bot_unified.py`)

Handle project-specific work:
- Code analysis
- Bug investigation
- Feature implementation
- Code reviews
- Testing

**Channels:** Any configured project channel (see `orchestrator_config.py`)

**Example:**
```
#dayist-dev
@Shellack what files are in Views/Settings?
@Shellack fix the login bug
@Shellack run tests
```

### 2. Orchestrator (`orchestrator.py`)

Cross-project coordination:
- Update CLAUDE.md across all projects
- Sync coding standards
- Global search
- Coordinate multi-project changes

**Channel:** `#slackclaw-central`

**Example:**
```
#slackclaw-central
@Shellack update all CLAUDE.md: prefer composition over inheritance
@Shellack sync standards from dayist to nova
@Shellack search all: deprecated UserDefaults
```

### 3. Peer Review (`peer_review.py`)

Autonomous code review:
- Code quality analysis
- Security scanning
- Performance review
- Approval workflow

**Channel:** `#code-review`

**Example:**
```
#code-review
🤖 PR #123 ready for review
Files: LoginView.swift, AuthManager.swift
Description: Fixed race condition

[Bot analyzes and provides review]
```

## Configuration

Edit `orchestrator_config.py` to:
- Add projects
- Configure channels
- Set global standards
- Define review rules

## Running the Bot

### Development
```bash
python bot_unified.py
```

### Production
```bash
# Option 1: systemd/launchd service
# Option 2: Docker
# Option 3: Cloud deployment (Railway, Fly.io, etc.)
```

## File Structure

```
Shellack/
├── bot_unified.py              # Main unified bot
├── orchestrator_config.py      # Configuration
├── orchestrator.py             # Cross-project operations
├── peer_review.py              # Autonomous review system
├── app_store_connect.py        # ASC integration
│
├── bot_enhanced.py             # Legacy: Full AI bot
├── monitor_only.py             # Legacy: Zero-cost monitoring
│
└── README.md                   # Project docs
```

## Adding New Projects

1. Edit `orchestrator_config.py`:
```python
PROJECTS = {
    "new-project": {
        "name": "NewProject",
        "path": "/path/to/project",
        "bundle_id": "com.example.app",
        "primary_channel": "new-project-dev",
        "language": "swift",
        "platform": "ios"
    }
}
```

2. Add channel routing:
```python
CHANNEL_ROUTING = {
    "new-project-dev": {
        "project": "new-project",
        "mode": "dedicated"
    }
}
```

3. Create Slack channel:
```
/create #new-project-dev
/invite @Shellack
```

Done! The bot automatically picks up the new project.

## Adding New Orchestrator Commands

1. Edit `orchestrator.py`
2. Add new method to `Orchestrator` class
3. Update `handle_orchestrator_message()` in `bot_unified.py`

## Benefits of This Architecture

✅ **Single deployment** - One bot process
✅ **Modular** - Easy to maintain and extend
✅ **Scalable** - Add projects without code changes
✅ **Flexible** - Enable/disable features per channel
✅ **Clean** - Clear separation of concerns
✅ **Powerful** - Cross-project coordination

## Future Enhancements

- [ ] Web dashboard for monitoring
- [ ] Metrics and analytics
- [ ] Custom review agents
- [ ] Workflow automation
- [ ] Multi-language support
- [ ] Integration with CI/CD
