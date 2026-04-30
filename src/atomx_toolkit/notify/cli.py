"""notify Typer subgroup: test (send a fixed test email), list-subscribers."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from atomx_toolkit.config import ConfigError, load_config
from atomx_toolkit.notify.credentials import (
    SmtpCredentialsMissing,
    load_smtp_credentials,
)
from atomx_toolkit.notify.recipients import ALL_EVENTS, resolve_recipients
from atomx_toolkit.notify.send import send_email

app = typer.Typer(name="notify", no_args_is_help=True, help="Email notification commands.")
console = Console(stderr=True)


def _default_config_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "config.toml"


def _default_smtp_env_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "smtp.env"


def _recipients_dir(config_path: Path) -> Path:
    cfg = load_config(config_path)
    return cfg.notify.recipients_dir


@app.command("test")
def test_cmd(
    event: Annotated[str, typer.Option("--event", help="Event name")],
    config: Annotated[Path | None, typer.Option("--config")] = None,
    smtp_env: Annotated[Path | None, typer.Option("--smtp-env")] = None,
    dry_run: Annotated[bool, typer.Option("--dry-run")] = False,
) -> None:
    """Send a fixed-content test email through the full credential chain."""
    cfg_path = config or _default_config_path()
    if event not in ALL_EVENTS:
        console.print(f"[red]unknown event:[/red] {event}; expected one of {ALL_EVENTS}")
        raise typer.Exit(code=2)
    try:
        rdir = _recipients_dir(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    res = resolve_recipients(event, rdir)
    if not res.emails:
        console.print(f"[yellow]no recipients for {event}[/yellow]; nothing to send")
        return
    console.print(f"recipients ({res.source}): {', '.join(res.emails)}")
    if dry_run:
        console.print("[yellow]dry-run; not sending[/yellow]")
        return
    creds = load_smtp_credentials(smtp_env or _default_smtp_env_path())
    if isinstance(creds, SmtpCredentialsMissing):
        console.print("[red]smtp credentials missing[/red]")
        raise typer.Exit(code=2)
    send_email(
        creds=creds,
        recipients=res.emails,
        subject=f"[atomx-toolkit] TEST email for event '{event}'",
        body=f"This is a test email from atomx-toolkit notify test --event {event}.\n",
    )
    console.print("[green]sent[/green]")


@app.command("list-subscribers")
def list_subscribers_cmd(
    event: Annotated[str | None, typer.Option("--event")] = None,
    config: Annotated[Path | None, typer.Option("--config")] = None,
) -> None:
    """List resolved subscribers per event."""
    cfg_path = config or _default_config_path()
    try:
        rdir = _recipients_dir(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    events = (event,) if event else ALL_EVENTS
    for ev in events:
        if ev not in ALL_EVENTS:
            console.print(f"[red]unknown event:[/red] {ev}")
            raise typer.Exit(code=2)
        res = resolve_recipients(ev, rdir)
        if res.emails:
            console.print(f"{ev} (from {res.source}):")
            for e in res.emails:
                console.print(f"  - {e}")
        else:
            console.print(f"{ev}: [yellow](empty)[/yellow]")
