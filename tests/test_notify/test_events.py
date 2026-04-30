"""Tests for TransferReport / BatchReport payload formatting (golden output)."""

from datetime import datetime, timedelta
from pathlib import Path

from atomx_toolkit.notify.events import (
    BatchItem,
    BatchReport,
    TransferReport,
    format_batch_report,
    format_transfer_report,
)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_format_transfer_report_success() -> None:
    report = TransferReport(
        name_remote="HCC_TMA006",
        name_local="HCC_TMA006_local",
        status="success",
        started_at=_ts("2026-04-30T12:00:00+00:00"),
        completed_at=_ts("2026-04-30T14:14:00+00:00"),
        file_count=1247,
        total_bytes=384 * 1024**3,
        failure_phase=None,
        failure_message=None,
        log_path=Path("/log/HCC_TMA006_local/HCC_TMA006_local.log"),
    )
    subject, body = format_transfer_report(report)
    assert "OK" in subject
    assert "HCC_TMA006_local" in subject
    assert "1247" in body
    assert "384.0 GiB" in body
    assert "/log/HCC_TMA006_local" in body


def test_format_transfer_report_failure() -> None:
    report = TransferReport(
        name_remote="HCC_TMA006",
        name_local="HCC_TMA006_local",
        status="failed",
        started_at=_ts("2026-04-30T12:00:00+00:00"),
        completed_at=_ts("2026-04-30T15:02:00+00:00"),
        file_count=None,
        total_bytes=None,
        failure_phase="md5_compare",
        failure_message="3 files mismatched",
        log_path=Path("/log/x.log"),
    )
    subject, body = format_transfer_report(report)
    assert "FAIL" in subject
    assert "md5_compare" in subject
    assert "3 files mismatched" in body


def test_format_batch_report() -> None:
    report = BatchReport(
        jobs_tsv=Path("/tmp/jobs.tsv"),
        started_at=_ts("2026-04-30T08:00:00+00:00"),
        completed_at=_ts("2026-04-30T18:30:00+00:00"),
        items=[
            BatchItem(
                name_remote="r1",
                name_local="loc1",
                status="succeeded",
                duration=timedelta(hours=2),
                failure_message=None,
            ),
            BatchItem(
                name_remote="r2",
                name_local="loc2",
                status="failed",
                duration=timedelta(hours=1),
                failure_message="md5 mismatch",
            ),
            BatchItem(
                name_remote="r3",
                name_local="loc3",
                status="skipped_locked",
                duration=None,
                failure_message="lock from h pid 1 at 2026-04-29T22:00:00Z",
            ),
        ],
    )
    subject, body = format_batch_report(report)
    assert "batch" in subject.lower()
    assert "loc1" in body
    assert "loc2" in body
    assert "loc3" in body
    assert "md5 mismatch" in body


def test_humanize_bytes_zero() -> None:
    from atomx_toolkit.notify.events import _humanize_bytes  # pyright: ignore[reportPrivateUsage]

    assert _humanize_bytes(0) == "0 B"


def test_humanize_bytes_kib_mib_gib() -> None:
    from atomx_toolkit.notify.events import _humanize_bytes  # pyright: ignore[reportPrivateUsage]

    assert _humanize_bytes(1024) == "1.0 KiB"
    assert _humanize_bytes(1024**2) == "1.0 MiB"
    assert _humanize_bytes(1024**3) == "1.0 GiB"
