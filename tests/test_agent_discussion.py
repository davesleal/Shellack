from tools.agent_discussion import DiscussionLog


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
