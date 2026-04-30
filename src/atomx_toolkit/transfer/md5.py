"""MD5 checksums via the system `md5sum` binary, plus a dict-based diff."""

from __future__ import annotations

import csv
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Md5Comparison:
    matched: int
    mismatched: int
    missing_in_1: int
    missing_in_2: int

    @property
    def all_match(self) -> bool:
        return self.mismatched == 0 and self.missing_in_1 == 0 and self.missing_in_2 == 0


def assert_md5sum_available() -> None:
    """Raise FileNotFoundError if the `md5sum` binary is not on PATH."""
    if shutil.which("md5sum") is None:
        raise FileNotFoundError("the `md5sum` binary is required (install GNU coreutils)")


def compute_md5_tree(root: Path) -> dict[str, str]:
    """Return {relpath_str: md5hash} for every regular file under root.

    Empty dir returns {}. Missing root raises FileNotFoundError.
    Files are processed one per `md5sum` invocation; this is slower
    than a batched call but keeps the per-file error handling clean.
    """
    if not root.exists():
        raise FileNotFoundError(f"path not found: {root}")
    if root.is_file():
        files = [root]
        relbase = root.parent
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file())
        relbase = root
    result: dict[str, str] = {}
    for file_path in files:
        try:
            md5 = _md5_one(file_path)
        except subprocess.CalledProcessError as exc:
            logger.error("md5sum failed for %s: %s", file_path, exc)
            continue
        rel = file_path.relative_to(relbase).as_posix()
        result[rel] = md5
    return result


def _md5_one(path: Path) -> str:
    proc = subprocess.run(
        ["md5sum", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.split()[0]


def write_md5_file(md5_dict: dict[str, str], output: Path) -> None:
    """Write a standard md5sum-format file: '<hash>  <relpath>\\n' per line."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for relpath, md5 in sorted(md5_dict.items()):
            f.write(f"{md5}  {relpath}\n")


def read_md5_file(path: Path) -> dict[str, str]:
    """Parse a md5sum-format file back into {relpath: hash}."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        # md5sum format: '<hash>  <relpath>'  (two spaces, but be tolerant)
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        result[parts[1].lstrip()] = parts[0]
    return result


def compare_md5_files(md5_path_1: Path, md5_path_2: Path, diff_csv: Path) -> Md5Comparison:
    """Compare two md5sum-format files. Write a diff CSV iff anything mismatches.

    The CSV has columns (file, md5_1, md5_2, status) where status is one of
    'mismatch', 'missing_in_1', 'missing_in_2'.
    """
    d1 = read_md5_file(md5_path_1)
    d2 = read_md5_file(md5_path_2)
    all_keys = sorted(set(d1) | set(d2))
    mismatched = 0
    missing_in_1 = 0
    missing_in_2 = 0
    matched = 0
    rows: list[dict[str, str]] = []
    for key in all_keys:
        h1 = d1.get(key)
        h2 = d2.get(key)
        if h1 is None:
            missing_in_1 += 1
            rows.append({"file": key, "md5_1": "", "md5_2": h2 or "", "status": "missing_in_1"})
        elif h2 is None:
            missing_in_2 += 1
            rows.append({"file": key, "md5_1": h1, "md5_2": "", "status": "missing_in_2"})
        elif h1 == h2:
            matched += 1
        else:
            mismatched += 1
            rows.append({"file": key, "md5_1": h1, "md5_2": h2, "status": "mismatch"})
    if rows:
        diff_csv.parent.mkdir(parents=True, exist_ok=True)
        with diff_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["file", "md5_1", "md5_2", "status"])
            writer.writeheader()
            writer.writerows(rows)
    return Md5Comparison(
        matched=matched,
        mismatched=mismatched,
        missing_in_1=missing_in_1,
        missing_in_2=missing_in_2,
    )
