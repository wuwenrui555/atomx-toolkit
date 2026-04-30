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
