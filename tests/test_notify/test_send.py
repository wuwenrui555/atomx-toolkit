"""Tests for SMTP send and toolkit_error dedup."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from atomx_toolkit.notify.credentials import SmtpCredentials
from atomx_toolkit.notify.send import (
    DedupState,
    send_email,
    should_send_toolkit_error,
)

if TYPE_CHECKING:
    from tests.test_notify.conftest import FakeSmtp


def test_send_email_delivers(tmp_path: Path, fake_smtp: FakeSmtp) -> None:
    creds = SmtpCredentials(
        user="anyone@example.com",
        password="ignored",
        host=fake_smtp.host,
        port=fake_smtp.port,
    )
    send_email(
        creds=creds,
        recipients=["alice@example.com", "bob@example.com"],
        subject="hello",
        body="world",
        use_tls=False,  # local fake doesn't do STARTTLS
    )
    assert len(fake_smtp.sink.messages) == 1
    msg = fake_smtp.sink.messages[0]
    assert "alice@example.com" in msg.recipients
    assert "bob@example.com" in msg.recipients
    assert b"hello" in msg.raw
    assert b"world" in msg.raw


def test_send_email_skipped_when_no_recipients(fake_smtp: FakeSmtp) -> None:
    creds = SmtpCredentials(
        user="x@x.com", password="p", host=fake_smtp.host, port=fake_smtp.port
    )
    send_email(creds=creds, recipients=[], subject="s", body="b", use_tls=False)
    assert fake_smtp.sink.messages == []


def test_dedup_first_send_allowed(tmp_path: Path) -> None:
    state_file = tmp_path / "dedup.json"
    state = DedupState(path=state_file, cooldown_seconds=300)
    assert should_send_toolkit_error(state, "key1") is True


def test_dedup_within_cooldown_blocks(tmp_path: Path) -> None:
    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    assert should_send_toolkit_error(state, "k") is True
    assert should_send_toolkit_error(state, "k") is False


def test_dedup_after_cooldown_allows(tmp_path: Path) -> None:
    import time

    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=0)
    assert should_send_toolkit_error(state, "k") is True
    time.sleep(0.05)
    assert should_send_toolkit_error(state, "k") is True


def test_dedup_strips_timestamps_for_key() -> None:
    from atomx_toolkit.notify.send import (
        _normalize_for_dedup,  # pyright: ignore[reportPrivateUsage]
    )

    a = "2026-04-30T12:00:00 ERROR something failed"
    b = "2026-04-30T12:00:01 ERROR something failed"
    assert _normalize_for_dedup(a) == _normalize_for_dedup(b)
