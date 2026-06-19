"""
Logging setup shared by all commands.

Console gets human-readable colored-ish output (no extra deps, just
plain prefixes). The log file gets a rotating handler so it doesn't
grow forever, and uses a stable timestamped format for grepping later.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT_FILE = "%(asctime)s [%(levelname)s] %(message)s"
LOG_FORMAT_CONSOLE = "%(message)s"


def setup_logging(log_path: Path, verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger("fim")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()  # avoid duplicate handlers if called twice (e.g. in tests)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG if verbose else logging.INFO)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT_CONSOLE))
    logger.addHandler(console_handler)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    file_handler = RotatingFileHandler(
        log_path, maxBytes=5 * 1024 * 1024, backupCount=3
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(LOG_FORMAT_FILE))
    logger.addHandler(file_handler)

    return logger
