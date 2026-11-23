import pytest

from genesis.core.money import Money
from genesis.policy.rule_set import DEFAULT_RULE_SET, RuleSet


def test_defaults_match_business_rules() -> None:
    r = DEFAULT_RULE_SET
    assert r.max_unit_cost == Money.eur("1.00")
    assert r.min_profit_per_unit == Money.eur("3.00")
    assert r.operator_funding_cap == Money.eur("100.00")  # D-011
    assert r.automation_level == 1


@pytest.mark.parametrize("n,expected", [(1, 300), (3, 900), (5, 1500), (10, 3000)])
def test_min_profit_for_pack(n: int, expected: int) -> None:
    assert DEFAULT_RULE_SET.min_profit_for_pack(n).cents == expected


def test_single_unit_must_be_compared() -> None:
    with pytest.raises(ValueError):
        RuleSet(version="x", pack_sizes=(2, 3))


def test_invalid_automation_level() -> None:
    with pytest.raises(ValueError):
        RuleSet(version="x", automation_level=5)
