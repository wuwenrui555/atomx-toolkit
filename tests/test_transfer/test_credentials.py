"""Tests for SFTP credential loading (env > dotenv > error)."""

from pathlib import Path

import pytest

from atomx_toolkit.transfer.credentials import (
    SftpCredentials,
    SftpCredentialsError,
    load_sftp_credentials,
)


def test_env_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOMX_SFTP_USER", "from_env")
    monkeypatch.setenv("ATOMX_SFTP_PASSWORD", "p_env")
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text("ATOMX_SFTP_USER=from_dotenv\nATOMX_SFTP_PASSWORD=p_dotenv\n")
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="from_env", password="p_env")


def test_dotenv_used_when_env_missing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text("# comment\nATOMX_SFTP_USER=alice\nexport ATOMX_SFTP_PASSWORD=secret\n\n")
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="alice", password="secret")


def test_missing_both_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    with pytest.raises(SftpCredentialsError, match="not found"):
        load_sftp_credentials(tmp_path / "absent.env")


def test_partial_credentials_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOMX_SFTP_USER", "alice")
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    with pytest.raises(SftpCredentialsError, match="ATOMX_SFTP_PASSWORD"):
        load_sftp_credentials(tmp_path / "absent.env")


def test_dotenv_quoted_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text("ATOMX_SFTP_USER=\"alice\"\nATOMX_SFTP_PASSWORD='p with spaces'\n")
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="alice", password="p with spaces")
