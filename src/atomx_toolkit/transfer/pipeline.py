"""Per-study transfer pipeline: 6 phases + entry guard, with atomic file writes
and resume on partial state.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    RemoteListInconsistent,
)
from atomx_toolkit.transfer.lock import (
    acquire_lock,
    release_lock,
)
from atomx_toolkit.transfer.md5 import (
    assert_md5sum_available,
    compare_md5_files,
    compute_md5_tree,
    write_md5_file,
)
from atomx_toolkit.transfer.sftp import SftpClient

logger = logging.getLogger(__name__)


PipelineStatus = Literal["success", "skipped_already_complete"]


@dataclass(frozen=True)
class PipelineResult:
    name_remote: str
    name_local: str
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime
    file_count: int | None = None
    total_bytes: int | None = None
    log_path: Path | None = None


def run_pipeline(
    *,
    host: str,
    port: int = 22,
    user: str,
    password: str,
    remote_root: str,
    name_remote: str,
    name_local: str,
    log_root: Path,
    backup_root: Path,
) -> PipelineResult:
    """Run the per-study pipeline. Raises TransferError subclasses on failure."""
    started_at = datetime.now(UTC)
    log_dir = log_root / name_local
    backup_dir = backup_root / name_local
    index_dir = log_dir / "index"
    path_dir = log_dir / "path"
    md5_dir = log_dir / "md5sum"
    primary = backup_dir / "AtoMx"
    secondary = backup_dir / "AtoMx_copy"

    # Guard: if a previous run completed successfully, skip everything.
    pass_file = index_dir / "md5sum_pass"
    if pass_file.exists():
        logger.info("study %s already complete; skipping", name_local)
        return PipelineResult(
            name_remote=name_remote,
            name_local=name_local,
            status="skipped_already_complete",
            started_at=started_at,
            completed_at=datetime.now(UTC),
        )

    assert_md5sum_available()

    # Phase 0: mkdir
    for d in (index_dir, path_dir, md5_dir, primary, secondary):
        d.mkdir(parents=True, exist_ok=True)

    # Acquire lock atomically. Raises LockHeldError on conflict.
    acquire_lock(backup_dir, name_remote=name_remote)

    file_count = 0
    total_bytes = 0
    try:
        with SftpClient(host=host, port=port, user=user, password=password) as client:
            remote_dir = _join_remote(remote_root, name_remote)

            # Phase 1: list twice and compare
            remote_fs_1 = sorted(client.walk_files(remote_dir))
            remote_fs_2 = sorted(client.walk_files(remote_dir))
            if set(remote_fs_1) != set(remote_fs_2):
                _touch(index_dir / "path_fail")
                raise RemoteListInconsistent(
                    f"remote file list differs across two attempts for {remote_dir}"
                )
            (path_dir / "path_1.txt").write_text(
                "\n".join(remote_fs_1) + ("\n" if remote_fs_1 else "")
            )
            (path_dir / "path_2.txt").write_text(
                "\n".join(remote_fs_2) + ("\n" if remote_fs_2 else "")
            )
            _touch(index_dir / "path_pass")

            file_count = len(remote_fs_1)
            if file_count == 0:
                logger.warning(
                    "study %s has no files on the remote (typo'd name? deleted study?)",
                    name_remote,
                )

            # Phase 2: download to AtoMx/
            _download_all(client, remote_dir, remote_fs_1, primary)
            # Phase 3: download to AtoMx_copy/
            _download_all(client, remote_dir, remote_fs_1, secondary)

        # Phase 4: md5 of AtoMx/
        md5_dict_1 = compute_md5_tree(primary)
        write_md5_file(md5_dict_1, md5_dir / "md5sum_1.txt")
        # Phase 5: md5 of AtoMx_copy/
        md5_dict_2 = compute_md5_tree(secondary)
        write_md5_file(md5_dict_2, md5_dir / "md5sum_2.txt")

        # Phase 6: compare
        cmp = compare_md5_files(
            md5_dir / "md5sum_1.txt",
            md5_dir / "md5sum_2.txt",
            md5_dir / "md5sum_diff.csv",
        )
        if not cmp.all_match:
            _touch(index_dir / "md5sum_fail")
            raise IntegrityError(
                f"md5 comparison failed: {cmp.mismatched} mismatched, "
                f"{cmp.missing_in_1} missing in 1, {cmp.missing_in_2} missing in 2"
            )

        shutil.rmtree(secondary)
        completed_at = datetime.now(UTC)
        pass_file.write_text(completed_at.isoformat(timespec="seconds"))
        for p in primary.rglob("*"):
            if p.is_file():
                total_bytes += p.stat().st_size

        return PipelineResult(
            name_remote=name_remote,
            name_local=name_local,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            file_count=file_count,
            total_bytes=total_bytes,
        )
    finally:
        release_lock(backup_dir)


def _join_remote(root: str, name: str) -> str:
    if not root.endswith("/"):
        root = root + "/"
    return root + name


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _download_all(
    client: SftpClient,
    remote_dir: str,
    remote_files: list[str],
    local_dir: Path,
) -> None:
    """Download each remote file to local_dir, with size-match resume."""
    remote_dir_with_slash = (
        remote_dir if remote_dir.endswith("/") else remote_dir + "/"
    )
    for remote in remote_files:
        if not remote.startswith(remote_dir_with_slash):
            # remote_dir itself is a file? skip
            continue
        rel = remote[len(remote_dir_with_slash) :]
        local = local_dir / rel
        if local.exists():
            try:
                remote_size = client.stat_size(remote)
            except Exception as exc:
                logger.warning("could not stat remote %s: %s", remote, exc)
                local.unlink(missing_ok=True)
            else:
                if local.stat().st_size == remote_size:
                    logger.debug("skipping %s (size matches)", rel)
                    continue
                logger.info("re-downloading %s (size mismatch)", rel)
                local.unlink(missing_ok=True)
        # Stale .part?
        part = local.with_suffix(local.suffix + ".part")
        if part.exists():
            part.unlink()
        client.download_file(remote, local)
