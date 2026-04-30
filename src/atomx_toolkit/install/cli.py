"""install Typer subgroup."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from atomx_toolkit.install.init import InstallInitError, init_config_dir

app = typer.Typer(name="install", no_args_is_help=True, help="Install commands.")
console = Console(stderr=True)


@app.command("init")
def init_cmd(
    config_dir: Annotated[Path | None, typer.Option("--config-dir")] = None,
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Write config templates to ~/.config/atomx-toolkit/ (or --config-dir)."""
    target = config_dir or (Path.home() / ".config" / "atomx-toolkit")
    try:
        init_config_dir(target, force=force)
    except InstallInitError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    console.print(f"[green]wrote templates to {target}[/green]")
