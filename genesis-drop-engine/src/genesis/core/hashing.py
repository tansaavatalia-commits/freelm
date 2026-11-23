"""Canonical JSON + SHA-256, used for snapshot input hashes and the audit hash chain."""

from __future__ import annotations

import hashlib
import json
from typing import Any


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def sha256_hex(data: Any) -> str:
    return hashlib.sha256(canonical_json(data).encode("utf-8")).hexdigest()
