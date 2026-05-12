"""Bridge from transfer-side data to notify subsystem.

Lives in `notify/` rather than in transfer/ so transfer remains
ignorant of email entirely.
"""

from __future__ import annotations

import logging
from pathlib import Path

from pingme import SmtpCredentialsMissing, resolve_recipients, send_email

from atomx_toolkit.config import Config
from atomx_toolkit.notify.credentials import load_smtp_credentials
from atomx_toolkit.notify.events import (
    BatchReport,
    TransferReport,
    format_batch_report,
    format_transfer_report,
)

logger = logging.getLogger(__name__)


def dispatch_transfer_report(report: TransferReport, *, cfg: Config, smtp_env: Path) -> None:
    if not cfg.notify.enabled:
        return
    creds = load_smtp_credentials(smtp_env)
    if isinstance(creds, SmtpCredentialsMissing):
        logger.warning("smtp credentials missing; skipping transfer_report email")
        return
    res = resolve_recipients("transfer_report", cfg.notify.recipients_dir)
    if not res.emails:
        logger.info("no recipients for transfer_report; skipping email")
        return
    subject, body = format_transfer_report(report)
    send_email(creds=creds, recipients=res.emails, subject=subject, body=body)


def dispatch_batch_report(report: BatchReport, *, cfg: Config, smtp_env: Path) -> None:
    if not cfg.notify.enabled:
        return
    creds = load_smtp_credentials(smtp_env)
    if isinstance(creds, SmtpCredentialsMissing):
        logger.warning("smtp credentials missing; skipping batch_report email")
        return
    res = resolve_recipients("batch_report", cfg.notify.recipients_dir)
    if not res.emails:
        logger.info("no recipients for batch_report; skipping email")
        return
    subject, body = format_batch_report(report)
    send_email(creds=creds, recipients=res.emails, subject=subject, body=body)
