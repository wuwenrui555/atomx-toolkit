# atomx-toolkit v0.1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or executing-plans-test-first to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a public `atomx-toolkit` Python package that downloads study directories from the AtoMx SFTP server with double-download MD5 integrity checks, per-file atomic writes, study-level crash locks, and email reporting — to fusion-toolkit's quality bar.

**Architecture:** Three subsystems (`transfer`, `notify`, `install`) under a Typer CLI shell. Each subsystem has clean module boundaries: `transfer` owns the SFTP pipeline; `notify` consumes `TransferReport` / `BatchReport` dataclasses and sends email; `install` writes config templates. Wiring (event dispatch, exit codes) lives in the CLI layer only.

**Tech Stack:** Python 3.12+, `paramiko>=3,<5`, `typer>=0.12`, `rich>=15`. Build: `uv_build`. Tests: `pytest`, `aiosmtpd` (mock SMTP), `paramiko.ServerInterface` (real local SFTP). Lint/type: `ruff`, `pyright` strict. Pre-commit + GitHub Actions CI.

**Spec:** `docs/superpowers/specs/2026-04-30-atomx-toolkit-design.md`. Read it before starting.

---

## File Structure

```
atomx-toolkit/
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore                          (already exists)
├── .pre-commit-config.yaml
├── .github/workflows/ci.yml
├── docs/
│   ├── setup-host.md
│   ├── transfer-pipeline.md
│   ├── superpowers/specs/...           (already committed)
│   └── superpowers/plans/...           (this file)
├── src/atomx_toolkit/
│   ├── __init__.py                     # __version__
│   ├── py.typed                        # empty marker
│   ├── config.py                       # TOML loader → Config dataclass
│   ├── cli.py                          # Typer root, mounts subgroups
│   ├── transfer/
│   │   ├── __init__.py
│   │   ├── errors.py                   # TransferError hierarchy
│   │   ├── credentials.py              # SFTP env-or-dotenv chain
│   │   ├── md5.py                      # md5sum subprocess + dict diff
│   │   ├── lock.py                     # atomic acquire/release/check
│   │   ├── sftp.py                     # paramiko wrapper, walk_files, download_file
│   │   ├── pipeline.py                 # 6-phase per-study orchestrator + guard
│   │   ├── batch.py                    # jobs.tsv parser + batch runner + plan
│   │   └── cli.py                      # transfer Typer group
│   ├── notify/
│   │   ├── __init__.py
│   │   ├── credentials.py              # SMTP env-or-dotenv chain
│   │   ├── recipients.py               # per-event recipient resolution
│   │   ├── events.py                   # dataclasses + body formatting
│   │   ├── send.py                     # smtplib + toolkit_error dedup state
│   │   ├── handler.py                  # logging.Handler → toolkit_error
│   │   ├── dispatch.py                 # bridge: TransferReport / BatchReport → email
│   │   └── cli.py                      # notify Typer group
│   └── install/
│       ├── __init__.py
│       ├── init.py                     # template writer + pre-checks
│       └── cli.py                      # install Typer group
└── tests/
    ├── __init__.py
    ├── conftest.py                     # shared fixtures (tmp config dir)
    ├── test_cli.py                     # subprocess invocations
    ├── test_config.py
    ├── test_transfer/
    │   ├── __init__.py
    │   ├── conftest.py                 # local SFTP server fixture
    │   ├── test_errors.py
    │   ├── test_credentials.py
    │   ├── test_md5.py
    │   ├── test_lock.py
    │   ├── test_sftp.py
    │   ├── test_pipeline.py
    │   └── test_batch.py
    ├── test_notify/
    │   ├── __init__.py
    │   ├── conftest.py                 # aiosmtpd fixture
    │   ├── test_credentials.py
    │   ├── test_recipients.py
    │   ├── test_events.py
    │   ├── test_send.py
    │   └── test_handler.py
    └── test_install/
        ├── __init__.py
        └── test_init.py
```

---

## Conventions used throughout this plan

- **TDD always:** every functional task is "write failing test → run → see fail → write impl → run → see pass → commit". No exceptions.
- **One commit per task** unless the task explicitly calls for multiple. Commit message format: `<type>: <subject>` where `<type>` is `feat`, `test`, `refactor`, `docs`, `chore`.
- **Exact paths:** every file path is absolute relative to the repo root.
- **Verification commands:** every step that says "run X" gives the exact command and expected outcome.
- **Pyright strict** is on from Task 1. Resolve type errors as you go; do not defer.
- **Don't write em-dashes in commit messages or PR descriptions** (per user's global CLAUDE.md). Em-dashes inside source / doc files are fine.

---

## Task 1: Project bootstrap

**Files:**
- Create: `pyproject.toml`
- Create: `LICENSE`
- Create: `README.md` (minimal stub; expanded in Task 16)
- Create: `.pre-commit-config.yaml`
- Create: `src/atomx_toolkit/__init__.py`
- Create: `src/atomx_toolkit/py.typed` (empty)
- Create: `src/atomx_toolkit/cli.py` (skeleton)
- Create: `tests/__init__.py` (empty)
- Create: `tests/conftest.py` (skeleton)
- Create: `tests/test_cli.py`

- [ ] **Step 1.1: Write `pyproject.toml`**

```toml
[project]
name = "atomx-toolkit"
version = "0.1.0"
description = "AtoMx SFTP transfer with double-download integrity check and email reporting."
readme = "README.md"
authors = [{ name = "wuwenrui555", email = "wuwenruiwwr@outlook.com" }]
requires-python = ">=3.12"
license = { text = "MIT" }
dependencies = [
    "paramiko>=3,<5",
    "typer>=0.12",
    "rich>=15.0.0",
]

[project.scripts]
atomx-toolkit = "atomx_toolkit.cli:app"

[dependency-groups]
dev = [
    "pytest>=8",
    "pytest-cov>=5",
    "ruff>=0.9",
    "pyright>=1.1.390",
    "pre-commit>=4",
    "aiosmtpd>=1.4",
]

[build-system]
requires = ["uv_build>=0.10.10,<0.11.0"]
build-backend = "uv_build"

[tool.ruff]
line-length = 100
target-version = "py312"

[tool.ruff.lint]
select = ["E", "W", "F", "I", "B", "UP", "SIM", "RUF"]

[tool.ruff.lint.per-file-ignores]
"tests/**/*.py" = ["B011"]

[tool.ruff.format]
quote-style = "double"

[tool.pyright]
include = ["src", "tests"]
pythonVersion = "3.12"
typeCheckingMode = "strict"
reportMissingTypeStubs = false

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-ra --strict-markers"
```

- [ ] **Step 1.2: Write `LICENSE` (MIT, current year)**

```
MIT License

Copyright (c) 2026 wuwenrui555

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 1.3: Write minimal `README.md`**

```markdown
# atomx-toolkit

AtoMx SFTP transfer with double-download integrity verification and email reporting.

> v0.1.0 — work in progress. See `docs/superpowers/specs/2026-04-30-atomx-toolkit-design.md` for design.

## Install

```bash
pip install git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.1.0
```

## Quick start

```bash
atomx-toolkit install init
# edit ~/.config/atomx-toolkit/{config.toml, sftp.env, smtp.env}
atomx-toolkit transfer run <name_remote> <name_local>
```
```

- [ ] **Step 1.4: Write `.pre-commit-config.yaml`**

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pyright
        name: pyright
        entry: uv run pyright
        language: system
        pass_filenames: false
        types: [python]
```

- [ ] **Step 1.5: Write package skeleton**

`src/atomx_toolkit/__init__.py`:
```python
"""atomx-toolkit: AtoMx SFTP transfer with integrity check and email reporting."""

__version__ = "0.1.0"
```

`src/atomx_toolkit/py.typed`: empty file (`touch` it).

`src/atomx_toolkit/cli.py`:
```python
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
```

- [ ] **Step 1.6: Write the failing test**

`tests/conftest.py`:
```python
"""Shared pytest fixtures."""
```

`tests/test_cli.py`:
```python
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
```

For `python -m atomx_toolkit` to work, also create:

`src/atomx_toolkit/__main__.py`:
```python
from atomx_toolkit.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 1.7: Run tests, expect failures**

```bash
uv sync
uv run pytest tests/test_cli.py -v
```

Expected: tests fail or pass — depends on whether `uv sync` + project script picked up the package. If `python -m atomx_toolkit` works, tests pass; otherwise, fix `__main__.py` import.

- [ ] **Step 1.8: Verify lint and type pass**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/ tests/
```

All three must succeed. Fix any issues inline.

- [ ] **Step 1.9: Commit**

```bash
git add pyproject.toml LICENSE README.md .pre-commit-config.yaml src/ tests/
git commit -m "feat: bootstrap atomx-toolkit package with CLI skeleton"
```

---

## Task 2: Config loading (`atomx_toolkit/config.py`)

**Files:**
- Create: `src/atomx_toolkit/config.py`
- Create: `tests/test_config.py`

The Config dataclass is the single source of truth for parsed
`config.toml`. Both `transfer` and `notify` consume it.

- [ ] **Step 2.1: Write the failing test**

`tests/test_config.py`:
```python
"""Tests for atomx_toolkit.config TOML loader."""

from pathlib import Path

import pytest

from atomx_toolkit.config import Config, ConfigError, load_config


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_load_minimal_valid_config(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "config.toml",
        """
        [sftp]
        hostname = "na.export.atomx.nanostring.com"
        remote_root = "/"

        [paths]
        log_root = "/data/log"
        backup_root = "/data/backup"
        """,
    )
    cfg = load_config(cfg_path)
    assert isinstance(cfg, Config)
    assert cfg.sftp.hostname == "na.export.atomx.nanostring.com"
    assert cfg.sftp.remote_root == "/"
    assert cfg.paths.log_root == Path("/data/log")
    assert cfg.paths.backup_root == Path("/data/backup")
    assert cfg.notify.enabled is True
    assert cfg.notify.toolkit_error_cooldown_seconds == 300


def test_missing_required_key_raises(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "config.toml",
        """
        [sftp]
        hostname = "h"

        [paths]
        log_root = "/x"
        """,  # missing backup_root
    )
    with pytest.raises(ConfigError, match="backup_root"):
        load_config(cfg_path)


def test_malformed_toml_raises(tmp_path: Path) -> None:
    cfg_path = _write(tmp_path / "config.toml", "not = valid = toml")
    with pytest.raises(ConfigError, match="parse"):
        load_config(cfg_path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "absent.toml")


def test_unknown_section_ignored(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "config.toml",
        """
        [sftp]
        hostname = "h"
        remote_root = "/"

        [paths]
        log_root = "/x"
        backup_root = "/y"

        [some_future_section]
        new_option = 42
        """,
    )
    cfg = load_config(cfg_path)
    assert cfg.sftp.hostname == "h"


def test_notify_overrides(tmp_path: Path) -> None:
    cfg_path = _write(
        tmp_path / "config.toml",
        """
        [sftp]
        hostname = "h"
        remote_root = "/"
        [paths]
        log_root = "/x"
        backup_root = "/y"
        [notify]
        enabled = false
        toolkit_error_cooldown_seconds = 60
        recipients_dir = "/custom/recipients"
        """,
    )
    cfg = load_config(cfg_path)
    assert cfg.notify.enabled is False
    assert cfg.notify.toolkit_error_cooldown_seconds == 60
    assert cfg.notify.recipients_dir == Path("/custom/recipients")
```

- [ ] **Step 2.2: Run, expect import failure**

```bash
uv run pytest tests/test_config.py -v
```

Expected: ImportError on `atomx_toolkit.config`.

- [ ] **Step 2.3: Implement `atomx_toolkit/config.py`**

```python
"""TOML configuration loader for atomx-toolkit."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


class ConfigError(Exception):
    """Raised on any configuration loading or validation failure."""


@dataclass(frozen=True)
class SftpConfig:
    hostname: str
    remote_root: str


@dataclass(frozen=True)
class PathsConfig:
    log_root: Path
    backup_root: Path


@dataclass(frozen=True)
class NotifyConfig:
    enabled: bool = True
    toolkit_error_cooldown_seconds: int = 300
    recipients_dir: Path | None = None


@dataclass(frozen=True)
class Config:
    sftp: SftpConfig
    paths: PathsConfig
    notify: NotifyConfig = field(default_factory=NotifyConfig)


def load_config(path: Path) -> Config:
    """Load and validate a config.toml file. Raises ConfigError on any problem."""
    if not path.exists():
        raise ConfigError(f"config file not found: {path}")
    try:
        with path.open("rb") as f:
            data: dict[str, Any] = tomllib.load(f)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"failed to parse {path}: {exc}") from exc

    sftp = _require_section(data, "sftp", path)
    paths = _require_section(data, "paths", path)

    sftp_cfg = SftpConfig(
        hostname=_require_str(sftp, "hostname", "[sftp].hostname", path),
        remote_root=_str_or_default(sftp, "remote_root", "/"),
    )
    paths_cfg = PathsConfig(
        log_root=Path(_require_str(paths, "log_root", "[paths].log_root", path)),
        backup_root=Path(_require_str(paths, "backup_root", "[paths].backup_root", path)),
    )
    notify_section = data.get("notify", {})
    if not isinstance(notify_section, dict):
        raise ConfigError(f"{path}: [notify] must be a table")
    recipients_dir_str = notify_section.get("recipients_dir")
    notify_cfg = NotifyConfig(
        enabled=bool(notify_section.get("enabled", True)),
        toolkit_error_cooldown_seconds=int(
            notify_section.get("toolkit_error_cooldown_seconds", 300)
        ),
        recipients_dir=Path(recipients_dir_str) if recipients_dir_str else None,
    )
    return Config(sftp=sftp_cfg, paths=paths_cfg, notify=notify_cfg)


def _require_section(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    section = data.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: missing required section [{name}]")
    return section


def _require_str(section: dict[str, Any], key: str, label: str, path: Path) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: missing required key {label}")
    return value


def _str_or_default(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key)
    return value if isinstance(value, str) and value else default
```

- [ ] **Step 2.4: Run tests, expect pass**

```bash
uv run pytest tests/test_config.py -v
```

All 6 tests pass.

- [ ] **Step 2.5: Lint + type check**

```bash
uv run ruff check src/atomx_toolkit/config.py tests/test_config.py
uv run pyright src/atomx_toolkit/config.py tests/test_config.py
```

Both clean.

- [ ] **Step 2.6: Commit**

```bash
git add src/atomx_toolkit/config.py tests/test_config.py
git commit -m "feat: TOML config loader with strict validation"
```

---

## Task 3: Transfer errors hierarchy + SFTP credentials

**Files:**
- Create: `src/atomx_toolkit/transfer/__init__.py`
- Create: `src/atomx_toolkit/transfer/errors.py`
- Create: `src/atomx_toolkit/transfer/credentials.py`
- Create: `tests/test_transfer/__init__.py`
- Create: `tests/test_transfer/test_errors.py`
- Create: `tests/test_transfer/test_credentials.py`

- [ ] **Step 3.1: Write failing tests for errors module**

`tests/test_transfer/__init__.py`: empty file.

