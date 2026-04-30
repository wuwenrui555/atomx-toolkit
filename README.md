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
