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
