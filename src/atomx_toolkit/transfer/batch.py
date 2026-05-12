"""jobs.tsv parsing, study classification, sequential batch execution, dry-run plan."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from jianglab_name_standard import CosmxRunName, NameValidationError

from atomx_toolkit.transfer.errors import JobsTsvError, LockHeldError
from atomx_toolkit.transfer.lock import LOCK_FILENAME, read_lock
from atomx_toolkit.transfer.pipeline import run_pipeline

logger = logging.getLogger(__name__)


Job = tuple[str, str]  # (name_remote, name_local)


@dataclass(frozen=True)
class BatchPlan:
    complete_already: list[Job]
    skipped_locked: list[Job]
    pending: list[Job]


BatchItemStatus = Literal[
    "complete_already",
    "skipped_locked",
    "succeeded",
    "failed",
]


@dataclass(frozen=True)
class BatchItemResult:
    name_remote: str
    name_local: str
    status: BatchItemStatus
    duration: timedelta | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class BatchRunResult:
    jobs_tsv: Path
    started_at: datetime
    completed_at: datetime
    items: list[BatchItemResult] = field(default_factory=list[BatchItemResult])

    @property
    def any_failed(self) -> bool:
        return any(i.status == "failed" for i in self.items)

    @property
    def all_skipped_locked(self) -> bool:
        return bool(self.items) and all(i.status == "skipped_locked" for i in self.items)


def parse_jobs_tsv(path: Path) -> list[Job]:
    """Parse a 2-column whitespace-separated jobs file. See spec 4.7."""
    if not path.exists():
        raise JobsTsvError(f"jobs.tsv not found: {path}")
    text = path.read_text(encoding="utf-8-sig")  # tolerates BOM
    jobs: list[Job] = []
    seen_locals: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = re.split(r"\s+", stripped)
        if len(fields) != 2:
            raise JobsTsvError(
                f"{path} line {lineno}: expected 2 fields, got {len(fields)}: {raw!r}"
            )
        remote, local = fields[0], fields[1]
        if local in seen_locals:
            raise JobsTsvError(f"{path} line {lineno}: duplicate name_local {local!r}")
        try:
            CosmxRunName(local)
        except NameValidationError as exc:
            raise JobsTsvError(
                f"{path} line {lineno}: invalid name_local {local!r}: "
                f"[{exc.rule_id}] {exc.message} | hint: {exc.hint}"
            ) from exc
        seen_locals.add(local)
        jobs.append((remote, local))
    if not jobs:
        raise JobsTsvError(f"{path} is empty after filtering blanks/comments")
    return jobs


def classify_jobs(
    jobs: list[Job],
    *,
    log_root: Path,
    backup_root: Path,
) -> BatchPlan:
    """Classify each job by its on-disk state. Used by both batch and plan."""
    complete: list[Job] = []
    locked: list[Job] = []
    pending: list[Job] = []
    for job in jobs:
        _, name_local = job
        if (log_root / name_local / "index" / "md5sum_pass").exists():
            complete.append(job)
        elif (backup_root / name_local / LOCK_FILENAME).exists():
            locked.append(job)
        else:
            pending.append(job)
    return BatchPlan(complete_already=complete, skipped_locked=locked, pending=pending)


def run_batch(
    jobs: list[Job],
    *,
    plan: BatchPlan,
    host: str,
    port: int,
    user: str,
    password: str,
    remote_root: str,
    log_root: Path,
    backup_root: Path,
    jobs_tsv_path: Path,
) -> BatchRunResult:
    """Run pending items sequentially. Returns a BatchRunResult covering all items.

    KeyboardInterrupt aborts the whole batch (does not continue). Remaining
    pending items are appended as 'failed' with reason 'not run, batch aborted'.
    Per-item exceptions are caught and recorded; the next item still runs.
    """
    logger.info(
        "batch started: %d pending, %d complete_already, %d skipped_locked",
        len(plan.pending),
        len(plan.complete_already),
        len(plan.skipped_locked),
    )
    started_at = datetime.now(UTC)
    items: list[BatchItemResult] = []
    for job in plan.complete_already:
        items.append(
            BatchItemResult(name_remote=job[0], name_local=job[1], status="complete_already")
        )
    for job in plan.skipped_locked:
        items.append(
            BatchItemResult(
                name_remote=job[0],
                name_local=job[1],
                status="skipped_locked",
                failure_message=_describe_lock(backup_root / job[1]),
            )
        )
    aborted = False
    for idx, job in enumerate(plan.pending):
        if aborted:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message="not run, batch aborted",
                )
            )
            continue
        logger.info("starting study %d/%d: %s", idx + 1, len(plan.pending), job[1])
        item_start = datetime.now(UTC)
        try:
            result = run_pipeline(
                host=host,
                port=port,
                user=user,
                password=password,
                remote_root=remote_root,
                name_remote=job[0],
                name_local=job[1],
                log_root=log_root,
                backup_root=backup_root,
            )
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="succeeded" if result.status == "success" else "complete_already",
                    duration=datetime.now(UTC) - item_start,
                )
            )
        except LockHeldError as exc:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="skipped_locked",
                    failure_message=str(exc),
                )
            )
        except KeyboardInterrupt:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message="interrupted",
                    duration=datetime.now(UTC) - item_start,
                )
            )
            aborted = True
            logger.warning(
                "KeyboardInterrupt; aborting remaining %d items",
                len(plan.pending) - idx - 1,
            )
        except Exception as exc:
            logger.exception("study %s failed", job[1])
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message=str(exc),
                    duration=datetime.now(UTC) - item_start,
                )
            )
    completed_at = datetime.now(UTC)
    logger.info(
        "batch finished: %d succeeded, %d failed, %d complete_already, %d skipped_locked",
        sum(1 for i in items if i.status == "succeeded"),
        sum(1 for i in items if i.status == "failed"),
        sum(1 for i in items if i.status == "complete_already"),
        sum(1 for i in items if i.status == "skipped_locked"),
    )
    return BatchRunResult(
        jobs_tsv=jobs_tsv_path,
        started_at=started_at,
        completed_at=completed_at,
        items=items,
    )


def _describe_lock(study_backup_dir: Path) -> str:
    payload = read_lock(study_backup_dir)
    if payload is None:
        return "lock present (could not read contents)"
    return (
        f"lock from {payload.get('hostname', '?')} pid {payload.get('pid', '?')} "
        f"at {payload.get('started_at', '?')}"
    )