`tests/test_transfer/test_errors.py`:
```python
"""Smoke tests for the transfer exception hierarchy."""

import pytest

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    JobsTsvError,
    LockHeldError,
    RemoteListInconsistent,
    TransferError,
)


def test_all_subclasses_of_transfer_error_except_jobs_tsv() -> None:
    assert issubclass(RemoteListInconsistent, TransferError)
    assert issubclass(IntegrityError, TransferError)
    assert issubclass(LockHeldError, TransferError)
    # JobsTsvError is for batch input parsing, not pipeline failures
    assert not issubclass(JobsTsvError, TransferError)


def test_lock_held_error_carries_payload() -> None:
    payload = {"hostname": "h", "pid": 1, "started_at": "x", "name_remote": "y"}
    err = LockHeldError(payload)
    assert err.lock_content == payload
    assert "h" in str(err)
    assert "1" in str(err)


def test_transfer_error_can_be_raised() -> None:
    with pytest.raises(TransferError):
        raise IntegrityError("md5 mismatch on 3 files")
```

- [ ] **Step 3.2: Run, expect ImportError**

```bash
uv run pytest tests/test_transfer/test_errors.py -v
```

- [ ] **Step 3.3: Implement errors module**

`src/atomx_toolkit/transfer/__init__.py`:
```python
"""Transfer subsystem: SFTP download with integrity check and resume."""
```

`src/atomx_toolkit/transfer/errors.py`:
```python
"""Exception hierarchy for the transfer subsystem."""

from __future__ import annotations

from typing import Any


class TransferError(Exception):
    """Base for all per-study pipeline failures."""


class RemoteListInconsistent(TransferError):
    """Phase 1 returned different file sets across two list attempts."""


class IntegrityError(TransferError):
    """Phase 6 detected a checksum mismatch or missing file."""


class LockHeldError(TransferError):
    """Pipeline entry found an existing .atomx-toolkit.lock."""

    def __init__(self, lock_content: dict[str, Any]) -> None:
        self.lock_content = lock_content
        super().__init__(
            f"lock held by {lock_content.get('hostname', '?')} "
            f"pid {lock_content.get('pid', '?')} "
            f"since {lock_content.get('started_at', '?')}"
        )


class JobsTsvError(Exception):
    """Failure parsing a jobs.tsv batch input file."""
```

- [ ] **Step 3.4: Write failing tests for credentials**

`tests/test_transfer/test_credentials.py`:
```python
"""Tests for SFTP credential loading (env > dotenv > error)."""

from pathlib import Path

import pytest

from atomx_toolkit.transfer.credentials import (
    SftpCredentials,
    SftpCredentialsError,
    load_sftp_credentials,
)


def test_env_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOMX_SFTP_USER", "from_env")
    monkeypatch.setenv("ATOMX_SFTP_PASSWORD", "p_env")
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text("ATOMX_SFTP_USER=from_dotenv\nATOMX_SFTP_PASSWORD=p_dotenv\n")
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="from_env", password="p_env")


def test_dotenv_used_when_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text(
        "# comment\n"
        "ATOMX_SFTP_USER=alice\n"
        "export ATOMX_SFTP_PASSWORD=secret\n"
        "\n"
    )
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="alice", password="secret")


def test_missing_both_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    with pytest.raises(SftpCredentialsError, match="not found"):
        load_sftp_credentials(tmp_path / "absent.env")


def test_partial_credentials_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ATOMX_SFTP_USER", "alice")
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    with pytest.raises(SftpCredentialsError, match="ATOMX_SFTP_PASSWORD"):
        load_sftp_credentials(tmp_path / "absent.env")


def test_dotenv_quoted_values(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ATOMX_SFTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SFTP_PASSWORD", raising=False)
    dotenv = tmp_path / "sftp.env"
    dotenv.write_text('ATOMX_SFTP_USER="alice"\nATOMX_SFTP_PASSWORD=\'p with spaces\'\n')
    creds = load_sftp_credentials(dotenv)
    assert creds == SftpCredentials(user="alice", password="p with spaces")
```

- [ ] **Step 3.5: Run, expect ImportError**

```bash
uv run pytest tests/test_transfer/test_credentials.py -v
```

- [ ] **Step 3.6: Implement credentials**

`src/atomx_toolkit/transfer/credentials.py`:
```python
"""Load SFTP credentials from environment or a dotenv-style file."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


class SftpCredentialsError(Exception):
    """Failure to resolve SFTP credentials."""


@dataclass(frozen=True)
class SftpCredentials:
    user: str
    password: str


_USER_KEY = "ATOMX_SFTP_USER"
_PASS_KEY = "ATOMX_SFTP_PASSWORD"


def load_sftp_credentials(dotenv_path: Path) -> SftpCredentials:
    """Resolve SFTP credentials. Env wins; dotenv is fallback.

    Either both keys present in env, or both in dotenv. Mixed sources
    are rejected to avoid the half-configured operator confusion.
    """
    env_user = os.environ.get(_USER_KEY)
    env_pass = os.environ.get(_PASS_KEY)
    if env_user and env_pass:
        return SftpCredentials(user=env_user, password=env_pass)
    if env_user or env_pass:
        missing = _PASS_KEY if env_user else _USER_KEY
        raise SftpCredentialsError(
            f"{missing} present in env but its counterpart is missing"
        )

    if not dotenv_path.exists():
        raise SftpCredentialsError(
            f"SFTP credentials not found: env vars {_USER_KEY}/{_PASS_KEY} unset "
            f"and dotenv file does not exist: {dotenv_path}"
        )
    parsed = _parse_dotenv(dotenv_path)
    user = parsed.get(_USER_KEY)
    password = parsed.get(_PASS_KEY)
    if not user or not password:
        missing = _USER_KEY if not user else _PASS_KEY
        raise SftpCredentialsError(f"{dotenv_path}: missing or empty {missing}")
    return SftpCredentials(user=user, password=password)


def _parse_dotenv(path: Path) -> dict[str, str]:
    """Minimal dotenv parser: KEY=VALUE per line, # comments, optional `export `."""
    result: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export ") :].lstrip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # Strip surrounding single or double quotes
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        result[key] = value
    return result
```

- [ ] **Step 3.7: Run all transfer tests, expect pass**

```bash
uv run pytest tests/test_transfer/ -v
```

- [ ] **Step 3.8: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/ tests/test_transfer/
uv run pyright src/atomx_toolkit/transfer/ tests/test_transfer/
git add src/atomx_toolkit/transfer/ tests/test_transfer/
git commit -m "feat: transfer error hierarchy and SFTP credential chain"
```

---

## Task 4: MD5 module

**Files:**
- Create: `src/atomx_toolkit/transfer/md5.py`
- Create: `tests/test_transfer/test_md5.py`

- [ ] **Step 4.1: Write failing test**

`tests/test_transfer/test_md5.py`:
```python
"""Tests for md5sum subprocess wrapper and dict-based comparison."""

import csv
from pathlib import Path

import pytest

from atomx_toolkit.transfer.md5 import (
    Md5Comparison,
    compute_md5_tree,
    compare_md5_files,
    write_md5_file,
)


def _seed(root: Path, files: dict[str, bytes]) -> None:
    for relpath, content in files.items():
        full = root / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)


def test_compute_md5_tree_returns_relpath_to_hash(tmp_path: Path) -> None:
    _seed(tmp_path, {"a.txt": b"hello", "sub/b.txt": b"world"})
    result = compute_md5_tree(tmp_path)
    assert set(result.keys()) == {"a.txt", "sub/b.txt"}
    assert result["a.txt"] == "5d41402abc4b2a76b9719d911017c592"  # md5("hello")


def test_compute_md5_tree_empty_dir(tmp_path: Path) -> None:
    result = compute_md5_tree(tmp_path)
    assert result == {}


def test_compute_md5_tree_missing_path(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        compute_md5_tree(tmp_path / "absent")


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path, {"a.txt": b"data"})
    md5_dict = compute_md5_tree(tmp_path)
    out = tmp_path / "md5sum.txt"
    write_md5_file(md5_dict, out)
    lines = out.read_text(encoding="utf-8").splitlines()
    assert any(line.endswith("  a.txt") for line in lines)


