"""Tests for jobs.tsv parsing, batch execution, and plan dry-run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomx_toolkit.transfer.batch import (
    JobsTsvError,
    classify_jobs,
    parse_jobs_tsv,
)
from atomx_toolkit.transfer.lock import LOCK_FILENAME


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
