"""Typer root CLI for atomx-toolkit."""

import typer

from atomx_toolkit import __version__

app = typer.Typer(
    name="atomx-toolkit",
    help="AtoMx SFTP transfer with integrity check and email reporting.",
    no_args_is_help=True,
)


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
    # Subcommand groups will be mounted in later tasks.
    _ = verbose


if __name__ == "__main__":
    app()
