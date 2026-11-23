"""Versioned, operator-approved business rule parameters (BUSINESS_RULES.md).

Changing any value requires a new version approved by the operator; the active
rule set version is recorded on every calculation and decision.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal
from typing import Any

from genesis.core.money import Money


@dataclass(frozen=True, slots=True)
class RuleSet:
    version: str
    # BR-001: max supplier purchase price per unit (excl. shipping and other costs)
    max_unit_cost: Money = field(default_factory=lambda: Money.eur("1.00"))
    # BR-005: prudential FX margin applied before checking BR-001
    fx_safety_margin: Decimal = Decimal("0.03")
    # BR-010/011: minimum net operating profit per unit (multipacks: x units)
    min_profit_per_unit: Money = field(default_factory=lambda: Money.eur("3.00"))
    # BR-012: pack sizes always compared
    pack_sizes: tuple[int, ...] = (1, 2, 3, 5, 10)
    # BR-003: target resale price per unit (optimiser goal, not a blocking gate)
    target_unit_price: Money = field(default_factory=lambda: Money.eur("6.00"))
    # D-011 (approved 2026-11-20): operator-funded working capital cap
    operator_funding_cap: Money = field(default_factory=lambda: Money.eur("100.00"))
    # D-007 defaults (pending approval): reserve parameters
    reserve_refunds_pct: Decimal = Decimal("0.10")
    reserve_chargebacks_pct: Decimal = Decimal("0.01")
    reserve_vat_pct: Decimal = Decimal("1.00")
    # BR-056: initial automation level
    automation_level: int = 1

    def __post_init__(self) -> None:
        if not self.version:
            raise ValueError("rule set version required")
        if not self.pack_sizes or any(n < 1 for n in self.pack_sizes):
            raise ValueError("pack sizes must be positive")
        if 1 not in self.pack_sizes:
            raise ValueError("single unit (1) must always be compared (BR-012)")
        if self.max_unit_cost.cents <= 0 or self.min_profit_per_unit.cents <= 0:
            raise ValueError("rule thresholds must be positive")
        if not (0 <= self.automation_level <= 4):
            raise ValueError("automation level must be 0..4")

    def min_profit_for_pack(self, pack_size: int) -> Money:
        """BR-011: minimum total profit for an n-unit pack."""
        return self.min_profit_per_unit.times(pack_size)

    def to_json(self) -> dict[str, Any]:
        out: dict[str, Any] = {}
        for k, v in asdict(self).items():
            if isinstance(v, dict) and "cents" in v:
                out[k] = v
            elif isinstance(v, Decimal):
                out[k] = str(v)
            elif isinstance(v, tuple):
                out[k] = list(v)
            else:
                out[k] = v
        return out


# Rule set approved by the operator in Phase 1 (D-003, D-010, D-011).
DEFAULT_RULE_SET = RuleSet(version="2026-11-20.1")
