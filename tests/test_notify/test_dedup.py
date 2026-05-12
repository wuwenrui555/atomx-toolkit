"""Tests for toolkit_error dedup state with timestamp normalization."""

from __future__ import annotations

import time
from pathlib import Path

from atomx_toolkit.notify.dedup import (
    DedupState,
    _normalize_for_dedup,  # pyright: ignore[reportPrivateUsage]
    should_send_toolkit_error,
)


def test_first_send_allowed(tmp_path: Path) -> None:
    state = DedupState(path=tmp_path / "dedup.json", cooldown_seconds=300)
    assert should_send_toolkit_error(state, "key1") is True


def test_within_cooldown_blocks(tmp_path: Path) -> None:
    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    assert should_send_toolkit_error(state, "k") is True
    assert should_send_toolkit_error(state, "k") is False


def test_after_cooldown_allows(tmp_path: Path) -> None:
    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=0)
    assert should_send_toolkit_error(state, "k") is True
    time.sleep(0.05)
    assert should_send_toolkit_error(state, "k") is True


def test_strips_timestamps_for_key() -> None:
    a = "2026-04-30T12:00:00 ERROR something failed"
    b = "2026-04-30T12:00:01 ERROR something failed"
    assert _normalize_for_dedup(a) == _normalize_for_dedup(b)
