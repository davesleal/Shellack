from tools.agent_discussion import DiscussionLog, AGENT_EMOJI


def test_add_and_format():
    log = DiscussionLog()
    log.add("observer", "User asked about migration")
    log.add("file_fetcher", "Loaded socialService.ts")
    log.add("gut_check", "PROCEED")
    result = log.format()
    assert "Agent Discussion" in result
    assert "\U0001f441" in result or "👁" in result
    assert "socialService" in result


def test_empty_format():
    log = DiscussionLog()
    assert log.format() == ""
    assert log.is_empty()


def test_unknown_agent_gets_robot():
    log = DiscussionLog()
    log.add("unknown_agent", "test")
    assert "\U0001f916" in log.format() or "🤖" in log.format()


def test_add_phase_header():
    log = DiscussionLog()
    log.add_phase_header("plan", "🎯", "Plan & Research")
    log.add("strategist", "Tasks: [schema, RLS, tests]")
    result = log.format()
    assert "🎯 Plan & Research" in result
    assert "🎯 Tasks:" in result


def test_all_persona_emojis_registered():
    """Every persona in the spec has an emoji registered."""
    required = [
        "strategist", "researcher", "historian",
        "architect", "specialist", "data_scientist",
        "empathizer", "connector", "reuser",
        "skeptic", "devils_advocate", "simplifier", "prioritizer",
        "rogue", "hacker", "infosec",
        "inspector", "tester", "visual_ux",
        "learner", "coach", "output_editor",
        "dreamer", "insights", "growth_coach",
    ]
    for name in required:
        assert name in AGENT_EMOJI, f"Missing emoji for {name}"


def test_format_with_phases():
    log = DiscussionLog()
    log.add_phase_header("intake", "📨", "Intake")
    log.add("agent_manager", "Complexity: moderate")
    log.add("observer", "User asking about migration")
    log.add_phase_header("plan", "🎯", "Plan & Research")
    log.add("historian", "Prior migration had 3 commits")
    result = log.format()
    assert "📨 Intake" in result
    assert "🎯 Plan & Research" in result


def test_add_phase_entries_with_indentation():
    log = DiscussionLog()
    log.add_phase_entries("challenge", "🤨", ["🤨 Schema looks solid", "⚖️ Prioritized: schema first"])
    result = log.format()
    assert "Challenge" in result
    assert "  🤨 Schema looks solid" in result


def test_add_phase_entries_skips_empty():
    log = DiscussionLog()
    log.add_phase_entries("empty", "🔮", [])
    assert log.is_empty()
