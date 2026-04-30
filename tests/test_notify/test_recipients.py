"""Tests for per-event recipient list resolution."""

from pathlib import Path

from atomx_toolkit.notify.recipients import RecipientResolution, resolve_recipients


def _seed(d: Path, files: dict[str, str]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content)


def test_event_specific_takes_precedence(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "alice@x.com\n", "default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res == RecipientResolution(emails=["alice@x.com"], source="transfer_report.txt")


def test_falls_back_to_default(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "# only comments\n", "default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res == RecipientResolution(emails=["bob@x.com"], source="default.txt")


def test_returns_empty_when_all_empty(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "\n", "default.txt": "\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == []
    assert res.source is None


def test_strips_comments_and_blanks(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {"transfer_report.txt": "# header\n\nalice@x.com\n# bob disabled\n  \nclaire@x.com\n"},
    )
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == ["alice@x.com", "claire@x.com"]


def test_missing_event_file_falls_back(tmp_path: Path) -> None:
    _seed(tmp_path, {"default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == ["bob@x.com"]
    assert res.source == "default.txt"
