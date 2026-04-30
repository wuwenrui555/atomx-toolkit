"""Tests for md5sum subprocess wrapper and dict-based comparison."""

import csv
from pathlib import Path

import pytest

from atomx_toolkit.transfer.md5 import (
    Md5Comparison,
    compare_md5_files,
    compute_md5_tree,
    write_md5_file,
)


def _seed(root: Path, files: dict[str, bytes]) -> None:
    for relpath, content in files.items():
        full = root / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)


def test_compute_md5_tree_returns_relpath_to_hash(tmp_path: Path) -> None:
    _seed(tmp_path, {"a.txt": b"hello", "sub/b.txt": b"world"})
    result = compute_md5_tree(tmp_path)
    assert set(result.keys()) == {"a.txt", "sub/b.txt"}
    assert result["a.txt"] == "5d41402abc4b2a76b9719d911017c592"  # md5("hello")


def test_compute_md5_tree_empty_dir(tmp_path: Path) -> None:
    result = compute_md5_tree(tmp_path)
    assert result == {}


def test_compute_md5_tree_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_md5_tree(tmp_path / "absent")


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path, {"a.txt": b"data"})
    md5_dict = compute_md5_tree(tmp_path)
    out = tmp_path / "md5sum.txt"
    write_md5_file(md5_dict, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("  a.txt") for line in lines)


def test_compare_all_match(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _seed(a, {"f.txt": b"same"})
    _seed(b, {"f.txt": b"same"})
    md5_a = tmp_path / "md5_a.txt"
    md5_b = tmp_path / "md5_b.txt"
    write_md5_file(compute_md5_tree(a), md5_a)
    write_md5_file(compute_md5_tree(b), md5_b)
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp == Md5Comparison(matched=1, mismatched=0, missing_in_1=0, missing_in_2=0)
    assert not diff_csv.exists()  # no diff CSV when fully matched


def test_compare_with_mismatch(tmp_path: Path) -> None:
    md5_a = tmp_path / "a.txt"
    md5_b = tmp_path / "b.txt"
    md5_a.write_text("aaaaaaaa11111111aaaaaaaa11111111  same.bin\n")
    md5_b.write_text("aaaaaaaa11111111aaaaaaaa22222222  same.bin\n")
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp.mismatched == 1
    assert diff_csv.exists()
    rows = list(csv.DictReader(diff_csv.open()))
    assert rows[0]["status"] == "mismatch"
    assert rows[0]["file"] == "same.bin"


def test_compare_with_missing(tmp_path: Path) -> None:
    md5_a = tmp_path / "a.txt"
    md5_b = tmp_path / "b.txt"
    md5_a.write_text("aaaaaaaa11111111aaaaaaaa11111111  only_in_1.bin\n")
    md5_b.write_text("bbbbbbbb22222222bbbbbbbb22222222  only_in_2.bin\n")
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp.missing_in_1 == 1
    assert cmp.missing_in_2 == 1
    rows = sorted(csv.DictReader(diff_csv.open()), key=lambda r: r["file"])
    assert {r["status"] for r in rows} == {"missing_in_1", "missing_in_2"}


def test_compute_handles_non_ascii_filenames(tmp_path: Path) -> None:
    _seed(tmp_path, {"中文.bin": b"x"})
    result = compute_md5_tree(tmp_path)
    assert "中文.bin" in result
