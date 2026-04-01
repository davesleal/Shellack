# Contributing to Shellack

## Quick start

```bash
git clone https://github.com/your-org/Shellack.git
cd Shellack
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp projects.example.yaml projects.yaml
# Edit projects.yaml with your projects, channels, and paths
cp .env.example .env
# Edit .env with your Slack, Anthropic, and GitHub credentials
git config core.hooksPath hooks
python bot_unified.py
```

Run the test suite to verify everything works:

```bash
pytest
```

For full setup details (Slack app creation, tokens, App Store Connect), see [SETUP_GUIDE.md](./SETUP_GUIDE.md). For an overview of what Shellack does and how to use it, see [README.md](./README.md).

## Project config

All project definitions live in `projects.yaml`. This file is **gitignored** because it contains your project names, local paths, and Slack channel IDs -- none of which belong in version control.

`projects.example.yaml` is the checked-in template. It shows the full schema with two example projects and every supported field documented inline. Copy it and fill in your details:

```bash
cp projects.example.yaml projects.yaml
```

The config loader (`orchestrator_config.py`) looks for `projects.yaml` in the repo root by default. Override the path with the `SHELLACK_CONFIG` environment variable:

```bash
export SHELLACK_CONFIG=/path/to/my-config.yaml
```

Per-project paths and bundle IDs can also be overridden via env vars. For a project with slug `myapp`, set `MYAPP_PROJECT_PATH` or `MYAPP_BUNDLE_ID` to override the YAML values.

## Secret safety

A pre-commit hook at `hooks/pre-commit` scans staged diffs for credential patterns before every commit. It catches:

- Slack tokens (`xoxb-`, `xoxp-`, `xoxs-`, `xoxa-`, `xapp-`)
- Anthropic API keys (`sk-ant-`)
- GitHub tokens (`ghp_`, `ghs_`)
- AWS access key IDs (`AKIA...`)
- Private keys (`-----BEGIN.*PRIVATE KEY`)
- Google API keys (`AIza...`)
- Stripe live keys (`sk-live`)

**Setup** (once per clone):

```bash
git config core.hooksPath hooks
```

The hook only scans added/changed lines in staged files. It automatically skips `*.example*` files, the hook script itself, and binary files.

**False positives.** If the hook blocks a commit that doesn't contain real secrets (e.g., documentation mentioning a token prefix), bypass with:

```bash
git commit --no-verify
```

Use this sparingly. If a pattern causes frequent false positives, fix the hook instead.

## Running tests

```bash
pytest
```

The test suite covers the config loader, triage logic, session backends, lifecycle posts, thinking indicator, project agents, agent factory, Slack sessions, usage tracking, bot commands, and more. All tests live in `tests/`.

**Fresh clones work automatically.** `tests/conftest.py` has a `pytest_configure` hook that detects when `projects.yaml` is absent and generates a minimal temporary config via `SHELLACK_CONFIG`. You don't need a real `projects.yaml` to run tests.

Run a specific test file:

```bash
pytest tests/test_triage.py -v
```

## Adding a new project

1. Add an entry to `projects.yaml` under the `projects:` key. Use `projects.example.yaml` as a reference for the full schema.

2. Add a channel mapping under the `channels:` key, pointing at your new project slug.

3. Create the Slack channel (e.g., `#myproject-dev`) and invite the bot: `/invite @Shellack`

4. Optionally add a `context:` block to enrich the agent's system prompt with project-specific description, tech stack, coding patterns, and things to watch out for.

The bot auto-detects new projects on startup -- no code changes required.

## Code style

- **PEP 8** with a **100 character** line length
- **Type hints** on all function signatures
- **Docstrings** on public functions
- **black** for formatting

These standards are also defined in the `standards:` section of `projects.example.yaml`.

## PR workflow

1. Create a branch from `main`.

2. Make your changes. Write tests alongside the code, not after.

3. Run the full suite before pushing:
   ```bash
   pytest
   ```

4. Commit using the repo's convention -- lowercase type prefix, colon, short description:
   ```
   feat: add widget support for dashboard projects
   fix: triage fallback evaluates SESSION_MODEL at call time
   refactor: remove hardcoded channel IDs from slack_bridge
   test: add ThinkingIndicator fallback coverage
   chore: strip all personal project references from tracked files
   docs: update STATE.md and JOURNAL.md
   ```

5. Push and open a PR against `main`.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
