# Project Descriptions for Slack Channels

Use these as Slack channel topics to give Claude, SlackClaw, and GitHub context.

---

## Dayist
**Channel:** `#dayist-dev`
**Topic:**
```
Dayist - iOS Personal Command Center • SwiftUI + SwiftData + CloudKit • Tasks, Calendar, Health, Subscriptions • https://github.com/davesleal/Dayist • App Store: com.daveleal.dayist
```

**Full Description:**
iOS 26+ personal productivity and wellness app. Unifies tasks, calendar, health insights, and subscription tracking with on-device Apple Intelligence. SwiftUI, SwiftData (local), CloudKit (sync), HealthKit, EventKit, Google OAuth.

**Status:** In active development
**Platform:** iOS 26.0+
**Tech:** SwiftUI, SwiftData, CloudKit, HealthKit, EventKit, Apple Foundation Models

---

## NOVA
**Channel:** `#nova-dev`
**Topic:**
```
NOVA - iOS App • Swift • https://github.com/davesleal/NOVA • In Development
```

**Full Description:**
iOS application (details TBD - update this description with project specifics)

**Status:** In development
**Platform:** iOS
**Tech:** Swift

---

## Nudge
**Channel:** `#nudge-dev`
**Topic:**
```
Nudge - iOS App • Swift • https://github.com/davesleal/Nudge • In Development
```

**Full Description:**
iOS application (details TBD - update this description with project specifics)

**Status:** In development
**Platform:** iOS
**Tech:** Swift

---

## TileDock
**Channel:** `#tiledock-dev`
**Topic:**
```
TileDock - macOS Grid Control Surface • SwiftUI • One tap. Many actions. • https://github.com/davesleal/TileDock • gridboard.app • App Store: com.daveleal.MacDock
```

**Full Description:**
macOS control surface app with grid-based layout. One tap triggers multiple actions across apps and services. Formerly GridBoard. Modern SwiftUI interface for macOS automation and productivity.

**Status:** Active development
**Platform:** macOS
**Tech:** SwiftUI, AppKit
**Domain:** gridboard.app

---

## Atmos Universal
**Channel:** `#atmos-dev`
**Topic:**
```
Atmos Universal - macOS Weather App • SwiftUI • https://github.com/davesleal/atmos-universal • Not on App Store
```

**Full Description:**
macOS weather application. Universal design for macOS platform. (Update with specific features and capabilities)

**Status:** In development
**Platform:** macOS
**Tech:** SwiftUI

---

## SidePlane
**Channel:** `#sideplane-dev`
**Topic:**
```
SidePlane - macOS Vision Companion • SwiftUI • Mac2Vision bridge • https://github.com/davesleal/SidePlane • App Store: com.daveleal.sideplane
```

**Full Description:**
macOS application for bridging Mac functionality with Vision Pro. Formerly Mac2Vision. Enables seamless workflows between macOS and visionOS platforms.

**Status:** Active development
**Platform:** macOS
**Tech:** SwiftUI, Spatial Computing APIs
**Related:** Vision Pro integration

---

## SlackClaw
**Channel:** `#slackclaw-dev`
**Topic:**
```
SlackClaw - Slack AI Bot • Python + Claude API • Multi-project dev automation • https://github.com/davesleal/SlackClaw • Orchestrator + Peer Review
```

**Full Description:**
Slack bot integrated with Claude AI for development workflows across multiple projects. Features:
- **Project Agents:** Dedicated channels per project with codebase access
- **Orchestrator:** Cross-project coordination via #slackclaw-central
- **Peer Review:** Autonomous code review with specialized agents
- **App Store Connect:** Automated monitoring of reviews and TestFlight feedback

**Status:** Production-ready
**Platform:** Server (Python)
**Tech:** Python, Slack Bolt, Anthropic API, App Store Connect API
**Architecture:** Modular unified bot with channel-based routing

---

## Special Channels

### #slackclaw-central
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
| Dayist | iOS 26+ | Active | ✅ com.daveleal.dayist | [Dayist](https://github.com/davesleal/Dayist) |
| NOVA | iOS | Dev | ❌ | [NOVA](https://github.com/davesleal/NOVA) |
| Nudge | iOS | Dev | ❌ | [Nudge](https://github.com/davesleal/Nudge) |
| TileDock | macOS | Active | ✅ com.daveleal.MacDock | [TileDock](https://github.com/davesleal/TileDock) |
| Atmos | macOS | Dev | ❌ | [atmos-universal](https://github.com/davesleal/atmos-universal) |
| SidePlane | macOS | Active | ✅ com.daveleal.sideplane | [SidePlane](https://github.com/davesleal/SidePlane) |
| SlackClaw | Server | Prod | N/A | [SlackClaw](https://github.com/davesleal/SlackClaw) |

---

## Usage

1. **Copy the "Topic" text** for each channel
2. **Update Slack channel topics:**
   - Open Slack
   - Go to channel (e.g., #dayist-dev)
   - Click channel name → Edit → Topic
   - Paste the topic text
   - Save

3. **Result:** Claude, SlackClaw, and GitHub all see:
   - What the project is
   - Where the code lives
   - Key technologies
   - App Store bundle IDs (for ASC integration)

---

## Notes

- **Update NOVA and Nudge** descriptions when project details are defined
- **Update Atmos** with specific weather features and capabilities
- **GitHub links** enable GitHub app to correlate repos to channels
- **Bundle IDs** enable App Store Connect monitoring
- **Tech stack** helps Claude understand project context for better responses
