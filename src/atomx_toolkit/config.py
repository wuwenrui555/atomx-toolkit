"""TOML configuration loader for atomx-toolkit."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast


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
    recipients_dir: Path
    enabled: bool = True
    toolkit_error_cooldown_seconds: int = 300


@dataclass(frozen=True)
class Config:
    sftp: SftpConfig
    paths: PathsConfig
    notify: NotifyConfig


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
    notify_raw = data.get("notify", {})
    if not isinstance(notify_raw, dict):
        raise ConfigError(f"{path}: [notify] must be a table")
    notify_section = cast(dict[str, Any], notify_raw)
    recipients_dir_str = notify_section.get("recipients_dir")
    if recipients_dir_str is not None and not isinstance(recipients_dir_str, str):
        raise ConfigError(
            f"{path}: [notify].recipients_dir must be a string, got "
            f"{type(recipients_dir_str).__name__}: {recipients_dir_str!r}"
        )
    recipients_dir = (
        Path(recipients_dir_str) if recipients_dir_str else path.parent / "recipients"
    )
    notify_cfg = NotifyConfig(
        enabled=_bool_or_default(notify_section, "enabled", True, "[notify].enabled", path),
        toolkit_error_cooldown_seconds=_int_or_default(
            notify_section,
            "toolkit_error_cooldown_seconds",
            300,
            "[notify].toolkit_error_cooldown_seconds",
            path,
        ),
        recipients_dir=recipients_dir,
    )
    return Config(sftp=sftp_cfg, paths=paths_cfg, notify=notify_cfg)


def _require_section(data: dict[str, Any], name: str, path: Path) -> dict[str, Any]:
    section = data.get(name)
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: missing required section [{name}]")
    return cast(dict[str, Any], section)


def _require_str(section: dict[str, Any], key: str, label: str, path: Path) -> str:
    value = section.get(key)
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{path}: missing required key {label}")
    return value


def _str_or_default(section: dict[str, Any], key: str, default: str) -> str:
    value = section.get(key)
    return value if isinstance(value, str) and value else default


def _bool_or_default(
    section: dict[str, Any], key: str, default: bool, label: str, path: Path
) -> bool:
    value = section.get(key, default)
    if not isinstance(value, bool):
        raise ConfigError(
            f"{path}: {label} must be a TOML boolean (true/false), got "
            f"{type(value).__name__}: {value!r}"
        )
    return value


def _int_or_default(
    section: dict[str, Any], key: str, default: int, label: str, path: Path
) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ConfigError(
            f"{path}: {label} must be a TOML integer, got "
            f"{type(value).__name__}: {value!r}"
        )
    return value
