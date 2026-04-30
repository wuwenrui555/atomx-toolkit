"""Typer root CLI for atomx-toolkit."""

import typer

from atomx_toolkit import __version__
from atomx_toolkit.transfer.cli import app as transfer_app

app = typer.Typer(
    name="atomx-toolkit",
    help="AtoMx SFTP transfer with integrity check and email reporting.",
    no_args_is_help=True,
)
app.add_typer(transfer_app, name="transfer")


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(f"atomx-toolkit {__version__}")
        raise typer.Exit()


@app.callback()
def main(
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
    _ = verbose


if __name__ == "__main__":
    app()
