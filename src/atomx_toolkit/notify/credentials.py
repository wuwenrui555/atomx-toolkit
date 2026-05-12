"""SMTP credentials adapter: reads ATOMX_SMTP_* env + dotenv, returns pingme types.

The atomx-toolkit operator surface is uniformly ATOMX_-prefixed. Internally we
hand pingme a ready-built ``SmtpCredentials`` so the operator never sees PINGME_
env vars. SMTP send uses pingme's ``send_email``.
"""

from __future__ import annotations

import os
from pathlib import Path

from pingme import SmtpCredentials, SmtpCredentialsMissing, parse_dotenv

__all__ = ["SmtpCredentials", "SmtpCredentialsMissing", "load_smtp_credentials"]

DEFAULT_HOST = "smtp.gmail.com"
DEFAULT_PORT = 465
_USER_KEY = "ATOMX_SMTP_USER"
_PASS_KEY = "ATOMX_SMTP_APP_PASSWORD"
_HOST_KEY = "ATOMX_SMTP_HOST"
_PORT_KEY = "ATOMX_SMTP_PORT"


def load_smtp_credentials(
    dotenv_path: Path,
) -> SmtpCredentials | SmtpCredentialsMissing:
    file_values = parse_dotenv(dotenv_path) if dotenv_path.exists() else {}
    user = os.environ.get(_USER_KEY) or file_values.get(_USER_KEY)
    password = os.environ.get(_PASS_KEY) or file_values.get(_PASS_KEY)
    host = os.environ.get(_HOST_KEY) or file_values.get(_HOST_KEY) or DEFAULT_HOST
    port_raw = os.environ.get(_PORT_KEY) or file_values.get(_PORT_KEY)
    if not user or not password:
        return SmtpCredentialsMissing()
    return SmtpCredentials(
        user=user,
        app_password=password,
        host=host,
        port=_coerce_port(port_raw),
        transport="ssl",
    )


def _coerce_port(raw: str | None) -> int:
    if raw is None:
        return DEFAULT_PORT
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PORT
