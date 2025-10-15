"""Structured logging helpers for project scripts."""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional


LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = LOG_DIR / "app.jsonl"


class JsonFormatter(logging.Formatter):
    """Simple JSON formatter for log records."""

    def format(self, record: logging.LogRecord) -> str:  # noqa: D401
        payload = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = record.stack_info
        return json.dumps(payload, ensure_ascii=False)


def setup_structured_logging(
    name: str,
    *,
    verbose: bool = False,
    log_file: Optional[Path] = None,
) -> logging.Logger:
    """Configure root logger if not already initialised and return module logger."""

    root_logger = logging.getLogger()
    if not getattr(root_logger, "_structured_configured", False):
        root_logger.setLevel(logging.INFO)
        target_file = log_file or DEFAULT_LOG_FILE
        target_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(target_file, encoding="utf-8")
        file_handler.setFormatter(JsonFormatter())
        root_logger.addHandler(file_handler)

        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setFormatter(
            logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
        )
        if verbose:
            root_logger.addHandler(stream_handler)
        else:
            # still add stream handler but lower level to WARNING to reduce noise
            stream_handler.setLevel(logging.WARNING)
            root_logger.addHandler(stream_handler)

        root_logger._structured_configured = True  # type: ignore[attr-defined]

    logger = logging.getLogger(name)
    if verbose:
        logger.setLevel(logging.INFO)
    return logger
