from decimal import ROUND_FLOOR, Decimal

import pytest

from genesis.core.money import CurrencyMismatch, Money, total


def test_construction_and_str() -> None:
    assert Money.eur("6.99").cents == 699
    assert str(Money(-217)) == "-2.17 EUR"
    assert Money.eur(3) == Money(300)


def test_rejects_floats_and_sub_cent_precision() -> None:
    with pytest.raises(TypeError):
        Money.eur(6.99)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        Money.eur("1.005")
    with pytest.raises(TypeError):
        Money(1.5)  # type: ignore[arg-type]


def test_currency_rules() -> None:
    with pytest.raises(CurrencyMismatch):
        Money(1, "EUR") + Money(1, "USD")
    with pytest.raises(ValueError):
        Money(1, "eur")
    with pytest.raises(CurrencyMismatch):
        _ = Money(1, "EUR") < Money(1, "USD")


def test_explicit_rounding() -> None:
    assert Money(699).scale(Decimal("0.15")).cents == 105  # 104.85 half-up
    assert Money(699).scale(Decimal("0.15"), rounding=ROUND_FLOOR).cents == 104
    assert Money(699).divide(Decimal("1.22")).cents == 573  # 572.95
    with pytest.raises(ZeroDivisionError):
        Money(1).divide(0)


def test_total_and_times() -> None:
    assert total([Money(100), Money(250)]) == Money(350)
    assert Money(300).times(5) == Money(1500)
    with pytest.raises(TypeError):
        Money(1).times(True)


def test_json_roundtrip() -> None:
    m = Money(123, "USD")
    assert Money.from_json(m.to_json()) == m
