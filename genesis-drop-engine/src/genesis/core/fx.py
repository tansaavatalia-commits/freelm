"""Currency conversion with a recorded rate and an explicit prudential margin (BR-005)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from genesis.core.money import Money, to_decimal
from genesis.core.provenance import Provenance


@dataclass(frozen=True, slots=True)
class FxRate:
    base: str  # e.g. "USD"
    quote: str  # e.g. "EUR"
    rate: Decimal  # 1 base = rate quote
    provenance: Provenance

    def __post_init__(self) -> None:
        object.__setattr__(self, "rate", to_decimal(self.rate))
        if self.rate <= 0:
            raise ValueError("fx rate must be positive")

    def convert_cost(self, amount: Money, safety_margin: Decimal | str = "0") -> Money:
        """Convert a *cost*: margin inflates it and rounding goes up (never optimistic)."""
        if amount.currency != self.base:
            raise ValueError(f"rate is {self.base}->{self.quote}, got {amount.currency}")
        factor = self.rate * (Decimal(1) + to_decimal(safety_margin))
        converted = amount.scale(factor, rounding=ROUND_CEILING)
        return Money(converted.cents, self.quote)
