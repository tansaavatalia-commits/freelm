"""JSON-lines log files with size-based rotation; secrets are redacted before writing."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..security.redact import redact

LOGGER_NAME = "genesis"
LOG_FILENAME = "genesis.log"


class JsonFormatter(logging.Formatter):
    """One JSON object per line; structured data goes in ``extra={"fields": {...}}``."""

    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        fields = getattr(record, "fields", None)
        if fields:
            entry["fields"] = fields
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        # Redact the serialized line so message, args, fields and tracebacks are all covered.
        return redact(json.dumps(entry, ensure_ascii=False, default=str))


def setup_logging(logs_dir: Path, level: str, max_bytes: int, backups: int) -> tuple[logging.Logger, logging.Handler]:
    """Attach a rotating JSON file handler to the ``genesis`` logger (replacing a previous one)."""
    logger = logging.getLogger(LOGGER_NAME)
    for old in [h for h in logger.handlers if getattr(h, "genesis_owned", False)]:
        logger.removeHandler(old)
        old.close()
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(
        logs_dir / LOG_FILENAME, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True
    )
    handler.genesis_owned = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    return logger, handler


def close_handler(handler: logging.Handler) -> None:
    logging.getLogger(LOGGER_NAME).removeHandler(handler)
    handler.close()
