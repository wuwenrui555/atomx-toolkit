"""Per-study lock file: atomic acquire via O_CREAT|O_EXCL, conservative release."""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from atomx_toolkit.transfer.errors import LockHeldError

logger = logging.getLogger(__name__)

LOCK_FILENAME = ".atomx-toolkit.lock"


def acquire_lock(study_dir: Path, name_remote: str) -> Path:
    """Atomically create the lock file for a study. Raises LockHeldError if held.

    The directory is created if it does not yet exist (Phase 0 may also have
    created it; mkdir -p is idempotent).
    """
    study_dir.mkdir(parents=True, exist_ok=True)
    lock_path = study_dir / LOCK_FILENAME
    payload: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "name_remote": name_remote,
    }
    try:
        fd = os.open(
            str(lock_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except FileExistsError as exc:
        existing = read_lock(study_dir)
        if existing is None:
            # Race: someone deleted between O_EXCL fail and re-read.
            existing = {"hostname": "?", "pid": 0, "started_at": "?", "name_remote": "?"}
        raise LockHeldError(existing) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        # Best effort cleanup if we created the lock but failed to write payload.
        lock_path.unlink(missing_ok=True)
        raise
    return lock_path


def release_lock(study_dir: Path) -> None:
    """Remove the lock file. Logs WARNING but does not raise if already gone."""
    lock_path = study_dir / LOCK_FILENAME
    try:
        lock_path.unlink()
    except FileNotFoundError:
        logger.warning("lock %s already gone at release time", lock_path)


def read_lock(study_dir: Path) -> dict[str, Any] | None:
    """Return parsed lock contents or None if no lock present."""
    lock_path = study_dir / LOCK_FILENAME
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("could not parse lock %s: %s", lock_path, exc)
        return None
