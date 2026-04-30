"""Centralized logging setup for the CLI."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s | %(message)s"


def setup_logging(log_path: Path, *, verbose: int) -> None:
    """Configure root logger: file handler (always INFO) + console handler (level by -v count).

    verbose: 0 -> WARNING, 1 -> INFO, 2+ -> DEBUG.
    Quiets paramiko to WARNING regardless of verbose level.
    Idempotent: safe to call multiple times; existing atomx file handlers are removed first.
    """
    log_path.parent.mkdir(parents=True, exist_ok=True)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    # Remove any prior file handlers we previously installed (idempotent re-call).
    for h in list(root.handlers):
        if isinstance(h, logging.FileHandler) and getattr(h, "_atomx_managed", False):
            root.removeHandler(h)
            h.close()

    file_handler = logging.FileHandler(log_path, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    file_handler._atomx_managed = True  # type: ignore[attr-defined]
    root.addHandler(file_handler)

    # Console handler -- only install one; otherwise just adjust its level.
    console_level = (
        logging.WARNING if verbose <= 0 else (logging.INFO if verbose == 1 else logging.DEBUG)
    )
    console_present = any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    )
    if not console_present:
        ch = logging.StreamHandler()
        ch.setLevel(console_level)
        ch.setFormatter(logging.Formatter(_LOG_FORMAT))
        root.addHandler(ch)
    else:
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(console_level)

    logging.getLogger("paramiko").setLevel(logging.WARNING)


def batch_log_path(log_root: Path) -> Path:
    """Compute the batch-run log path with UTC timestamp."""
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    return log_root / "_batch" / f"batch_{ts}.log"
