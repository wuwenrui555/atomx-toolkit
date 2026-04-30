"""Tests for the study-level lock (atomic acquire, crash detection)."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from atomx_toolkit.transfer.errors import LockHeldError
from atomx_toolkit.transfer.lock import (
    LOCK_FILENAME,
    acquire_lock,
    read_lock,
    release_lock,
)


def test_acquire_creates_lock_file(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="study_x")
    lock_path = tmp_path / LOCK_FILENAME
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text())
    assert payload["name_remote"] == "study_x"
    assert payload["pid"] > 0
    assert "started_at" in payload
    # started_at is parseable ISO 8601
    datetime.fromisoformat(payload["started_at"])


def test_acquire_when_already_held_raises_lock_held_error(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    with pytest.raises(LockHeldError) as ei:
        acquire_lock(tmp_path, name_remote="y")
    assert ei.value.lock_content["name_remote"] == "x"


def test_release_removes_lock(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    release_lock(tmp_path)
    assert not (tmp_path / LOCK_FILENAME).exists()


def test_release_when_already_gone_logs_but_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Lock never created
    with caplog.at_level("WARNING"):
        release_lock(tmp_path)
    assert any("lock" in rec.message.lower() for rec in caplog.records)


def test_read_lock_returns_payload(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    payload = read_lock(tmp_path)
    assert payload is not None
    assert payload["name_remote"] == "x"


def test_read_lock_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_lock(tmp_path) is None


def test_acquire_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "subdir"
    acquire_lock(target, name_remote="x")
    assert (target / LOCK_FILENAME).exists()