def test_compare_all_match(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    _seed(a, {"f.txt": b"same"})
    _seed(b, {"f.txt": b"same"})
    md5_a = tmp_path / "md5_a.txt"
    md5_b = tmp_path / "md5_b.txt"
    write_md5_file(compute_md5_tree(a), md5_a)
    write_md5_file(compute_md5_tree(b), md5_b)
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp == Md5Comparison(matched=1, mismatched=0, missing_in_1=0, missing_in_2=0)
    assert not diff_csv.exists()  # no diff CSV when fully matched


def test_compare_with_mismatch(tmp_path: Path) -> None:
    md5_a = tmp_path / "a.txt"
    md5_b = tmp_path / "b.txt"
    md5_a.write_text("aaaaaaaa11111111aaaaaaaa11111111  same.bin\n")
    md5_b.write_text("aaaaaaaa11111111aaaaaaaa22222222  same.bin\n")
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp.mismatched == 1
    assert diff_csv.exists()
    rows = list(csv.DictReader(diff_csv.open()))
    assert rows[0]["status"] == "mismatch"
    assert rows[0]["file"] == "same.bin"


def test_compare_with_missing(tmp_path: Path) -> None:
    md5_a = tmp_path / "a.txt"
    md5_b = tmp_path / "b.txt"
    md5_a.write_text("aaaaaaaa11111111aaaaaaaa11111111  only_in_1.bin\n")
    md5_b.write_text("bbbbbbbb22222222bbbbbbbb22222222  only_in_2.bin\n")
    diff_csv = tmp_path / "diff.csv"
    cmp = compare_md5_files(md5_a, md5_b, diff_csv)
    assert cmp.missing_in_1 == 1
    assert cmp.missing_in_2 == 1
    rows = sorted(csv.DictReader(diff_csv.open()), key=lambda r: r["file"])
    assert {r["status"] for r in rows} == {"missing_in_1", "missing_in_2"}


def test_compute_handles_non_ascii_filenames(tmp_path: Path) -> None:
    _seed(tmp_path, {"中文.bin": b"x"})
    result = compute_md5_tree(tmp_path)
    assert "中文.bin" in result
```

- [ ] **Step 4.2: Run, expect import failure**

```bash
uv run pytest tests/test_transfer/test_md5.py -v
```

- [ ] **Step 4.3: Implement md5 module**

`src/atomx_toolkit/transfer/md5.py`:
```python
"""MD5 checksums via the system `md5sum` binary, plus a dict-based diff."""

from __future__ import annotations

import csv
import logging
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Md5Comparison:
    matched: int
    mismatched: int
    missing_in_1: int
    missing_in_2: int

    @property
    def all_match(self) -> bool:
        return self.mismatched == 0 and self.missing_in_1 == 0 and self.missing_in_2 == 0


def assert_md5sum_available() -> None:
    """Raise FileNotFoundError if the `md5sum` binary is not on PATH."""
    if shutil.which("md5sum") is None:
        raise FileNotFoundError(
            "the `md5sum` binary is required (install GNU coreutils)"
        )


def compute_md5_tree(root: Path) -> dict[str, str]:
    """Return {relpath_str: md5hash} for every regular file under root.

    Empty dir returns {}. Missing root raises FileNotFoundError.
    Files are processed one per `md5sum` invocation; this is slower
    than a batched call but keeps the per-file error handling clean.
    """
    if not root.exists():
        raise FileNotFoundError(f"path not found: {root}")
    if root.is_file():
        files = [root]
        relbase = root.parent
    else:
        files = sorted(p for p in root.rglob("*") if p.is_file())
        relbase = root
    result: dict[str, str] = {}
    for file_path in files:
        try:
            md5 = _md5_one(file_path)
        except subprocess.CalledProcessError as exc:
            logger.error("md5sum failed for %s: %s", file_path, exc)
            continue
        rel = file_path.relative_to(relbase).as_posix()
        result[rel] = md5
    return result


def _md5_one(path: Path) -> str:
    proc = subprocess.run(
        ["md5sum", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.split()[0]


def write_md5_file(md5_dict: dict[str, str], output: Path) -> None:
    """Write a standard md5sum-format file: '<hash>  <relpath>\\n' per line."""
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        for relpath, md5 in sorted(md5_dict.items()):
            f.write(f"{md5}  {relpath}\n")


def read_md5_file(path: Path) -> dict[str, str]:
    """Parse a md5sum-format file back into {relpath: hash}."""
    result: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line:
            continue
        # md5sum format: '<hash>  <relpath>'  (two spaces, but be tolerant)
        parts = line.split(maxsplit=1)
        if len(parts) != 2:
            continue
        result[parts[1].lstrip()] = parts[0]
    return result


def compare_md5_files(
    md5_path_1: Path, md5_path_2: Path, diff_csv: Path
) -> Md5Comparison:
    """Compare two md5sum-format files. Write a diff CSV iff anything mismatches.

    The CSV has columns (file, md5_1, md5_2, status) where status is one of
    'mismatch', 'missing_in_1', 'missing_in_2'.
    """
    d1 = read_md5_file(md5_path_1)
    d2 = read_md5_file(md5_path_2)
    all_keys = sorted(set(d1) | set(d2))
    mismatched = 0
    missing_in_1 = 0
    missing_in_2 = 0
    matched = 0
    rows: list[dict[str, str]] = []
    for key in all_keys:
        h1 = d1.get(key)
        h2 = d2.get(key)
        if h1 is None:
            missing_in_1 += 1
            rows.append(
                {"file": key, "md5_1": "", "md5_2": h2 or "", "status": "missing_in_1"}
            )
        elif h2 is None:
            missing_in_2 += 1
            rows.append(
                {"file": key, "md5_1": h1, "md5_2": "", "status": "missing_in_2"}
            )
        elif h1 == h2:
            matched += 1
        else:
            mismatched += 1
            rows.append(
                {"file": key, "md5_1": h1, "md5_2": h2, "status": "mismatch"}
            )
    if rows:
        diff_csv.parent.mkdir(parents=True, exist_ok=True)
        with diff_csv.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["file", "md5_1", "md5_2", "status"]
            )
            writer.writeheader()
            writer.writerows(rows)
    return Md5Comparison(
        matched=matched,
        mismatched=mismatched,
        missing_in_1=missing_in_1,
        missing_in_2=missing_in_2,
    )
```

- [ ] **Step 4.4: Run tests, expect pass**

```bash
uv run pytest tests/test_transfer/test_md5.py -v
```

- [ ] **Step 4.5: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/md5.py tests/test_transfer/test_md5.py
uv run pyright src/atomx_toolkit/transfer/md5.py tests/test_transfer/test_md5.py
git add src/atomx_toolkit/transfer/md5.py tests/test_transfer/test_md5.py
git commit -m "feat: md5 subprocess wrapper and dict-based comparison"
```

---

## Task 5: Lock module

**Files:**
- Create: `src/atomx_toolkit/transfer/lock.py`
- Create: `tests/test_transfer/test_lock.py`

- [ ] **Step 5.1: Write failing tests**

`tests/test_transfer/test_lock.py`:
```python
"""Tests for the study-level lock (atomic acquire, crash detection)."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from atomx_toolkit.transfer.errors import LockHeldError
from atomx_toolkit.transfer.lock import (
    LOCK_FILENAME,
    acquire_lock,
    read_lock,
    release_lock,
)


def test_acquire_creates_lock_file(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="study_x")
    lock_path = tmp_path / LOCK_FILENAME
    assert lock_path.exists()
    payload = json.loads(lock_path.read_text())
    assert payload["name_remote"] == "study_x"
    assert payload["pid"] > 0
    assert "started_at" in payload
    # started_at is parseable ISO 8601
    datetime.fromisoformat(payload["started_at"])


def test_acquire_when_already_held_raises_lock_held_error(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    with pytest.raises(LockHeldError) as ei:
        acquire_lock(tmp_path, name_remote="y")
    assert ei.value.lock_content["name_remote"] == "x"


def test_release_removes_lock(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    release_lock(tmp_path)
    assert not (tmp_path / LOCK_FILENAME).exists()


def test_release_when_already_gone_logs_but_does_not_raise(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # Lock never created
    with caplog.at_level("WARNING"):
        release_lock(tmp_path)
    assert any("lock" in rec.message.lower() for rec in caplog.records)


def test_read_lock_returns_payload(tmp_path: Path) -> None:
    acquire_lock(tmp_path, name_remote="x")
    payload = read_lock(tmp_path)
    assert payload is not None
    assert payload["name_remote"] == "x"


def test_read_lock_returns_none_when_absent(tmp_path: Path) -> None:
    assert read_lock(tmp_path) is None


def test_acquire_creates_parent_dir_if_missing(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "subdir"
    acquire_lock(target, name_remote="x")
    assert (target / LOCK_FILENAME).exists()
```

- [ ] **Step 5.2: Run, expect ImportError**

```bash
uv run pytest tests/test_transfer/test_lock.py -v
```

- [ ] **Step 5.3: Implement lock module**

`src/atomx_toolkit/transfer/lock.py`:
```python
"""Per-study lock file: atomic acquire via O_CREAT|O_EXCL, conservative release."""

from __future__ import annotations

import json
import logging
import os
import socket
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from atomx_toolkit.transfer.errors import LockHeldError

logger = logging.getLogger(__name__)

LOCK_FILENAME = ".atomx-toolkit.lock"


def acquire_lock(study_dir: Path, name_remote: str) -> Path:
    """Atomically create the lock file for a study. Raises LockHeldError if held.

    The directory is created if it does not yet exist (Phase 0 may also have
    created it; mkdir -p is idempotent).
    """
    study_dir.mkdir(parents=True, exist_ok=True)
    lock_path = study_dir / LOCK_FILENAME
    payload: dict[str, Any] = {
        "hostname": socket.gethostname(),
        "pid": os.getpid(),
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "name_remote": name_remote,
    }
    try:
        fd = os.open(
            str(lock_path),
            os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            0o644,
        )
    except FileExistsError as exc:
        existing = read_lock(study_dir)
        if existing is None:
            # Race: someone deleted between O_EXCL fail and re-read.
            existing = {"hostname": "?", "pid": 0, "started_at": "?", "name_remote": "?"}
        raise LockHeldError(existing) from exc
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f)
    except Exception:
        # Best effort cleanup if we created the lock but failed to write payload.
        lock_path.unlink(missing_ok=True)
        raise
    return lock_path


def release_lock(study_dir: Path) -> None:
    """Remove the lock file. Logs WARNING but does not raise if already gone."""
    lock_path = study_dir / LOCK_FILENAME
    try:
        lock_path.unlink()
    except FileNotFoundError:
        logger.warning("lock %s already gone at release time", lock_path)


def read_lock(study_dir: Path) -> dict[str, Any] | None:
    """Return parsed lock contents or None if no lock present."""
    lock_path = study_dir / LOCK_FILENAME
    if not lock_path.exists():
        return None
    try:
        return json.loads(lock_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("could not parse lock %s: %s", lock_path, exc)
        return None
```

- [ ] **Step 5.4: Run tests, expect pass**

```bash
uv run pytest tests/test_transfer/test_lock.py -v
```

- [ ] **Step 5.5: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/lock.py tests/test_transfer/test_lock.py
uv run pyright src/atomx_toolkit/transfer/lock.py tests/test_transfer/test_lock.py
git add src/atomx_toolkit/transfer/lock.py tests/test_transfer/test_lock.py
git commit -m "feat: study-level atomic lock with crash detection"
```

---

## Task 6: SFTP wrapper + paramiko test server fixture

**Files:**
- Create: `src/atomx_toolkit/transfer/sftp.py`
- Create: `tests/test_transfer/conftest.py`
- Create: `tests/test_transfer/test_sftp.py`

This is the heaviest infrastructure task: we need a real local SFTP
server fixture for tests to interact with. Use paramiko's
`ServerInterface` to spin one up serving a tmp directory.

- [ ] **Step 6.1: Write the conftest fixture**

`tests/test_transfer/conftest.py`:
```python
"""Local SFTP server fixture for transfer integration tests."""

from __future__ import annotations

import os
import socket
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import paramiko
import pytest


@dataclass
class _SftpServer:
    host: str
    port: int
    user: str
    password: str
    rootdir: Path
    stop_event: threading.Event
    listener: socket.socket


class _AuthHandler(paramiko.ServerInterface):
    def __init__(self, expected_user: str, expected_password: str) -> None:
        self._user = expected_user
        self._password = expected_password

    def check_auth_password(self, username: str, password: str) -> int:
        if username == self._user and password == self._password:
            return paramiko.AUTH_SUCCESSFUL
        return paramiko.AUTH_FAILED

    def get_allowed_auths(self, username: str) -> str:
        return "password"

    def check_channel_request(self, kind: str, chanid: int) -> int:
        return paramiko.OPEN_SUCCEEDED


class _SftpHandler(paramiko.SFTPServerInterface):
    """Tiny SFTP handler that serves a fixed root directory read-only."""

    ROOT: Path = Path()

    def _real(self, path: str) -> Path:
        path = path.lstrip("/")
        return self.ROOT / path

    def list_folder(self, path: str) -> list[paramiko.SFTPAttributes] | int:
        full = self._real(path)
        if not full.is_dir():
            return paramiko.SFTP_NO_SUCH_FILE
        out: list[paramiko.SFTPAttributes] = []
        for entry in full.iterdir():
            attr = paramiko.SFTPAttributes.from_stat(entry.stat())
            attr.filename = entry.name
            out.append(attr)
        return out

    def stat(self, path: str) -> paramiko.SFTPAttributes | int:
        full = self._real(path)
        if not full.exists():
            return paramiko.SFTP_NO_SUCH_FILE
        return paramiko.SFTPAttributes.from_stat(full.stat())

    lstat = stat

    def open(
        self, path: str, flags: int, attr: paramiko.SFTPAttributes
    ) -> paramiko.SFTPHandle | int:
        full = self._real(path)
        if not full.exists() or not full.is_file():
            return paramiko.SFTP_NO_SUCH_FILE
        handle = paramiko.SFTPHandle(flags)
        handle.readfile = full.open("rb")  # type: ignore[attr-defined]
        return handle


def _serve_one(
    listener: socket.socket,
    host_key: paramiko.RSAKey,
    user: str,
    password: str,
    rootdir: Path,
    stop_event: threading.Event,
) -> None:
    listener.settimeout(0.5)
    while not stop_event.is_set():
        try:
            client_sock, _ = listener.accept()
        except socket.timeout:
            continue
        transport = paramiko.Transport(client_sock)
        transport.add_server_key(host_key)
        _SftpHandler.ROOT = rootdir  # set per-connection root
        transport.set_subsystem_handler(
            "sftp", paramiko.SFTPServer, _SftpHandler
        )
        try:
            transport.start_server(server=_AuthHandler(user, password))
        except paramiko.SSHException:
            transport.close()
            continue
        # transport runs subsystem in its own thread


@pytest.fixture
def sftp_server(tmp_path: Path) -> Iterator[_SftpServer]:
    rootdir = tmp_path / "remote"
    rootdir.mkdir()
    user = "tester"
    password = "secret"
    host_key = paramiko.RSAKey.generate(2048)
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 0))
    listener.listen(5)
    port = listener.getsockname()[1]
    stop_event = threading.Event()
    thread = threading.Thread(
        target=_serve_one,
        args=(listener, host_key, user, password, rootdir, stop_event),
        daemon=True,
    )
    thread.start()
    server = _SftpServer(
        host="127.0.0.1",
        port=port,
        user=user,
        password=password,
        rootdir=rootdir,
        stop_event=stop_event,
        listener=listener,
    )
    yield server
    stop_event.set()
    listener.close()
    thread.join(timeout=2)


def seed_remote(server: _SftpServer, files: dict[str, bytes]) -> None:
    """Helper used by tests to populate the remote rootdir."""
    for relpath, content in files.items():
        full = server.rootdir / relpath
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_bytes(content)


@pytest.fixture
def known_hosts_isolated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect ~/.ssh/known_hosts to a tmp path so tests don't pollute the user's."""
    ssh_dir = tmp_path / "ssh"
    ssh_dir.mkdir()
    known_hosts = ssh_dir / "known_hosts"
    known_hosts.touch()
    monkeypatch.setenv("HOME", str(tmp_path))
    return known_hosts
```

- [ ] **Step 6.2: Write the failing test**

`tests/test_transfer/test_sftp.py`:
```python
"""Tests for the paramiko-backed SFTP wrapper."""

from __future__ import annotations

from pathlib import Path

import pytest

from atomx_toolkit.transfer.sftp import SftpClient

from .conftest import seed_remote


def test_walk_files_returns_absolute_posix_paths(
    sftp_server: object, known_hosts_isolated: Path
) -> None:
    seed_remote(sftp_server, {"a.txt": b"x", "sub/b.txt": b"y", "sub/c/d.txt": b"z"})
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        files = sorted(client.walk_files("/"))
    assert files == ["/a.txt", "/sub/b.txt", "/sub/c/d.txt"]


def test_walk_files_empty_dir(sftp_server: object, known_hosts_isolated: Path) -> None:
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        assert list(client.walk_files("/")) == []


def test_download_file_atomic_rename(
    sftp_server: object, tmp_path: Path, known_hosts_isolated: Path
) -> None:
    seed_remote(sftp_server, {"a.bin": b"hello world"})
    local = tmp_path / "out" / "a.bin"
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        client.download_file("/a.bin", local)
    assert local.read_bytes() == b"hello world"
    assert not local.with_suffix(".bin.part").exists()


def test_stat_size(sftp_server: object, known_hosts_isolated: Path) -> None:
    seed_remote(sftp_server, {"big.bin": b"x" * 12345})
    with SftpClient(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
    ) as client:
        assert client.stat_size("/big.bin") == 12345


def test_auth_failure_raises(
    sftp_server: object, known_hosts_isolated: Path
) -> None:
    with pytest.raises(Exception):  # paramiko AuthenticationException specifically
        with SftpClient(
            host=sftp_server.host,
            port=sftp_server.port,
            user=sftp_server.user,
            password="wrong",
        ):
            pass
```

- [ ] **Step 6.3: Run, expect failure**

```bash
uv run pytest tests/test_transfer/test_sftp.py -v
```

- [ ] **Step 6.4: Implement sftp.py**

`src/atomx_toolkit/transfer/sftp.py`:
```python
"""paramiko-based SFTP client with iterative walk and atomic download."""

from __future__ import annotations

import logging
import os
import posixpath
import stat
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

import paramiko

logger = logging.getLogger(__name__)

DEFAULT_CONNECT_TIMEOUT_S = 60.0
DEFAULT_READ_TIMEOUT_S = 300.0


class SftpClient:
    """SSH/SFTP context manager for AtoMx-style password auth.

    On enter: opens an SSHClient, loads known_hosts, connects, opens SFTP.
    On exit: closes SFTP and SSH cleanly.

    Host-key policy: AutoAddPolicy + load_system_host_keys. New hosts are
    auto-added to ~/.ssh/known_hosts; mismatched hosts raise BadHostKeyException
    (paramiko consults the policy only for missing keys, not mismatches).
    """

    def __init__(
        self,
        *,
        host: str,
        port: int = 22,
        user: str,
        password: str,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT_S,
        read_timeout: float = DEFAULT_READ_TIMEOUT_S,
    ) -> None:
        self._host = host
        self._port = port
        self._user = user
        self._password = password
        self._connect_timeout = connect_timeout
        self._read_timeout = read_timeout
        self._ssh: paramiko.SSHClient | None = None
        self._sftp: paramiko.SFTPClient | None = None

    def __enter__(self) -> Self:
        ssh = paramiko.SSHClient()
        try:
            ssh.load_system_host_keys()
        except OSError:
            # known_hosts may not exist yet; that's fine.
            pass
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            hostname=self._host,
            port=self._port,
            username=self._user,
            password=self._password,
            timeout=self._connect_timeout,
            allow_agent=False,
            look_for_keys=False,
        )
        sftp = ssh.open_sftp()
        sftp.get_channel().settimeout(self._read_timeout)  # type: ignore[union-attr]
        self._ssh = ssh
        self._sftp = sftp
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception as exc_close:
                logger.warning("error closing sftp: %s", exc_close)
        if self._ssh is not None:
            try:
                self._ssh.close()
            except Exception as exc_close:
                logger.warning("error closing ssh: %s", exc_close)

    @property
    def _client(self) -> paramiko.SFTPClient:
        if self._sftp is None:
            raise RuntimeError("SftpClient used outside its context manager")
        return self._sftp

    def walk_files(self, root: str) -> Iterator[str]:
        """Iterative DFS yielding absolute POSIX paths of regular files under root."""
        stack: list[str] = [root.rstrip("/") or "/"]
        while stack:
            current = stack.pop()
            for attr in self._client.listdir_attr(current):
                if attr.filename in (".", ".."):
                    continue
                full = posixpath.join(current, attr.filename)
                mode = attr.st_mode or 0
                if stat.S_ISDIR(mode):
                    stack.append(full)
                elif stat.S_ISREG(mode):
                    yield full

    def stat_size(self, remote: str) -> int:
        attr = self._client.stat(remote)
        if attr.st_size is None:
            raise RuntimeError(f"remote {remote} has no size attr")
        return attr.st_size

    def download_file(self, remote: str, local: Path) -> None:
        """Stream download to `<local>.part`, then os.rename to final path.

        The .part file lives in the same directory as the final, so the rename
        is atomic on POSIX.
        """
        local.parent.mkdir(parents=True, exist_ok=True)
        part = local.with_suffix(local.suffix + ".part")
        # Defensive: clear any stale .part from a previous run.
        if part.exists():
            part.unlink()
        with self._client.open(remote, "rb") as remote_f, part.open("wb") as local_f:
            while True:
                chunk = remote_f.read(1024 * 1024)
                if not chunk:
                    break
                local_f.write(chunk)
            local_f.flush()
            os.fsync(local_f.fileno())
        os.rename(part, local)
```

- [ ] **Step 6.5: Run tests, expect pass**

```bash
uv run pytest tests/test_transfer/test_sftp.py -v
```

If a test hangs on auth failure, add a connect timeout assertion in the test.

- [ ] **Step 6.6: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/sftp.py tests/test_transfer/{conftest,test_sftp}.py
uv run pyright src/atomx_toolkit/transfer/sftp.py tests/test_transfer/{conftest,test_sftp}.py
git add src/atomx_toolkit/transfer/sftp.py tests/test_transfer/conftest.py tests/test_transfer/test_sftp.py
git commit -m "feat: paramiko SFTP wrapper with atomic per-file download"
```

---

## Task 7: Pipeline orchestrator (the 6 phases + guard)

**Files:**
- Create: `src/atomx_toolkit/transfer/pipeline.py`
- Create: `tests/test_transfer/test_pipeline.py`

This is the heaviest task. It glues lock + sftp + md5 into the
6-phase pipeline with the guard, atomic writes, and resume.

- [ ] **Step 7.1: Write the failing test**

`tests/test_transfer/test_pipeline.py`:
```python
"""Tests for the per-study transfer pipeline."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    LockHeldError,
    RemoteListInconsistent,
)
from atomx_toolkit.transfer.lock import LOCK_FILENAME
from atomx_toolkit.transfer.pipeline import PipelineResult, run_pipeline

