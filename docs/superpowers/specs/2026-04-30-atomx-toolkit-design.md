# atomx-toolkit — Design Spec

**Date:** 2026-04-30
**Status:** Draft, awaiting user review
**Repo (planned):** `wuwenrui555/atomx-toolkit` (public, GitHub-only install)
**Replaces:** loosely succeeds `SizunJiangLab/cosmx_utils` (the `atomx/` subsystem); no migration shim, no deprecation notice in cosmx_utils.

## 1. Overview

`atomx-toolkit` is a Python CLI that downloads study directories from the
NanoString AtoMx SFTP export server to local disk, with strict
integrity checks and email reporting for unattended runs. It is a
ground-up rewrite of the `atomx/` module currently living in
`SizunJiangLab/cosmx_utils`, packaged to fusion-toolkit's quality bar
(strict typing, tests, src layout, Typer CLI, TOML config, env-or-dotenv
credential chain).

The expected operator workflow:

1. An experimenter maintains a Google Sheet of studies awaiting
   transfer (columns: `name_atomx`, `name_storage`, etc.).
2. The operator (Wenrui) exports the relevant rows to a 2-column TSV.
3. `atomx-toolkit transfer batch jobs.tsv` downloads each study
   sequentially with double-download MD5 verification, emails a
   summary report when the batch finishes.

The Google Sheet schema, filtering by `ready_to_run`, and write-back
status updates are explicitly **out of scope** — they belong in a
lab-private wrapper layer that calls atomx-toolkit, not in this public
package.

## 2. Goals & Non-goals

### Goals

- Reliable download of an AtoMx SFTP study directory tree to local disk.
- Detect transfer corruption / interruption via double-download +
  double-md5sum + comparison.
- Survive interruption: per-file atomic writes (`.part` rename), so
  re-running skips already-complete files; study-level lock catches
  process crashes.
- Operate unattended: every run sends an email summary (success: one
  line; failure: full diagnostics).
- Public, MIT-licensed, GitHub-installable, no external auth surface
  beyond AtoMx + SMTP.

### Non-goals

- **No QC subsystem in v0.1.0.** Mentioned in README Roadmap only.
- **No Google Sheet integration.** Wrapper layer responsibility.
- **No TrueNAS / S3 / cloud archive.** Single source-to-destination
  copy. The destination is a plain local directory; what happens to
  it after that is out of scope.
- **No manifest / ledger.** Per-run state lives in the per-study
  index files; no global account of all runs ever performed.
- **No scheduled tasks / cron / systemd integration.** Operator runs
  it manually.
- **No parallel downloads in `transfer batch`.** Sequential only.
  AtoMx connections are limited; parallelism would risk hitting
  server-side limits and complicate integrity reasoning.
- **No PyPI release in v0.1.0.** GitHub-only install. Can be
  reconsidered later.

## 3. Subsystems

```
src/atomx_toolkit/
├── __init__.py
├── py.typed
├── cli.py                  # Typer root, mounts subcommand groups
├── transfer/
│   ├── __init__.py
│   ├── config.py           # TOML loader + sftp.env credential chain
│   ├── sftp.py             # paramiko-based SFTP client + walktree helper
│   ├── md5.py              # md5sum subprocess + dict-based comparison
│   ├── lock.py             # .atomx-toolkit.lock JSON read/write/check
│   ├── pipeline.py         # 6-phase per-study orchestrator
│   ├── batch.py            # jobs.tsv parser + sequential batch runner + plan
│   └── cli.py              # transfer {run, batch, plan} Typer group
├── notify/
│   ├── __init__.py
│   ├── config.py           # [notify] TOML section parser
│   ├── credentials.py      # SMTP env-or-dotenv chain
│   ├── recipients.py       # recipients/*.txt parser + resolution
│   ├── events.py           # TransferReport / BatchReport / event dispatch
│   ├── send.py             # smtplib.SMTP send (Gmail SSL/STARTTLS)
│   └── cli.py              # notify {test, list-subscribers}
└── install/
    ├── __init__.py
    ├── init.py             # write config.toml / sftp.env / smtp.env / recipients/
    └── cli.py              # install {init}
```

