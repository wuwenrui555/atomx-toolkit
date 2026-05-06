"""Load SFTP credentials from environment or a dotenv-style file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class SftpCredentialsError(Exception):
    """Failure to resolve SFTP credentials."""


@dataclass(frozen=True)
class SftpCredentials:
    user: str
    password: str


_USER_KEY = "ATOMX_SFTP_USER"
_PASS_KEY = "ATOMX_SFTP_PASSWORD"


def load_sftp_credentials(dotenv_path: Path) -> SftpCredentials:
    """Resolve SFTP credentials. Env wins; dotenv is fallback.

    Either both keys present in env, or both in dotenv. Mixed sources
    are rejected to avoid the half-configured operator confusion.
    """
    env_user = os.environ.get(_USER_KEY)
    env_pass = os.environ.get(_PASS_KEY)
    if env_user and env_pass:
        return SftpCredentials(user=env_user, password=env_pass)
    if env_user or env_pass:
        missing = _PASS_KEY if env_user else _USER_KEY
        raise SftpCredentialsError(f"{missing} present in env but its counterpart is missing")

    if not dotenv_path.exists():
        raise SftpCredentialsError(
            f"SFTP credentials not found: env vars {_USER_KEY}/{_PASS_KEY} unset "
            f"and dotenv file does not exist: {dotenv_path}"
        )
    parsed = parse_dotenv(dotenv_path)
    user = parsed.get(_USER_KEY)
    password = parsed.get(_PASS_KEY)
    if not user or not password:
        missing = _USER_KEY if not user else _PASS_KEY
        raise SftpCredentialsError(f"{dotenv_path}: missing or empty {missing}")
    return SftpCredentials(user=user, password=password)


def parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal dotenv parser: KEY=VALUE per line, # comments, optional `export `."""
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding single or double quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key] = value
    return result