from .conftest import seed_remote


def _run(
    sftp_server: object,
    log_root: Path,
    backup_root: Path,
    name_remote: str,
    name_local: str,
) -> PipelineResult:
    return run_pipeline(
        host=sftp_server.host,
        port=sftp_server.port,
        user=sftp_server.user,
        password=sftp_server.password,
        remote_root="/",
        name_remote=name_remote,
        name_local=name_local,
        log_root=log_root,
        backup_root=backup_root,
    )


def test_happy_path(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(
        sftp_server,
        {
            "study/a.txt": b"hello",
            "study/sub/b.txt": b"world",
        },
    )
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    assert result.file_count == 2
    # md5sum_pass content is a parseable ISO 8601 timestamp
    pass_file = log_root / "study_local" / "index" / "md5sum_pass"
    datetime.fromisoformat(pass_file.read_text().strip())
    # AtoMx_copy was deleted, AtoMx remains
    assert (backup_root / "study_local" / "AtoMx" / "a.txt").exists()
    assert not (backup_root / "study_local" / "AtoMx_copy").exists()
    # Lock was released
    assert not (backup_root / "study_local" / LOCK_FILENAME).exists()


def test_guard_skips_already_complete(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    pass_file = log_root / "study_local" / "index" / "md5sum_pass"
    pass_file.parent.mkdir(parents=True)
    pass_file.write_text("2026-01-01T00:00:00+00:00")
    # No remote files seeded — pipeline should never connect
    result = _run(sftp_server, log_root, backup_root, "absent_remote", "study_local")
    assert result.status == "skipped_already_complete"
    assert result.file_count is None


def test_lock_held_aborts(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"x"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    study_backup = backup_root / "study_local"
    study_backup.mkdir(parents=True)
    (study_backup / LOCK_FILENAME).write_text(
        json.dumps(
            {
                "hostname": "other",
                "pid": 99999,
                "started_at": "2026-01-01T00:00:00+00:00",
                "name_remote": "earlier_run",
            }
        )
    )
    with pytest.raises(LockHeldError):
        _run(sftp_server, log_root, backup_root, "study", "study_local")


def test_phase1_zero_files_warns_but_succeeds(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    seed_remote(sftp_server, {})
    # Create the empty 'study' dir on the remote
    (sftp_server.rootdir / "study").mkdir()
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    with caplog.at_level("WARNING"):
        result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    assert result.file_count == 0
    assert any("no files" in rec.message.lower() for rec in caplog.records)


def test_resume_skips_already_downloaded_files(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"hello", "study/b.txt": b"world"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    # Pre-stage a fully-correct local file in AtoMx/
    pre = backup_root / "study_local" / "AtoMx" / "a.txt"
    pre.parent.mkdir(parents=True)
    pre.write_bytes(b"hello")
    result = _run(sftp_server, log_root, backup_root, "study", "study_local")
    assert result.status == "success"
    # File must still exist with correct content
    assert pre.read_bytes() == b"hello"


def test_md5_mismatch_raises_integrity_error(
    sftp_server: object,
    tmp_path: Path,
    known_hosts_isolated: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seed_remote(sftp_server, {"study/a.txt": b"original"})
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"

    # Patch sftp download_file in the second backup directory to corrupt content.
    from atomx_toolkit.transfer import sftp as sftp_module

    original_download = sftp_module.SftpClient.download_file
    call_count = {"n": 0}

    def corrupt_second(self, remote, local):  # type: ignore[no-untyped-def]
        original_download(self, remote, local)
        call_count["n"] += 1
        # The second download targets AtoMx_copy/; corrupt it
        if "AtoMx_copy" in str(local):
            local.write_bytes(b"corrupted")

    monkeypatch.setattr(sftp_module.SftpClient, "download_file", corrupt_second)

    with pytest.raises(IntegrityError):
        _run(sftp_server, log_root, backup_root, "study", "study_local")

    assert (log_root / "study_local" / "index" / "md5sum_fail").exists()
    assert (log_root / "study_local" / "md5sum" / "md5sum_diff.csv").exists()
```

- [ ] **Step 7.2: Run, expect ImportError**

```bash
uv run pytest tests/test_transfer/test_pipeline.py -v
```

- [ ] **Step 7.3: Implement pipeline**

`src/atomx_toolkit/transfer/pipeline.py`:
```python
"""Per-study transfer pipeline: 6 phases + entry guard, with atomic file writes
and resume on partial state.
"""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from atomx_toolkit.transfer.errors import (
    IntegrityError,
    LockHeldError,
    RemoteListInconsistent,
)
from atomx_toolkit.transfer.lock import (
    LOCK_FILENAME,
    acquire_lock,
    read_lock,
    release_lock,
)
from atomx_toolkit.transfer.md5 import (
    assert_md5sum_available,
    compare_md5_files,
    compute_md5_tree,
    write_md5_file,
)
from atomx_toolkit.transfer.sftp import SftpClient

logger = logging.getLogger(__name__)


PipelineStatus = Literal["success", "skipped_already_complete"]


@dataclass(frozen=True)
class PipelineResult:
    name_remote: str
    name_local: str
    status: PipelineStatus
    started_at: datetime
    completed_at: datetime
    file_count: int | None = None
    total_bytes: int | None = None
    log_path: Path | None = None


def run_pipeline(
    *,
    host: str,
    port: int = 22,
    user: str,
    password: str,
    remote_root: str,
    name_remote: str,
    name_local: str,
    log_root: Path,
    backup_root: Path,
) -> PipelineResult:
    """Run the per-study pipeline. Raises TransferError subclasses on failure."""
    started_at = datetime.now(timezone.utc)
    log_dir = log_root / name_local
    backup_dir = backup_root / name_local
    index_dir = log_dir / "index"
    path_dir = log_dir / "path"
    md5_dir = log_dir / "md5sum"
    primary = backup_dir / "AtoMx"
    secondary = backup_dir / "AtoMx_copy"

    # Guard: if a previous run completed successfully, skip everything.
    pass_file = index_dir / "md5sum_pass"
    if pass_file.exists():
        logger.info("study %s already complete; skipping", name_local)
        return PipelineResult(
            name_remote=name_remote,
            name_local=name_local,
            status="skipped_already_complete",
            started_at=started_at,
            completed_at=datetime.now(timezone.utc),
        )

    assert_md5sum_available()

    # Phase 0: mkdir
    for d in (index_dir, path_dir, md5_dir, primary, secondary):
        d.mkdir(parents=True, exist_ok=True)

    # Acquire lock atomically. Raises LockHeldError on conflict.
    acquire_lock(backup_dir, name_remote=name_remote)

    file_count = 0
    total_bytes = 0
    try:
        with SftpClient(host=host, port=port, user=user, password=password) as client:
            remote_dir = _join_remote(remote_root, name_remote)

            # Phase 1: list twice and compare
            remote_fs_1 = sorted(client.walk_files(remote_dir))
            remote_fs_2 = sorted(client.walk_files(remote_dir))
            if set(remote_fs_1) != set(remote_fs_2):
                _touch(index_dir / "path_fail")
                raise RemoteListInconsistent(
                    f"remote file list differs across two attempts for {remote_dir}"
                )
            (path_dir / "path_1.txt").write_text(
                "\n".join(remote_fs_1) + ("\n" if remote_fs_1 else "")
            )
            (path_dir / "path_2.txt").write_text(
                "\n".join(remote_fs_2) + ("\n" if remote_fs_2 else "")
            )
            _touch(index_dir / "path_pass")

            file_count = len(remote_fs_1)
            if file_count == 0:
                logger.warning(
                    "study %s has no files on the remote (typo'd name? deleted study?)",
                    name_remote,
                )

            # Phase 2: download to AtoMx/
            _download_all(client, remote_dir, remote_fs_1, primary)
            # Phase 3: download to AtoMx_copy/
            _download_all(client, remote_dir, remote_fs_1, secondary)

        # Phase 4: md5 of AtoMx/
        md5_dict_1 = compute_md5_tree(primary)
        write_md5_file(md5_dict_1, md5_dir / "md5sum_1.txt")
        # Phase 5: md5 of AtoMx_copy/
        md5_dict_2 = compute_md5_tree(secondary)
        write_md5_file(md5_dict_2, md5_dir / "md5sum_2.txt")

        # Phase 6: compare
        cmp = compare_md5_files(
            md5_dir / "md5sum_1.txt",
            md5_dir / "md5sum_2.txt",
            md5_dir / "md5sum_diff.csv",
        )
        if not cmp.all_match:
            _touch(index_dir / "md5sum_fail")
            raise IntegrityError(
                f"md5 comparison failed: {cmp.mismatched} mismatched, "
                f"{cmp.missing_in_1} missing in 1, {cmp.missing_in_2} missing in 2"
            )

        shutil.rmtree(secondary)
        completed_at = datetime.now(timezone.utc)
        pass_file.write_text(completed_at.isoformat(timespec="seconds"))
        for p in primary.rglob("*"):
            if p.is_file():
                total_bytes += p.stat().st_size

        return PipelineResult(
            name_remote=name_remote,
            name_local=name_local,
            status="success",
            started_at=started_at,
            completed_at=completed_at,
            file_count=file_count,
            total_bytes=total_bytes,
        )
    finally:
        release_lock(backup_dir)


def _join_remote(root: str, name: str) -> str:
    if not root.endswith("/"):
        root = root + "/"
    return root + name


def _touch(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _download_all(
    client: SftpClient,
    remote_dir: str,
    remote_files: list[str],
    local_dir: Path,
) -> None:
    """Download each remote file to local_dir, with size-match resume."""
    if not remote_dir.endswith("/"):
        remote_dir_with_slash = remote_dir + "/"
    else:
        remote_dir_with_slash = remote_dir
    for remote in remote_files:
        if not remote.startswith(remote_dir_with_slash):
            # remote_dir itself is a file? skip
            continue
        rel = remote[len(remote_dir_with_slash) :]
        local = local_dir / rel
        if local.exists():
            try:
                remote_size = client.stat_size(remote)
            except Exception as exc:
                logger.warning("could not stat remote %s: %s", remote, exc)
                local.unlink(missing_ok=True)
            else:
                if local.stat().st_size == remote_size:
                    logger.debug("skipping %s (size matches)", rel)
                    continue
                logger.info("re-downloading %s (size mismatch)", rel)
                local.unlink(missing_ok=True)
        # Stale .part?
        part = local.with_suffix(local.suffix + ".part")
        if part.exists():
            part.unlink()
        client.download_file(remote, local)
```

- [ ] **Step 7.4: Run tests, expect pass**

```bash
uv run pytest tests/test_transfer/test_pipeline.py -v
```

If `test_phase1_zero_files_warns_but_succeeds` fails because `walk_files` errors on missing dir vs. empty dir, ensure the test seeds an empty `study/` directory.

- [ ] **Step 7.5: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/pipeline.py tests/test_transfer/test_pipeline.py
uv run pyright src/atomx_toolkit/transfer/pipeline.py tests/test_transfer/test_pipeline.py
git add src/atomx_toolkit/transfer/pipeline.py tests/test_transfer/test_pipeline.py
git commit -m "feat: 6-phase per-study pipeline with guard and resume"
```

---

## Task 8: Batch (jobs.tsv parser + runner + plan)

**Files:**
- Create: `src/atomx_toolkit/transfer/batch.py`
- Create: `tests/test_transfer/test_batch.py`

- [ ] **Step 8.1: Write failing tests**

`tests/test_transfer/test_batch.py`:
```python
"""Tests for jobs.tsv parsing, batch execution, and plan dry-run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from atomx_toolkit.transfer.batch import (
    BatchItemResult,
    BatchPlan,
    JobsTsvError,
    classify_jobs,
    parse_jobs_tsv,
)
from atomx_toolkit.transfer.lock import LOCK_FILENAME


def _write(p: Path, content: str) -> Path:
    p.write_text(content, encoding="utf-8")
    return p


# ---- parse_jobs_tsv ----


def test_parse_simple(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "remoteA\tlocalA\nremoteB\tlocalB\n")
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        "# header\n\nremoteA\tlocalA\n  # indented comment\nremoteB\tlocalB\n",
    )
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_tolerates_bom(tmp_path: Path) -> None:
    p = tmp_path / "j.tsv"
    p.write_bytes(b"\xef\xbb\xbfremoteA\tlocalA\n")
    assert parse_jobs_tsv(p) == [("remoteA", "localA")]


def test_parse_accepts_arbitrary_whitespace(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "remoteA    localA\nremoteB\t\tlocalB\n")
    assert parse_jobs_tsv(p) == [("remoteA", "localA"), ("remoteB", "localB")]


def test_parse_empty_after_filter_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "# only comments\n\n")
    with pytest.raises(JobsTsvError, match="empty"):
        parse_jobs_tsv(p)


def test_parse_one_field_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "only_one_column\n")
    with pytest.raises(JobsTsvError, match="line 1"):
        parse_jobs_tsv(p)


def test_parse_three_fields_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "a\tb\tc\n")
    with pytest.raises(JobsTsvError, match="line 1"):
        parse_jobs_tsv(p)


def test_parse_duplicate_local_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", "r1\tlocal\nr2\tlocal\n")
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)


# ---- classify_jobs ----


def test_classify_pending_when_no_state(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.pending == [("r", "loc")]
    assert plan.complete_already == []
    assert plan.skipped_locked == []


def test_classify_complete_already(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    pf = log_root / "loc" / "index" / "md5sum_pass"
    pf.parent.mkdir(parents=True)
    pf.write_text("2026-01-01T00:00:00+00:00")
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.complete_already and plan.complete_already[0][0] == "r"
    assert plan.pending == []


def test_classify_skipped_locked(tmp_path: Path) -> None:
    log_root = tmp_path / "log"
    backup_root = tmp_path / "backup"
    lf = backup_root / "loc" / LOCK_FILENAME
    lf.parent.mkdir(parents=True)
    lf.write_text(
        json.dumps(
            {
                "hostname": "h",
                "pid": 1,
                "started_at": "2026-01-01T00:00:00+00:00",
                "name_remote": "r",
            }
        )
    )
    plan = classify_jobs([("r", "loc")], log_root=log_root, backup_root=backup_root)
    assert plan.skipped_locked and plan.skipped_locked[0][0] == "r"
    assert plan.pending == []
```

- [ ] **Step 8.2: Run, expect ImportError**

```bash
uv run pytest tests/test_transfer/test_batch.py -v
```

- [ ] **Step 8.3: Implement batch.py**

`src/atomx_toolkit/transfer/batch.py`:
```python
"""jobs.tsv parsing, study classification, sequential batch execution, dry-run plan."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from atomx_toolkit.transfer.errors import JobsTsvError, LockHeldError, TransferError
from atomx_toolkit.transfer.lock import LOCK_FILENAME, read_lock
from atomx_toolkit.transfer.pipeline import PipelineResult, run_pipeline

logger = logging.getLogger(__name__)


Job = tuple[str, str]  # (name_remote, name_local)


@dataclass(frozen=True)
class BatchPlan:
    complete_already: list[Job]
    skipped_locked: list[Job]
    pending: list[Job]


BatchItemStatus = Literal[
    "complete_already",
    "skipped_locked",
    "succeeded",
    "failed",
]


@dataclass(frozen=True)
class BatchItemResult:
    name_remote: str
    name_local: str
    status: BatchItemStatus
    duration: timedelta | None = None
    failure_message: str | None = None


@dataclass(frozen=True)
class BatchRunResult:
    jobs_tsv: Path
    started_at: datetime
    completed_at: datetime
    items: list[BatchItemResult] = field(default_factory=list)

    @property
    def any_failed(self) -> bool:
        return any(i.status == "failed" for i in self.items)

    @property
    def all_skipped_locked(self) -> bool:
        return bool(self.items) and all(i.status == "skipped_locked" for i in self.items)


def parse_jobs_tsv(path: Path) -> list[Job]:
    """Parse a 2-column whitespace-separated jobs file. See spec 4.7."""
    if not path.exists():
        raise JobsTsvError(f"jobs.tsv not found: {path}")
    text = path.read_text(encoding="utf-8-sig")  # tolerates BOM
    jobs: list[Job] = []
    seen_locals: set[str] = set()
    for lineno, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = re.split(r"\s+", stripped)
        if len(fields) != 2:
            raise JobsTsvError(
                f"{path} line {lineno}: expected 2 fields, got {len(fields)}: {raw!r}"
            )
        remote, local = fields[0], fields[1]
        if local in seen_locals:
            raise JobsTsvError(
                f"{path} line {lineno}: duplicate name_local {local!r}"
            )
        seen_locals.add(local)
        jobs.append((remote, local))
    if not jobs:
        raise JobsTsvError(f"{path} contains no jobs after filtering blanks/comments")
    return jobs


def classify_jobs(
    jobs: list[Job],
    *,
    log_root: Path,
    backup_root: Path,
) -> BatchPlan:
    """Classify each job by its on-disk state. Used by both batch and plan."""
    complete: list[Job] = []
    locked: list[Job] = []
    pending: list[Job] = []
    for job in jobs:
        _, name_local = job
        if (log_root / name_local / "index" / "md5sum_pass").exists():
            complete.append(job)
        elif (backup_root / name_local / LOCK_FILENAME).exists():
            locked.append(job)
        else:
            pending.append(job)
    return BatchPlan(
        complete_already=complete, skipped_locked=locked, pending=pending
    )


def run_batch(
    jobs: list[Job],
    *,
    plan: BatchPlan,
    host: str,
    port: int,
    user: str,
    password: str,
    remote_root: str,
    log_root: Path,
    backup_root: Path,
    jobs_tsv_path: Path,
) -> BatchRunResult:
    """Run pending items sequentially. Returns a BatchRunResult covering all items.

    KeyboardInterrupt aborts the whole batch (does not continue). Remaining
    pending items are appended as 'failed' with reason 'not run, batch aborted'.
    Per-item exceptions are caught and recorded; the next item still runs.
    """
    started_at = datetime.now(timezone.utc)
    items: list[BatchItemResult] = []
    for job in plan.complete_already:
        items.append(
            BatchItemResult(
                name_remote=job[0], name_local=job[1], status="complete_already"
            )
        )
    for job in plan.skipped_locked:
        items.append(
            BatchItemResult(
                name_remote=job[0],
                name_local=job[1],
                status="skipped_locked",
                failure_message=_describe_lock(backup_root / job[1]),
            )
        )
    aborted = False
    for idx, job in enumerate(plan.pending):
        if aborted:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message="not run, batch aborted",
                )
            )
            continue
        item_start = datetime.now(timezone.utc)
        try:
            result = run_pipeline(
                host=host,
                port=port,
                user=user,
                password=password,
                remote_root=remote_root,
                name_remote=job[0],
                name_local=job[1],
                log_root=log_root,
                backup_root=backup_root,
            )
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="succeeded"
                    if result.status == "success"
                    else "complete_already",
                    duration=datetime.now(timezone.utc) - item_start,
                )
            )
        except LockHeldError as exc:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="skipped_locked",
                    failure_message=str(exc),
                )
            )
        except KeyboardInterrupt:
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message="interrupted",
                    duration=datetime.now(timezone.utc) - item_start,
                )
            )
            aborted = True
            logger.warning("KeyboardInterrupt; aborting remaining %d items", len(plan.pending) - idx - 1)
        except (TransferError, Exception) as exc:
            logger.exception("study %s failed", job[1])
            items.append(
                BatchItemResult(
                    name_remote=job[0],
                    name_local=job[1],
                    status="failed",
                    failure_message=str(exc),
                    duration=datetime.now(timezone.utc) - item_start,
                )
            )
    completed_at = datetime.now(timezone.utc)
    return BatchRunResult(
        jobs_tsv=jobs_tsv_path,
        started_at=started_at,
        completed_at=completed_at,
        items=items,
    )


def _describe_lock(study_backup_dir: Path) -> str:
    payload = read_lock(study_backup_dir)
    if payload is None:
        return "lock present (could not read contents)"
    return (
        f"lock from {payload.get('hostname', '?')} pid {payload.get('pid', '?')} "
        f"at {payload.get('started_at', '?')}"
    )
```

- [ ] **Step 8.4: Run tests, expect pass**

```bash
uv run pytest tests/test_transfer/test_batch.py -v
```

- [ ] **Step 8.5: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/batch.py tests/test_transfer/test_batch.py
uv run pyright src/atomx_toolkit/transfer/batch.py tests/test_transfer/test_batch.py
git add src/atomx_toolkit/transfer/batch.py tests/test_transfer/test_batch.py
git commit -m "feat: jobs.tsv parser, batch classifier, sequential runner"
```

---

## Task 9: Transfer CLI group

**Files:**
- Create: `src/atomx_toolkit/transfer/cli.py`
- Modify: `src/atomx_toolkit/cli.py` (mount transfer group)
- Modify: `tests/test_cli.py` (add CLI smoke tests for transfer group)

The CLI layer is thin: parse args, load config, call pipeline / batch,
print to stderr, set exit code. Email dispatch comes in Task 14.

- [ ] **Step 9.1: Write failing CLI smoke tests**

Append to `tests/test_cli.py`:
```python
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
```

- [ ] **Step 9.2: Run, expect failure (no transfer subcommand yet)**

```bash
uv run pytest tests/test_cli.py -v
```

- [ ] **Step 9.3: Implement transfer/cli.py**

`src/atomx_toolkit/transfer/cli.py`:
```python
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
    config: Annotated[Path, typer.Option("--config", help="config.toml path")] = None,  # type: ignore[assignment]
) -> None:
    """Download a single study, with double-MD5 verification."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2)
    try:
        creds = load_sftp_credentials(_default_sftp_env_path())
    except SftpCredentialsError as exc:
        console.print(f"[red]credential error:[/red] {exc}")
        raise typer.Exit(code=2)
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
        raise typer.Exit(code=2)
    except TransferError as exc:
        console.print(f"[red]transfer failed:[/red] {exc}")
        raise typer.Exit(code=1)
    if result.status == "skipped_already_complete":
        console.print(f"[yellow]already complete:[/yellow] {name_local}")
    else:
        console.print(
            f"[green]ok:[/green] {name_local} ({result.file_count} files)"
        )


@app.command("batch")
def batch_cmd(
    jobs_tsv: Annotated[Path, typer.Argument(help="jobs.tsv path")],
    config: Annotated[Path, typer.Option("--config", help="config.toml path")] = None,  # type: ignore[assignment]
) -> None:
    """Run a batch of studies sequentially from a 2-column TSV."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
        creds = load_sftp_credentials(_default_sftp_env_path())
        jobs = parse_jobs_tsv(jobs_tsv)
    except (ConfigError, SftpCredentialsError, JobsTsvError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2)
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
    config: Annotated[Path, typer.Option("--config", help="config.toml path")] = None,  # type: ignore[assignment]
) -> None:
    """Dry-run preview of which studies would run."""
    cfg_path = config or _default_config_path()
    try:
        cfg = load_config(cfg_path)
        jobs = parse_jobs_tsv(jobs_tsv)
    except (ConfigError, JobsTsvError) as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2)
    plan = classify_jobs(
        jobs, log_root=cfg.paths.log_root, backup_root=cfg.paths.backup_root
    )
    _render_plan(plan, cfg.paths.log_root, cfg.paths.backup_root)


def _render_plan(plan: BatchPlan, log_root: Path, backup_root: Path) -> None:
    console.print(
        f"Plan ({len(plan.complete_already) + len(plan.skipped_locked) + len(plan.pending)} entries):"
    )
    if plan.complete_already:
        console.print(f"  complete_already ({len(plan.complete_already)})")
        for r, loc in plan.complete_already:
            ts = (log_root / loc / "index" / "md5sum_pass").read_text().strip()
            console.print(f"    - {loc} (completed {ts})")
    if plan.skipped_locked:
        console.print(f"  skipped_locked ({len(plan.skipped_locked)})")
        for r, loc in plan.skipped_locked:
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
        for r, loc in plan.pending:
            console.print(f"    - {loc}")


def _render_batch_summary(result) -> None:  # type: ignore[no-untyped-def]
    succeeded = sum(1 for i in result.items if i.status == "succeeded")
    complete = sum(1 for i in result.items if i.status == "complete_already")
    locked = sum(1 for i in result.items if i.status == "skipped_locked")
    failed = sum(1 for i in result.items if i.status == "failed")
    console.print(
        f"batch finished: succeeded={succeeded} complete_already={complete} "
        f"skipped_locked={locked} failed={failed}"
    )
```

- [ ] **Step 9.4: Mount transfer group on root CLI**

Modify `src/atomx_toolkit/cli.py`. Replace the file contents with:
```python
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
```

- [ ] **Step 9.5: Run tests**

```bash
uv run pytest tests/test_cli.py tests/test_transfer/ -v
```

- [ ] **Step 9.6: Lint, type check, commit**

```bash
uv run ruff check src/atomx_toolkit/transfer/cli.py src/atomx_toolkit/cli.py tests/test_cli.py
uv run pyright src/atomx_toolkit/transfer/cli.py src/atomx_toolkit/cli.py
git add src/atomx_toolkit/transfer/cli.py src/atomx_toolkit/cli.py tests/test_cli.py
git commit -m "feat: transfer Typer subcommands (run, batch, plan)"
```

---

## Task 10: Notify credentials + recipients

**Files:**
- Create: `src/atomx_toolkit/notify/__init__.py`
- Create: `src/atomx_toolkit/notify/credentials.py`
- Create: `src/atomx_toolkit/notify/recipients.py`
- Create: `tests/test_notify/__init__.py`
- Create: `tests/test_notify/conftest.py`
- Create: `tests/test_notify/test_credentials.py`
- Create: `tests/test_notify/test_recipients.py`

- [ ] **Step 10.1: Write credentials tests**

`tests/test_notify/__init__.py`: empty.
`tests/test_notify/conftest.py`: empty (placeholder; aiosmtpd fixture added in Task 12).

`tests/test_notify/test_credentials.py`:
```python
"""Tests for SMTP credential chain (env > dotenv > none)."""

from pathlib import Path

import pytest

from atomx_toolkit.notify.credentials import (
    SmtpCredentials,
    SmtpCredentialsMissing,
    load_smtp_credentials,
)


def test_env_takes_precedence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ATOMX_SMTP_USER", "envuser")
    monkeypatch.setenv("ATOMX_SMTP_APP_PASSWORD", "envpw")
    creds = load_smtp_credentials(tmp_path / "smtp.env")
    assert creds is not None
    assert creds.user == "envuser"
    assert creds.password == "envpw"
    assert creds.host == "smtp.gmail.com"
    assert creds.port == 587


def test_dotenv_used_when_env_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    p = tmp_path / "smtp.env"
    p.write_text(
        "ATOMX_SMTP_USER=alice\n"
        "ATOMX_SMTP_APP_PASSWORD=secret\n"
        "ATOMX_SMTP_HOST=smtp.example.com\n"
        "ATOMX_SMTP_PORT=2525\n"
    )
    creds = load_smtp_credentials(p)
    assert creds == SmtpCredentials(
        user="alice", password="secret", host="smtp.example.com", port=2525
    )


def test_returns_missing_when_neither(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    result = load_smtp_credentials(tmp_path / "absent.env")
    assert isinstance(result, SmtpCredentialsMissing)


def test_partial_dotenv_returns_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("ATOMX_SMTP_USER", raising=False)
    monkeypatch.delenv("ATOMX_SMTP_APP_PASSWORD", raising=False)
    p = tmp_path / "smtp.env"
    p.write_text("ATOMX_SMTP_USER=alice\n")
    result = load_smtp_credentials(p)
    assert isinstance(result, SmtpCredentialsMissing)
```

- [ ] **Step 10.2: Implement notify/credentials.py**

`src/atomx_toolkit/notify/__init__.py`:
```python
"""Notify subsystem: SMTP delivery of TransferReport / BatchReport / toolkit_error."""
```

`src/atomx_toolkit/notify/credentials.py`:
```python
"""SMTP credential chain: env > dotenv > none. Returns a sentinel on missing,
not an exception, because email is best-effort.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from atomx_toolkit.transfer.credentials import _parse_dotenv  # reuse parser

DEFAULT_HOST = "smtp.gmail.com"
DEFAULT_PORT = 587
_USER_KEY = "ATOMX_SMTP_USER"
_PASS_KEY = "ATOMX_SMTP_APP_PASSWORD"
_HOST_KEY = "ATOMX_SMTP_HOST"
_PORT_KEY = "ATOMX_SMTP_PORT"


@dataclass(frozen=True)
class SmtpCredentials:
    user: str
    password: str
    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT


@dataclass(frozen=True)
class SmtpCredentialsMissing:
    """Sentinel: email send should be skipped, not retried."""


def load_smtp_credentials(
    dotenv_path: Path,
) -> SmtpCredentials | SmtpCredentialsMissing:
    user = os.environ.get(_USER_KEY)
    password = os.environ.get(_PASS_KEY)
    host = os.environ.get(_HOST_KEY)
    port_raw = os.environ.get(_PORT_KEY)
    if not (user and password) and dotenv_path.exists():
        parsed = _parse_dotenv(dotenv_path)
        user = user or parsed.get(_USER_KEY)
        password = password or parsed.get(_PASS_KEY)
        host = host or parsed.get(_HOST_KEY)
        port_raw = port_raw or parsed.get(_PORT_KEY)
    if not user or not password:
        return SmtpCredentialsMissing()
    return SmtpCredentials(
        user=user,
        password=password,
        host=host or DEFAULT_HOST,
        port=int(port_raw) if port_raw else DEFAULT_PORT,
    )
```

- [ ] **Step 10.3: Write recipients tests**

`tests/test_notify/test_recipients.py`:
```python
"""Tests for per-event recipient list resolution."""

from pathlib import Path

from atomx_toolkit.notify.recipients import RecipientResolution, resolve_recipients


def _seed(d: Path, files: dict[str, str]) -> None:
    d.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (d / name).write_text(content)


def test_event_specific_takes_precedence(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "alice@x.com\n", "default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res == RecipientResolution(emails=["alice@x.com"], source="transfer_report.txt")


def test_falls_back_to_default(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "# only comments\n", "default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res == RecipientResolution(emails=["bob@x.com"], source="default.txt")


def test_returns_empty_when_all_empty(tmp_path: Path) -> None:
    _seed(tmp_path, {"transfer_report.txt": "\n", "default.txt": "\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == []
    assert res.source is None


def test_strips_comments_and_blanks(tmp_path: Path) -> None:
    _seed(
        tmp_path,
        {"transfer_report.txt": "# header\n\nalice@x.com\n# bob disabled\n  \nclaire@x.com\n"},
    )
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == ["alice@x.com", "claire@x.com"]


def test_missing_event_file_falls_back(tmp_path: Path) -> None:
    _seed(tmp_path, {"default.txt": "bob@x.com\n"})
    res = resolve_recipients("transfer_report", tmp_path)
    assert res.emails == ["bob@x.com"]
    assert res.source == "default.txt"
```

- [ ] **Step 10.4: Implement notify/recipients.py**

`src/atomx_toolkit/notify/recipients.py`:
```python
"""Recipient resolution per event, with hot-reload (files re-read each call)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

ALL_EVENTS = ("transfer_report", "batch_report", "toolkit_error")


@dataclass(frozen=True)
class RecipientResolution:
    emails: list[str]
    source: str | None  # which file the addresses came from, or None if empty


def resolve_recipients(event: str, recipients_dir: Path) -> RecipientResolution:
    """Resolve subscribers for an event. Event-specific file wins; default.txt is fallback."""
    candidates = [f"{event}.txt", "default.txt"]
    for filename in candidates:
        path = recipients_dir / filename
        if not path.exists():
            continue
        emails = _parse(path)
        if emails:
            return RecipientResolution(emails=emails, source=filename)
    return RecipientResolution(emails=[], source=None)


def _parse(path: Path) -> list[str]:
    out: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        out.append(line)
    return out
```

- [ ] **Step 10.5: Run tests, lint, type check, commit**

```bash
uv run pytest tests/test_notify/test_credentials.py tests/test_notify/test_recipients.py -v
uv run ruff check src/atomx_toolkit/notify/ tests/test_notify/
uv run pyright src/atomx_toolkit/notify/ tests/test_notify/
git add src/atomx_toolkit/notify/__init__.py src/atomx_toolkit/notify/credentials.py src/atomx_toolkit/notify/recipients.py tests/test_notify/
git commit -m "feat: SMTP credential chain and per-event recipient resolution"
```

---

## Task 11: Notify events (dataclasses + body formatting)

**Files:**
- Create: `src/atomx_toolkit/notify/events.py`
- Create: `tests/test_notify/test_events.py`

- [ ] **Step 11.1: Write tests**

`tests/test_notify/test_events.py`:
```python
"""Tests for TransferReport / BatchReport payload formatting (golden output)."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

from atomx_toolkit.notify.events import (
    BatchItem,
    BatchReport,
    TransferReport,
    format_batch_report,
    format_transfer_report,
)


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s)


def test_format_transfer_report_success() -> None:
    report = TransferReport(
        name_remote="HCC_TMA006",
        name_local="HCC_TMA006_local",
        status="success",
        started_at=_ts("2026-04-30T12:00:00+00:00"),
        completed_at=_ts("2026-04-30T14:14:00+00:00"),
        file_count=1247,
        total_bytes=384 * 1024**3,
        failure_phase=None,
        failure_message=None,
        log_path=Path("/log/HCC_TMA006_local/HCC_TMA006_local.log"),
    )
    subject, body = format_transfer_report(report)
    assert "OK" in subject
    assert "HCC_TMA006_local" in subject
    assert "1247" in body
    assert "384.0 GiB" in body
    assert "/log/HCC_TMA006_local" in body


def test_format_transfer_report_failure() -> None:
    report = TransferReport(
        name_remote="HCC_TMA006",
        name_local="HCC_TMA006_local",
        status="failed",
        started_at=_ts("2026-04-30T12:00:00+00:00"),
        completed_at=_ts("2026-04-30T15:02:00+00:00"),
        file_count=None,
        total_bytes=None,
        failure_phase="md5_compare",
        failure_message="3 files mismatched",
        log_path=Path("/log/x.log"),
    )
    subject, body = format_transfer_report(report)
    assert "FAIL" in subject
    assert "md5_compare" in subject
    assert "3 files mismatched" in body


def test_format_batch_report() -> None:
    report = BatchReport(
        jobs_tsv=Path("/tmp/jobs.tsv"),
        started_at=_ts("2026-04-30T08:00:00+00:00"),
        completed_at=_ts("2026-04-30T18:30:00+00:00"),
        items=[
            BatchItem(
                name_remote="r1",
                name_local="loc1",
                status="succeeded",
                duration=timedelta(hours=2),
                failure_message=None,
            ),
            BatchItem(
                name_remote="r2",
                name_local="loc2",
                status="failed",
                duration=timedelta(hours=1),
                failure_message="md5 mismatch",
            ),
            BatchItem(
                name_remote="r3",
                name_local="loc3",
                status="skipped_locked",
                duration=None,
                failure_message="lock from h pid 1 at 2026-04-29T22:00:00Z",
            ),
        ],
    )
    subject, body = format_batch_report(report)
    assert "batch" in subject.lower()
    assert "loc1" in body
    assert "loc2" in body
    assert "loc3" in body
    assert "md5 mismatch" in body


def test_humanize_bytes_zero() -> None:
    from atomx_toolkit.notify.events import _humanize_bytes

    assert _humanize_bytes(0) == "0 B"


def test_humanize_bytes_kib_mib_gib() -> None:
    from atomx_toolkit.notify.events import _humanize_bytes

    assert _humanize_bytes(1024) == "1.0 KiB"
    assert _humanize_bytes(1024**2) == "1.0 MiB"
    assert _humanize_bytes(1024**3) == "1.0 GiB"
```

- [ ] **Step 11.2: Implement events.py**

`src/atomx_toolkit/notify/events.py`:
```python
"""TransferReport / BatchReport dataclasses and plain-text email body formatting."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

TransferStatus = Literal["success", "failed"]
BatchItemStatus = Literal[
    "complete_already", "skipped_locked", "succeeded", "failed"
]


@dataclass(frozen=True)
class TransferReport:
    name_remote: str
    name_local: str
    status: TransferStatus
    started_at: datetime
    completed_at: datetime
    file_count: int | None
    total_bytes: int | None
    failure_phase: str | None
    failure_message: str | None
    log_path: Path


@dataclass(frozen=True)
class BatchItem:
    name_remote: str
    name_local: str
    status: BatchItemStatus
    duration: timedelta | None
    failure_message: str | None


@dataclass(frozen=True)
class BatchReport:
    jobs_tsv: Path
    started_at: datetime
    completed_at: datetime
    items: list[BatchItem]


def format_transfer_report(r: TransferReport) -> tuple[str, str]:
    if r.status == "success":
        subject = f"[atomx-toolkit] OK: {r.name_local}"
        body = (
            f"study     : {r.name_local}\n"
            f"remote    : {r.name_remote}\n"
            f"files     : {r.file_count}\n"
            f"total     : {_humanize_bytes(r.total_bytes or 0)}\n"
            f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}\n"
            f"md5 check : pass ({r.file_count}/{r.file_count} match)\n"
            f"log       : {r.log_path}\n"
        )
        return subject, body
    subject = f"[atomx-toolkit] FAIL: {r.name_local} at {r.failure_phase}"
    body = (
        f"study     : {r.name_local}\n"
        f"remote    : {r.name_remote}\n"
        f"phase     : {r.failure_phase}\n"
        f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}\n"
        f"error     : {r.failure_message}\n"
        f"\n"
        f"log       : {r.log_path}\n"
    )
    log_tail = _tail_log(r.log_path, lines=30)
    if log_tail:
        body += f"\n--- last 30 lines of log ---\n{log_tail}\n"
    return subject, body


def format_batch_report(r: BatchReport) -> tuple[str, str]:
    succeeded = sum(1 for i in r.items if i.status == "succeeded")
    complete = sum(1 for i in r.items if i.status == "complete_already")
    locked = sum(1 for i in r.items if i.status == "skipped_locked")
    failed = sum(1 for i in r.items if i.status == "failed")
    subject = (
        f"[atomx-toolkit] batch: {succeeded} ok, {failed} fail, "
        f"{complete} already, {locked} locked"
    )
    rows: list[str] = [
        f"jobs.tsv  : {r.jobs_tsv}",
        f"started   : {r.started_at.isoformat()}",
        f"finished  : {r.completed_at.isoformat()}",
        f"elapsed   : {_humanize_duration(r.completed_at - r.started_at)}",
        f"summary   : succeeded={succeeded} complete_already={complete} "
        f"skipped_locked={locked} failed={failed}",
        "",
        "items:",
    ]
    for item in r.items:
        line = f"  [{item.status:18s}] {item.name_local}"
        if item.duration is not None:
            line += f"  ({_humanize_duration(item.duration)})"
        if item.failure_message:
            line += f"  -- {item.failure_message}"
        rows.append(line)
    return subject, "\n".join(rows) + "\n"


def _humanize_bytes(n: int) -> str:
    if n == 0:
        return "0 B"
    units = ["B", "KiB", "MiB", "GiB", "TiB", "PiB"]
    size = float(n)
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024
        idx += 1
    return f"{size:.1f} {units[idx]}" if idx > 0 else f"{int(size)} {units[idx]}"


def _humanize_duration(d: timedelta) -> str:
    total = int(d.total_seconds())
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}min"
    if m:
        return f"{m}min {s:02d}s"
    return f"{s}s"


def _tail_log(path: Path, lines: int) -> str | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    return "\n".join(text.splitlines()[-lines:])
```

- [ ] **Step 11.3: Run, lint, type check, commit**

```bash
uv run pytest tests/test_notify/test_events.py -v
uv run ruff check src/atomx_toolkit/notify/events.py tests/test_notify/test_events.py
uv run pyright src/atomx_toolkit/notify/events.py tests/test_notify/test_events.py
git add src/atomx_toolkit/notify/events.py tests/test_notify/test_events.py
git commit -m "feat: notify event dataclasses and email body formatters"
```

---

## Task 12: Notify send (smtplib + dedup state) + aiosmtpd fixture

**Files:**
- Create: `src/atomx_toolkit/notify/send.py`
- Modify: `tests/test_notify/conftest.py` (aiosmtpd fixture)
- Create: `tests/test_notify/test_send.py`

- [ ] **Step 12.1: Write the aiosmtpd fixture**

Replace `tests/test_notify/conftest.py`:
```python
"""Mock SMTP server fixture using aiosmtpd."""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pytest
from aiosmtpd.controller import Controller


@dataclass
class _CapturedEmail:
    sender: str
    recipients: list[str]
    raw: bytes


class _Sink:
    def __init__(self) -> None:
        self.messages: list[_CapturedEmail] = []

    async def handle_DATA(self, server: Any, session: Any, envelope: Any) -> str:
        self.messages.append(
            _CapturedEmail(
                sender=envelope.mail_from,
                recipients=list(envelope.rcpt_tos),
                raw=envelope.content,
            )
        )
        return "250 OK"


@dataclass
class FakeSmtp:
    host: str
    port: int
    sink: _Sink


@pytest.fixture
def fake_smtp() -> Iterator[FakeSmtp]:
    sink = _Sink()
    controller = Controller(sink, hostname="127.0.0.1", port=0)
    controller.start()
    yield FakeSmtp(host=controller.hostname, port=controller.server.sockets[0].getsockname()[1], sink=sink)
    controller.stop()
```

- [ ] **Step 12.2: Write send tests**

`tests/test_notify/test_send.py`:
```python
"""Tests for SMTP send and toolkit_error dedup."""

from __future__ import annotations

from pathlib import Path

import pytest

from atomx_toolkit.notify.credentials import SmtpCredentials
from atomx_toolkit.notify.send import (
    DedupState,
    send_email,
    should_send_toolkit_error,
)


def test_send_email_delivers(tmp_path: Path, fake_smtp: object) -> None:
    creds = SmtpCredentials(
        user="anyone@example.com",
        password="ignored",
        host=fake_smtp.host,
        port=fake_smtp.port,
    )
    send_email(
        creds=creds,
        recipients=["alice@example.com", "bob@example.com"],
        subject="hello",
        body="world",
        use_tls=False,  # local fake doesn't do STARTTLS
    )
    assert len(fake_smtp.sink.messages) == 1
    msg = fake_smtp.sink.messages[0]
    assert "alice@example.com" in msg.recipients
    assert "bob@example.com" in msg.recipients
    assert b"hello" in msg.raw
    assert b"world" in msg.raw


def test_send_email_skipped_when_no_recipients(fake_smtp: object) -> None:
    creds = SmtpCredentials(
        user="x@x.com", password="p", host=fake_smtp.host, port=fake_smtp.port
    )
    send_email(creds=creds, recipients=[], subject="s", body="b", use_tls=False)
    assert fake_smtp.sink.messages == []


def test_dedup_first_send_allowed(tmp_path: Path) -> None:
    state_file = tmp_path / "dedup.json"
    state = DedupState(path=state_file, cooldown_seconds=300)
    assert should_send_toolkit_error(state, "key1") is True


def test_dedup_within_cooldown_blocks(tmp_path: Path) -> None:
    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    assert should_send_toolkit_error(state, "k") is True
    assert should_send_toolkit_error(state, "k") is False


def test_dedup_after_cooldown_allows(tmp_path: Path) -> None:
    import time

    state = DedupState(path=tmp_path / "d.json", cooldown_seconds=0)
    assert should_send_toolkit_error(state, "k") is True
    time.sleep(0.05)
    assert should_send_toolkit_error(state, "k") is True


def test_dedup_strips_timestamps_for_key() -> None:
    from atomx_toolkit.notify.send import _normalize_for_dedup

    a = "2026-04-30T12:00:00 ERROR something failed"
    b = "2026-04-30T12:00:01 ERROR something failed"
    assert _normalize_for_dedup(a) == _normalize_for_dedup(b)
```

- [ ] **Step 12.3: Implement send.py**

`src/atomx_toolkit/notify/send.py`:
```python
"""SMTP send + toolkit_error dedup state."""

from __future__ import annotations

import json
import logging
import re
import smtplib
import time
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path

from atomx_toolkit.notify.credentials import SmtpCredentials

logger = logging.getLogger(__name__)


def send_email(
    *,
    creds: SmtpCredentials,
    recipients: list[str],
    subject: str,
    body: str,
    use_tls: bool = True,
) -> None:
    """Send a single plain-text email. Logs and returns silently on no recipients."""
    if not recipients:
        logger.info("no recipients; skipping email %r", subject)
        return
    msg = EmailMessage()
    msg["From"] = creds.user
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(creds.host, creds.port, timeout=30) as smtp:
            if use_tls:
                smtp.starttls()
                smtp.login(creds.user, creds.password)
            smtp.send_message(msg)
        logger.info("sent email %r to %d recipients", subject, len(recipients))
    except (smtplib.SMTPException, OSError) as exc:
        logger.error("smtp failure for %r: %s", subject, exc)


# ---- dedup ----


@dataclass
class DedupState:
    path: Path
    cooldown_seconds: int

    def _read(self) -> dict[str, float]:
        if not self.path.exists():
            return {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}

    def _write(self, data: dict[str, float]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data), encoding="utf-8")


_TIMESTAMP_PATTERNS = [
    re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:[+-]\d{2}:?\d{2}|Z)?"),
    re.compile(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}"),
]


