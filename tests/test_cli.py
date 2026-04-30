"""End-to-end CLI smoke tests via subprocess."""

import subprocess
import sys


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "atomx_toolkit", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_version_flag_prints_version() -> None:
    result = _run("--version")
    assert result.returncode == 0
    assert "atomx-toolkit" in result.stdout
    assert "0.1.0" in result.stdout


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
