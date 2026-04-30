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
