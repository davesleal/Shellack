# Contributing to SlackClaw 🦞

Thanks for your interest in contributing! This document provides guidelines for contributing to SlackClaw.

## 🚀 Quick Start

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/SlackClaw.git`
3. Create a branch: `git checkout -b feature/amazing-feature`
4. Make your changes
5. Test thoroughly
6. Commit: `git commit -m 'Add amazing feature'`
7. Push: `git push origin feature/amazing-feature`
8. Open a Pull Request

## 🎯 How to Contribute

### Reporting Bugs

Open an issue with:
- Clear title and description
- Steps to reproduce
- Expected vs actual behavior
- Environment details (Python version, OS, etc.)
- Relevant logs or screenshots

### Suggesting Features

Open an issue with:
- Use case and motivation
- Proposed solution
- Alternative solutions considered
- Implementation considerations

### Pull Requests

**Before submitting:**
- Ensure code follows existing style
- Add tests if applicable
- Update documentation
- Test in both full AI and zero-cost modes

**PR Guidelines:**
- One feature per PR
- Clear, descriptive title
- Detailed description of changes
- Reference related issues
- Add screenshots/demos if relevant

## 🏗️ Development Setup

```bash
# Clone your fork
git clone https://github.com/YOUR_USERNAME/SlackClaw.git
cd SlackClaw

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install dev dependencies
pip install pytest black flake8 mypy

# Run tests
pytest

# Format code
black *.py

# Lint
flake8 *.py
```

## 📝 Code Style

- Follow [PEP 8](https://pep8.org/)
- Use `black` for formatting
- Maximum line length: 100 characters
- Use type hints where possible
- Add docstrings for functions/classes

Example:
```python
def execute_claude_task(
    project_path: str,
    task: str,
    thread_context: Optional[List[Dict]] = None
) -> str:
    """
    Execute a task using Claude with full context.

    Args:
        project_path: Path to the project directory
        task: Task description for Claude
        thread_context: Optional conversation history

    Returns:
        Claude's response as a string

    Raises:
        ValueError: If project_path doesn't exist
    """
    # Implementation
```

## 🧪 Testing

Add tests for new features:

```python
# tests/test_app_store_connect.py
def test_format_feedback_for_slack():
    feedback = {
        "type": "review",
        "rating": 2,
        "title": "Test",
        "body": "Test review"
    }
    result = format_feedback_for_slack(feedback)
    assert "⭐⭐" in result
    assert "Test review" in result
```

Run tests:
```bash
pytest
pytest --cov  # With coverage
```

## 📖 Documentation

Update documentation when:
- Adding new features
- Changing configuration options
- Modifying setup process
- Adding new dependencies

Update these files as needed:
- `README.md` - Overview and quick start
- `SETUP_GUIDE.md` - Detailed setup instructions
- `HYBRID_APPROACH.md` - Zero-cost mode documentation
- Inline code comments
- Docstrings

## 🎨 Feature Ideas

Looking for contribution ideas? Check issues tagged with:
- `good-first-issue` - Great for newcomers
- `help-wanted` - Community help needed
- `enhancement` - Feature requests

### Potential Contributions

**Features:**
- [ ] GitHub Actions integration
- [ ] Crash log analysis from App Store Connect
- [ ] Multi-language support (Android, web)
- [ ] Custom agent marketplace
- [ ] Web dashboard
- [ ] Telegram bot integration
- [ ] Discord bot integration

**Improvements:**
- [ ] Better error handling
- [ ] Rate limit management
- [ ] Caching for API responses
- [ ] Metrics and monitoring
- [ ] Docker support
- [ ] Kubernetes deployment

**Documentation:**
- [ ] Video tutorials
- [ ] More examples
- [ ] Troubleshooting guide
- [ ] Architecture diagrams
- [ ] API documentation

## 🔒 Security

**Reporting vulnerabilities:**
- DO NOT open public issues for security bugs
- Email: you@example.com
- Include detailed description and reproduction steps

**Security considerations:**
- Never commit API keys or tokens
- Validate all user inputs
- Sanitize data before logging
- Follow principle of least privilege

## 💬 Community

- [Discussions](https://github.com/YOUR_ORG/SlackClaw/discussions) - Questions and ideas
- [Issues](https://github.com/YOUR_ORG/SlackClaw/issues) - Bug reports and feature requests

## 📜 License

By contributing, you agree that your contributions will be licensed under the MIT License.

## 🙏 Thank You!

Every contribution helps make SlackClaw better for everyone. Thank you for being part of the community! 🎉
