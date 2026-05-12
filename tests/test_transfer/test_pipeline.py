"""Tests for the per-study transfer pipeline."""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path

import pytest

import atomx_toolkit.transfer.pipeline as pipeline_module
from atomx_toolkit.transfer.errors import (
    IntegrityError,
    LockHeldError,
    RemoteListInconsistent,
    TransferError,
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

    def corrupt_second(self: sftp_module.SftpClient, remote: str, local: Path) -> None:
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


def test_phase1_list_inconsistency_raises(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the remote returns different file sets across two listdir calls,
    pipeline must raise RemoteListInconsistent and write index/path_fail."""
    seed_remote(sftp_server, {"study/a.txt": b"x", "study/b.txt": b"y"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"

    # Patch SftpClient.walk_files to return DIFFERENT sets on consecutive calls.
    from atomx_toolkit.transfer import sftp as sftp_module

    call_count = {"n": 0}

    def flaky_walk(self: sftp_module.SftpClient, root: str):
        call_count["n"] += 1
        if call_count["n"] == 1:
            yield "/study/a.txt"
            yield "/study/b.txt"
        else:
            # Second call returns a different set
            yield "/study/a.txt"
            # b.txt missing intentionally

    monkeypatch.setattr(sftp_module.SftpClient, "walk_files", flaky_walk)

    with pytest.raises(RemoteListInconsistent):
        _run(sftp_server, log_root, backup_root, "study", "study_local")

    # path_fail marker present, path_pass absent
    assert (log_root / "study_local" / "index" / "path_fail").exists()
    assert not (log_root / "study_local" / "index" / "path_pass").exists()


def test_resume_after_phase2_interruption(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If a download fails mid-Phase-2, re-running the pipeline completes successfully."""
    seed_remote(
        sftp_server,
        {
            "study/a.txt": b"alpha",
            "study/b.txt": b"beta",
            "study/c.txt": b"gamma",
        },
    )
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"

    # Patch download_file to raise on the SECOND call of the FIRST run only.
    from atomx_toolkit.transfer import sftp as sftp_module

    original_download = sftp_module.SftpClient.download_file
    state = {"calls": 0, "raise_on_call": 2}

    def flaky_download(self: sftp_module.SftpClient, remote: str, local: Path) -> None:
        state["calls"] += 1
        if state["calls"] == state["raise_on_call"]:
            raise OSError("simulated network drop")
        original_download(self, remote, local)

    monkeypatch.setattr(sftp_module.SftpClient, "download_file", flaky_download)

    # First run should fail somewhere in Phase 2
    with pytest.raises((OSError, TransferError)):
        _run(sftp_server, log_root, backup_root, "study", "study_local")

    # Lock should be released by the finally block
    assert not (backup_root / "study_local" / LOCK_FILENAME).exists()

    # Restore download_file for the retry
    monkeypatch.setattr(sftp_module.SftpClient, "download_file", original_download)

    # Re-run completes
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    assert result.file_count == 3
    # All three files present in primary backup
    primary = backup_root / "study_local" / "AtoMx"
    assert (primary / "a.txt").exists()
    assert (primary / "b.txt").exists()
    assert (primary / "c.txt").exists()
    # No leftover .part files
    assert not list(primary.glob("**/*.part"))


def test_run_pipeline_emits_phase_logs(
    sftp_server: SftpServerFixture,
    tmp_path: Path,
    known_hosts_isolated: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Happy-path run emits an ordered sequence of phase-level INFO logs so
    operators tailing the batch log can see progress."""
    seed_remote(
        sftp_server,
        {
            "study/a.txt": b"hello",
            "study/sub/b.txt": b"world",
        },
    )
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    caplog.set_level(logging.INFO, logger="atomx_toolkit.transfer.pipeline")
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"

    info_msgs = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.INFO]
    expected_substrings = [
        "starting study",
        "phase 1: listing remote files",
        "files listed",
        "phase 2: downloading primary",
        "phase 3: downloading secondary",
        "phase 4: computing md5",
        "phase 5: computing md5",
        "phase 6: comparing md5",
        "complete:",
    ]
    # Assert each substring appears, in order.
    idx = 0
    for needle in expected_substrings:
        while idx < len(info_msgs) and needle not in info_msgs[idx]:
            idx += 1
        assert idx < len(info_msgs), (
            f"missing INFO log containing {needle!r}; captured: {info_msgs}"
        )
        idx += 1


def test_download_all_emits_progress_every_n_files(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """_download_all emits an INFO `[N/total] progress in <dir>` line every
    PROGRESS_INTERVAL completed files plus a final line when total isn't a
    multiple of the interval.

    With PROGRESS_INTERVAL=2 and 5 files, expect logs at 2, 4, 5."""
    monkeypatch.setattr(pipeline_module, "PROGRESS_INTERVAL", 2)
    local_dir = tmp_path / "AtoMx"
    local_dir.mkdir()

    remote_dir = "/remote/study"
    remote_files = [f"{remote_dir}/f{i}.txt" for i in range(5)]

    download_calls: list[tuple[str, Path]] = []

    class FakeClient:
        def download_file(self, remote: str, local: Path) -> None:
            download_calls.append((remote, local))
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(b"x")

        def stat_size(self, remote: str) -> int:  # pragma: no cover - unused here
            return 1

    caplog.set_level(logging.INFO, logger="atomx_toolkit.transfer.pipeline")
    pipeline_module._download_all(  # pyright: ignore[reportPrivateUsage]
        FakeClient(),  # type: ignore[arg-type]
        remote_dir,
        remote_files,
        local_dir,
    )

    assert len(download_calls) == 5
    progress_msgs = [
        rec.getMessage()
        for rec in caplog.records
        if rec.levelno == logging.INFO and "progress in" in rec.getMessage()
    ]
    assert len(progress_msgs) == 3, f"expected 3 progress lines, got {progress_msgs}"
    assert "[2/5]" in progress_msgs[0]
    assert "[4/5]" in progress_msgs[1]
    assert "[5/5]" in progress_msgs[2]
    for msg in progress_msgs:
        assert "AtoMx" in msg
