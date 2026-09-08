"""
Application logging (Phase 1 §38). Two rotating log files:
  logs/application.log — INFO and above, everything
  logs/error.log       — ERROR and above only

Called once from main.py at startup. Service-layer code should generally
raise ApplicationError subclasses (caught and shown politely by the UI)
rather than logging directly — this setup exists mainly to capture
unexpected exceptions and low-level diagnostics, not routine business
events (those belong in the audit log, not the text log).
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from app.config.settings import LOG_DIR

_MAX_BYTES = 5 * 1024 * 1024  # 5 MB per file
_BACKUP_COUNT = 5


def configure_logging() -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if root_logger.handlers:
        return  # already configured (e.g. re-entrant call) — don't duplicate handlers

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    app_handler = RotatingFileHandler(
        LOG_DIR / "application.log", maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    app_handler.setLevel(logging.INFO)
    app_handler.setFormatter(formatter)
    root_logger.addHandler(app_handler)

    error_handler = RotatingFileHandler(
        LOG_DIR / "error.log", maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
    )
    error_handler.setLevel(logging.ERROR)
    error_handler.setFormatter(formatter)
    root_logger.addHandler(error_handler)

    def _log_uncaught_exception(exc_type, exc_value, exc_traceback) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.error("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = _log_uncaught_exception
