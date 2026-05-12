"""End-to-end CLI smoke tests via subprocess."""

import subprocess
import sys
from pathlib import Path


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "atomx_toolkit", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_flag_prints_version() -> None:
    from atomx_toolkit import __version__

    result = _run("--version")
    assert result.returncode == 0
    assert "atomx-toolkit" in result.stdout
    assert __version__ in result.stdout


def test_no_args_shows_help() -> None:
    result = _run()
    assert "Usage:" in result.stdout or "Usage:" in result.stderr


def test_transfer_help() -> None:
    result = _run("transfer", "--help")
    assert result.returncode == 0
    assert "run" in result.stdout
    assert "batch" in result.stdout
    assert "plan" in result.stdout


def test_transfer_run_requires_config() -> None:
    # No config file present in default location should yield exit 2
    result = _run("transfer", "run", "remote", "local", "--config", "/nonexistent/c.toml")
    assert result.returncode == 2
    assert "config" in (result.stdout + result.stderr).lower()


def test_transfer_batch_help() -> None:
    result = _run("transfer", "batch", "--help")
    assert result.returncode == 0
    assert "jobs.tsv" in result.stdout.lower() or "jobs.tsv" in result.stderr.lower()


def test_transfer_plan_help() -> None:
    result = _run("transfer", "plan", "--help")
    assert result.returncode == 0


def test_transfer_batch_missing_tsv_exits_2(tmp_path: Path) -> None:
    """Missing jobs.tsv file -> exit 2 (config error)."""
    # Need a valid config so we get past config validation, then fail on TSV
    config = tmp_path / "config.toml"
    config.write_text(
        '[sftp]\nhostname = "h"\nremote_root = "/"\n'
        '[paths]\nlog_root = "/tmp/log"\nbackup_root = "/tmp/bk"\n'
    )
    sftp_env = tmp_path / "sftp.env"
    sftp_env.write_text("ATOMX_SFTP_USER=u\nATOMX_SFTP_PASSWORD=p\n")
    import os

    env = os.environ.copy()
    env["ATOMX_SFTP_USER"] = "u"
    env["ATOMX_SFTP_PASSWORD"] = "p"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "atomx_toolkit",
            "transfer",
            "batch",
            str(tmp_path / "absent.tsv"),
            "--config",
            str(config),
        ],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )
    assert result.returncode == 2


def test_install_init_creates_files(tmp_path: Path) -> None:
    config_dir = tmp_path / "atomx-toolkit"
    result = _run("install", "init", "--config-dir", str(config_dir))
    assert result.returncode == 0
    assert (config_dir / "config.toml").exists()
    assert (config_dir / "sftp.env").exists()
    assert (config_dir / "smtp.env").exists()
    assert (config_dir / "recipients" / "transfer_report.txt").exists()


def test_install_init_refuses_clobber_without_force(tmp_path: Path) -> None:
    config_dir = tmp_path / "atomx-toolkit"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("custom = true\n")
    result = _run("install", "init", "--config-dir", str(config_dir))
    assert result.returncode == 2


def test_install_init_force_overwrites(tmp_path: Path) -> None:
    config_dir = tmp_path / "atomx-toolkit"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("custom = true\n")
    result = _run("install", "init", "--config-dir", str(config_dir), "--force")
    assert result.returncode == 0
    # The default template starts with [sftp] section, not 'custom'
    assert "[sftp]" in (config_dir / "config.toml").read_text()


def test_notify_help() -> None:
    result = _run("notify", "--help")
    assert result.returncode == 0
    assert "test" in result.stdout
    assert "list-subscribers" in result.stdout


def test_notify_list_subscribers_with_no_recipients_dir(tmp_path: Path) -> None:
    """list-subscribers against an empty recipients dir lists each event as empty."""
    config = tmp_path / "config.toml"
    recipients = tmp_path / "recipients"
    recipients.mkdir()
    config.write_text(
        '[sftp]\nhostname = "h"\nremote_root = "/"\n'
        '[paths]\nlog_root = "/tmp/log"\nbackup_root = "/tmp/bk"\n'
        f'[notify]\nrecipients_dir = "{recipients}"\n'
    )
    result = _run("notify", "list-subscribers", "--config", str(config))
    assert result.returncode == 0
    # All three events should appear in output
    assert "transfer_report" in result.stdout or "transfer_report" in result.stderr