Boundaries:

- `transfer` knows nothing about email. Its only side effect besides
  filesystem writes is raising `TransferError` subclasses.
- `notify` accepts `TransferReport` / `BatchReport` dataclasses as
  inputs. It does not import `transfer`.
- `install` is pure file IO. It imports neither `transfer` nor
  `notify`; just writes templates.
- `cli` is the only place where `transfer` exceptions get turned
  into `notify` events and exit codes.

## 4. `transfer` subsystem

### 4.1 Pipeline (per study)

```
Pipeline entry
   ↓
Guard: if <log_root>/<name_local>/index/md5sum_pass exists
   → log "already complete, skipping" → return (no mkdir, no lock,
     no phases). Idempotent re-run.
   ↓
Phase 0  mkdir -p
   - <log_root>/<name_local>/{index,path,md5sum}
   - <backup_root>/<name_local>/{AtoMx,AtoMx_copy}
   ↓
acquire study lock <backup_root>/<name_local>/.atomx-toolkit.lock
   (atomic: os.open with O_CREAT | O_EXCL | O_WRONLY)
   ↓
Phase 1  list remote files (×2)
   - sftp.walk_files(remote_dir) → remote_fs_1
   - sftp.walk_files(remote_dir) → remote_fs_2
   - assert set(remote_fs_1) == set(remote_fs_2)
   - on mismatch: write index/path_fail, raise RemoteListInconsistent
   - if both empty: log WARNING (study has no files; the toolkit_error
     handler will surface this as an email — silent zero-file
     success is a known foot-gun for typo'd remote names)
   - on match:    write index/path_pass + path/path_1.txt + path/path_2.txt
                  (one absolute remote POSIX path per line, UTF-8, LF)
   ↓
Phase 2  download → AtoMx/   (resume-aware, atomic per-file)
   ↓
Phase 3  download → AtoMx_copy/   (resume-aware, atomic per-file)
   ↓
Phase 4  md5sum AtoMx/        → md5sum/md5sum_1.txt
   ↓
Phase 5  md5sum AtoMx_copy/   → md5sum/md5sum_2.txt
   ↓
Phase 6  compare md5 dicts
   - dict outer-join by relative path
   - any mismatch or missing key:
     - write index/md5sum_fail + md5sum/md5sum_diff.csv
     - raise IntegrityError
   - all match:
     - shutil.rmtree(AtoMx_copy/)
     - write index/md5sum_pass with content = ISO 8601 timestamp
   ↓
release study lock (finally)
```

### 4.2 Atomic per-file writes & resume

Per-file rule inside Phase 2 / 3:

| Local state | Action |
|---|---|
| final exists, size matches `sftp.stat(remote).st_size` | skip |
| final exists, size differs | delete final, re-download |
| only `*.part` exists | delete `*.part`, re-download |
| nothing exists | download to `*.part`, then `os.rename(*.part, final)` |

`os.rename` within the same filesystem is atomic on POSIX, so the
final file is never partial. Cross-fs rename is a non-issue here
because the temp `.part` lives in the same directory as the final.

### 4.3 Study-level lock

- File: `<backup_root>/<name_local>/.atomx-toolkit.lock`
- Created: just after Phase 0 (mkdir), before Phase 1.
- **Acquisition:** `os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)`.
  Atomically creates the lock or fails with `FileExistsError` if it
  already exists. No TOCTOU between "check exists" and "create".
  After the fd is opened, write the JSON content and close.
- Removed: in `finally` of the per-study `try/except`, success or
  failure. Removal is best-effort: if the lock file vanished on us
  somehow (operator manually deleted, filesystem unmount), log
  WARNING but don't raise.
- Content (JSON, written via the `os.open` fd):
  ```json
  {
    "hostname": "binks",
    "pid": 12345,
    "started_at": "2026-04-30T12:34:56+00:00",
    "name_remote": "HCC_TMA006_..._116"
  }
  ```
