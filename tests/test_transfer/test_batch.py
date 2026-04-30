"""Tests for jobs.tsv parsing, batch execution, and plan dry-run."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import atomx_toolkit.transfer.batch as batch_module
from atomx_toolkit.transfer.batch import (
    BatchPlan,
    JobsTsvError,
    classify_jobs,
    parse_jobs_tsv,
    run_batch,
)
from atomx_toolkit.transfer.errors import LockHeldError
from atomx_toolkit.transfer.lock import LOCK_FILENAME
from atomx_toolkit.transfer.pipeline import PipelineResult


def _write(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


# ---- parse_jobs_tsv ----


def test_parse_simple(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "remoteA\tlocalA\nremoteB\tlocalB\n")
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        "# header\n\nremoteA\tlocalA\n  # indented comment\nremoteB\tlocalB\n",
    )
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_tolerates_bom(tmp_path: Path) -> None:
    p = tmp_path / "j.tsv"
    p.write_bytes(b"\xef\xbb\xbfremoteA\tlocalA\n")
    assert parse_jobs_tsv(p) == [("remoteA", "localA")]


def test_parse_accepts_arbitrary_whitespace(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "remoteA    localA\nremoteB\t\tlocalB\n")
    assert parse_jobs_tsv(p) == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_empty_after_filter_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "# only comments\n\n")
    with pytest.raises(JobsTsvError, match="empty"):
        parse_jobs_tsv(p)


def test_parse_one_field_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "only_one_column\n")
    with pytest.raises(JobsTsvError, match="line 1"):
        parse_jobs_tsv(p)


def test_parse_three_fields_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "a\tb\tc\n")
    with pytest.raises(JobsTsvError, match="line 1"):
        parse_jobs_tsv(p)


def test_parse_duplicate_local_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "r1\tlocal\nr2\tlocal\n")
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)


# ---- classify_jobs ----


def test_classify_pending_when_no_state(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.pending == [("r", "loc")]
    assert plan.complete_already == []
    assert plan.skipped_locked == []


def test_classify_complete_already(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    pf = log_root / "loc" / "index" / "md5sum_pass"
    pf.parent.mkdir(parents=True)
    pf.write_text("2026-01-01T00:00:00+00:00")
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.complete_already and plan.complete_already[0][0] == "r"
    assert plan.pending == []


def test_classify_skipped_locked(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    lf = backup_root / "loc" / LOCK_FILENAME
    lf.parent.mkdir(parents=True)
    lf.write_text(
        json.dumps(
            {
                "hostname": "h",
                "pid": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
                "name_remote": "r",
            }
        )
    )
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.skipped_locked and plan.skipped_locked[0][0] == "r"
    assert plan.pending == []


# ---- run_batch ----


def _make_fake_pipeline(behaviors: list[object]) -> tuple[object, dict[str, int]]:
    """Build a fake run_pipeline that consumes one behavior per call.

    behaviors[i] is one of: "success", or an Exception/BaseException instance to raise.
    """
    call_count = {"n": 0}

    def fake(
        *,
        name_remote: str,
        name_local: str,
        **_kw: object,
    ) -> PipelineResult:
        idx = call_count["n"]
        call_count["n"] += 1
        b = behaviors[idx]
        if b == "success":
            now = datetime.now(UTC)
            return PipelineResult(
                name_remote=name_remote,
                name_local=name_local,
                status="success",
                started_at=now,
                completed_at=now,
                file_count=0,
                total_bytes=0,
            )
        assert isinstance(b, BaseException)
        raise b

    return fake, call_count


def _run_batch_args(tmp_path: Path) -> dict[str, object]:
    return {
        "host": "h",
        "port": 22,
        "user": "u",
        "password": "p",
        "remote_root": "/remote",
        "log_root": tmp_path / "log",
        "backup_root": tmp_path / "backup",
        "jobs_tsv_path": tmp_path / "jobs.tsv",
    }


def test_run_batch_continues_after_lock_held(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = [("r1", "l1"), ("r2", "l2"), ("r3", "l3")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, call_count = _make_fake_pipeline(
        [
            "success",
            LockHeldError(
                {
                    "hostname": "other",
                    "pid": 42,
                    "started_at": "2026-01-01T00:00:00+00:00",
                }
            ),
            "success",
        ]
    )
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    assert call_count["n"] == 3
    assert [i.status for i in result.items] == [
        "succeeded",
        "skipped_locked",
        "succeeded",
    ]
    assert [i.name_local for i in result.items] == ["l1", "l2", "l3"]
    # Lock-held item gets the exception's message as failure_message.
    assert result.items[1].failure_message is not None
    assert "lock held by other" in result.items[1].failure_message


def test_run_batch_aborts_on_keyboard_interrupt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = [("r1", "l1"), ("r2", "l2"), ("r3", "l3"), ("r4", "l4")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, call_count = _make_fake_pipeline(
        [
            "success",
            KeyboardInterrupt(),
            # Remaining entries should never be consumed.
            "success",
            "success",
        ]
    )
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    assert call_count["n"] == 2
    assert [i.status for i in result.items] == [
        "succeeded",
        "failed",
        "failed",
        "failed",
    ]
    assert result.items[1].failure_message == "interrupted"
    assert result.items[2].failure_message == "not run, batch aborted"
    assert result.items[3].failure_message == "not run, batch aborted"


def test_run_batch_continues_after_other_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    jobs = [("r1", "l1"), ("r2", "l2"), ("r3", "l3")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, call_count = _make_fake_pipeline(
        ["success", ValueError("boom"), "success"]
    )
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    assert call_count["n"] == 3
    assert [i.status for i in result.items] == ["succeeded", "failed", "succeeded"]
    assert result.items[1].failure_message == "boom"


def test_run_batch_includes_pre_scan_items(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"

    # complete_already: marker file must exist for _describe_lock to be skipped
    # (only matters for skipped_locked) but classify needs md5sum_pass present too;
    # here we pass plan directly so the file isn't required, but we create it for
    # realism / future-proofing.
    pf = log_root / "lc" / "index" / "md5sum_pass"
    pf.parent.mkdir(parents=True)
    pf.write_text("2026-01-01T00:00:00+00:00")

    # skipped_locked: real lock file so _describe_lock reads contents.
    lf = backup_root / "ls" / LOCK_FILENAME
    lf.parent.mkdir(parents=True)
    lf.write_text(
        json.dumps(
            {
                "hostname": "host-x",
                "pid": 99,
                "started_at": "2026-01-01T00:00:00+00:00",
                "name_remote": "rs",
            }
        )
    )

    jobs = [("rc", "lc"), ("rs", "ls"), ("rp", "lp")]
    plan = BatchPlan(
        complete_already=[("rc", "lc")],
        skipped_locked=[("rs", "ls")],
        pending=[("rp", "lp")],
    )
    fake, call_count = _make_fake_pipeline(["success"])
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    args = _run_batch_args(tmp_path)
    args["log_root"] = log_root
    args["backup_root"] = backup_root
    result = run_batch(jobs, plan=plan, **args)  # type: ignore[arg-type]

    assert call_count["n"] == 1
    assert [i.status for i in result.items] == [
        "complete_already",
        "skipped_locked",
        "succeeded",
    ]
    assert [i.name_local for i in result.items] == ["lc", "ls", "lp"]
    # complete_already pre-scan item carries no failure_message.
    assert result.items[0].failure_message is None
    # skipped_locked pre-scan item gets the lock description (not the cosmetic fallback).
    msg = result.items[1].failure_message
    assert msg is not None
    assert "host-x" in msg and "99" in msg
