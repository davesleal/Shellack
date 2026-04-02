"""Tests for cost_tracker — per-turn and per-thread spend tracking."""

import pytest

from tools.cost_tracker import TurnCost, ThreadCost, _fmt_tokens


class TestTurnCost:
    def test_turn_cost_calculation_haiku(self):
        turn = TurnCost(
            input_tokens=1000, output_tokens=500, model="claude-haiku-4-5-20251001"
        )
        cost = turn.calculate()
        # input: 1000 * 0.25 / 1_000_000 = 0.00025
        # output: 500 * 1.25 / 1_000_000 = 0.000625
        expected = 0.000875
        assert abs(cost - expected) < 1e-9
        assert abs(turn.cost_usd - expected) < 1e-9

    def test_turn_cost_calculation_sonnet(self):
        turn = TurnCost(
            input_tokens=2000, output_tokens=1000, model="claude-sonnet-4-6"
        )
        turn.calculate()
        # input: 2000 * 3.0 / 1_000_000 = 0.006
        # output: 1000 * 15.0 / 1_000_000 = 0.015
        assert abs(turn.cost_usd - 0.021) < 1e-9

    def test_turn_cost_calculation_opus(self):
        turn = TurnCost(input_tokens=5000, output_tokens=2000, model="claude-opus-4-6")
        turn.calculate()
        # input: 5000 * 15.0 / 1_000_000 = 0.075
        # output: 2000 * 75.0 / 1_000_000 = 0.15
        assert abs(turn.cost_usd - 0.225) < 1e-9

    def test_turn_cost_unknown_model_uses_default(self):
        turn = TurnCost(
            input_tokens=1000, output_tokens=1000, model="claude-unknown-99"
        )
        turn.calculate()
        # default: input 3.0, output 15.0
        # input: 1000 * 3.0 / 1_000_000 = 0.003
        # output: 1000 * 15.0 / 1_000_000 = 0.015
        assert abs(turn.cost_usd - 0.018) < 1e-9

    def test_turn_cost_zero_tokens(self):
        turn = TurnCost(input_tokens=0, output_tokens=0, model="claude-sonnet-4-6")
        turn.calculate()
        assert turn.cost_usd == 0.0


class TestThreadCost:
    def test_thread_cost_accumulates(self):
        thread = ThreadCost()
        thread.add_turn(
            TurnCost(input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6")
        )
        thread.add_turn(
            TurnCost(input_tokens=2000, output_tokens=1000, model="claude-sonnet-4-6")
        )
        assert len(thread.turns) == 2
        # Turn 1: 1000*3/1M + 500*15/1M = 0.003 + 0.0075 = 0.0105
        # Turn 2: 2000*3/1M + 1000*15/1M = 0.006 + 0.015 = 0.021
        assert abs(thread.total_usd - 0.0315) < 1e-9

    def test_total_tokens(self):
        thread = ThreadCost()
        thread.add_turn(
            TurnCost(input_tokens=100, output_tokens=50, model="claude-sonnet-4-6")
        )
        thread.add_turn(
            TurnCost(input_tokens=200, output_tokens=75, model="claude-sonnet-4-6")
        )
        assert thread.total_input_tokens == 300
        assert thread.total_output_tokens == 125

    def test_format_turn_summary(self):
        thread = ThreadCost()
        turn = TurnCost(input_tokens=2100, output_tokens=890, model="claude-sonnet-4-6")
        thread.add_turn(turn)
        summary = thread.format_turn_summary(turn)
        assert "$" in summary
        assert "2.1k in" in summary
        assert "890 out" in summary

    def test_format_thread_summary(self):
        thread = ThreadCost()
        thread.add_turn(
            TurnCost(input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6")
        )
        thread.add_turn(
            TurnCost(input_tokens=1000, output_tokens=500, model="claude-sonnet-4-6")
        )
        summary = thread.format_thread_summary()
        assert "Thread:" in summary
        assert "2 turns" in summary

    def test_empty_thread(self):
        thread = ThreadCost()
        assert thread.total_usd == 0.0
        assert thread.total_input_tokens == 0
        assert thread.total_output_tokens == 0
        assert "0 turns" in thread.format_thread_summary()


class TestFmtTokens:
    def test_below_thousand(self):
        assert _fmt_tokens(500) == "500"
        assert _fmt_tokens(0) == "0"
        assert _fmt_tokens(999) == "999"

    def test_thousands(self):
        assert _fmt_tokens(1000) == "1.0k"
        assert _fmt_tokens(2100) == "2.1k"
        assert _fmt_tokens(15000) == "15.0k"
