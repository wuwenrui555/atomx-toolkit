"""Local SFTP server fixture for transfer integration tests."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import paramiko
import pytest
from paramiko.common import AUTH_FAILED, AUTH_SUCCESSFUL, OPEN_SUCCEEDED
from paramiko.sftp import SFTP_NO_SUCH_FILE


@dataclass
class SftpServerFixture:
    host: str
    port: int
    user: str
    password: str
    rootdir: Path
    stop_event: threading.Event
    listener: socket.socket


class _AuthHandler(paramiko.ServerInterface):
    def __init__(self, expected_user: str, expected_password: str) -> None:
        self._user = expected_user
        self._password = expected_password

    def check_auth_password(self, username: str, password: str) -> int:
        if username == self._user and password == self._password:
            return AUTH_SUCCESSFUL
        return AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return OPEN_SUCCEEDED


class _SftpHandler(paramiko.SFTPServerInterface):
    """Tiny SFTP handler that serves a fixed root directory read-only."""

    ROOT: Path = Path()

    def _real(self, path: str) -> Path:
        path = path.lstrip("/")
        return self.ROOT / path

    def list_folder(self, path: str) -> list[paramiko.SFTPAttributes] | int:
        full = self._real(path)
        if not full.is_dir():
            return SFTP_NO_SUCH_FILE
        out: list[paramiko.SFTPAttributes] = []
        for entry in full.iterdir():
            attr = paramiko.SFTPAttributes.from_stat(entry.stat())
            attr.filename = entry.name
            out.append(attr)
        return out

    def stat(self, path: str) -> paramiko.SFTPAttributes | int:
        full = self._real(path)
        if not full.exists():
            return SFTP_NO_SUCH_FILE
        return paramiko.SFTPAttributes.from_stat(full.stat())

    lstat = stat

    def open(
        self, path: str, flags: int, attr: paramiko.SFTPAttributes
    ) -> paramiko.SFTPHandle | int:
        full = self._real(path)
        if not full.exists() or not full.is_file():
            return SFTP_NO_SUCH_FILE
        handle = paramiko.SFTPHandle(flags)
        handle.readfile = full.open("rb")  # type: ignore[attr-defined]
        return handle


def _serve_one(
    listener: socket.socket,
    host_key: paramiko.RSAKey,
    user: str,
    password: str,
    rootdir: Path,
    stop_event: threading.Event,
) -> None:
    listener.settimeout(0.5)
    while not stop_event.is_set():
        try:
            client_sock, _ = listener.accept()
        except TimeoutError:
            continue
        except OSError:
            # Listener was closed during teardown.
            return
        transport = paramiko.Transport(client_sock)
        transport.add_server_key(host_key)
        _SftpHandler.ROOT = rootdir  # set per-connection root
        transport.set_subsystem_handler("sftp", paramiko.SFTPServer, _SftpHandler)
        try:
            transport.start_server(server=_AuthHandler(user, password))
        except paramiko.SSHException:
            transport.close()
            continue
        # transport runs subsystem in its own thread


@pytest.fixture
def sftp_server(tmp_path: Path) -> Iterator[SftpServerFixture]:
    rootdir = tmp_path / "remote"
    rootdir.mkdir()
    user = "tester"
    password = "secret"
    host_key = paramiko.RSAKey.generate(2048)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_serve_one,
        args=(listener, host_key, user, password, rootdir, stop_event),
        daemon=True,
    )
    thread.start()
    server = SftpServerFixture(
        host="127.0.0.1",
        port=port,
        user=user,
        password=password,
        rootdir=rootdir,
        stop_event=stop_event,
        listener=listener,
    )
    yield server
    stop_event.set()
    listener.close()
    thread.join(timeout=2)


def seed_remote(server: SftpServerFixture, files: dict[str, bytes]) -> None:
    """Helper used by tests to populate the remote rootdir."""
    for relpath, content in files.items():
        full = server.rootdir / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)


@pytest.fixture
def known_hosts_isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ~/.ssh/known_hosts to a tmp path so tests don't pollute the user's."""
    ssh_dir = tmp_path / "ssh"
    ssh_dir.mkdir()
    known_hosts = ssh_dir / "known_hosts"
    known_hosts.touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    return known_hosts
