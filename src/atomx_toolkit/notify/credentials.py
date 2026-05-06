"""SMTP credential chain: env > dotenv > none. Returns a sentinel on missing,
not an exception, because email is best-effort.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from atomx_toolkit.transfer.credentials import parse_dotenv

DEFAULT_HOST = "smtp.gmail.com"
DEFAULT_PORT = 587
_USER_KEY = "ATOMX_SMTP_USER"
_PASS_KEY = "ATOMX_SMTP_APP_PASSWORD"
_HOST_KEY = "ATOMX_SMTP_HOST"
_PORT_KEY = "ATOMX_SMTP_PORT"


@dataclass(frozen=True)
class SmtpCredentials:
    user: str
    password: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


@dataclass(frozen=True)
class SmtpCredentialsMissing:
    """Sentinel: email send should be skipped, not retried."""


def load_smtp_credentials(
    dotenv_path: Path,
) -> SmtpCredentials | SmtpCredentialsMissing:
    user = os.environ.get(_USER_KEY)
    password = os.environ.get(_PASS_KEY)
    host = os.environ.get(_HOST_KEY)
    port_raw = os.environ.get(_PORT_KEY)
    if not (user and password) and dotenv_path.exists():
        parsed = parse_dotenv(dotenv_path)
        user = user or parsed.get(_USER_KEY)
        password = password or parsed.get(_PASS_KEY)
        host = host or parsed.get(_HOST_KEY)
        port_raw = port_raw or parsed.get(_PORT_KEY)
    if not user or not password:
        return SmtpCredentialsMissing()
    return SmtpCredentials(
        user=user,
        password=password,
        host=host or DEFAULT_HOST,
        port=int(port_raw) if port_raw else DEFAULT_PORT,
    )
