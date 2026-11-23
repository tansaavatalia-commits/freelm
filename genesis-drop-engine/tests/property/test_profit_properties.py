from hypothesis import given
from hypothesis import strategies as st

from genesis.core.money import Money
from genesis.modules.profit.domain import CostComponent, CostGroup, Scenario, calculate
from genesis.policy.rule_set import DEFAULT_RULE_SET as RULES
from tests.conftest import NOW, V, example_input

prices = st.integers(min_value=100, max_value=50_000)
ads = st.integers(min_value=0, max_value=5_000)


def _with_ads(price_cents: int, ads_cents: int, pack: int = 1):  # type: ignore[no-untyped-def]
    return example_input(pack_size=pack, price=str(Money(price_cents).amount),
                         drop=("advertising",),
                         extra=(CostComponent.fixed("advertising", CostGroup.OPERATING, V,
                                                    Money(ads_cents)),))


@given(prices, ads, ads)
def test_higher_cost_never_increases_profit(p: int, a1: int, a2: int) -> None:
    lo, hi = sorted((a1, a2))
    r_lo = calculate(_with_ads(p, lo), RULES, NOW).results[Scenario.PRUDENT]
    r_hi = calculate(_with_ads(p, hi), RULES, NOW).results[Scenario.PRUDENT]
    assert r_hi.net_operating_profit <= r_lo.net_operating_profit


@given(prices, ads)
def test_scenarios_are_ordered(p: int, a: int) -> None:
    r = calculate(_with_ads(p, a, pack=5), RULES, NOW).results
    assert (r[Scenario.PRUDENT].net_operating_profit <= r[Scenario.CENTRAL].net_operating_profit
            <= r[Scenario.OPTIMISTIC].net_operating_profit)


@given(prices, ads, st.sampled_from(RULES.pack_sizes))
def test_eligibility_equals_prudent_threshold(p: int, a: int, n: int) -> None:
    s = calculate(_with_ads(p * n, a, pack=n), RULES, NOW)
    prudent = s.results[Scenario.PRUDENT].net_operating_profit
    assert s.eligible == (prudent >= RULES.min_profit_for_pack(n))


@given(prices)
def test_vat_split_is_exact(p: int) -> None:
    r = calculate(_with_ads(p, 0), RULES, NOW).results[Scenario.CENTRAL]
    assert r.vat + r.revenue_ex_vat == r.gross_revenue
