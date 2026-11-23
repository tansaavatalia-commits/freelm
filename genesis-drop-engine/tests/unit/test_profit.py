from datetime import date
from decimal import Decimal

import pytest

from genesis.core.fx import FxRate
from genesis.core.money import Money
from genesis.core.provenance import Provenance, Verification
from genesis.modules.profit.domain import (
    CostComponent,
    CostGroup,
    Scenario,
    calculate,
)
from genesis.modules.profit.duty import CountingBasis, eu_import_duty
from genesis.modules.profit.packs import BASIS_EXPECTED, BASIS_PROFIT_ONLY, compare_packs
from genesis.policy.rule_set import DEFAULT_RULE_SET as RULES
from tests.conftest import NOW, V, example_input


def gate(snap, rule_id):  # type: ignore[no-untyped-def]
    return next(g for g in snap.gates if g.rule_id == rule_id)


def test_business_rules_example_single_unit_loses_2_17() -> None:
    snap = calculate(example_input(), RULES, NOW)
    p = snap.results[Scenario.PRUDENT]
    assert snap.status == "COMPLETE"
    assert p.revenue_ex_vat == Money(573)
    assert p.vat == Money(126)
    assert p.net_operating_profit == Money(-217)
    assert not snap.eligible
    assert not gate(snap, "BR-010").passed
    assert gate(snap, "BR-001").passed


def test_margin_hierarchy_is_reported_separately() -> None:
    p = calculate(example_input(), RULES, NOW).results[Scenario.CENTRAL]
    assert p.gross_margin == Money(573 - 100 - 250 - 300)
    assert p.contribution_margin == p.gross_margin - Money(105 + 35)
    assert p.net_operating_profit == p.contribution_margin  # no ads


def test_single_unit_break_even_price_for_3_eur_is_about_15_33() -> None:
    # cost rounding goes up (prudent), so the exact threshold is 15.35
    assert not calculate(example_input(price="15.34"), RULES, NOW).eligible
    assert calculate(example_input(price="15.35"), RULES, NOW).eligible


def test_five_pack_uses_prudent_per_item_duty() -> None:
    # per tariff line ~42.76 would suffice; prudent per-item reading needs ~62.13
    s = calculate(example_input(pack_size=5, price="50.00", shipping="3.50"), RULES, NOW)
    assert s.results[Scenario.CENTRAL].net_operating_profit >= Money(1500)
    assert s.results[Scenario.PRUDENT].net_operating_profit < Money(1500)
    assert not s.eligible
    assert calculate(example_input(pack_size=5, price="62.20", shipping="3.50"), RULES, NOW).eligible


def test_resolved_per_tariff_line_basis_lowers_requirement() -> None:
    duty = eu_import_duty(origin_in_eu=False, ship_date=date(2026, 11, 20), pack_size=5,
                          distinct_tariff_lines=1, consignment_value=Money.eur("5.00"),
                          resolved_basis=CountingBasis.PER_TARIFF_LINE)
    s = calculate(example_input(pack_size=5, price="42.80", shipping="3.50",
                                drop=("import_duty",), extra=(duty,)), RULES, NOW)
    assert s.eligible


def test_exactly_three_euro_passes_and_one_cent_less_fails() -> None:
    # tune advertising so the prudent profit lands exactly on the threshold
    base = calculate(example_input(price="20.00"), RULES, NOW).results[Scenario.PRUDENT]
    ads = base.net_operating_profit - Money(300)
    exact = example_input(price="20.00", drop=("advertising",), extra=(
        CostComponent.fixed("advertising", CostGroup.OPERATING, V, ads),))
    assert calculate(exact, RULES, NOW).eligible
    short = example_input(price="20.00", drop=("advertising",), extra=(
        CostComponent.fixed("advertising", CostGroup.OPERATING, V, ads + Money(1)),))
    assert not calculate(short, RULES, NOW).eligible


def test_missing_cost_makes_calculation_incomplete() -> None:
    s = calculate(example_input(price="99.00", drop=("advertising",)), RULES, NOW)
    assert s.status == "INCOMPLETE" and "advertising" in s.missing
    assert not s.eligible and s.results == {}
    s2 = calculate(example_input(price="99.00", drop=("advertising",),
                                 extra=(CostComponent.missing("advertising"),)), RULES, NOW)
    assert s2.status == "INCOMPLETE"