- **Crash detection on entry:** when `os.open` raises `FileExistsError`,
  the pipeline reads the existing lock, raises `LockHeldError(content)`
  for the caller. `transfer run` maps this to exit 2 + a message
  printing the lock contents and instructing the operator to inspect
  the partial state and delete the lock manually. `transfer batch`
  catches `LockHeldError` per item and marks it `skipped_locked`,
  continuing to the next item.
- **No PID liveness check.** Auto-judging "is the PID still alive"
  is unreliable across reboots, containers, and cross-host
  deployments. The conservative default forces a human to verify
  no other process is mid-pipeline.

### 4.4 Resume granularity

- **File-level** (inside Phase 2/3): per the table in 4.2.
- **Study-level** (`pipeline.run` entry):
  - If `<log_root>/<name_local>/index/md5sum_pass` exists → log "already complete, skipping" and return early (exit 0). The
    pipeline is idempotent: re-running a complete study is a no-op.
  - Otherwise enter the pipeline; partial files are picked up by
    file-level resume.
- **Batch-level** (`transfer batch`):
  - Pre-scan `jobs.tsv`, classify each row:
    - `complete_already` if `<log_root>/<name_local>/index/md5sum_pass` exists
    - `skipped_locked` if `<backup_root>/<name_local>/.atomx-toolkit.lock` exists
    - `pending` otherwise
  - Iterate `pending` sequentially. Each study runs in its own
    `try/except`. On exception:
    - `LockHeldError` → mark `skipped_locked` (covers the race where
      another process grabbed the lock between pre-scan and pipeline
      entry), continue.
    - Any other exception → mark `failed`, append failure message,
      continue.
  - **Pre-scan reads two roots** (`<log_root>` and `<backup_root>`)
    so config must be loaded before pre-scan.

### 4.5 SFTP layer

- Library: `paramiko>=3,<5` directly. No `pysftp`.
- Connection: `paramiko.SSHClient` with `load_system_host_keys()` +
  `AutoAddPolicy` for host keys. AtoMx is a vendor-managed endpoint
  with a stable hostname; the combination gives the exact behavior
  we want:
    - Unknown host (first connect, no entry in `~/.ssh/known_hosts`)
      → key auto-added by policy.
    - Known host with matching key → connection proceeds.
    - Known host with **mismatched** key → paramiko raises
      `BadHostKeyException` regardless of policy (the policy is
      only consulted for *missing* keys), so an attacker swapping
      the server cannot get past first connect.
- Auth: password only (AtoMx does not advertise SSH key auth).
- `walk_files(root)` helper: iterative DFS using
  `SFTPClient.listdir_attr` + `stat.S_ISDIR`, yields absolute
  POSIX paths of regular files. Replaces the `pysftp.walktree`
  callback API with a generator.
- `download_file(remote, local)`: open remote in `'rb'`, write
  local `*.part`, `fsync`, close, then `os.rename(*.part, local)`.
- Connection timeout: 60s. SFTP read timeout: 300s.
- Retries: none in v0.1.0. If a download fails, the file's `*.part`
  is left in place; the next run skips files that completed and
  re-tries the rest.

### 4.6 MD5

- Calculation: `subprocess.run(["md5sum", str(file)], ...)`. Linux
  only. `install init` checks `shutil.which("md5sum")` and refuses
  to proceed if missing (clear error pointing to coreutils).
- Storage format: standard `md5sum` text file, `<hash>  <relative-path>\n`.
- Comparison: parse both files into `dict[str, str]`, build a set of
  all relative paths from the union, walk paths, classify each as
  `match | mismatch | missing_in_1 | missing_in_2`. Any non-match
  → `md5sum_diff.csv` with columns `(file, md5_1, md5_2, status)`
  and `IntegrityError` raised.
- No `pandas` dependency.

### 4.7 `jobs.tsv` format

