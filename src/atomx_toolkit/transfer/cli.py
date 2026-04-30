"""Transfer Typer subcommand group: run / batch / plan."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from atomx_toolkit.config import ConfigError, load_config
from atomx_toolkit.transfer.batch import (
    BatchPlan,
    BatchRunResult,
    JobsTsvError,
    classify_jobs,
    parse_jobs_tsv,
    run_batch,
)
from atomx_toolkit.transfer.credentials import (
    SftpCredentialsError,
    load_sftp_credentials,
)
from atomx_toolkit.transfer.errors import LockHeldError, TransferError
from atomx_toolkit.transfer.pipeline import run_pipeline

app = typer.Typer(name="transfer", no_args_is_help=True, help="SFTP transfer commands.")
console = Console(stderr=True)
logger = logging.getLogger(__name__)


def _default_config_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "config.toml"


def _default_sftp_env_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "sftp.env"


@app.command("run")
def run_cmd(
    name_remote: Annotated[str, typer.Argument(help="Remote study directory name")],
    name_local: Annotated[str, typer.Argument(help="Local destination directory name")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Download a single study, with double-MD5 verification."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    try:
        creds = load_sftp_credentials(_default_sftp_env_path())
    except SftpCredentialsError as exc:
        console.print(f"[red]credential error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    try:
        result = run_pipeline(
            host=cfg.sftp.hostname,
            user=creds.user,
            password=creds.password,
            remote_root=cfg.sftp.remote_root,
            name_remote=name_remote,
            name_local=name_local,
            log_root=cfg.paths.log_root,
            backup_root=cfg.paths.backup_root,
        )
    except LockHeldError as exc:
        console.print(f"[red]lock held:[/red] {exc}")
        console.print(
            f"to retry, manually delete the lock at "
            f"{cfg.paths.backup_root / name_local / '.atomx-toolkit.lock'}"
        )
        raise typer.Exit(code=2) from exc
    except TransferError as exc:
        console.print(f"[red]transfer failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    if result.status == "skipped_already_complete":
        console.print(f"[yellow]already complete:[/yellow] {name_local}")
    else:
        console.print(f"[green]ok:[/green] {name_local} ({result.file_count} files)")


@app.command("batch")
def batch_cmd(
    jobs_tsv: Annotated[Path, typer.Argument(help="jobs.tsv path")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Run a batch of studies sequentially from a 2-column TSV."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
        creds = load_sftp_credentials(_default_sftp_env_path())
        jobs = parse_jobs_tsv(jobs_tsv)
    except (ConfigError, SftpCredentialsError, JobsTsvError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    plan = classify_jobs(jobs, log_root=cfg.paths.log_root, backup_root=cfg.paths.backup_root)
    result = run_batch(
        jobs=jobs,
        plan=plan,
        host=cfg.sftp.hostname,
        port=22,
        user=creds.user,
        password=creds.password,
        remote_root=cfg.sftp.remote_root,
        log_root=cfg.paths.log_root,
        backup_root=cfg.paths.backup_root,
        jobs_tsv_path=jobs_tsv,
    )
    _render_batch_summary(result)
    if result.any_failed or result.all_skipped_locked:
        raise typer.Exit(code=1)


@app.command("plan")
def plan_cmd(
    jobs_tsv: Annotated[Path, typer.Argument(help="jobs.tsv path")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Dry-run preview of which studies would run."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
        jobs = parse_jobs_tsv(jobs_tsv)
    except (ConfigError, JobsTsvError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    plan = classify_jobs(jobs, log_root=cfg.paths.log_root, backup_root=cfg.paths.backup_root)
    _render_plan(plan, cfg.paths.log_root, cfg.paths.backup_root)


def _render_plan(plan: BatchPlan, log_root: Path, backup_root: Path) -> None:
    total = len(plan.complete_already) + len(plan.skipped_locked) + len(plan.pending)
    console.print(f"Plan ({total} entries):")
    if plan.complete_already:
        console.print(f"  complete_already ({len(plan.complete_already)})")
        for _r, loc in plan.complete_already:
            ts = (log_root / loc / "index" / "md5sum_pass").read_text().strip()
            console.print(f"    - {loc} (completed {ts})")
    if plan.skipped_locked:
        console.print(f"  skipped_locked ({len(plan.skipped_locked)})")
        for _r, loc in plan.skipped_locked:
            from atomx_toolkit.transfer.lock import read_lock

            payload = read_lock(backup_root / loc)
            desc = (
                f"lock from {payload.get('hostname', '?')} pid {payload.get('pid', '?')} "
                f"at {payload.get('started_at', '?')}"
                if payload
                else "lock present"
            )
            console.print(f"    - {loc}\n        {desc}")
    if plan.pending:
        console.print(f"  pending ({len(plan.pending)})")
        for _r, loc in plan.pending:
            console.print(f"    - {loc}")


def _render_batch_summary(result: BatchRunResult) -> None:
    succeeded = sum(1 for i in result.items if i.status == "succeeded")
    complete = sum(1 for i in result.items if i.status == "complete_already")
    locked = sum(1 for i in result.items if i.status == "skipped_locked")
    failed = sum(1 for i in result.items if i.status == "failed")
    console.print(
        f"batch finished: succeeded={succeeded} complete_already={complete} "
        f"skipped_locked={locked} failed={failed}"
    )
