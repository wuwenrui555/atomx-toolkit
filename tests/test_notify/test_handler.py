"""Tests for the toolkit_error logging handler."""

import logging
from pathlib import Path
from unittest.mock import MagicMock

from atomx_toolkit.notify.handler import ToolkitErrorHandler
from atomx_toolkit.notify.send import DedupState


def test_handler_dispatches_on_warning(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.warning("disk almost full at /var")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 1
    _args, kwargs = sender.call_args
    assert "disk almost full" in kwargs["body"]


def test_handler_does_not_fire_on_info(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler_info")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.info("nothing wrong")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 0


def test_handler_dedup_suppresses_repeat(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler_dup")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.warning("same message")
        logger.warning("same message")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 1
