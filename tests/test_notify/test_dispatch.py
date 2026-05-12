"""Tests for dispatch wiring: credential resolution, recipient lookup, send dispatch."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from atomx_toolkit.config import Config, NotifyConfig, PathsConfig, SftpConfig
from atomx_toolkit.notify.dispatch import (
    dispatch_batch_report,
    dispatch_transfer_report,
)
from atomx_toolkit.notify.events import BatchReport, TransferReport


def _make_config(recipients_dir: Path, *, enabled: bool = True) -> Config:
    return Config(
        sftp=SftpConfig(hostname="h", remote_root="/"),
        paths=PathsConfig(log_root=Path("/tmp/log"), backup_root=Path("/tmp/bk")),
        notify=NotifyConfig(recipients_dir=recipients_dir, enabled=enabled),
    )


def _make_transfer_report(tmp_path: Path) -> TransferReport:
    return TransferReport(
        name_remote="r",
        name_local="s",
        status="success",
        started_at=datetime(2026, 1, 1, 0, 0, 0),
        completed_at=datetime(2026, 1, 1, 0, 1, 0),
        file_count=1,
        total_bytes=1,
        failure_phase=None,
        failure_message=None,
        log_path=tmp_path / "log.txt",
    )


def _write_smtp_env(tmp_path: Path) -> Path:
    p = tmp_path / "smtp.env"
    p.write_text("ATOMX_SMTP_USER=u@example.com\nATOMX_SMTP_APP_PASSWORD=pw\n")
    return p


def _write_recipients(tmp_path: Path, event: str, *emails: str) -> Path:
    rdir = tmp_path / "recipients"
    rdir.mkdir(exist_ok=True)
    (rdir / f"{event}.txt").write_text("\n".join(emails) + "\n")
    return rdir


def test_dispatch_skipped_when_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    send = MagicMock()
    monkeypatch.setattr("atomx_toolkit.notify.dispatch.send_email", send)
    cfg = _make_config(tmp_path / "recipients", enabled=False)
    dispatch_transfer_report(_make_transfer_report(tmp_path), cfg=cfg, smtp_env=tmp_path / "x.env")
    send.assert_not_called()


def test_dispatch_skipped_when_creds_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    send = MagicMock()
    monkeypatch.setattr("atomx_toolkit.notify.dispatch.send_email", send)
    rdir = _write_recipients(tmp_path, "transfer_report", "alice@example.com")
    cfg = _make_config(rdir)
    dispatch_transfer_report(
        _make_transfer_report(tmp_path), cfg=cfg, smtp_env=tmp_path / "absent.env"
    )
    send.assert_not_called()


def test_dispatch_skipped_when_no_recipients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = MagicMock()
    monkeypatch.setattr("atomx_toolkit.notify.dispatch.send_email", send)
    cfg = _make_config(tmp_path / "missing-recipients-dir")
    dispatch_transfer_report(
        _make_transfer_report(tmp_path), cfg=cfg, smtp_env=_write_smtp_env(tmp_path)
    )
    send.assert_not_called()


def test_dispatch_transfer_calls_send_email(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = MagicMock()
    monkeypatch.setattr("atomx_toolkit.notify.dispatch.send_email", send)
    rdir = _write_recipients(tmp_path, "transfer_report", "alice@example.com")
    cfg = _make_config(rdir)
    dispatch_transfer_report(
        _make_transfer_report(tmp_path), cfg=cfg, smtp_env=_write_smtp_env(tmp_path)
    )
    send.assert_called_once()
    _args, kwargs = send.call_args
    assert kwargs["recipients"] == ["alice@example.com"]
    assert "OK" in kwargs["subject"]
    assert kwargs["creds"].user == "u@example.com"


def test_dispatch_batch_uses_batch_report_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    send = MagicMock()
    monkeypatch.setattr("atomx_toolkit.notify.dispatch.send_email", send)
    rdir = _write_recipients(tmp_path, "batch_report", "ops@example.com")
    cfg = _make_config(rdir)
    report = BatchReport(
        jobs_tsv=tmp_path / "j.tsv",
        started_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 1, 0, 1),
        items=[],
    )
    dispatch_batch_report(report, cfg=cfg, smtp_env=_write_smtp_env(tmp_path))
    send.assert_called_once()
    _args, kwargs = send.call_args
    assert kwargs["recipients"] == ["ops@example.com"]
