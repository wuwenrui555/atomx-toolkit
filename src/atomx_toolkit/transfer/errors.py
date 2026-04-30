"""Exception hierarchy for the transfer subsystem."""

from __future__ import annotations

from typing import Any


class TransferError(Exception):
    """Base for all per-study pipeline failures."""


class RemoteListInconsistent(TransferError):
    """Phase 1 returned different file sets across two list attempts."""


class IntegrityError(TransferError):
    """Phase 6 detected a checksum mismatch or missing file."""


class LockHeldError(TransferError):
    """Pipeline entry found an existing .atomx-toolkit.lock."""

    def __init__(self, lock_content: dict[str, Any]) -> None:
        self.lock_content = lock_content
        super().__init__(
            f"lock held by {lock_content.get('hostname', '?')} "
            f"pid {lock_content.get('pid', '?')} "
            f"since {lock_content.get('started_at', '?')}"
        )


class JobsTsvError(Exception):
    """Failure parsing a jobs.tsv batch input file."""
