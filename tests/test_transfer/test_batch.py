"""Tests for jobs.tsv parsing, batch execution, and plan dry-run."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

import pytest

import atomx_toolkit.transfer.batch as batch_module
from atomx_toolkit.transfer.batch import (
    BatchItemResult,
    BatchPlan,
    BatchRunResult,
    JobsTsvError,
    classify_jobs,
    parse_jobs_tsv,
    run_batch,
)
from atomx_toolkit.transfer.errors import IntegrityError, LockHeldError
from atomx_toolkit.transfer.lock import LOCK_FILENAME
from atomx_toolkit.transfer.pipeline import PipelineResult


def _write(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


def _local(suffix: str) -> str:
    """Return a CosmxRunName-conformant name_local for tests. Stable date/user."""
    return f"20260101_T_D_s{suffix}_v1-0-0"


# ---- parse_jobs_tsv ----


def test_parse_simple(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", f"remoteA\t{_local('A')}\nremoteB\t{_local('B')}\n")
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", _local("A")), ("remoteB", _local("B"))]


def test_parse_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        f"# header\n\nremoteA\t{_local('A')}\n  # indented comment\nremoteB\t{_local('B')}\n",
    )
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", _local("A")), ("remoteB", _local("B"))]


def test_parse_tolerates_bom(tmp_path: Path) -> None:
    p = tmp_path / "j.tsv"
    name = _local("A")
    p.write_bytes(b"\xef\xbb\xbfremoteA\t" + name.encode("utf-8") + b"\n")
    assert parse_jobs_tsv(p) == [("remoteA", name)]


def test_parse_accepts_arbitrary_whitespace(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        f"remoteA    {_local('A')}\nremoteB\t\t{_local('B')}\n",
    )
    assert parse_jobs_tsv(p) == [("remoteA", _local("A")), ("remoteB", _local("B"))]


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
    p = _write(tmp_path / "j.tsv", f"r1\t{_local('Dup')}\nr2\t{_local('Dup')}\n")
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)


def test_parse_rejects_invalid_name_local(tmp_path: Path) -> None:
    """name_local that does not match CosmxRunName raises JobsTsvError with
    line number, the bad name, the rule_id, and the jianglab hint."""
    p = _write(tmp_path / "j.tsv", "remoteA\tbad_name\n")
    with pytest.raises(JobsTsvError) as excinfo:
        parse_jobs_tsv(p)
    msg = str(excinfo.value)
    assert "line 1" in msg
    assert "bad_name" in msg
    assert "[R1]" in msg
    assert "hint:" in msg


def test_parse_duplicate_check_runs_before_validation(tmp_path: Path) -> None:
    """When a TSV has both a duplicate name_local AND an invalid one further
    down, the duplicate error wins (because the duplicate check runs first)."""
    p = _write(
        tmp_path / "j.tsv",
        f"r1\t{_local('A')}\nr2\t{_local('A')}\nr3\tbad_name\n",
    )
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)


def test_parse_valid_cosmx_name_local_passes(tmp_path: Path) -> None:
    """A canonical 5-field CosmxRunName parses fine."""
    name = "20260211_WW_ACLF_run1_v2-2-1"
    p = _write(tmp_path / "j.tsv", f"remoteA\t{name}\n")
    assert parse_jobs_tsv(p) == [("remoteA", name)]


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
    fake, call_count = _make_fake_pipeline(["success", ValueError("boom"), "success"])
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    assert call_count["n"] == 3
    assert [i.status for i in result.items] == ["succeeded", "failed", "succeeded"]
    assert result.items[1].failure_message == "boom"


def test_run_batch_includes_pre_scan_items(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_run_batch_emits_boundary_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """run_batch emits a `batch started:` line, one `starting study N/M:` line
    per pending item, and a final `batch finished:` summary line."""
    jobs = [("r1", "l1"), ("r2", "l2")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, _call_count = _make_fake_pipeline(["success", "success"])
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    caplog.set_level(logging.INFO, logger="atomx_toolkit.transfer.batch")
    run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    info_msgs = [rec.getMessage() for rec in caplog.records if rec.levelno == logging.INFO]
    assert any("batch started:" in m for m in info_msgs), info_msgs
    starting_msgs = [m for m in info_msgs if "starting study" in m]
    assert len(starting_msgs) == 2, info_msgs
    assert "1/2" in starting_msgs[0]
    assert "l1" in starting_msgs[0]
    assert "2/2" in starting_msgs[1]
    assert "l2" in starting_msgs[1]
    assert any("batch finished:" in m for m in info_msgs), info_msgs


# ---- new fields populated by run_batch ----


def _fake_pipeline_with_stats(file_count: int, total_bytes: int) -> object:
    """Fake run_pipeline that returns a successful PipelineResult with given stats."""

    def fake(
        *,
        name_remote: str,
        name_local: str,
        **_kw: object,
    ) -> PipelineResult:
        now = datetime.now(UTC)
        return PipelineResult(
            name_remote=name_remote,
            name_local=name_local,
            status="success",
            started_at=now,
            completed_at=now,
            file_count=file_count,
            total_bytes=total_bytes,
        )

    return fake


def test_run_batch_populates_new_fields_on_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful run populates started_at, completed_at, file_count, total_bytes."""
    jobs = [("r1", "l1")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    monkeypatch.setattr(batch_module, "run_pipeline", _fake_pipeline_with_stats(10, 12345))

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    item = result.items[0]
    assert item.status == "succeeded"
    assert item.started_at is not None
    assert item.completed_at is not None
    assert item.completed_at >= item.started_at
    assert item.file_count == 10
    assert item.total_bytes == 12345
    assert item.failure_phase is None
    assert item.failure_message is None


def test_run_batch_populates_failure_phase_on_exception(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Generic exception populates failure_phase=type-name and started/completed timestamps."""
    jobs = [("r1", "l1")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, _ = _make_fake_pipeline([IntegrityError("md5 mismatch")])
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    item = result.items[0]
    assert item.status == "failed"
    assert item.failure_phase == "IntegrityError"
    assert item.failure_message is not None
    assert "md5 mismatch" in item.failure_message
    assert item.started_at is not None
    assert item.completed_at is not None
    assert item.completed_at >= item.started_at
    assert item.file_count is None
    assert item.total_bytes is None


def test_run_batch_lock_held_leaves_new_fields_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """LockHeldError path: item did not run, so started_at/completed_at/file_count
    /total_bytes/failure_phase all stay None."""
    jobs = [("r1", "l1")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, _ = _make_fake_pipeline(
        [
            LockHeldError(
                {
                    "hostname": "other",
                    "pid": 42,
                    "started_at": "2026-01-01T00:00:00+00:00",
                }
            )
        ]
    )
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    item = result.items[0]
    assert item.status == "skipped_locked"
    assert item.started_at is None
    assert item.completed_at is None
    assert item.file_count is None
    assert item.total_bytes is None
    assert item.failure_phase is None


def test_run_batch_keyboard_interrupt_populates_phase_and_timestamps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """KeyboardInterrupt path: started_at/completed_at set, failure_phase='interrupted'.
    Subsequent aborted-tail items leave timestamps/phase as None."""
    jobs = [("r1", "l1"), ("r2", "l2")]
    plan = BatchPlan(complete_already=[], skipped_locked=[], pending=jobs)
    fake, _ = _make_fake_pipeline([KeyboardInterrupt(), "success"])
    monkeypatch.setattr(batch_module, "run_pipeline", fake)

    result = run_batch(jobs, plan=plan, **_run_batch_args(tmp_path))  # type: ignore[arg-type]

    # Item 0: the interrupted item.
    interrupted = result.items[0]
    assert interrupted.status == "failed"
    assert interrupted.failure_phase == "interrupted"
    assert interrupted.started_at is not None
    assert interrupted.completed_at is not None
    assert interrupted.completed_at >= interrupted.started_at

    # Item 1: the aborted-tail item (never ran).
    aborted = result.items[1]
    assert aborted.status == "failed"
    assert aborted.failure_message == "not run, batch aborted"
    assert aborted.started_at is None
    assert aborted.completed_at is None
    assert aborted.failure_phase is None


# ---- batch_cmd dispatches per-study transfer_report ----


def test_batch_cmd_dispatches_transfer_report_per_succeeded_or_failed_item(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """batch_cmd should dispatch a transfer_report exactly once per
    {succeeded, failed} item (skipping complete_already and skipped_locked),
    and one batch_report at the end."""
    from unittest.mock import MagicMock

    from typer.testing import CliRunner

    import atomx_toolkit.transfer.cli as transfer_cli_module
    from atomx_toolkit.transfer.cli import app

    # Build a fake BatchRunResult with one item of each status.
    now = datetime.now(UTC)
    fake_items = [
        BatchItemResult(
            name_remote="rA",
            name_local="20260101_T_D_sA_v1-0-0",
            status="succeeded",
            started_at=now,
            completed_at=now,
            file_count=3,
            total_bytes=999,
        ),
        BatchItemResult(
            name_remote="rB",
            name_local="20260101_T_D_sB_v1-0-0",
            status="failed",
            started_at=now,
            completed_at=now,
            failure_phase="IntegrityError",
            failure_message="md5 mismatch",
        ),
        BatchItemResult(
            name_remote="rC",
            name_local="20260101_T_D_sC_v1-0-0",
            status="complete_already",
        ),
        BatchItemResult(
            name_remote="rD",
            name_local="20260101_T_D_sD_v1-0-0",
            status="skipped_locked",
            failure_message="locked",
        ),
    ]
    fake_result = BatchRunResult(
        jobs_tsv=tmp_path / "jobs.tsv",
        started_at=now,
        completed_at=now,
        items=fake_items,
    )

    mock_dispatch_transfer = MagicMock()
    mock_dispatch_batch = MagicMock()

    def fake_run_batch(**_kw: object) -> BatchRunResult:
        return fake_result

    def fake_md5_available() -> None:
        return None

    monkeypatch.setattr(transfer_cli_module, "run_batch", fake_run_batch)
    monkeypatch.setattr(transfer_cli_module, "dispatch_transfer_report", mock_dispatch_transfer)
    monkeypatch.setattr(transfer_cli_module, "dispatch_batch_report", mock_dispatch_batch)
    monkeypatch.setattr(transfer_cli_module, "assert_md5sum_available", fake_md5_available)

    # Minimal config and credentials so batch_cmd can load them without erroring.
    config_path = tmp_path / "config.toml"
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    config_path.write_text(
        '[sftp]\nhostname = "h"\nremote_root = "/"\n'
        f'[paths]\nlog_root = "{log_root.as_posix()}"\n'
        f'backup_root = "{backup_root.as_posix()}"\n'
    )
    sftp_env_path = tmp_path / "sftp.env"
    sftp_env_path.write_text("ATOMX_SFTP_USER=u\nATOMX_SFTP_PASSWORD=p\n")
    monkeypatch.setattr(transfer_cli_module, "_default_sftp_env_path", lambda: sftp_env_path)
    monkeypatch.setattr(
        transfer_cli_module,
        "_default_smtp_env_path",
        lambda: tmp_path / "smtp.env",
    )

    # jobs.tsv with two valid CosmxRunNames (only parsed, the fake run_batch ignores them).
    jobs_tsv = tmp_path / "jobs.tsv"
    jobs_tsv.write_text(
        "rA\t20260101_T_D_sA_v1-0-0\nrB\t20260101_T_D_sB_v1-0-0\n",
    )

    runner = CliRunner()
    result_cli = runner.invoke(
        app,
        ["batch", str(jobs_tsv), "--config", str(config_path)],
    )

    # batch_cmd exits 1 because any_failed is True; that's fine for this test.
    assert result_cli.exit_code == 1
    assert mock_dispatch_transfer.call_count == 2
    assert mock_dispatch_batch.call_count == 1

    # Confirm the per-study reports carry the expected status mapping.
    dispatched_statuses = sorted(
        call.args[0].status for call in mock_dispatch_transfer.call_args_list
    )
    assert dispatched_statuses == ["failed", "success"]
