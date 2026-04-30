"""paramiko-based SFTP client with iterative walk and atomic download."""

from __future__ import annotations

import contextlib
import logging
import os
import posixpath
import stat
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

import paramiko

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT_S = 60.0
DEFAULT_READ_TIMEOUT_S = 300.0


class SftpClient:
    """SSH/SFTP context manager for AtoMx-style password auth.

    On enter: opens an SSHClient, loads known_hosts, connects, opens SFTP.
    On exit: closes SFTP and SSH cleanly.

    Host-key policy: AutoAddPolicy + load_system_host_keys. New hosts are
    auto-added to ~/.ssh/known_hosts; mismatched hosts raise BadHostKeyException
    (paramiko consults the policy only for missing keys, not mismatches).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = 22,
        user: str,
        password: str,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout: float = DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> Self:
        ssh = paramiko.SSHClient()
        # known_hosts may not exist yet; that's fine.
        with contextlib.suppress(OSError):
            ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            timeout=self._connect_timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(self._read_timeout)  # type: ignore[union-attr]
        self._ssh = ssh
        self._sftp = sftp
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception as exc_close:
                logger.warning("error closing sftp: %s", exc_close)
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception as exc_close:
                logger.warning("error closing ssh: %s", exc_close)

    @property
    def _client(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            raise RuntimeError("SftpClient used outside its context manager")
        return self._sftp

    def walk_files(self, root: str) -> Iterator[str]:
        """Iterative DFS yielding absolute POSIX paths of regular files under root."""
        stack: list[str] = [root.rstrip("/") or "/"]
        while stack:
            current = stack.pop()
            for attr in self._client.listdir_attr(current):
                if attr.filename in (".", ".."):
                    continue
                full = posixpath.join(current, attr.filename)
                mode = attr.st_mode or 0
                if stat.S_ISDIR(mode):
                    stack.append(full)
                elif stat.S_ISREG(mode):
                    yield full

    def stat_size(self, remote: str) -> int:
        attr = self._client.stat(remote)
        if attr.st_size is None:
            raise RuntimeError(f"remote {remote} has no size attr")
        return attr.st_size

    def download_file(self, remote: str, local: Path) -> None:
        """Stream download to `<local>.part`, then os.rename to final path.

        The .part file lives in the same directory as the final, so the rename
        is atomic on POSIX.
        """
        local.parent.mkdir(parents=True, exist_ok=True)
        part = local.with_suffix(local.suffix + ".part")
        # Defensive: clear any stale .part from a previous run.
        if part.exists():
            part.unlink()
        with self._client.open(remote, "rb") as remote_f, part.open("wb") as local_f:
            while True:
                chunk = remote_f.read(1024 * 1024)
                if not chunk:
                    break
                local_f.write(chunk)
            local_f.flush()
            os.fsync(local_f.fileno())
        os.rename(part, local)
