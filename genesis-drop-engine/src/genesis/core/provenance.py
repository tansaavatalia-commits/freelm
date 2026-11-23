"""Data provenance: every external value carries its source, time and verification status."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class Verification(StrEnum):
    VERIFIED = "VERIFIED"  # from an official source/API, timestamped
    ESTIMATED = "ESTIMATED"  # estimate with a declared method
    UNVERIFIED = "UNVERIFIED"  # unconfirmed value
    MISSING = "MISSING"  # no value available


@dataclass(frozen=True, slots=True)
class Provenance:
    source: str
    verification: Verification
    fetched_at: datetime | None = None
    note: str = ""

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise ValueError("provenance.source must not be empty")
        if self.fetched_at is not None and self.fetched_at.tzinfo is None:
            raise ValueError("provenance.fetched_at must be timezone-aware")

    @classmethod
    def missing(cls, source: str = "none") -> Provenance:
        return cls(source=source, verification=Verification.MISSING)

    def to_json(self) -> dict[str, str | None]:
        return {
            "source": self.source,
            "verification": self.verification.value,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
            "note": self.note,
        }