Splitting rule: each non-comment, non-blank line is split on
`re.split(r"\s+", line.strip())` — any run of whitespace counts as
the separator, which lets the operator paste columns from a sheet
without worrying about tabs vs. spaces.

```
# Comment lines start with '#'
# Two TAB-separated columns: name_remote, name_local
# Multiple whitespace is also accepted as a separator (so columns can be space-aligned).

HCC_TMA006_section05_3ug_v132_07_01_2025_22_50_43_116    HCC_TMA006_section05_3ug_v132
HCC_TMA005_section11_3ug_v132_07_01_2025_22_49_15_796    HCC_TMA005_section11_3ug_v132
```

Parser rules:

- UTF-8, BOM tolerated.
- Skip blank lines and lines whose first non-whitespace char is `#`.
- Each non-comment line must split into exactly 2 fields. 0, 1, or
  3+ fields → `JobsTsvError` with line number.
- Duplicate `name_local` across rows → error.
- Empty file (no jobs after filtering) → error.

### 4.8 `transfer plan <jobs.tsv>` output

A dry-run preview, no SFTP / no downloads:

```
Plan for jobs.tsv (10 entries):

  complete_already  (3)
    - HCC_TMA006_section05_3ug_v132   (completed 2026-04-25T14:32:11Z)
    - HCC_TMA005_section11_3ug_v132   (completed 2026-04-26T08:11:02Z)
    - HCC_TMA005_section09_0.1ug_v132 (completed 2026-04-26T12:45:33Z)

  skipped_locked    (1)
    - HCC_TMA006_section03_0.1ug_v132
        lock from binks pid 12345 at 2026-04-29T22:00:00Z

  pending           (6)
    - HCC_TMA009_section11_NS_3ug_v132
    - HCC_TMA009_section09_NS_1ug_v132
    - HCC_TMA009_section12_JL_1ug_v132
    - HCC_TMA009_section14_JL_3ug_v132
    - HCC_TMA007_section05_3ug_v132
    - HCC_TMA010_section09_3ug_v132
```

Exit 0 always (informational). No email sent.

### 4.9 Status files (per study)

```
<log_root>/<name_local>/
├── <name_local>.log
├── index/
│   ├── path_pass            # phase 1 passed (empty file)
│   ├── path_fail            # phase 1 failed (empty file)
│   ├── md5sum_pass          # phase 6 passed; CONTENTS = ISO 8601 timestamp
│   └── md5sum_fail          # phase 6 failed (empty file)
├── path/
│   ├── path_1.txt           # one absolute remote POSIX path per line, UTF-8, LF
│   └── path_2.txt           # same format
└── md5sum/
    ├── md5sum_1.txt         # `md5sum` standard format: <hash><SP><SP><relpath>\n
    ├── md5sum_2.txt
    └── md5sum_diff.csv      # phase 6 failure only; cols (file, md5_1, md5_2, status)
```

```
<backup_root>/<name_local>/
├── .atomx-toolkit.lock      # JSON, present only while pipeline is running
├── AtoMx/                   # primary backup, persists after success
└── AtoMx_copy/              # secondary backup, removed after phase 6 passes
```

The presence of `md5sum_pass` is the authoritative "study is done"
signal. Its content is the completion time, eliminating a separate
`completed_at` file.

## 5. `notify` subsystem

### 5.1 Events

| Event | Trigger | Payload |
|---|---|---|
| `transfer_report` | every `transfer run` exit, success or failure | `TransferReport` |
| `batch_report` | every `transfer batch` exit | `BatchReport` |
| `toolkit_error` | atomx-toolkit's own logger emits WARNING+, dedup + cooldown | string + log excerpt |

`transfer_report` collapses what fusion-toolkit splits into
`backup_failure` / `backup_success` — one event, payload's `status`
field controls success vs failure formatting.

### 5.2 Recipients

```
~/.config/atomx-toolkit/recipients/
├── transfer_report.txt
├── batch_report.txt
├── toolkit_error.txt
└── default.txt
```

