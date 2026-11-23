"""Remove credentials from any text before it is logged, stored or shown."""

from __future__ import annotations

import re

REDACTED = "[REDACTED]"

# Known key formats of the providers GÉNESIS may use, plus generic bearer tokens.
_TOKEN_PATTERNS = (
    re.compile(r"sk-or-v1-[A-Za-z0-9]{16,}"),  # OpenRouter
    re.compile(r"sk-(?:proj-|ant-)?[A-Za-z0-9_\-]{20,}"),  # OpenAI-style
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google
    re.compile(r"gsk_[A-Za-z0-9]{20,}"),  # Groq
    re.compile(r"nvapi-[A-Za-z0-9_\-]{20,}"),  # NVIDIA NIM
    re.compile(r"csk-[A-Za-z0-9]{20,}"),  # Cerebras
    re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=\-]{12,}"),
)
# key=value, key: value and "key": "value" for secret-looking names.
_KEY_VALUE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|token|secret|password|passwd)\b"
    r"(\s*[=:]\s*|\"\s*:\s*\")([^\s\"'&,;]{6,})"
)


def redact(text: str) -> str:
    for pattern in _TOKEN_PATTERNS:
        text = pattern.sub(REDACTED, text)
    return _KEY_VALUE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", text)


def mask(secret: str) -> str:
    """Short display form of a secret: first and last 4 characters only."""
    return "****" if len(secret) < 12 else f"{secret[:4]}…{secret[-4:]}"
