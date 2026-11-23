"""Exact money arithmetic.

Amounts are integer minor units (cents) plus an ISO 4217 currency code.
Floats are rejected everywhere: every conversion that can produce a fraction
of a cent takes an explicit rounding mode.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Self

ROUND_DEFAULT = ROUND_HALF_UP


class CurrencyMismatch(ValueError):
    """Two amounts in different currencies were combined."""


def to_decimal(value: Decimal | int | str) -> Decimal:
    """Convert to Decimal, refusing floats (they are not exact)."""
    if isinstance(value, (bool, float)):
        raise TypeError("floats/bools are not accepted for money or rates; use Decimal or str")
    return value if isinstance(value, Decimal) else Decimal(value)


@dataclass(frozen=True, slots=True, order=False)
class Money:
    cents: int
    currency: str = "EUR"

    def __post_init__(self) -> None:
        if isinstance(self.cents, bool) or not isinstance(self.cents, int):
            raise TypeError("Money.cents must be an int (minor units)")
        if len(self.currency) != 3 or not self.currency.isalpha() or not self.currency.isupper():
            raise ValueError(f"invalid ISO 4217 currency code: {self.currency!r}")

    # -- construction -------------------------------------------------------
    @classmethod
    def eur(cls, amount: Decimal | int | str) -> Money:
        """Build from a major-unit amount, e.g. Money.eur("6.99")."""
        return cls.of(amount, "EUR")

    @classmethod
    def of(cls, amount: Decimal | int | str, currency: str) -> Money:
        d = to_decimal(amount) * 100
        if d != d.to_integral_value():
            raise ValueError(f"amount {amount} has more precision than one cent")
        return cls(int(d), currency)

    @classmethod
    def zero(cls, currency: str = "EUR") -> Money:
        return cls(0, currency)

    # -- arithmetic ---------------------------------------------------------
    def _check(self, other: Money) -> None:
        if not isinstance(other, Money):
            raise TypeError("can only combine Money with Money")
        if other.currency != self.currency:
            raise CurrencyMismatch(f"{self.currency} vs {other.currency}")

    def __add__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.cents + other.cents, self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check(other)
        return Money(self.cents - other.cents, self.currency)

    def __neg__(self) -> Money:
        return Money(-self.cents, self.currency)

    def times(self, qty: int) -> Money:
        """Multiply by an integer quantity (exact)."""
        if isinstance(qty, bool) or not isinstance(qty, int):
            raise TypeError("quantity must be an int")
        return Money(self.cents * qty, self.currency)

    def scale(self, factor: Decimal | int | str, rounding: str = ROUND_DEFAULT) -> Money:
        """Multiply by a Decimal factor, rounding to the cent explicitly."""
        raw = Decimal(self.cents) * to_decimal(factor)
        return Money(int(raw.to_integral_value(rounding=rounding)), self.currency)

    def divide(self, divisor: Decimal | int | str, rounding: str = ROUND_DEFAULT) -> Money:
        d = to_decimal(divisor)
        if d == 0:
            raise ZeroDivisionError("division of money by zero")
        raw = Decimal(self.cents) / d
        return Money(int(raw.to_integral_value(rounding=rounding)), self.currency)

    # -- comparison ---------------------------------------------------------
    def __lt__(self, other: Money) -> bool:
        self._check(other)
        return self.cents < other.cents

    def __le__(self, other: Money) -> bool:
        self._check(other)
        return self.cents <= other.cents

    def __gt__(self, other: Money) -> bool:
        self._check(other)
        return self.cents > other.cents

    def __ge__(self, other: Money) -> bool:
        self._check(other)
        return self.cents >= other.cents

    # -- presentation -------------------------------------------------------
    @property
    def amount(self) -> Decimal:
        return Decimal(self.cents) / 100

    def __str__(self) -> str:
        sign = "-" if self.cents < 0 else ""
        whole, frac = divmod(abs(self.cents), 100)
        return f"{sign}{whole}.{frac:02d} {self.currency}"

    def to_json(self) -> dict[str, int | str]:
        return {"cents": self.cents, "currency": self.currency}

    @classmethod
    def from_json(cls, data: dict[str, int | str]) -> Self:
        return cls(int(data["cents"]), str(data["currency"]))


def total(items: list[Money], currency: str = "EUR") -> Money:
    acc = Money.zero(currency)
    for m in items:
        acc = acc + m
    return acc