- One email per line; `#` line comments; blank lines ignored.
- Hot-reload: every send re-reads the file from disk.
- Resolution per event:
  1. `<event>.txt` if it has any uncommented address → use those.
  2. Else `default.txt` if non-empty → use those.
  3. Else log "recipients empty for `<event>`, skipping email" and
     don't raise. The pipeline does not depend on email delivery.

### 5.3 Credentials

SMTP credential chain (in order):

1. Environment: `ATOMX_SMTP_USER`, `ATOMX_SMTP_APP_PASSWORD`.
2. Dotenv file: `~/.config/atomx-toolkit/smtp.env` (key=value lines,
   `export` prefix tolerated, `#` comments).
3. Neither: log warning, skip email send. Toolkit does not abort.

`smtp.env` template, written by `install init`:

```env
# Gmail app password — generate at https://myaccount.google.com/apppasswords
ATOMX_SMTP_USER=
ATOMX_SMTP_APP_PASSWORD=

# Optional overrides; defaults shown
# ATOMX_SMTP_HOST=smtp.gmail.com
# ATOMX_SMTP_PORT=587
```

### 5.4 Payload dataclasses

```python
# notify/events.py

@dataclass(frozen=True)
class TransferReport:
    name_remote: str
    name_local: str
    status: Literal["success", "failed"]
    started_at: datetime
    completed_at: datetime
    file_count: int | None
    total_bytes: int | None
    failure_phase: str | None      # "list_remote" | "download_1" | ... | None
    failure_message: str | None
    log_path: Path

@dataclass(frozen=True)
class BatchItem:
    name_remote: str
    name_local: str
    status: Literal["complete_already", "skipped_locked", "succeeded", "failed"]
    duration: timedelta | None
    failure_message: str | None

@dataclass(frozen=True)
class BatchReport:
    jobs_tsv: Path
    started_at: datetime
    completed_at: datetime
    items: list[BatchItem]
```

### 5.5 Email body templates

Plain-text only. No HTML. Subject and body formats:

**`transfer_report` success:**

```
Subject: [atomx-toolkit] OK: <name_local>

study     : <name_local>
remote    : <name_remote>
files     : <file_count>
total     : <total_bytes humanized>
elapsed   : <duration humanized>
md5 check : pass (<n>/<n> match)
log       : <log_path>
```

**`transfer_report` failure:**

```
Subject: [atomx-toolkit] FAIL: <name_local> at <failure_phase>

study     : <name_local>
remote    : <name_remote>
phase     : <failure_phase>
elapsed   : <duration humanized>
error     : <failure_message>

[md5 diff  : <md5sum_diff.csv path>]      # only when phase == md5_compare
log       : <log_path>

--- last 30 lines of log ---
<log tail>
```

**`batch_report`:** ASCII table of items (rendered via `rich.table`
to a string), counts summary at the top, log paths at the bottom.

**`toolkit_error`:** subject `[atomx-toolkit] toolkit error`, body =
log message + recent context. Subject deduplicated by first 200
chars of body.

### 5.6 Cooldown / dedup

- `transfer_report` and `batch_report`: no dedup. Operator wants every
  run reported.
- `toolkit_error`: dedup by a key derived from the error content —
  timestamps stripped (regex against ISO 8601 + standard log
  timestamps), then the first 200 chars of the remainder. Same key
  suppressed for `toolkit_error_cooldown_seconds` (default 300).
  State persisted to
  `~/.config/atomx-toolkit/state/toolkit_error_dedup.json`.

### 5.7 `notify test` / `notify list-subscribers`

- `atomx-toolkit notify test --event <name>` sends a fixed-content
  test email through the full credential chain to the resolved
  recipients. `--dry-run` prints what would be sent without
  connecting to SMTP. Useful for validating the `recipients/`
  configuration on the host.
- `atomx-toolkit notify list-subscribers [--event <name>]` prints
  the resolved recipient list per event, indicating whether it
  came from the event-specific file or from `default.txt`.

## 6. `install` subsystem

