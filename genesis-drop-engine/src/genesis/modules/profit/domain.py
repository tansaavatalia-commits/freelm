"""Profit Engine (M5) - pure, auditable profitability calculation.

Implements BUSINESS_RULES.md sections 2-5:
- three scenarios per uncertain cost (optimistic / central / prudent);
- the BR-010/011 minimum-profit gate uses the PRUDENT scenario;
- a MISSING required cost makes the calculation INCOMPLETE (never optimistic);
- BR-001 is checked on the supplier unit cost converted to EUR *with* the FX safety margin;
- revenue/VAT/margins are reported separately; the tax profit is never certified here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from genesis.core.fx import FxRate
from genesis.core.hashing import sha256_hex
from genesis.core.money import Money, to_decimal
from genesis.core.provenance import Provenance, Verification
from genesis.policy.gates import GateResult, all_passed
from genesis.policy.rule_set import RuleSet

FORMULA_VERSION = "profit-1.0"
TAX_PROFIT_NOTE = (
    "Profitto contabile/fiscale NON certificato: paese di registrazione e struttura fiscale "
    "non ancora definiti."
)


class Scenario(StrEnum):
    OPTIMISTIC = "OPTIMISTIC"
    CENTRAL = "CENTRAL"
    PRUDENT = "PRUDENT"


SCENARIOS: tuple[Scenario, ...] = (Scenario.OPTIMISTIC, Scenario.CENTRAL, Scenario.PRUDENT)


class CostGroup(StrEnum):
    COGS = "COGS"  # -> gross margin
    CONTRIBUTION = "CONTRIBUTION"  # -> contribution margin
    OPERATING = "OPERATING"  # -> net operating profit


class Basis(StrEnum):
    PER_ORDER = "PER_ORDER"  # fixed amount for the whole order/parcel
    PER_UNIT = "PER_UNIT"  # amount x pack size
    PCT_OF_GROSS = "PCT_OF_GROSS"  # rate x gross price (VAT incl.)


# Costs every calculation must declare (a verified 0 is allowed; absence is not).
REQUIRED_COSTS: dict[str, CostGroup] = {
    "product": CostGroup.COGS,
    "supplier_shipping": CostGroup.COGS,
    "import_duty": CostGroup.COGS,
    "supplier_charged_vat": CostGroup.COGS,  # e.g. IOSS VAT charged by the supplier
    "marketplace_commission": CostGroup.CONTRIBUTION,
    "payment_fee": CostGroup.CONTRIBUTION,
    "packaging": CostGroup.CONTRIBUTION,
    "returns_reserve": CostGroup.CONTRIBUTION,
    "chargeback_reserve": CostGroup.CONTRIBUTION,
    "advertising": CostGroup.OPERATING,
}


class IncompleteInput(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CostComponent:
    code: str
    group: CostGroup
    basis: Basis
    provenance: Provenance
    amounts: tuple[Money, Money, Money] | None = None  # PER_ORDER / PER_UNIT
    rates: tuple[Decimal, Decimal, Decimal] | None = None  # PCT_OF_GROSS

    def __post_init__(self) -> None:
        if self.provenance.verification is Verification.MISSING:
            return  # placeholder for a missing cost: values are not used
        if self.basis is Basis.PCT_OF_GROSS:
            if self.rates is None or self.amounts is not None:
                raise ValueError(f"{self.code}: PCT_OF_GROSS needs rates only")
            rs = tuple(to_decimal(r) for r in self.rates)
            if any(r < 0 or r > 1 for r in rs):
                raise ValueError(f"{self.code}: rates must be within [0, 1]")
            if not (rs[0] <= rs[1] <= rs[2]):
                raise ValueError(f"{self.code}: need optimistic <= central <= prudent")
            object.__setattr__(self, "rates", rs)
        else:
            if self.amounts is None or self.rates is not None:
                raise ValueError(f"{self.code}: {self.basis} needs amounts only")
            a = self.amounts
            if any(m.cents < 0 for m in a):
                raise ValueError(f"{self.code}: cost amounts must be >= 0")
            if not (a[0] <= a[1] <= a[2]):
                raise ValueError(f"{self.code}: need optimistic <= central <= prudent")

    @property
    def is_missing(self) -> bool:
        return self.provenance.verification is Verification.MISSING

    # -- constructors -------------------------------------------------------
    @classmethod
    def fixed(
        cls, code: str, group: CostGroup, provenance: Provenance,
        central: Money, optimistic: Money | None = None, prudent: Money | None = None,
    ) -> CostComponent:
        return cls(code, group, Basis.PER_ORDER, provenance,
                   amounts=(optimistic or central, central, prudent or central))

    @classmethod
    def per_unit(
        cls, code: str, group: CostGroup, provenance: Provenance,
        central: Money, optimistic: Money | None = None, prudent: Money | None = None,
    ) -> CostComponent:
        return cls(code, group, Basis.PER_UNIT, provenance,
                   amounts=(optimistic or central, central, prudent or central))

    @classmethod
    def pct(
        cls, code: str, group: CostGroup, provenance: Provenance,
        central: Decimal | str, optimistic: Decimal | str | None = None,
        prudent: Decimal | str | None = None,
    ) -> CostComponent:
        c = to_decimal(central)
        o = to_decimal(optimistic) if optimistic is not None else c
        p = to_decimal(prudent) if prudent is not None else c
        return cls(code, group, Basis.PCT_OF_GROSS, provenance, rates=(o, c, p))

    @classmethod
    def missing(cls, code: str, group: CostGroup | None = None, source: str = "none") -> CostComponent:
        return cls(code, group or REQUIRED_COSTS.get(code, CostGroup.OPERATING),
                   Basis.PER_ORDER, Provenance.missing(source))

    def amount(self, scenario: Scenario, pack_size: int, gross: Money) -> Money:
        if self.is_missing:
            raise IncompleteInput(self.code)
        i = SCENARIOS.index(scenario)
        if self.basis is Basis.PCT_OF_GROSS:
            assert self.rates is not None
            return gross.scale(self.rates[i], rounding=ROUND_CEILING)
        assert self.amounts is not None
        m = self.amounts[i]
        return m.times(pack_size) if self.basis is Basis.PER_UNIT else m

    def to_json(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "group": self.group.value,
            "basis": self.basis.value,
            "amounts": [m.to_json() for m in self.amounts] if self.amounts else None,
            "rates": [str(r) for r in self.rates] if self.rates else None,
            "provenance": self.provenance.to_json(),
        }


@dataclass(frozen=True, slots=True)
class ProfitInput:
    product_ref: str
    supplier_ref: str
    destination_country: str
    channel: str
    pack_size: int
    price_gross: Money  # total paid by the customer for the pack, VAT incl.
    vat_rate: Decimal
    vat_provenance: Provenance
    unit_cost: Money  # supplier price per unit, original currency
    unit_cost_provenance: Provenance
    costs: tuple[CostComponent, ...]  # everything except "product"
    fx: FxRate | None = None  # required when unit_cost is not EUR
    acquisition_exception_approval: str | None = None  # BR-002 approval id

    def __post_init__(self) -> None:
        if self.pack_size < 1:
            raise ValueError("pack_size must be >= 1")
        if self.price_gross.currency != "EUR" or self.price_gross.cents <= 0:
            raise ValueError("price_gross must be a positive EUR amount")
        object.__setattr__(self, "vat_rate", to_decimal(self.vat_rate))
        if not (0 <= self.vat_rate < 1):
            raise ValueError("vat_rate must be within [0, 1)")
        codes = [c.code for c in self.costs]
        if len(codes) != len(set(codes)):
            raise ValueError("duplicate cost component codes")
        if "product" in codes:
            raise ValueError("'product' is derived from unit_cost; do not pass it in costs")
        if self.unit_cost.currency != "EUR" and self.fx is None:
            raise ValueError("fx rate required for a non-EUR unit cost")

    def to_json(self) -> dict[str, Any]:
        return {
            "product_ref": self.product_ref,
            "supplier_ref": self.supplier_ref,
            "destination_country": self.destination_country,
            "channel": self.channel,
            "pack_size": self.pack_size,
            "price_gross": self.price_gross.to_json(),
            "vat_rate": str(self.vat_rate),
            "vat_provenance": self.vat_provenance.to_json(),
            "unit_cost": self.unit_cost.to_json(),
            "unit_cost_provenance": self.unit_cost_provenance.to_json(),
            "fx": None if self.fx is None else {
                "base": self.fx.base, "quote": self.fx.quote, "rate": str(self.fx.rate),
                "provenance": self.fx.provenance.to_json(),
            },
            "costs": sorted((c.to_json() for c in self.costs), key=lambda c: str(c["code"])),
            "acquisition_exception_approval": self.acquisition_exception_approval,
        }


@dataclass(frozen=True, slots=True)
class Line:
    code: str
    group: CostGroup
    amount: Money
    verification: Verification


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: Scenario
    gross_revenue: Money
    vat: Money
    revenue_ex_vat: Money
    lines: tuple[Line, ...]
    gross_margin: Money
    contribution_margin: Money
    net_operating_profit: Money
    profit_per_unit: Money

    def to_json(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario.value,
            "gross_revenue": self.gross_revenue.to_json(),
            "vat": self.vat.to_json(),
            "revenue_ex_vat": self.revenue_ex_vat.to_json(),
            "lines": [{"code": ln.code, "group": ln.group.value, "amount": ln.amount.to_json(),
                       "verification": ln.verification.value} for ln in self.lines],
            "gross_margin": self.gross_margin.to_json(),
            "contribution_margin": self.contribution_margin.to_json(),
            "net_operating_profit": self.net_operating_profit.to_json(),
            "profit_per_unit": self.profit_per_unit.to_json(),
        }


@dataclass(frozen=True, slots=True)
class ProfitSnapshot:
    inputs: ProfitInput
    status: str  # COMPLETE | INCOMPLETE
    missing: tuple[str, ...]
    unit_cost_eur: Money | None
    results: dict[Scenario, ScenarioResult]
    gates: tuple[GateResult, ...]
    eligible: bool
    data_reliability: Decimal  # share of cost lines (+VAT, unit cost) that are VERIFIED
    rule_set_version: str
    formula_version: str
    inputs_hash: str
    computed_at: datetime
    tax_profit_note: str = TAX_PROFIT_NOTE
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def prudent(self) -> ScenarioResult | None:
        return self.results.get(Scenario.PRUDENT)

    def to_json(self) -> dict[str, Any]:
        return {
            "inputs": self.inputs.to_json(),
            "status": self.status,
            "missing": list(self.missing),
            "unit_cost_eur": self.unit_cost_eur.to_json() if self.unit_cost_eur else None,
            "results": {k.value: v.to_json() for k, v in self.results.items()},
            "gates": [g.to_json() for g in self.gates],
            "eligible": self.eligible,
            "data_reliability": str(self.data_reliability),
            "rule_set_version": self.rule_set_version,
            "formula_version": self.formula_version,
            "inputs_hash": self.inputs_hash,
            "computed_at": self.computed_at.isoformat(),
            "tax_profit_note": self.tax_profit_note,
            "warnings": list(self.warnings),
        }


def _unit_cost_eur(inp: ProfitInput, rules: RuleSet) -> Money:
    if inp.unit_cost.currency == "EUR":
        # BR-005 margin applies only to converted amounts
        return inp.unit_cost
    assert inp.fx is not None
    if inp.fx.base != inp.unit_cost.currency or inp.fx.quote != "EUR":
        raise ValueError("fx rate does not convert unit cost currency to EUR")
    return inp.fx.convert_cost(inp.unit_cost, rules.fx_safety_margin)


def calculate(inp: ProfitInput, rules: RuleSet, computed_at: datetime) -> ProfitSnapshot:
    """Compute a ProfitSnapshot. Pure: same inputs + rules -> same result."""
    if computed_at.tzinfo is None:
        raise ValueError("computed_at must be timezone-aware")
    gates: list[GateResult] = []
    warnings: list[str] = []

    # -- completeness (BR-004) ------------------------------------------------
    provided = {c.code: c for c in inp.costs}
    missing = sorted(
        [code for code in REQUIRED_COSTS if code != "product"
         and (code not in provided or provided[code].is_missing)]
        + [c.code for c in inp.costs if c.is_missing and c.code not in REQUIRED_COSTS]
    )
    if inp.unit_cost_provenance.verification is Verification.MISSING:
        missing.append("product")
    if inp.vat_provenance.verification is Verification.MISSING:
        missing.append("vat_rate")
    if inp.fx is not None and inp.fx.provenance.verification is Verification.MISSING:
        missing.append("fx_rate")
    missing = sorted(set(missing))
    complete = not missing
    gates.append(GateResult(
        "BR-004", complete,
        "Tutti i costi richiesti sono dichiarati" if complete
        else "Calcolo INCOMPLETO: costi mancanti " + ", ".join(missing),
        {"missing": missing},
    ))

    # -- acquisition cap (BR-001 / BR-002 / BR-005) --------------------------
    unit_cost_eur: Money | None = None
    if "product" not in missing and "fx_rate" not in missing:
        unit_cost_eur = _unit_cost_eur(inp, rules)
        within = unit_cost_eur <= rules.max_unit_cost
        excepted = (not within) and bool(inp.acquisition_exception_approval)
        gates.append(GateResult(
            "BR-001", within or excepted,
            (f"Costo unitario {unit_cost_eur} entro il limite {rules.max_unit_cost}" if within
             else f"Costo unitario {unit_cost_eur} oltre il limite {rules.max_unit_cost}"
             + (" (eccezione approvata)" if excepted else " - solo ricerca")),
            {"unit_cost_eur": unit_cost_eur.to_json(), "cap": rules.max_unit_cost.to_json(),
             "fx_margin_applied": inp.unit_cost.currency != "EUR",
             "exception_approval": inp.acquisition_exception_approval},
        ))
        if excepted:
            warnings.append("BR-002: prodotto oltre il limite di acquisto con eccezione approvata")
    else:
        gates.append(GateResult("BR-001", False, "Costo unitario non disponibile", {}))

    # -- scenarios -----------------------------------------------------------
    results: dict[Scenario, ScenarioResult] = {}
    if complete:
        assert unit_cost_eur is not None
        product = CostComponent.per_unit("product", CostGroup.COGS, inp.unit_cost_provenance,
                                         unit_cost_eur)
        components = (product, *inp.costs)
        gross = inp.price_gross
        revenue_ex_vat = gross.divide(Decimal(1) + inp.vat_rate, rounding=ROUND_HALF_UP)
        vat = gross - revenue_ex_vat
        for sc in SCENARIOS:
            lines = tuple(
                Line(c.code, c.group, c.amount(sc, inp.pack_size, gross), c.provenance.verification)
                for c in components
            )

            def group_sum(g: CostGroup, lines: tuple[Line, ...] = lines) -> Money:
                return sum((ln.amount for ln in lines if ln.group is g), Money.zero())

            gm = revenue_ex_vat - group_sum(CostGroup.COGS)
            cm = gm - group_sum(CostGroup.CONTRIBUTION)
            np_ = cm - group_sum(CostGroup.OPERATING)
            # per-unit figure for display, rounded towards -inf (never flattering)
            per_unit = Money(np_.cents // inp.pack_size, np_.currency)
            results[sc] = ScenarioResult(sc, gross, vat, revenue_ex_vat, lines, gm, cm, np_,
                                         per_unit)

        # -- minimum profit (BR-010 / BR-011 / BR-014) ------------------------
        prudent = results[Scenario.PRUDENT]
        required = rules.min_profit_for_pack(inp.pack_size)
        ok = prudent.net_operating_profit >= required
        gates.append(GateResult(
            "BR-010", ok,
            (f"Profitto prudenziale {prudent.net_operating_profit} >= minimo {required}" if ok
             else f"Profitto prudenziale {prudent.net_operating_profit} sotto il minimo {required}"),
            {"pack_size": inp.pack_size, "required": required.to_json(),
             "prudent_profit": prudent.net_operating_profit.to_json(),
             "central_profit": results[Scenario.CENTRAL].net_operating_profit.to_json()},
        ))
        if inp.price_gross.divide(inp.pack_size) < rules.target_unit_price:
            warnings.append("BR-003: prezzo per unità sotto l'obiettivo")
    else:
        gates.append(GateResult("BR-010", False, "Profitto non verificabile: calcolo incompleto",
                                {"missing": missing}))

    # -- data reliability ----------------------------------------------------
    provs = [c.provenance for c in inp.costs] + [inp.unit_cost_provenance, inp.vat_provenance]
    verified = sum(1 for p in provs if p.verification is Verification.VERIFIED)
    reliability = (Decimal(verified) / Decimal(len(provs))).quantize(Decimal("0.0001"))

    return ProfitSnapshot(
        inputs=inp,
        status="COMPLETE" if complete else "INCOMPLETE",
        missing=tuple(missing),
        unit_cost_eur=unit_cost_eur,
        results=results,
        gates=tuple(gates),
        eligible=complete and all_passed(gates),
        data_reliability=reliability,
        rule_set_version=rules.version,
        formula_version=FORMULA_VERSION,
        inputs_hash=sha256_hex({"inputs": inp.to_json(), "rules": rules.to_json(),
                                "formula": FORMULA_VERSION}),
        computed_at=computed_at,
        warnings=tuple(warnings),
    )
