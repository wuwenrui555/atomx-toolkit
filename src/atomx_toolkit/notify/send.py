"""SMTP send + toolkit_error dedup state."""

from __future__ import annotations

import json
import logging
import re
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from atomx_toolkit.notify.credentials import SmtpCredentials

logger = logging.getLogger(__name__)


def send_email(
    *,
    creds: SmtpCredentials,
    recipients: list[str],
    subject: str,
    body: str,
    use_tls: bool = True,
) -> None:
    """Send a single plain-text email. Logs and returns silently on no recipients."""
    if not recipients:
        logger.info("no recipients; skipping email %r", subject)
        return
    msg = EmailMessage()
    msg["From"] = creds.user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(creds.host, creds.port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
                smtp.login(creds.user, creds.password)
            smtp.send_message(msg)
        logger.info("sent email %r to %d recipients", subject, len(recipients))
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("smtp failure for %r: %s", subject, exc)


# ---- dedup ----


@dataclass
class DedupState:
    path: Path
    cooldown_seconds: int

    def _read(self) -> dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, float]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")


_TIMESTAMP_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"),
    re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}"),
]


def _normalize_for_dedup(content: str) -> str:
    out = content
    for pat in _TIMESTAMP_PATTERNS:
        out = pat.sub("<TS>", out)
    return out[:200]


def should_send_toolkit_error(state: DedupState, content: str) -> bool:
    """Return True iff this content key has not been seen within cooldown."""
    key = _normalize_for_dedup(content)
    now = time.time()
    data = state._read()  # pyright: ignore[reportPrivateUsage]
    last = data.get(key, 0.0)
    if now - last < state.cooldown_seconds:
        return False
    data[key] = now
    state._write(data)  # pyright: ignore[reportPrivateUsage]
    return True
