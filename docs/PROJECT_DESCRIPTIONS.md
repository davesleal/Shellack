# Project Descriptions for Slack Channels

Use these as Slack channel topics to give Claude, Shellack, and GitHub context.

---

## Template

**Channel:** `#<project>-dev`
**Topic:**
```
<Project Name> - <Platform> <Short Description> • <Tech Stack> • https://github.com/your-org/<repo> • App Store: com.example.yourapp
```

**Full Description:**
Brief description of the project's purpose, features, and tech stack.

**Status:** In development / Active / Production
**Platform:** iOS / macOS / Server
**Tech:** SwiftUI, SwiftData, etc.

---

## Special Channels

### #shellack-central
**Topic:**
```
Orchestrator Channel • Cross-project coordination • Update CLAUDE.md globally • Sync standards • Search all projects
```

**Purpose:** Meta-channel for operations that span multiple projects. Commands affect all configured projects simultaneously.

### #code-review
**Topic:**
```
Peer Review Channel • Autonomous code review • 3 agents: Quality, Security, Performance • PR approval workflow
```

**Purpose:** Automated code review system with specialized review agents providing feedback on quality, security, and performance.

---

## Quick Reference

| Project | Platform | Status | App Store | Repo |
|---------|----------|--------|-----------|------|
| _MyApp_ | _iOS_ | _Active_ | _com.example.yourapp_ | _[MyApp](https://github.com/your-org/MyApp)_ |

---

## Usage

1. **Copy the "Topic" text** for each channel
2. **Update Slack channel topics:**
   - Open Slack
   - Go to channel (e.g., #project-a-dev)
   - Click channel name → Edit → Topic
   - Paste the topic text
   - Save

3. **Result:** Claude, Shellack, and GitHub all see:
   - What the project is
   - Where the code lives
   - Key technologies
   - App Store bundle IDs (for ASC integration)

---

## Notes

- **GitHub links** enable GitHub app to correlate repos to channels
- **Bundle IDs** enable App Store Connect monitoring
- **Tech stack** helps Claude understand project context for better responses
