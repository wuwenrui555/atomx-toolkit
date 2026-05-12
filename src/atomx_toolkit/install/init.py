"""Write atomx-toolkit config templates into a config directory."""

from __future__ import annotations

import logging
import shutil
import sys
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
# ATOMX_SMTP_PORT=465
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
        print(f"[ok] md5sum present at {md5sum}", file=sys.stderr)
    else:
        print(
            "[warn] md5sum not on PATH; install GNU coreutils before running transfers",
            file=sys.stderr,
        )

    known_hosts = Path.home() / ".ssh" / "known_hosts"
    if known_hosts.exists() or known_hosts.parent.is_dir():
        print(f"[ok] known_hosts location ready at {known_hosts}", file=sys.stderr)
    else:
        print(
            f"[warn] {known_hosts.parent} does not exist; first SFTP connect will fail "
            f"to persist host key. mkdir -p ~/.ssh and chmod 700 ~/.ssh",
            file=sys.stderr,
        )
