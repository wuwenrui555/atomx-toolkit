"""Recipient resolution per event, with hot-reload (files re-read each call)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ALL_EVENTS = ("transfer_report", "batch_report", "toolkit_error")


@dataclass(frozen=True)
class RecipientResolution:
    emails: list[str]
    source: str | None  # which file the addresses came from, or None if empty


def resolve_recipients(event: str, recipients_dir: Path) -> RecipientResolution:
    """Resolve subscribers for an event. Event-specific file wins; default.txt is fallback."""
    candidates = [f"{event}.txt", "default.txt"]
    for filename in candidates:
        path = recipients_dir / filename
        if not path.exists():
            continue
        emails = _parse(path)
        if emails:
            return RecipientResolution(emails=emails, source=filename)
    return RecipientResolution(emails=[], source=None)


def _parse(path: Path) -> list[str]:
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out
