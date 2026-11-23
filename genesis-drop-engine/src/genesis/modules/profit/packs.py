"""Single-unit vs multipack comparison (BR-012 / BR-013)."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from genesis.modules.profit.domain import ProfitInput, ProfitSnapshot, Scenario, calculate
from genesis.policy.rule_set import RuleSet

BASIS_EXPECTED = "EXPECTED_OUTCOME"  # prudent profit x conversion estimate
BASIS_PROFIT_ONLY = "PRUDENT_PROFIT_ONLY"  # no demand data: profit only, flagged


@dataclass(frozen=True, slots=True)
class PackComparison:
    snapshots: tuple[ProfitSnapshot, ...]
    chosen: ProfitSnapshot | None
    selection_basis: str
    warnings: tuple[str, ...]


def compare_packs(
    build_input: Callable[[int], ProfitInput],
    rules: RuleSet,
    computed_at: datetime,
    conversion_estimates: Mapping[int, Decimal] | None = None,
) -> PackComparison:
    """Evaluate every pack size of the rule set and pick the best *eligible* one.

    `conversion_estimates` maps pack size -> relative conversion likelihood (0..1).
    Without it, the choice falls back to prudent total profit and says so,
    because optimising margin alone is not a realistic commercial outcome (BR-013).
    """
    snaps = tuple(calculate(build_input(n), rules, computed_at) for n in rules.pack_sizes)
    for s, n in zip(snaps, rules.pack_sizes, strict=True):
        if s.inputs.pack_size != n:
            raise ValueError("build_input must return the requested pack size")
    eligible = [s for s in snaps if s.eligible]
    warnings: list[str] = []

    have_all = conversion_estimates is not None and all(
        s.inputs.pack_size in conversion_estimates for s in eligible
    )
    if conversion_estimates is not None:
        for v in conversion_estimates.values():
            if not (Decimal(0) <= v <= Decimal(1)):
                raise ValueError("conversion estimates must be within [0, 1]")

    def value(s: ProfitSnapshot) -> Decimal:
        profit = Decimal(s.results[Scenario.PRUDENT].net_operating_profit.cents)
        if have_all:
            assert conversion_estimates is not None
            return profit * conversion_estimates[s.inputs.pack_size]
        return profit

    chosen = None
    if eligible:
        # tie-break: smaller pack (less capital tied up, lower risk)
        chosen = max(eligible, key=lambda s: (value(s), -s.inputs.pack_size))
    else:
        warnings.append("Nessuna configurazione rispetta tutte le regole")
    if eligible and not have_all:
        warnings.append(
            "Dati di domanda/conversione mancanti: scelta basata solo sul profitto prudenziale"
        )
    return PackComparison(snaps, chosen, BASIS_EXPECTED if have_all else BASIS_PROFIT_ONLY,
                          tuple(warnings))
