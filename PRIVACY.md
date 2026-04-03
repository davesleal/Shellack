# Privacy Policy — Shellack

**Last updated:** April 2, 2026

## Overview

Shellack is a **self-hosted** Slack bot. It runs on your own machine or server. No data is transmitted to Shellack's developers or any third-party service operated by Shellack.

## Data handling

### What Shellack processes
- **Slack messages** in configured project channels (text content of messages mentioning the bot)
- **Voice messages** (if enabled) — downloaded from Slack, transcribed locally, then deleted
- **File paths** on your machine as configured in `projects.yaml`
- **Conversation context** — stored in-memory during active threads, discarded on bot restart

### Where data goes
- **Anthropic API** — Message content is sent to the Anthropic API (or Claude CLI) for AI processing. This is governed by [Anthropic's privacy policy](https://www.anthropic.com/privacy) and your agreement with Anthropic.
- **GitHub API** — If GitHub integration is configured, issue titles and descriptions are sent to GitHub via your personal access token.
- **Your local machine** — Project registry files (`.shellack/registry.md`), thread memory (`.shellack/thread-memory/`), and journal drafts are stored as files in your project directories.

### What Shellack does NOT do
- Does not collect telemetry or analytics
- Does not phone home to any server
- Does not store data outside your machine (except via APIs you explicitly configure)
- Does not share data between workspace users beyond normal Slack channel visibility
- Does not access Slack channels that are not configured in `projects.yaml`
- Does not retain conversation data after bot restart (in-memory only)

## Third-party services

Shellack integrates with services **you** configure. Each requires your own credentials:

| Service | Purpose | Your credential | Their privacy policy |
|---|---|---|---|
| Anthropic | AI responses | `ANTHROPIC_API_KEY` | [anthropic.com/privacy](https://www.anthropic.com/privacy) |
| Slack | Messaging | `SLACK_BOT_TOKEN` | [slack.com/privacy-policy](https://slack.com/privacy-policy) |
| GitHub | Issue tracking | `GITHUB_TOKEN` | [github.com/privacy](https://docs.github.com/en/site-policy/privacy-policies/github-general-privacy-statement) |
| App Store Connect | Review monitoring | ASC credentials | [apple.com/privacy](https://www.apple.com/privacy/) |

## Voice transcription

When voice transcription is enabled, audio files are:
1. Downloaded from Slack to a temporary file on your machine
2. Transcribed locally using the Whisper model (no cloud service)
3. Deleted immediately after transcription
4. The transcript is processed as a normal text message

No audio data leaves your machine.

## Security

- All credentials stored in `.env` (gitignored, never committed)
- Pre-commit hook scans for 16 secret patterns to prevent accidental commits
- Owner-only gates on administrative commands (fail-closed)
- Error messages sanitized — no internal details leak to Slack

## Your rights

Since Shellack is self-hosted, you have complete control over your data. You can:
- Stop the bot at any time
- Delete all local data (`.shellack/` directories, `usage.json`)
- Revoke API credentials
- Uninstall the Slack app from your workspace

## Contact

For questions about this privacy policy or Shellack's data handling:
- GitHub Issues: [github.com/davesleal/Shellack/issues](https://github.com/davesleal/Shellack/issues)
- GitHub Discussions: [github.com/davesleal/Shellack/discussions](https://github.com/davesleal/Shellack/discussions)
