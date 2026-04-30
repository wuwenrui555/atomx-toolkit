"""Tests for the paramiko-backed SFTP wrapper."""

from __future__ import annotations

from pathlib import Path

import paramiko
import pytest

from atomx_toolkit.transfer.sftp import SftpClient

from .conftest import SftpServerFixture, seed_remote


def test_walk_files_returns_absolute_posix_paths(
    sftp_server: SftpServerFixture, known_hosts_isolated: Path
) -> None:
    seed_remote(sftp_server, {"a.txt": b"x", "sub/b.txt": b"y", "sub/c/d.txt": b"z"})
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        files = sorted(client.walk_files("/"))
    assert files == ["/a.txt", "/sub/b.txt", "/sub/c/d.txt"]


def test_walk_files_empty_dir(sftp_server: SftpServerFixture, known_hosts_isolated: Path) -> None:
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        assert list(client.walk_files("/")) == []


def test_download_file_atomic_rename(
    sftp_server: SftpServerFixture, tmp_path: Path, known_hosts_isolated: Path
) -> None:
    seed_remote(sftp_server, {"a.bin": b"hello world"})
    local = tmp_path / "out" / "a.bin"
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        client.download_file("/a.bin", local)
    assert local.read_bytes() == b"hello world"
    assert not local.with_suffix(".bin.part").exists()


def test_stat_size(sftp_server: SftpServerFixture, known_hosts_isolated: Path) -> None:
    seed_remote(sftp_server, {"big.bin": b"x" * 12345})
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        assert client.stat_size("/big.bin") == 12345


def test_auth_failure_raises(
    sftp_server: SftpServerFixture, known_hosts_isolated: Path
) -> None:
    with (
        pytest.raises(paramiko.AuthenticationException),
        SftpClient(
            host=sftp_server.host,
            port=sftp_server.port,
            user=sftp_server.user,
            password="wrong",
        ),
    ):
        pass
