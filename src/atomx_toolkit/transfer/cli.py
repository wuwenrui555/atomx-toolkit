"""Transfer Typer subcommand group: run / batch / plan."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, cast

import typer
from jianglab_name_standard import CosmxRunName, NameValidationError
from rich.console import Console

from atomx_toolkit._logging import batch_log_path, setup_logging
from atomx_toolkit.config import ConfigError, load_config
from atomx_toolkit.notify.dispatch import (
    dispatch_batch_report,
    dispatch_transfer_report,
)
from atomx_toolkit.notify.events import (
    BatchItem,
    BatchReport,
    TransferReport,
)
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
from atomx_toolkit.transfer.lock import read_lock
from atomx_toolkit.transfer.md5 import assert_md5sum_available
from atomx_toolkit.transfer.pipeline import run_pipeline

app = typer.Typer(name="transfer", no_args_is_help=True, help="SFTP transfer commands.")
console = Console(stderr=True)
logger = logging.getLogger(__name__)


def _default_config_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "config.toml"


def _default_sftp_env_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "sftp.env"


def _default_smtp_env_path() -> Path:
    return Path.home() / ".config" / "atomx-toolkit" / "smtp.env"


def _verbose(ctx: typer.Context) -> int:
    obj = ctx.obj
    if not isinstance(obj, dict):
        return 0
    value = cast(dict[str, Any], obj).get("verbose", 0)
    return int(value) if isinstance(value, int) else 0


@app.command("run")
def run_cmd(
    ctx: typer.Context,
    name_remote: Annotated[str, typer.Argument(help="Remote study directory name")],
    name_local: Annotated[str, typer.Argument(help="Local destination directory name")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Download a single study, with double-MD5 verification."""
    try:
        CosmxRunName(name_local)
    except NameValidationError as exc:
        raise typer.BadParameter(
            f"[{exc.rule_id}] {exc.message}\nhint: {exc.hint}",
            param_hint="'NAME_LOCAL'",
        ) from exc
    cfg_path = config or _default_config_path()
    smtp_env_path = _default_smtp_env_path()
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
        assert_md5sum_available()
    except FileNotFoundError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    log_path = cfg.paths.log_root / name_local / f"{name_local}.log"
    setup_logging(log_path, verbose=_verbose(ctx))

    started = datetime.now(UTC)
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
        completed = datetime.now(UTC)
        report = TransferReport(
            name_remote=name_remote,
            name_local=name_local,
            status="failed",
            started_at=started,
            completed_at=completed,
            file_count=None,
            total_bytes=None,
            failure_phase=type(exc).__name__,
            failure_message=str(exc),
            log_path=log_path,
        )
        dispatch_transfer_report(report, cfg=cfg, smtp_env=smtp_env_path)
        console.print(f"[red]transfer failed:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    except KeyboardInterrupt:
        completed = datetime.now(UTC)
        logger.warning("transfer interrupted by user")
        report = TransferReport(
            name_remote=name_remote,
            name_local=name_local,
            status="failed",
            started_at=started,
            completed_at=completed,
            file_count=None,
            total_bytes=None,
            failure_phase="interrupted",
            failure_message="KeyboardInterrupt",
            log_path=log_path,
        )
        dispatch_transfer_report(report, cfg=cfg, smtp_env=smtp_env_path)
        console.print("[yellow]interrupted[/yellow]")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        completed = datetime.now(UTC)
        logger.exception("unexpected runtime error in transfer run")
        report = TransferReport(
            name_remote=name_remote,
            name_local=name_local,
            status="failed",
            started_at=started,
            completed_at=completed,
            file_count=None,
            total_bytes=None,
            failure_phase="runtime_error",
            failure_message=f"{type(exc).__name__}: {exc}",
            log_path=log_path,
        )
        dispatch_transfer_report(report, cfg=cfg, smtp_env=smtp_env_path)
        console.print(f"[red]unexpected error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    if result.status == "skipped_already_complete":
        console.print(f"[yellow]already complete:[/yellow] {name_local}")
        return
    report = TransferReport(
        name_remote=name_remote,
        name_local=name_local,
        status="success",
        started_at=result.started_at,
        completed_at=result.completed_at,
        file_count=result.file_count,
        total_bytes=result.total_bytes,
        failure_phase=None,
        failure_message=None,
        log_path=log_path,
    )
    dispatch_transfer_report(report, cfg=cfg, smtp_env=smtp_env_path)
    console.print(f"[green]ok:[/green] {name_local} ({result.file_count} files)")


@app.command("batch")
def batch_cmd(
    ctx: typer.Context,
    jobs_tsv: Annotated[Path, typer.Argument(help="jobs.tsv path")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Run a batch of studies sequentially from a 2-column TSV."""
    cfg_path = config or _default_config_path()
    smtp_env_path = _default_smtp_env_path()
    try:
        cfg = load_config(cfg_path)
        creds = load_sftp_credentials(_default_sftp_env_path())
        jobs = parse_jobs_tsv(jobs_tsv)
    except (ConfigError, SftpCredentialsError, JobsTsvError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc
    try:
        assert_md5sum_available()
    except FileNotFoundError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    log_path = batch_log_path(cfg.paths.log_root)
    setup_logging(log_path, verbose=_verbose(ctx))

    plan = classify_jobs(jobs, log_root=cfg.paths.log_root, backup_root=cfg.paths.backup_root)
    try:
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
    except KeyboardInterrupt:
        logger.warning("batch interrupted by user before run_batch returned")
        console.print("[yellow]interrupted[/yellow]")
        raise typer.Exit(code=1) from None
    except Exception as exc:
        logger.exception("unexpected runtime error in transfer batch")
        console.print(f"[red]unexpected error:[/red] {exc}")
        raise typer.Exit(code=3) from exc

    for item in result.items:
        if item.status not in ("succeeded", "failed"):
            continue
        if item.started_at is None or item.completed_at is None:
            continue
        per_study_status = "success" if item.status == "succeeded" else "failed"
        per_study_log = cfg.paths.log_root / item.name_local / f"{item.name_local}.log"
        per_study_report = TransferReport(
            name_remote=item.name_remote,
            name_local=item.name_local,
            status=per_study_status,
            started_at=item.started_at,
            completed_at=item.completed_at,
            file_count=item.file_count,
            total_bytes=item.total_bytes,
            failure_phase=item.failure_phase,
            failure_message=item.failure_message,
            log_path=per_study_log,
        )
        dispatch_transfer_report(per_study_report, cfg=cfg, smtp_env=smtp_env_path)

    _render_batch_summary(result)
    items = [BatchItem.from_result(i) for i in result.items]
    batch_report = BatchReport(
        jobs_tsv=jobs_tsv,
        started_at=result.started_at,
        completed_at=result.completed_at,
        items=items,
    )
    dispatch_batch_report(batch_report, cfg=cfg, smtp_env=smtp_env_path)
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