def _normalize_for_dedup(content: str) -> str:
    out = content
    for pat in _TIMESTAMP_PATTERNS:
        out = pat.sub("<TS>", out)
    return out[:200]


def should_send_toolkit_error(state: DedupState, content: str) -> bool:
    """Return True iff this content key has not been seen within cooldown."""
    key = _normalize_for_dedup(content)
    now = time.time()
    data = state._read()
    last = data.get(key, 0.0)
    if now - last < state.cooldown_seconds:
        return False
    data[key] = now
    state._write(data)
    return True
```

- [ ] **Step 12.4: Run, lint, type check, commit**

```bash
uv run pytest tests/test_notify/test_send.py -v
uv run ruff check src/atomx_toolkit/notify/send.py tests/test_notify/{conftest,test_send}.py
uv run pyright src/atomx_toolkit/notify/send.py tests/test_notify/{conftest,test_send}.py
git add src/atomx_toolkit/notify/send.py tests/test_notify/conftest.py tests/test_notify/test_send.py
git commit -m "feat: SMTP send and toolkit_error dedup state"
```

---

## Task 13: Notify CLI group (test, list-subscribers) + toolkit_error logging handler

**Files:**
- Create: `src/atomx_toolkit/notify/handler.py`
- Create: `src/atomx_toolkit/notify/cli.py`
- Modify: `src/atomx_toolkit/cli.py` (mount notify group)
- Create: `tests/test_notify/test_handler.py`

- [ ] **Step 13.1: Write handler test**

`tests/test_notify/test_handler.py`:
```python
"""Tests for the toolkit_error logging handler."""

