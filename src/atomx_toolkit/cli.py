"""Typer root CLI for atomx-toolkit."""

from __future__ import annotations

import logging
from pathlib import Path

import typer
from pingme import SmtpCredentialsMissing, resolve_recipients, send_email

from atomx_toolkit import __version__
from atomx_toolkit.config import ConfigError, load_config
from atomx_toolkit.install.cli import app as install_app
from atomx_toolkit.notify.cli import app as notify_app
from atomx_toolkit.notify.credentials import load_smtp_credentials
from atomx_toolkit.notify.dedup import DedupState
from atomx_toolkit.notify.handler import ToolkitErrorHandler
from atomx_toolkit.transfer.cli import app as transfer_app

app = typer.Typer(
    name="atomx-toolkit",
    help="AtoMx SFTP transfer with integrity check and email reporting.",
    no_args_is_help=True,
)
app.add_typer(transfer_app, name="transfer")
app.add_typer(notify_app, name="notify")
app.add_typer(install_app, name="install")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"atomx-toolkit {__version__}")
        raise typer.Exit()


def _install_toolkit_error_handler() -> None:
    """Best-effort install: if config/creds aren't available, do nothing.

    Skipped silently if the user hasn't run install init yet, if the config
    fails to parse, if notifications are disabled, or if SMTP credentials
    are missing. In any of those cases toolkit_error stays in file logs only.
    """
    config_path = Path.home() / ".config" / "atomx-toolkit" / "config.toml"
    smtp_env = Path.home() / ".config" / "atomx-toolkit" / "smtp.env"
    if not config_path.exists():
        return
    try:
        cfg = load_config(config_path)
    except ConfigError:
        return
    if not cfg.notify.enabled:
        return

    creds = load_smtp_credentials(smtp_env)
    if isinstance(creds, SmtpCredentialsMissing):
        return

    state_dir = config_path.parent / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    dedup = DedupState(
        path=state_dir / "toolkit_error_dedup.json",
        cooldown_seconds=cfg.notify.toolkit_error_cooldown_seconds,
    )
    recipients_dir = cfg.notify.recipients_dir

    def sender(*, subject: str, body: str) -> None:
        res = resolve_recipients("toolkit_error", recipients_dir)
        if not res.emails:
            return
        send_email(creds=creds, recipients=res.emails, subject=subject, body=body)

    root = logging.getLogger()
    # Avoid double-install if main() somehow runs twice in the same process.
    if any(isinstance(h, ToolkitErrorHandler) for h in root.handlers):
        return
    handler = ToolkitErrorHandler(sender=sender, dedup=dedup, level=logging.WARNING)
    root.addHandler(handler)


@app.callback()
def main(
    ctx: typer.Context,
    version: bool = typer.Option(
        False,
        "--version",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit.",
    ),
    verbose: int = typer.Option(
        0,
        "-v",
        "--verbose",
        count=True,
        help="Increase verbosity (repeatable, up to -vv).",
    ),
) -> None:
    """atomx-toolkit root command."""
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose
    _install_toolkit_error_handler()


if __name__ == "__main__":
    app()
