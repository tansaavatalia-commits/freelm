"""JSON-lines log files with size-based rotation; secrets are redacted before writing."""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..security.redact import redact

LOGGER_NAME = "genesis"
LOG_FILENAME = "genesis.log"
_LOCK = threading.Lock()


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
    """Attach a rotating JSON file handler to the ``genesis`` logger.

    Several cores of the same data folder in one process (the API thread and the
    worker thread of ``genesis serve``) share one reference-counted handler, so
    the log file is never opened twice (Windows cannot rotate a file held open).
    """
    logger = logging.getLogger(LOGGER_NAME)
    path = os.path.abspath(logs_dir / LOG_FILENAME)
    logger.setLevel(level)
    logger.propagate = False
    with _LOCK:
        for h in logger.handlers:
            if getattr(h, "genesis_owned", False) and getattr(h, "baseFilename", None) == path:
                h.genesis_refs += 1  # type: ignore[attr-defined]
                return logger, h
        for old in [h for h in logger.handlers if getattr(h, "genesis_owned", False)]:
            logger.removeHandler(old)
            old.close()
        logs_dir.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=max_bytes, backupCount=backups, encoding="utf-8", delay=True)
        handler.genesis_owned = True  # type: ignore[attr-defined]
        handler.genesis_refs = 1  # type: ignore[attr-defined]
        handler.setFormatter(JsonFormatter())
        logger.addHandler(handler)
        return logger, handler


def close_handler(handler: logging.Handler) -> None:
    with _LOCK:
        handler.genesis_refs = getattr(handler, "genesis_refs", 1) - 1  # type: ignore[attr-defined]
        if handler.genesis_refs > 0:  # type: ignore[attr-defined]
            return
        logging.getLogger(LOGGER_NAME).removeHandler(handler)
        handler.close()