import logging
from pathlib import Path
from unittest.mock import MagicMock

from atomx_toolkit.notify.handler import ToolkitErrorHandler
from atomx_toolkit.notify.send import DedupState


def test_handler_dispatches_on_warning(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.warning("disk almost full at /var")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 1
    args, kwargs = sender.call_args
    assert "disk almost full" in kwargs["body"]


def test_handler_does_not_fire_on_info(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler_info")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.info("nothing wrong")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 0


def test_handler_dedup_suppresses_repeat(tmp_path: Path) -> None:
    sender = MagicMock()
    handler = ToolkitErrorHandler(
        sender=sender, dedup=DedupState(path=tmp_path / "d.json", cooldown_seconds=300)
    )
    logger = logging.getLogger("test_handler_dup")
    logger.setLevel(logging.DEBUG)
    logger.addHandler(handler)
    try:
        logger.warning("same message")
        logger.warning("same message")
    finally:
        logger.removeHandler(handler)
    assert sender.call_count == 1
```

- [ ] **Step 13.2: Implement handler.py**

`src/atomx_toolkit/notify/handler.py`:
```python
"""logging.Handler that dispatches toolkit_error emails on WARNING+ records."""

from __future__ import annotations

import logging
from typing import Callable

from atomx_toolkit.notify.send import DedupState, should_send_toolkit_error

ToolkitErrorSender = Callable[..., None]
"""Signature: sender(*, subject: str, body: str) -> None."""


class ToolkitErrorHandler(logging.Handler):
    def __init__(
        self,
        sender: ToolkitErrorSender,
        dedup: DedupState,
        level: int = logging.WARNING,
    ) -> None:
        super().__init__(level=level)
        self._sender = sender
        self._dedup = dedup

    def emit(self, record: logging.LogRecord) -> None:
        try:
            body = self.format(record)
            if not should_send_toolkit_error(self._dedup, body):
                return
            self._sender(subject="[atomx-toolkit] toolkit error", body=body)
        except Exception:  # never let logging crash the app
            self.handleError(record)
```

- [ ] **Step 13.3: Implement notify/cli.py**

`src/atomx_toolkit/notify/cli.py`:
```python
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
    if cfg.notify.recipients_dir is not None:
        return cfg.notify.recipients_dir
    return config_path.parent / "recipients"


@app.command("test")
def test_cmd(
    event: Annotated[str, typer.Option("--event", help="Event name")],
    config: Annotated[Path, typer.Option("--config")] = None,  # type: ignore[assignment]
    smtp_env: Annotated[Path, typer.Option("--smtp-env")] = None,  # type: ignore[assignment]
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
        raise typer.Exit(code=2)
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
    config: Annotated[Path, typer.Option("--config")] = None,  # type: ignore[assignment]
) -> None:
    """List resolved subscribers per event."""
    cfg_path = config or _default_config_path()
    try:
        rdir = _recipients_dir(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2)
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
```

- [ ] **Step 13.4: Mount notify group on root CLI**

Modify `src/atomx_toolkit/cli.py` to add:
```python
from atomx_toolkit.notify.cli import app as notify_app

# after app = typer.Typer(...) and before existing add_typer:
app.add_typer(notify_app, name="notify")
```

- [ ] **Step 13.5: Run tests, lint, type check, commit**

```bash
uv run pytest tests/test_notify/test_handler.py tests/test_cli.py -v
uv run ruff check src/atomx_toolkit/notify/handler.py src/atomx_toolkit/notify/cli.py src/atomx_toolkit/cli.py
uv run pyright src/atomx_toolkit/notify/handler.py src/atomx_toolkit/notify/cli.py src/atomx_toolkit/cli.py
git add src/atomx_toolkit/notify/handler.py src/atomx_toolkit/notify/cli.py src/atomx_toolkit/cli.py tests/test_notify/test_handler.py
git commit -m "feat: notify Typer commands and toolkit_error logging handler"
```

---

## Task 14: Wire notify into transfer CLI

**Files:**
- Modify: `src/atomx_toolkit/transfer/cli.py`
- Modify: `tests/test_transfer/test_pipeline.py` (verify dispatch happens — optional integration test)

The pipeline functions stay pure (they raise / return). The dispatch
of `TransferReport` / `BatchReport` happens at the CLI layer where
all three subsystems meet.

- [ ] **Step 14.1: Add a small dispatch helper module**

Create `src/atomx_toolkit/notify/dispatch.py`:
```python
"""Bridge from transfer-side data to notify subsystem.

Lives in `notify/` rather than in transfer/ so transfer remains
ignorant of email entirely.
"""

from __future__ import annotations

import logging
from pathlib import Path

from atomx_toolkit.config import Config
from atomx_toolkit.notify.credentials import (
    SmtpCredentialsMissing,
    load_smtp_credentials,
)
from atomx_toolkit.notify.events import (
    BatchReport,
    TransferReport,
    format_batch_report,
    format_transfer_report,
)
from atomx_toolkit.notify.recipients import resolve_recipients
from atomx_toolkit.notify.send import send_email

logger = logging.getLogger(__name__)


def _recipients_dir(config_path: Path, cfg: Config) -> Path:
    return cfg.notify.recipients_dir or (config_path.parent / "recipients")


def dispatch_transfer_report(
    report: TransferReport, *, cfg: Config, config_path: Path, smtp_env: Path
) -> None:
    if not cfg.notify.enabled:
        return
    creds = load_smtp_credentials(smtp_env)
    if isinstance(creds, SmtpCredentialsMissing):
        logger.warning("smtp credentials missing; skipping transfer_report email")
        return
    res = resolve_recipients("transfer_report", _recipients_dir(config_path, cfg))
    if not res.emails:
        logger.info("no recipients for transfer_report; skipping email")
        return
    subject, body = format_transfer_report(report)
    send_email(creds=creds, recipients=res.emails, subject=subject, body=body)


def dispatch_batch_report(
    report: BatchReport, *, cfg: Config, config_path: Path, smtp_env: Path
) -> None:
    if not cfg.notify.enabled:
        return
    creds = load_smtp_credentials(smtp_env)
    if isinstance(creds, SmtpCredentialsMissing):
        logger.warning("smtp credentials missing; skipping batch_report email")
        return
    res = resolve_recipients("batch_report", _recipients_dir(config_path, cfg))
    if not res.emails:
        logger.info("no recipients for batch_report; skipping email")
        return
    subject, body = format_batch_report(report)
    send_email(creds=creds, recipients=res.emails, subject=subject, body=body)
```

- [ ] **Step 14.2: Update transfer/cli.py to dispatch reports**

Modify `src/atomx_toolkit/transfer/cli.py`:

1. Add imports at top:
```python
from datetime import datetime, timezone

from atomx_toolkit.notify.dispatch import dispatch_batch_report, dispatch_transfer_report
from atomx_toolkit.notify.events import BatchItem, BatchReport, TransferReport
```

2. In `run_cmd`, after the pipeline call, build a `TransferReport` for the success case and dispatch. For the failure path, build a `TransferReport(status="failed", ...)` from inside the `except TransferError` block. Updated body:

```python
@app.command("run")
def run_cmd(
    name_remote: Annotated[str, typer.Argument(...)],
    name_local: Annotated[str, typer.Argument(...)],
    config: Annotated[Path, typer.Option("--config")] = None,  # type: ignore[assignment]
) -> None:
    cfg_path = config or _default_config_path()
    smtp_env_path = _default_config_path().parent / "smtp.env"
    try:
        cfg = load_config(cfg_path)
    except ConfigError as exc:
        console.print(f"[red]config error:[/red] {exc}")
        raise typer.Exit(code=2)
    try:
        creds = load_sftp_credentials(_default_sftp_env_path())
    except SftpCredentialsError as exc:
        console.print(f"[red]credential error:[/red] {exc}")
        raise typer.Exit(code=2)
    started = datetime.now(timezone.utc)
    log_path = cfg.paths.log_root / name_local / f"{name_local}.log"
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
        raise typer.Exit(code=2)
    except TransferError as exc:
        completed = datetime.now(timezone.utc)
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
        dispatch_transfer_report(report, cfg=cfg, config_path=cfg_path, smtp_env=smtp_env_path)
        console.print(f"[red]transfer failed:[/red] {exc}")
        raise typer.Exit(code=1)

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
    dispatch_transfer_report(report, cfg=cfg, config_path=cfg_path, smtp_env=smtp_env_path)
    console.print(f"[green]ok:[/green] {name_local} ({result.file_count} files)")
```

3. In `batch_cmd`, after `run_batch` returns, convert each `BatchItemResult` to a `BatchItem` and dispatch a `BatchReport`:

```python
items = [
    BatchItem(
        name_remote=i.name_remote,
        name_local=i.name_local,
        status=i.status,
        duration=i.duration,
        failure_message=i.failure_message,
    )
    for i in result.items
]
report = BatchReport(
    jobs_tsv=jobs_tsv,
    started_at=result.started_at,
    completed_at=result.completed_at,
    items=items,
)
dispatch_batch_report(report, cfg=cfg, config_path=cfg_path, smtp_env=smtp_env_path)
```

(Insert this just before the `if result.any_failed or result.all_skipped_locked` check.)

- [ ] **Step 14.3: Run all tests**

```bash
uv run pytest -v
```

Existing tests should still pass (notify dispatch is silently skipped when SMTP creds are missing — which they will be in test envs).

- [ ] **Step 14.4: Lint, type check, commit**

```bash
uv run ruff check src/ tests/
uv run pyright src/ tests/
git add src/atomx_toolkit/notify/dispatch.py src/atomx_toolkit/transfer/cli.py
git commit -m "feat: dispatch transfer/batch reports through notify subsystem"
```

---

## Task 15: Install init

**Files:**
- Create: `src/atomx_toolkit/install/__init__.py`
- Create: `src/atomx_toolkit/install/init.py`
- Create: `src/atomx_toolkit/install/cli.py`
- Modify: `src/atomx_toolkit/cli.py` (mount install group)
- Create: `tests/test_install/__init__.py`
- Create: `tests/test_install/test_init.py`

- [ ] **Step 15.1: Write tests**

`tests/test_install/__init__.py`: empty.

`tests/test_install/test_init.py`:
```python
"""Tests for `install init` template writer."""

from pathlib import Path

import pytest

from atomx_toolkit.install.init import (
    InstallInitError,
    init_config_dir,
)


def test_creates_all_files_on_clean_dir(tmp_path: Path) -> None:
    init_config_dir(tmp_path)
    for name in ("config.toml", "sftp.env", "smtp.env"):
        assert (tmp_path / name).exists()
    for ev in ("transfer_report", "batch_report", "toolkit_error", "default"):
        assert (tmp_path / "recipients" / f"{ev}.txt").exists()
    assert (tmp_path / "state").is_dir()


def test_refuses_to_clobber_config(tmp_path: Path) -> None:
    (tmp_path / "config.toml").write_text("custom = true")
    with pytest.raises(InstallInitError, match="exists"):
        init_config_dir(tmp_path)


def test_force_overwrites_envs_but_not_recipients(tmp_path: Path) -> None:
    init_config_dir(tmp_path)
    # User edits the recipients file
    rfile = tmp_path / "recipients" / "transfer_report.txt"
    rfile.write_text("alice@example.com\n")
    # User also edits config.toml
    cfg = tmp_path / "config.toml"
    cfg.write_text("custom = true")
    init_config_dir(tmp_path, force=True)
    assert "custom" not in cfg.read_text()  # overwritten
    assert "alice@example.com" in rfile.read_text()  # preserved


def test_recipient_files_have_header(tmp_path: Path) -> None:
    init_config_dir(tmp_path)
    content = (tmp_path / "recipients" / "transfer_report.txt").read_text()
    assert content.startswith("# ")
    assert "transfer_report" in content
```

- [ ] **Step 15.2: Implement install/init.py**

`src/atomx_toolkit/install/__init__.py`:
```python
"""Install subsystem: writes config templates."""
```

`src/atomx_toolkit/install/init.py`:
```python
"""Write atomx-toolkit config templates into a config directory."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class InstallInitError(Exception):
    """Refusal to clobber existing files without --force."""


_CONFIG_TOML = """\
[sftp]
hostname = "na.export.atomx.nanostring.com"
remote_root = "/"
# username and password come from env or sftp.env (never put them here).

[paths]
log_root = "/data/log/atomx"
backup_root = "/data/backup/atomx"

[notify]
enabled = true
toolkit_error_cooldown_seconds = 300
# recipients_dir = "/some/other/path"  # optional
"""

_SFTP_ENV = """\
ATOMX_SFTP_USER=
ATOMX_SFTP_PASSWORD=
"""

_SMTP_ENV = """\
# Gmail app password: https://myaccount.google.com/apppasswords
ATOMX_SMTP_USER=
ATOMX_SMTP_APP_PASSWORD=

# Optional overrides; defaults shown
# ATOMX_SMTP_HOST=smtp.gmail.com
# ATOMX_SMTP_PORT=587
"""


_RECIPIENT_EVENTS = ("transfer_report", "batch_report", "toolkit_error", "default")


def _recipient_template(event: str) -> str:
    return (
        f"# Subscribers for {event}. One email per line.\n"
        f"# Blank lines and lines starting with '#' are ignored.\n"
        f"# Edit at runtime; changes take effect on the next email send.\n"
        f"\n"
    )


def init_config_dir(config_dir: Path, *, force: bool = False) -> None:
    """Populate config_dir with templates. Raises InstallInitError if files exist
    and --force is not given. recipient files are NEVER overwritten."""
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "recipients").mkdir(exist_ok=True)
    (config_dir / "state").mkdir(exist_ok=True)

    _write_overwriteable(config_dir / "config.toml", _CONFIG_TOML, force)
    _write_overwriteable(config_dir / "sftp.env", _SFTP_ENV, force)
    _write_overwriteable(config_dir / "smtp.env", _SMTP_ENV, force)

    for event in _RECIPIENT_EVENTS:
        path = config_dir / "recipients" / f"{event}.txt"
        if path.exists():
            continue
        path.write_text(_recipient_template(event), encoding="utf-8")

    _print_pre_checks(config_dir)


def _write_overwriteable(path: Path, content: str, force: bool) -> None:
    if path.exists() and not force:
        raise InstallInitError(f"{path} already exists; use --force to overwrite")
    path.write_text(content, encoding="utf-8")


def _print_pre_checks(config_dir: Path) -> None:
    md5sum = shutil.which("md5sum")
    if md5sum:
        print(f"[ok] md5sum present at {md5sum}")
    else:
        print("[warn] md5sum not on PATH; install GNU coreutils before running transfers")

    known_hosts = Path.home() / ".ssh" / "known_hosts"
    if known_hosts.exists() or known_hosts.parent.is_dir():
        print(f"[ok] known_hosts location ready at {known_hosts}")
    else:
        print(
            f"[warn] {known_hosts.parent} does not exist; first SFTP connect will fail "
            f"to persist host key. mkdir -p ~/.ssh and chmod 700 ~/.ssh"
        )
```

- [ ] **Step 15.3: Implement install/cli.py**

`src/atomx_toolkit/install/cli.py`:
```python
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
    config_dir: Annotated[Path, typer.Option("--config-dir")] = None,  # type: ignore[assignment]
    force: Annotated[bool, typer.Option("--force")] = False,
) -> None:
    """Write config templates to ~/.config/atomx-toolkit/ (or --config-dir)."""
    target = config_dir or (Path.home() / ".config" / "atomx-toolkit")
    try:
        init_config_dir(target, force=force)
    except InstallInitError as exc:
        console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2)
    console.print(f"[green]wrote templates to {target}[/green]")
```

- [ ] **Step 15.4: Mount install group**

Add to `src/atomx_toolkit/cli.py`:
```python
from atomx_toolkit.install.cli import app as install_app

# after the existing add_typer calls:
app.add_typer(install_app, name="install")
```

- [ ] **Step 15.5: Run tests, lint, type check, commit**

```bash
uv run pytest tests/test_install/ tests/test_cli.py -v
uv run ruff check src/atomx_toolkit/install/ tests/test_install/ src/atomx_toolkit/cli.py
uv run pyright src/atomx_toolkit/install/ src/atomx_toolkit/cli.py
git add src/atomx_toolkit/install/ tests/test_install/ src/atomx_toolkit/cli.py
git commit -m "feat: install init writes config templates and pre-check status"
```

---

## Task 16: Final docs, CI, pre-commit verification, and end-to-end smoke

**Files:**
- Create: `docs/setup-host.md`
- Create: `docs/transfer-pipeline.md`
- Modify: `README.md` (expand from Task 1 stub)
- Create: `.github/workflows/ci.yml`

- [ ] **Step 16.1: Expand README.md**

Replace `README.md` with:
```markdown
# atomx-toolkit

AtoMx SFTP transfer with double-download MD5 integrity verification, per-file atomic writes, study-level crash locks, and email reporting.

> v0.1.0. Built for unattended runs on Linux.

## Subsystems

- `transfer` — SFTP download pipeline. `transfer run` for a single study, `transfer batch` for a TSV-driven queue, `transfer plan` for a dry-run preview.
- `notify` — Plain-text email reports per run (success summary or failure diagnostics) and a tool-health channel for warnings/errors. Recipients per event in `~/.config/atomx-toolkit/recipients/<event>.txt`.
- `install` — `install init` writes config templates and pre-check report.

## Install

```bash
pip install git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.1.0
```

Requires Python 3.12+ and the `md5sum` binary (GNU coreutils, default on Linux).

## Setup

```bash
atomx-toolkit install init
# edit ~/.config/atomx-toolkit/config.toml — paths and SFTP host
# edit ~/.config/atomx-toolkit/sftp.env — AtoMx username/password
# edit ~/.config/atomx-toolkit/smtp.env — Gmail app password
# edit ~/.config/atomx-toolkit/recipients/*.txt — your email addresses
```

See [`docs/setup-host.md`](docs/setup-host.md) for full setup details.

## Usage

Single study:
```bash
atomx-toolkit transfer run <name_remote> <name_local>
```

Batch (recommended):
```bash
# jobs.tsv: two whitespace-separated columns
echo 'HCC_TMA006_..._116    HCC_TMA006_section05_3ug_v132' > jobs.tsv

atomx-toolkit transfer plan jobs.tsv     # preview
atomx-toolkit transfer batch jobs.tsv    # run
```

Reports go to email; details in [`docs/transfer-pipeline.md`](docs/transfer-pipeline.md).

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Operational failure: at least one study failed, or batch made no progress |
| 2 | Configuration error: missing or malformed TOML, missing required key, lock held, missing `md5sum` |
| 3 | Unexpected runtime error |

## Roadmap

- QC subsystem (post-transfer report generation)
- PyPI release once external usage warrants it
- Parallel batch (currently sequential by design)

## License

MIT, see [LICENSE](LICENSE).
```

- [ ] **Step 16.2: Write `docs/setup-host.md`**

```markdown
# Host setup

Run on a Linux host with Python 3.12+, `md5sum`, and outbound network
to AtoMx and SMTP.

## 1. Install Python and md5sum

```bash
# Debian/Ubuntu
sudo apt install python3.12 python3.12-venv coreutils

# Fedora
sudo dnf install python3.12 coreutils
```

## 2. Install atomx-toolkit

```bash
pip install --user git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.1.0
```

Or use `uv`:
```bash
uv tool install git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.1.0
```

## 3. Initialize config

```bash
atomx-toolkit install init
```

This creates `~/.config/atomx-toolkit/`:
```
config.toml         # paths, hostname, [notify] toggle
sftp.env            # ATOMX_SFTP_USER / ATOMX_SFTP_PASSWORD
smtp.env            # ATOMX_SMTP_USER / ATOMX_SMTP_APP_PASSWORD
recipients/         # per-event subscriber lists
state/              # runtime dedup state (managed automatically)
```

## 4. Edit config.toml

```toml
[paths]
log_root = "/data/log/atomx"
backup_root = "/data/backup/atomx"
```

`backup_root` must have free space >= the largest expected study size,
because each study is downloaded twice (then the second copy is removed
on success).

## 5. Set credentials

`sftp.env`:
```env
ATOMX_SFTP_USER=your_atomx_username
ATOMX_SFTP_PASSWORD=your_atomx_password
```

`smtp.env` (for Gmail; generate an app password at <https://myaccount.google.com/apppasswords>):
```env
ATOMX_SMTP_USER=youraccount@gmail.com
ATOMX_SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

Alternative: set the same names as environment variables (env wins
over the dotenv file).

## 6. Subscribe recipients

`~/.config/atomx-toolkit/recipients/transfer_report.txt`:
```
you@example.com
```

`~/.config/atomx-toolkit/recipients/batch_report.txt`:
```
you@example.com
```

`~/.config/atomx-toolkit/recipients/toolkit_error.txt`:
```
you@example.com
```

(default.txt is a fallback; leave empty if event-specific files cover
your needs.)

## 7. Test the pipeline

```bash
atomx-toolkit notify test --event transfer_report --dry-run
atomx-toolkit notify test --event transfer_report
# check your inbox

atomx-toolkit transfer plan example_jobs.tsv
```
```

- [ ] **Step 16.3: Write `docs/transfer-pipeline.md`**

```markdown
# Transfer pipeline

Per study, the pipeline walks 6 phases (plus a guard) before writing
the success marker. Failures abort with a clear exit code and an email.

```
Pipeline entry
   ↓
Guard: md5sum_pass exists? → return early (exit 0, no work)
   ↓
Phase 0  mkdir -p log dirs and backup dirs
   ↓
Acquire .atomx-toolkit.lock (atomic, O_CREAT|O_EXCL)
   ↓
Phase 1  list remote files (×2), assert sets equal
   - on mismatch: write index/path_fail, RemoteListInconsistent
   - on zero files: WARNING (toolkit_error email)
   ↓
Phase 2  download → AtoMx/   (per-file *.part rename, size-match resume)
Phase 3  download → AtoMx_copy/
   ↓
Phase 4  md5sum AtoMx/        → md5sum/md5sum_1.txt
Phase 5  md5sum AtoMx_copy/   → md5sum/md5sum_2.txt
   ↓
Phase 6  compare md5 dicts
   - mismatch / missing: write index/md5sum_fail + md5sum_diff.csv,
     IntegrityError
   - all match: rmtree(AtoMx_copy/), write index/md5sum_pass = ISO timestamp
   ↓
Release lock (finally)
```

## State files

`<log_root>/<name_local>/index/`:
- `path_pass` / `path_fail` — phase 1 result (empty marker)
- `md5sum_pass` — phase 6 success; **content is the ISO 8601
  completion timestamp**, used by `transfer plan` to display history
- `md5sum_fail` — phase 6 failure (empty marker)

`<log_root>/<name_local>/path/path_{1,2}.txt` — one absolute remote
POSIX path per line.

`<log_root>/<name_local>/md5sum/`:
- `md5sum_1.txt`, `md5sum_2.txt` — `md5sum` standard format
- `md5sum_diff.csv` — present only on phase 6 failure; columns
  `(file, md5_1, md5_2, status)`

`<backup_root>/<name_local>/`:
- `.atomx-toolkit.lock` — JSON, present only while pipeline is running
- `AtoMx/` — primary backup, persists after success
- `AtoMx_copy/` — secondary backup, removed after phase 6

## Lock semantics

A study-level lock prevents two pipelines from racing on the same
study. **No PID liveness check**: if a process crashed and left a
lock behind, you must inspect the partial state and `rm` the lock
manually. This forces a human to verify before re-running.

When a lock is found by `transfer batch`, the affected study is
classified `skipped_locked` in the batch report, and the batch
continues with the next study.

## Resume

Three layers of resume:

1. **Per-file** (Phase 2/3): if local file exists with size matching
   remote, skip; if it exists with wrong size or only `*.part` is
   present, delete and re-download.
2. **Per-study** (pipeline entry guard): if `md5sum_pass` exists,
   return immediately.
3. **Per-batch** (`transfer batch` pre-scan): each TSV row
   classified into `complete_already` / `skipped_locked` / `pending`
   before any pipeline starts.

## Why double-download

The original cosmx_utils workflow caught a transfer interruption
issue this way; the integrity check is preserved verbatim. A single
download with read-back-verify catches local-disk write corruption
but not remote-side instability. Double download to two distinct
local paths catches both, at the cost of 2× bandwidth and disk
peak. For the AtoMx workflow's typical study sizes this is
acceptable.
```

- [ ] **Step 16.4: Write GitHub Actions CI**

`.github/workflows/ci.yml`:
```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true
      - name: install python
        run: uv python install 3.12
      - name: sync dependencies
        run: uv sync --all-extras --dev
      - name: ruff check
        run: uv run ruff check src/ tests/
      - name: ruff format check
        run: uv run ruff format --check src/ tests/
      - name: pyright
        run: uv run pyright src/ tests/
      - name: pytest
        run: uv run pytest --cov=atomx_toolkit --cov-report=term
```

- [ ] **Step 16.5: Run pre-commit + full test suite**

```bash
uv run pre-commit run --all-files
uv run pytest -v --cov=atomx_toolkit --cov-report=term
```

Coverage on `src/atomx_toolkit/transfer/` and `src/atomx_toolkit/notify/`
should be ≥ 85%. If not, identify the gap and add a test.

- [ ] **Step 16.6: Commit final docs and CI**

```bash
git add README.md docs/setup-host.md docs/transfer-pipeline.md .github/workflows/ci.yml
git commit -m "docs: README, setup-host, transfer-pipeline, and GitHub Actions CI"
```

- [ ] **Step 16.7: Tag v0.1.0**

Only after the operator verifies a real end-to-end transfer against
AtoMx (manual step, not testable in CI):

```bash
git tag -a v0.1.0 -m "atomx-toolkit v0.1.0"
git push origin main --tags
```

---

## Self-review notes (post-write)

The plan covers every spec requirement:

- Spec §3 subsystems → Tasks 3-15 (each subsystem split into 1-3 tasks)
- Spec §4.1 6 phases + guard → Task 7
- Spec §4.2 atomic per-file writes → Task 6 (sftp.download_file)
- Spec §4.3 lock with O_CREAT|O_EXCL → Task 5
- Spec §4.4 resume granularity → Tasks 7 (per-file, per-study) + 8 (per-batch)
- Spec §4.5 paramiko + AutoAddPolicy → Task 6
- Spec §4.6 md5 dict-based diff → Task 4
- Spec §4.7 jobs.tsv format → Task 8
- Spec §4.8 transfer plan → Task 8 (classify_jobs) + Task 9 (CLI)
- Spec §4.9 status files → Tasks 5, 7
- Spec §5 notify subsystem → Tasks 10-13
- Spec §6 install init → Task 15
- Spec §7 config TOML → Task 2
- Spec §8 CLI surface → Tasks 9, 13, 15
- Spec §9 exit codes → Tasks 9, 13, 15 (handled per command)
- Spec §10 error handling + KeyboardInterrupt → Tasks 8, 9, 14
- Spec §11 logging → setup is implicit; explicit log file handlers can be added in Task 14 if missing
- Spec §12 testing strategy → mirrored in every task
- Spec §13 project layout → Task 1 + each task creates files in the right place
- Spec §14 toolchain → Task 1
- Spec §15 roadmap → README in Task 16
- Spec §16 out of scope → respected

No placeholders ("TBD", "TODO", "implement later", "fill in details")
left in the plan. Type / function names are consistent across tasks
(e.g., `Config`, `SftpCredentials`, `SmtpCredentials`,
`PipelineResult`, `BatchPlan`, `BatchRunResult`, `BatchItem`,
`TransferReport`, `BatchReport`).
