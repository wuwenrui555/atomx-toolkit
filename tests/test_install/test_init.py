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
