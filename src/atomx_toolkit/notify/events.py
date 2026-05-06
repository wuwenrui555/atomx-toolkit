"""TransferReport / BatchReport dataclasses and plain-text email body formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from atomx_toolkit.transfer.batch import BatchItemResult

TransferStatus = Literal["success", "failed"]
BatchItemStatus = Literal["complete_already", "skipped_locked", "succeeded", "failed"]


@dataclass(frozen=True)
class TransferReport:
    name_remote: str
    name_local: str
    status: TransferStatus
    started_at: datetime
    completed_at: datetime
    file_count: int | None
    total_bytes: int | None
    failure_phase: str | None
    failure_message: str | None
    log_path: Path


@dataclass(frozen=True)
class BatchItem:
    name_remote: str
    name_local: str
    status: BatchItemStatus
    duration: timedelta | None
    failure_message: str | None

    @classmethod
    def from_result(cls, item: BatchItemResult) -> BatchItem:
        return cls(
            name_remote=item.name_remote,
            name_local=item.name_local,
            status=item.status,
            duration=item.duration,
            failure_message=item.failure_message,
        )


@dataclass(frozen=True)
class BatchReport:
    jobs_tsv: Path
    started_at: datetime
    completed_at: datetime
    items: list[BatchItem]


def format_transfer_report(r: TransferReport) -> tuple[str, str]:
    if r.status == "success":
        subject = f"[atomx-toolkit] OK: {r.name_local}"
        body = (
            f"study     : {r.name_local}\n"
            f"remote    : {r.name_remote}\n"
            f"files     : {r.file_count}\n"
            f"total     : {_humanize_bytes(r.total_bytes or 0)}\n"
            f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}\n"
            f"md5 check : pass ({r.file_count}/{r.file_count} match)\n"
            f"log       : {r.log_path}\n"
        )
        return subject, body
    subject = f"[atomx-toolkit] FAIL: {r.name_local} at {r.failure_phase}"
    body = (
        f"study     : {r.name_local}\n"
        f"remote    : {r.name_remote}\n"
        f"phase     : {r.failure_phase}\n"
        f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}\n"
        f"error     : {r.failure_message}\n"
        f"\n"
        f"log       : {r.log_path}\n"
    )
    log_tail = _tail_log(r.log_path, lines=30)
    if log_tail:
        body += f"\n--- last 30 lines of log ---\n{log_tail}\n"
    return subject, body


def format_batch_report(r: BatchReport) -> tuple[str, str]:
    succeeded = sum(1 for i in r.items if i.status == "succeeded")
    complete = sum(1 for i in r.items if i.status == "complete_already")
    locked = sum(1 for i in r.items if i.status == "skipped_locked")
    failed = sum(1 for i in r.items if i.status == "failed")
    subject = (
        f"[atomx-toolkit] batch: {succeeded} ok, {failed} fail, {complete} already, {locked} locked"
    )
    rows: list[str] = [
        f"jobs.tsv  : {r.jobs_tsv}",
        f"started   : {r.started_at.isoformat()}",
        f"finished  : {r.completed_at.isoformat()}",
        f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}",
        f"summary   : succeeded={succeeded} complete_already={complete} "
        f"skipped_locked={locked} failed={failed}",
        "",
        "items:",
    ]
    for item in r.items:
        line = f"  [{item.status:18s}] {item.name_local}"
        if item.duration is not None:
            line += f"  ({_humanize_duration(item.duration)})"
        if item.failure_message:
            line += f"  -- {item.failure_message}"
        rows.append(line)
    return subject, "\n".join(rows) + "\n"


def _humanize_bytes(n: int) -> str:
    if n == 0:
        return "0 B"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(n)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.1f} {units[idx]}" if idx > 0 else f"{int(size)} {units[idx]}"


def _humanize_duration(d: timedelta) -> str:
    total = int(d.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}min"
    if m:
        return f"{m}min {s:02d}s"
    return f"{s}s"


def _tail_log(path: Path, lines: int) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])