### 6.1 `install init [--config-dir PATH] [--force]`

Writes templates under `~/.config/atomx-toolkit/` (or
`--config-dir`):

| File | Overwrite policy |
|---|---|
| `config.toml` | refuse if exists, allow with `--force` |
| `sftp.env` | refuse if exists, allow with `--force` |
| `smtp.env` | refuse if exists, allow with `--force` |
| `recipients/transfer_report.txt` | **never** overwrite, `--force` ignored |
| `recipients/batch_report.txt` | **never** overwrite |
| `recipients/toolkit_error.txt` | **never** overwrite |
| `recipients/default.txt` | **never** overwrite |

Recipients are operator-curated state and must never be clobbered.

`install init` also runs two pre-checks and prints their results:

1. `shutil.which("md5sum")` — required for transfer pipeline.
2. `~/.ssh/known_hosts` exists or its parent dir is writable —
   required for first SFTP connect.

Non-fatal if either fails; `init` still writes templates but prints
a warning summary so the operator sees what to fix.

**State directory.** `install init` also creates
`<config_dir>/state/` (used at runtime for
`toolkit_error_dedup.json`) but does not pre-populate any state
files — runtime code creates them lazily.

**Recipient templates.** Each `recipients/*.txt` file is created
with a 4-line header explaining the format, e.g.:

```text
# Subscribers for transfer_report. One email per line.
# Blank lines and lines starting with '#' are ignored.
# Edit at runtime; changes take effect on the next email send.

```

This makes the format self-documenting and avoids "is this file
really supposed to be empty?" confusion.

## 7. Configuration

### 7.1 `config.toml`

```toml
[sftp]
hostname = "na.export.atomx.nanostring.com"
remote_root = "/"
# username and password come from env or sftp.env, never from this file.

[paths]
log_root = "/data/log/atomx"
backup_root = "/data/backup/atomx"

[notify]
enabled = true
toolkit_error_cooldown_seconds = 300
# recipients_dir = "/some/other/path"   # optional override; defaults to <config_dir>/recipients
```

`sftp.env` template:

```env
ATOMX_SFTP_USER=
ATOMX_SFTP_PASSWORD=
```

### 7.2 Loader behavior

