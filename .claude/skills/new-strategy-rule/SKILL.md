---
name: new-strategy-rule
description: Add or change a Delta→Iceberg strategy rule or Delta→Iceberg type mapping in table-mcp with its mandatory named tests and record entry.
---
# New strategy rule / type mapping (table-mcp)

1. Read `servers/table-mcp/SPEC.md` section 5 and `src/table_mcp/strategy.py`.
2. Add the rule as a pure predicate `rule_<id>(profile: TableProfile) -> RuleResult` in the documented decision order (S6 → S7 → S5 → S4 → S3 → S2 → S1). Do not reorder existing rules.
3. Append a rationale string to `RuleResult.rationale` for every rule evaluated, matched or not.
4. Add `tests/unit/test_strategy.py::test_strategy_rule_<id>` with at least one positive and one negative profile. For type mappings add `test_type_map_<delta_type>` including a round-trip schema check.
5. Update the strategy matrix table in `SPEC.md` if behaviour changed, and add an ADR if the change is a design decision.
6. Run the full unit suite; coverage on `strategy.py` must stay ≥ 90%.
