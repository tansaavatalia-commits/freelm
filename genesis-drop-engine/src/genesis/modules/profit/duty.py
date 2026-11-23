"""EU import duty for low-value B2C parcels (BUSINESS_RULES.md section 6).

From 2026-07-01 (Reg. (EU) 2026/382, until 2028-07-01) non-EU B2C consignments
<= EUR 150 pay a flat EUR 3 customs duty. Sources disagree on the counting
basis ("per item" vs "per tariff line in the parcel"). Until the operator or
an official source resolves it, both readings are modelled: the per-tariff-line
amount is the optimistic/central value and the per-item amount is the prudent
value, so the profit gate always uses the more expensive reading.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum

from genesis.core.money import Money
from genesis.core.provenance import Provenance, Verification
from genesis.modules.profit.domain import CostComponent, CostGroup

FLAT_DUTY_FROM = date(2026, 7, 1)
FLAT_DUTY_UNTIL = date(2028, 7, 1)
FLAT_DUTY_AMOUNT = Money.eur("3.00")
LOW_VALUE_THRESHOLD = Money.eur("150.00")
SOURCE = (
    "Reg. (UE) 2026/382; guida Commissione UE 2026-06-08 "
    "(taxation-customs.ec.europa.eu) - base di conteggio da verificare"
)


class CountingBasis(StrEnum):
    PER_ITEM = "PER_ITEM"
    PER_TARIFF_LINE = "PER_TARIFF_LINE"


def eu_import_duty(
    *,
    origin_in_eu: bool,
    ship_date: date,
    pack_size: int,
    distinct_tariff_lines: int,
    consignment_value: Money,
    resolved_basis: CountingBasis | None = None,
) -> CostComponent:
    """Return the `import_duty` cost component for one parcel."""
    if pack_size < 1 or not (1 <= distinct_tariff_lines <= pack_size):
        raise ValueError("need 1 <= distinct_tariff_lines <= pack_size")
    if origin_in_eu:
        return CostComponent.fixed(
            "import_duty", CostGroup.COGS,
            Provenance("spedizione intra-UE: nessun dazio", Verification.VERIFIED),
            Money.zero(),
        )
    if consignment_value > LOW_VALUE_THRESHOLD:
        # standard tariff rates apply: needs the product's real duty rate
        return CostComponent.missing("import_duty", source="dazio ordinario (>150 EUR) non noto")
    if not (FLAT_DUTY_FROM <= ship_date < FLAT_DUTY_UNTIL):
        return CostComponent.missing("import_duty", source="regime dazio fuori dal periodo noto")

    per_line = FLAT_DUTY_AMOUNT.times(distinct_tariff_lines)
    per_item = FLAT_DUTY_AMOUNT.times(pack_size)
    if resolved_basis is CountingBasis.PER_ITEM:
        return CostComponent.fixed("import_duty", CostGroup.COGS,
                                   Provenance(SOURCE + " [PER_ITEM]", Verification.VERIFIED),
                                   per_item)
    if resolved_basis is CountingBasis.PER_TARIFF_LINE:
        return CostComponent.fixed("import_duty", CostGroup.COGS,
                                   Provenance(SOURCE + " [PER_TARIFF_LINE]", Verification.VERIFIED),
                                   per_line)
    return CostComponent.fixed(
        "import_duty", CostGroup.COGS,
        Provenance(SOURCE, Verification.ESTIMATED,
                   note="ottimistico/centrale = per linea tariffaria; prudenziale = per articolo"),
        central=per_line, optimistic=per_line, prudent=per_item,
    )