- Search order for `config.toml`: `--config <path>` flag, then
  `~/.config/atomx-toolkit/config.toml`. No CWD-relative search (avoid
  surprising "you ran me from a different dir and got different
  config").
- Required keys: `[sftp].hostname`, `[paths].log_root`,
  `[paths].backup_root`. Missing → exit 2 with the missing key.
- TOML parse error → exit 2 with line/column from `tomllib`.
- Unknown sections / keys: ignored. (Forward-compat for new options
  in later versions; the price is fewer typo errors.)

## 8. CLI

```text
atomx-toolkit --version
atomx-toolkit [-v | --verbose]            # global flag, repeatable

atomx-toolkit transfer run    <name_remote> <name_local> [--config PATH]
atomx-toolkit transfer batch  <jobs.tsv>                 [--config PATH]
atomx-toolkit transfer plan   <jobs.tsv>                 [--config PATH]

atomx-toolkit notify test --event EVENT [--config PATH] [--smtp-env PATH] [--dry-run]
atomx-toolkit notify list-subscribers [--event EVENT] [--config PATH]

atomx-toolkit install init [--config-dir PATH] [--force]
```

- Implementation: `typer.Typer` with subcommand groups; Rich for log
  formatting in stderr.
- All commands accept `--config` / `--smtp-env` to override default
  paths (mostly useful for tests and ad-hoc invocations).
- Global `-v` / `--verbose` raises console log level from WARNING to
  INFO; `-vv` to DEBUG. The file log is always INFO.

## 9. Exit codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Operational failure: at least one study failed (md5 mismatch, list inconsistency, SFTP error) |
| 2 | Configuration error: missing/malformed TOML, missing required key, lock held, missing `md5sum` binary |
| 3 | Unexpected runtime error (uncaught exception, network down, permissions) |

`transfer batch` exit code rules:

- 1 if any item ended in `failed`.
- 1 if every item ended in `skipped_locked` (no progress was made
  this run).
- 0 otherwise — i.e., any combination of `succeeded`,
  `complete_already`, and possibly some `skipped_locked` mixed in,
  with no outright failures.

The locked items that didn't fail still appear in the
`batch_report` email, so the operator sees them and clears their
locks manually.

## 10. Error handling & notifications

- Each subcommand wraps its body in a top-level `try/except` in
  `cli.py`.
- `transfer run` catches all exceptions, builds a `TransferReport`
  with `status="failed"`, dispatches `transfer_report`, exits with
  the appropriate code.
- `transfer batch` does the same per-item; the batch wrapper itself
  also dispatches `batch_report` after all items finish.
- A `logging.Handler` subclass attached to the root logger watches
  for WARNING+ records and dispatches `toolkit_error` (with cooldown
  / dedup). This catches issues outside the per-study `try/except`
  scope (e.g., config load errors, SMTP auth failures).
- **KeyboardInterrupt semantics:**
  - In `transfer run`: lock released in `finally`, partial files
    left for resume, `transfer_report` dispatched with
    `failure_phase="interrupted"`, exit 1.
  - In `transfer batch`: **abort the entire batch** (do not
    continue to remaining items — operator hit Ctrl-C means "stop
    everything"). The currently-running item is marked `failed`
    with `failure_message="interrupted"`; remaining `pending`
    items are appended as `failed` with `failure_message="not run, batch aborted"`.
    Partial `batch_report` is dispatched. Exit 1.

## 11. Logging

- Per-study log: `<log_root>/<name_local>/<name_local>.log` (mode
  `"a"` — append, so re-runs accumulate history).
- Batch log: `<log_root>/_batch/batch_<UTC-ISO-compact>.log` (one
  file per batch invocation, e.g.
  `batch_20260430T123456Z.log`).
- Format: `%(asctime)s %(levelname)s %(name)s | %(message)s`.
- Console handler: WARNING by default, INFO with `-v`, DEBUG with `-vv`.
- File handler: always INFO.
- **Third-party noise:** `paramiko` logs at INFO are very chatty
  (channel open/close, packet metadata). At setup time, the
  toolkit explicitly sets `logging.getLogger("paramiko").setLevel(logging.WARNING)`.

## 12. Testing strategy

### 12.1 Unit tests (no network, no real SFTP)

- `transfer/md5.py`: dict comparison, edge cases (missing keys,
  binary-identical empty file, non-ascii filename), `md5sum_diff.csv`
  shape.
- `transfer/lock.py`: write/read/check, content schema, atomic write
  via temp+rename.
- `transfer/sftp.py`: `walk_files` against a mocked `SFTPClient`.
- `transfer/batch.py`: `jobs.tsv` parser corner cases (BOM, varied
  whitespace, comments, duplicates, empty file, 1-field, 3-field).
- `notify/recipients.py`: per-event resolution, default fallback,
  empty file handling.
- `notify/credentials.py`: env > dotenv > none precedence.
- `notify/events.py`: payload formatting (golden tests).
- `install/init.py`: file write/refuse/force behavior, recipient
  protection.

### 12.2 Integration tests

- **Real local SFTP server** via `paramiko.ServerInterface` fixture
  serving a temp directory. Tests run the full pipeline against it:
  - happy path
  - guard: re-running an already-`md5sum_pass`'d study is a no-op
    (no mkdir, no lock, no SFTP connect)
  - mid-Phase-2 interruption (raise inside the download loop) →
    re-run completes
  - Phase-1 list inconsistency (server returns different listings on
    consecutive `listdir_attr`)
  - Phase-1 zero files (empty remote dir) → WARNING logged + study
    still "succeeds" with empty md5sum_pass
  - Phase-6 md5 mismatch (corrupt one file in `AtoMx_copy/` between
    Phase 3 and Phase 4)
  - lock race: pre-existing `.atomx-toolkit.lock` → `LockHeldError`,
    `transfer run` exits 2; same scenario inside batch → item
    classified `skipped_locked`, batch continues
- **Mock SMTP** via `aiosmtpd` fixture for `notify test` end-to-end.

### 12.3 Coverage target

≥85% line coverage on `transfer/` and `notify/`. CLI layer
exercised via subprocess tests for argv → exit code mapping (a
handful of cases, not exhaustive).

## 13. Project layout (full)

```
atomx-toolkit/
├── pyproject.toml
├── README.md
├── LICENSE                  # MIT
├── .gitignore
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       └── ci.yml           # ruff + pyright + pytest on push/PR
├── docs/
│   ├── setup-host.md        # how to install + run on binks-style Linux
│   ├── transfer-pipeline.md # the 6-phase diagram + state file map
│   └── superpowers/specs/2026-04-30-atomx-toolkit-design.md   # this file
├── src/atomx_toolkit/
│   └── ...                  # see Section 3
└── tests/
    ├── test_transfer/
    │   ├── conftest.py      # local SFTP server fixture
    │   ├── test_md5.py
    │   ├── test_lock.py
    │   ├── test_sftp.py
    │   ├── test_pipeline.py
    │   └── test_batch.py
    ├── test_notify/
    │   ├── conftest.py      # aiosmtpd fixture
    │   ├── test_recipients.py
    │   ├── test_credentials.py
    │   ├── test_events.py
    │   └── test_send.py
    ├── test_install/
    │   └── test_init.py
    └── test_cli.py
```

## 14. Toolchain & dependencies

### 14.1 `pyproject.toml`

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

### 14.2 Python version

3.12+. The lab's binks server is 3.12-capable; the AtoMx workflow
runs only on the operator's controlled hosts (no Windows / older
Linux constraints, unlike fusion-toolkit which had to run on a
Windows Fusion instrument host).

### 14.3 Why `paramiko` not `pysftp`

`pysftp` last released in 2018, no upstream activity, requires
pinning `paramiko<4`. paramiko 3.x's native `SFTPClient` covers
everything we need; the `walktree` callback API replaced by a
~25-line generator.

### 14.4 Why no `pandas`

Original `cosmx_utils.atomx.transfer` used `pandas` for one outer
join in MD5 comparison. Replaced with a stdlib dict-based
diff (~30 lines). Drops ~50 MB from the install footprint.

## 15. Roadmap (post v0.1.0)

- **QC subsystem**: post-transfer report generation. Inputs are the
  final `<backup_root>/<name_local>/AtoMx/` directory; outputs are
  TBD (likely an HTML/PDF QC summary covering FOV counts, image
  channel completeness, basic QC metrics). Shape and dependencies
  to be designed when the actual QC requirements are clarified.
- **PyPI release**: reconsider once the API is exercised by more
  than one user.
- **Parallel batch downloads**: only if the AtoMx server tolerates
  multiple connections without throttling, and only after the
  serial code path is proven stable.

## 16. Out of scope for this spec

- Detailed implementation pseudocode of each function. The implementation
  plan (next document via `superpowers:writing-plans`) covers that.
- Concrete test cases line by line. Covered at plan time and during
  TDD.
- README content. Drafted at implementation time once the package
  shape is concrete.
- CI workflow YAML. Drafted at implementation time.

## 17. Open questions for the user (none blocking)

The interactive brainstorm resolved all blocking choices. Items
the operator may want to revisit during implementation review:

- **License = MIT** is my default for a public lab tool. If you want
  Apache 2.0 or no license at all, change before tagging v0.1.0.
- **`SMTP_HOST` / `SMTP_PORT` defaults** are Gmail. If the lab
  switches to a different provider, override via env. The defaults
  can be hard-coded for simplicity but I left them overridable at
  near-zero cost.
- **`AutoAddPolicy` for SSH host keys** is permissive on first
  connect. If you want stricter — e.g., pinning AtoMx's public key
  in `config.toml` — that's a small follow-up.
