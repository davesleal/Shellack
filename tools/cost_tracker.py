"""Cost tracking for Token Cart — per-turn and per-thread spend."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# Pricing per million tokens (as of 2026-04)
_PRICING = {
    "claude-haiku-4-5-20251001": {"input": 0.25, "output": 1.25},
    "claude-sonnet-4-6": {"input": 3.0, "output": 15.0},
    "claude-opus-4-6": {"input": 15.0, "output": 75.0},
}

# Fallback for unknown models
_DEFAULT_PRICING = {"input": 3.0, "output": 15.0}


def _get_pricing(model: str) -> dict:
    """Get pricing for a model, with fallback."""
    return _PRICING.get(model, _DEFAULT_PRICING)


@dataclass
class TurnCost:
    """Cost for a single turn."""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    cost_usd: float = 0.0

    def calculate(self) -> float:
        pricing = _get_pricing(self.model)
        self.cost_usd = (
            (self.input_tokens * pricing["input"] / 1_000_000)
            + (self.output_tokens * pricing["output"] / 1_000_000)
        )
        return self.cost_usd


@dataclass
class ThreadCost:
    """Accumulated cost for a thread."""
    turns: list[TurnCost] = field(default_factory=list)

    @property
    def total_usd(self) -> float:
        return sum(t.cost_usd for t in self.turns)

    @property
    def total_input_tokens(self) -> int:
        return sum(t.input_tokens for t in self.turns)

    @property
    def total_output_tokens(self) -> int:
        return sum(t.output_tokens for t in self.turns)

    def add_turn(self, turn: TurnCost) -> None:
        turn.calculate()
        self.turns.append(turn)

    def format_turn_summary(self, turn: TurnCost) -> str:
        """Format cost for display in the Churned block."""
        return f"${turn.cost_usd:.4f} ({_fmt_tokens(turn.input_tokens)} in · {_fmt_tokens(turn.output_tokens)} out)"

    def format_thread_summary(self) -> str:
        """Format total thread cost."""
        return f"Thread: ${self.total_usd:.3f} across {len(self.turns)} turns"


def _fmt_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)