def test_duty_above_150_is_missing_not_zero() -> None:
    d = eu_import_duty(origin_in_eu=False, ship_date=date(2026, 11, 20), pack_size=1,
                       distinct_tariff_lines=1, consignment_value=Money.eur("151.00"))
    assert d.is_missing


def test_intra_eu_has_no_duty() -> None:
    d = eu_import_duty(origin_in_eu=True, ship_date=date(2026, 11, 20), pack_size=3,
                       distinct_tariff_lines=1, consignment_value=Money.eur("3.00"))
    assert d.amount(Scenario.PRUDENT, 3, Money.eur("10.00")) == Money.zero()


def test_acquisition_cap_br001() -> None:
    assert gate(calculate(example_input(unit_cost=Money.eur("1.00"), price="30.00"), RULES, NOW),
                "BR-001").passed
    s = calculate(example_input(unit_cost=Money.eur("1.01"), price="30.00"), RULES, NOW)
    assert not gate(s, "BR-001").passed and not s.eligible


def test_acquisition_exception_requires_approval_id() -> None:
    s = calculate(example_input(unit_cost=Money.eur("1.50"), price="30.00",
                                acquisition_exception_approval="APR-1"), RULES, NOW)
    assert gate(s, "BR-001").passed and s.eligible
    assert any("BR-002" in w for w in s.warnings)


def test_fx_margin_applies_before_cap() -> None:
    # 1.05 USD * 0.95 = 0.9975 EUR -> within cap; with 3% margin = 1.0274 -> over cap
    fx = FxRate("USD", "EUR", Decimal("0.95"), Provenance("BCE", Verification.VERIFIED))
    s = calculate(example_input(unit_cost=Money.of("1.05", "USD"), fx=fx, price="30.00"),
                  RULES, NOW)
    assert s.unit_cost_eur == Money(103)
    assert not gate(s, "BR-001").passed


def test_non_eur_without_fx_is_rejected() -> None:
    with pytest.raises(ValueError):
        example_input(unit_cost=Money.of("0.90", "USD"))


def test_cost_range_ordering_validated() -> None:
    with pytest.raises(ValueError):
        CostComponent.fixed("packaging", CostGroup.CONTRIBUTION, V, Money(100),
                            optimistic=Money(200))


def test_snapshot_is_reproducible_and_hash_sensitive() -> None:
    a = calculate(example_input(), RULES, NOW)
    b = calculate(example_input(), RULES, NOW)
    c = calculate(example_input(price="7.00"), RULES, NOW)
    assert a.inputs_hash == b.inputs_hash != c.inputs_hash
    assert a.to_json()["tax_profit_note"].startswith("Profitto contabile/fiscale NON")
    assert a.rule_set_version == RULES.version


def test_data_reliability_counts_verified_share() -> None:
    s = calculate(example_input(), RULES, NOW)
    assert Decimal(0) < s.data_reliability < Decimal(1)


def test_compare_packs_without_demand_data_is_flagged() -> None:
    cmp = compare_packs(lambda n: example_input(pack_size=n, price=str(13 * n),
                                                shipping="3.50"), RULES, NOW)
    assert len(cmp.snapshots) == len(RULES.pack_sizes)
    assert cmp.selection_basis == BASIS_PROFIT_ONLY
    assert cmp.chosen is not None and cmp.chosen.eligible
    assert any("mancanti" in w for w in cmp.warnings)


def test_compare_packs_with_conversion_prefers_realistic_outcome() -> None:
    conv = {1: Decimal("1"), 2: Decimal("0.9"), 3: Decimal("0.8"), 5: Decimal("0.5"),
            10: Decimal("0.05")}
    cmp = compare_packs(lambda n: example_input(pack_size=n, price=str(13 * n),
                                                shipping="3.50"), RULES, NOW, conv)
    assert cmp.selection_basis == BASIS_EXPECTED
    assert cmp.chosen is not None and cmp.chosen.inputs.pack_size != 10


def test_compare_packs_none_eligible() -> None:
    cmp = compare_packs(lambda n: example_input(pack_size=n, price=str(Decimal("6.99") * n)),
                        RULES, NOW)
    assert cmp.chosen is None
