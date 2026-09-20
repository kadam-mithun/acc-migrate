"""The strategy matrix (SPEC §5) and conversion planning (SPEC §3).

`recommend_strategy` is a pure, tested function over a `TableProfile`. Decision
order is fixed at S6 → S7 → S5 → S4 → S3 → S2 → S1; first match wins and the
rationale lists every rule evaluated. Never reorder (server CLAUDE.md).

Coverage gate: ≥ 90% on this module. Every rule has `test_strategy_rule_<id>`,
every trigger condition its own test, every order boundary its own test.
"""

from __future__ import annotations

from table_mcp.schemas import (
    PlanConversionInput,
    PlanConversionOutput,
    RecommendStrategyInput,
    RecommendStrategyOutput,
)

# Fixed evaluation order of SPEC §5. Read by the order-boundary tests.
DECISION_ORDER: tuple[str, ...] = ("S6", "S7", "S5", "S4", "S3", "S2", "S1")


def recommend_strategy(params: RecommendStrategyInput) -> RecommendStrategyOutput:
    """Return the `StrategyDecision` for a profile. Pure function, no I/O."""
    raise NotImplementedError("SPEC §5 strategy matrix")


def plan_conversion(params: PlanConversionInput) -> PlanConversionOutput:
    """Build a `ConversionPlan`: per-table strategy, ordering, parallelism,
    staging locations and estimated totals. No side effects (SPEC §3)."""
    raise NotImplementedError("SPEC §3 plan_conversion")
