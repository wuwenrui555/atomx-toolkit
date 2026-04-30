"""Tests for the per-study transfer pipeline."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    LockHeldError,
)
from atomx_toolkit.transfer.lock import LOCK_FILENAME
from atomx_toolkit.transfer.pipeline import PipelineResult, run_pipeline

from .conftest import SftpServerFixture, seed_remote


def _run(
    sftp_server: SftpServerFixture,
    log_root: Path,
    backup_root: Path,
    name_remote: str,
    name_local: str,
) -> PipelineResult:
    return run_pipeline(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
        remote_root="/",
        name_remote=name_remote,
        name_local=name_local,
        log_root=log_root,
        backup_root=backup_root,
    )


def test_happy_path(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(
        sftp_server,
        {
            "study/a.txt": b"hello",
            "study/sub/b.txt": b"world",
        },
    )
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    assert result.file_count == 2
    # md5sum_pass content is a parseable ISO 8601 timestamp
    pass_file = log_root / "study_local" / "index" / "md5sum_pass"
    datetime.fromisoformat(pass_file.read_text().strip())
    # AtoMx_copy was deleted, AtoMx remains
    assert (backup_root / "study_local" / "AtoMx" / "a.txt").exists()
    assert not (backup_root / "study_local" / "AtoMx_copy").exists()
    # Lock was released
    assert not (backup_root / "study_local" / LOCK_FILENAME).exists()


def test_guard_skips_already_complete(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    pass_file = log_root / "study_local" / "index" / "md5sum_pass"
    pass_file.parent.mkdir(parents=True)
    pass_file.write_text("2026-01-01T00:00:00+00:00")
    # No remote files seeded — pipeline should never connect
    result = _run(sftp_server, log_root, backup_root, "absent_remote", "study_local")
    assert result.status == "skipped_already_complete"
    assert result.file_count is None


def test_lock_held_aborts(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"x"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    study_backup = backup_root / "study_local"
    study_backup.mkdir(parents=True)
    (study_backup / LOCK_FILENAME).write_text(
        json.dumps(
            {
                "hostname": "other",
                "pid": 99999,
                "started_at": "2026-01-01T00:00:00+00:00",
                "name_remote": "earlier_run",
            }
        )
    )
    with pytest.raises(LockHeldError):
        _run(sftp_server, log_root, backup_root, "study", "study_local")


def test_phase1_zero_files_warns_but_succeeds(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_remote(sftp_server, {})
    # Create the empty 'study' dir on the remote
    (sftp_server.rootdir / "study").mkdir()
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    with caplog.at_level("WARNING"):
        result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    assert result.file_count == 0
    assert any("no files" in rec.message.lower() for rec in caplog.records)


def test_resume_skips_already_downloaded_files(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"hello", "study/b.txt": b"world"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    # Pre-stage a fully-correct local file in AtoMx/
    pre = backup_root / "study_local" / "AtoMx" / "a.txt"
    pre.parent.mkdir(parents=True)
    pre.write_bytes(b"hello")
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    # File must still exist with correct content
    assert pre.read_bytes() == b"hello"


def test_md5_mismatch_raises_integrity_error(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"original"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"

    # Patch sftp download_file in the second backup directory to corrupt content.
    from atomx_toolkit.transfer import sftp as sftp_module

    original_download = sftp_module.SftpClient.download_file
    call_count = {"n": 0}

    def corrupt_second(
        self: sftp_module.SftpClient, remote: str, local: Path
    ) -> None:
        original_download(self, remote, local)
        call_count["n"] += 1
        # The second download targets AtoMx_copy/; corrupt it
        if "AtoMx_copy" in str(local):
            local.write_bytes(b"corrupted")

    monkeypatch.setattr(sftp_module.SftpClient, "download_file", corrupt_second)

    with pytest.raises(IntegrityError):
        _run(sftp_server, log_root, backup_root, "study", "study_local")

    assert (log_root / "study_local" / "index" / "md5sum_fail").exists()
    assert (log_root / "study_local" / "md5sum" / "md5sum_diff.csv").exists()
