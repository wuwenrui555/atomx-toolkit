"""Smoke tests for the transfer exception hierarchy."""

import pytest

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    JobsTsvError,
    LockHeldError,
    RemoteListInconsistent,
    TransferError,
)


def test_all_subclasses_of_transfer_error_except_jobs_tsv() -> None:
    assert issubclass(RemoteListInconsistent, TransferError)
    assert issubclass(IntegrityError, TransferError)
    assert issubclass(LockHeldError, TransferError)
    # JobsTsvError is for batch input parsing, not pipeline failures
    assert not issubclass(JobsTsvError, TransferError)


def test_lock_held_error_carries_payload() -> None:
    payload = {"hostname": "h", "pid": 1, "started_at": "x", "name_remote": "y"}
    err = LockHeldError(payload)
    assert err.lock_content == payload
    assert "h" in str(err)
    assert "1" in str(err)


def test_transfer_error_can_be_raised() -> None:
    with pytest.raises(TransferError):
        raise IntegrityError("md5 mismatch on 3 files")
