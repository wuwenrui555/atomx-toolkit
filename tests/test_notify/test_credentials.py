"""Tests for SMTP credential chain (env > dotenv > none)."""

from pathlib import Path

import pytest

from atomx_toolkit.notify.credentials import (
    SmtpCredentials,
    SmtpCredentialsMissing,
    load_smtp_credentials,
)


def test_env_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOMX_SMTP_USER", "envuser")
    monkeypatch.setenv("ATOMX_SMTP_APP_PASSWORD", "envpw")
    creds = load_smtp_credentials(tmp_path / "smtp.env")
    assert isinstance(creds, SmtpCredentials)
    assert creds.user == "envuser"
    assert creds.password == "envpw"
    assert creds.host == "smtp.gmail.com"
    assert creds.port == 587


def test_dotenv_used_when_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    p = tmp_path / "smtp.env"
    p.write_text(
        "ATOMX_SMTP_USER=alice\n"
        "ATOMX_SMTP_APP_PASSWORD=secret\n"
        "ATOMX_SMTP_HOST=smtp.example.com\n"
        "ATOMX_SMTP_PORT=2525\n"
    )
    creds = load_smtp_credentials(p)
    assert creds == SmtpCredentials(
        user="alice", password="secret", host="smtp.example.com", port=2525
    )


def test_returns_missing_when_neither(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    result = load_smtp_credentials(tmp_path / "absent.env")
    assert isinstance(result, SmtpCredentialsMissing)


def test_partial_dotenv_returns_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    p = tmp_path / "smtp.env"
    p.write_text("ATOMX_SMTP_USER=alice\n")
    result = load_smtp_credentials(p)
    assert isinstance(result, SmtpCredentialsMissing)
