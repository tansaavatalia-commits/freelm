from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from genesis.core.money import Money
from genesis.core.provenance import Provenance, Verification
from genesis.modules.profit.domain import CostComponent, CostGroup, ProfitInput
from genesis.modules.profit.duty import eu_import_duty

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)
V = Provenance("test fixture", Verification.VERIFIED)
E = Provenance("test fixture (estimate)", Verification.ESTIMATED)


def example_input(
    pack_size: int = 1,
    price: str = "6.99",
    shipping: str = "2.50",
    unit_cost: Money | None = None,
    extra: tuple[CostComponent, ...] = (),
    drop: tuple[str, ...] = (),
    **kw: object,
) -> ProfitInput:
    """The illustrative case of BUSINESS_RULES.md section 5 (Italy, China origin)."""
    costs = [
        CostComponent.fixed("supplier_shipping", CostGroup.COGS, E, Money.eur(shipping)),
        eu_import_duty(origin_in_eu=False, ship_date=date(2026, 11, 20), pack_size=pack_size,
                       distinct_tariff_lines=1, consignment_value=Money.eur("1.00").times(pack_size)),
        CostComponent.fixed("supplier_charged_vat", CostGroup.COGS, V, Money.zero()),
        CostComponent.pct("marketplace_commission", CostGroup.CONTRIBUTION, E, "0.15"),
        CostComponent.fixed("payment_fee", CostGroup.CONTRIBUTION, V, Money.zero()),
        CostComponent.fixed("packaging", CostGroup.CONTRIBUTION, V, Money.zero()),
        CostComponent.pct("returns_reserve", CostGroup.CONTRIBUTION, E, "0.05"),
        CostComponent.fixed("chargeback_reserve", CostGroup.CONTRIBUTION, V, Money.zero()),
        CostComponent.fixed("advertising", CostGroup.OPERATING, E, Money.zero()),
    ]
    costs = [c for c in costs if c.code not in drop] + list(extra)
    args: dict[str, object] = dict(
        product_ref="P1", supplier_ref="S1", destination_country="IT", channel="test",
        pack_size=pack_size, price_gross=Money.eur(price), vat_rate="0.22", vat_provenance=V,
        unit_cost=unit_cost or Money.eur("1.00"), unit_cost_provenance=V, costs=tuple(costs),
    )
    args.update(kw)
    return ProfitInput(**args)  # type: ignore[arg-type]


@pytest.fixture
def now() -> datetime:
    return NOW
