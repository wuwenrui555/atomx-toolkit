"""Tests for centralized logging setup."""

import logging
from pathlib import Path

from atomx_toolkit._logging import batch_log_path, setup_logging


def _cleanup_root() -> None:
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


def test_setup_logging_creates_file(tmp_path: Path) -> None:
    log_path = tmp_path / "x" / "y.log"
    setup_logging(log_path, verbose=0)
    try:
        logging.getLogger("test").warning("hello")
        assert log_path.exists()
        assert "hello" in log_path.read_text(encoding="utf-8")
    finally:
        _cleanup_root()


def test_setup_logging_verbose_levels(tmp_path: Path) -> None:
    setup_logging(tmp_path / "log.log", verbose=2)
    try:
        root = logging.getLogger()
        console_handlers: list[logging.Handler] = [
            h
            for h in root.handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert console_handlers
        assert console_handlers[0].level == logging.DEBUG
    finally:
        _cleanup_root()


def test_setup_logging_quiets_paramiko(tmp_path: Path) -> None:
    setup_logging(tmp_path / "log.log", verbose=2)
    try:
        assert logging.getLogger("paramiko").level == logging.WARNING
    finally:
        _cleanup_root()


def test_batch_log_path_format(tmp_path: Path) -> None:
    p = batch_log_path(tmp_path)
    assert p.parent == tmp_path / "_batch"
    assert p.name.startswith("batch_") and p.name.endswith(".log")
    assert "T" in p.name and "Z" in p.name
