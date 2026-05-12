# Changelog

All notable changes to this project will be documented in this file.
The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.1] - 2026-05-12

### Added

- Phase-level INFO logging in `run_pipeline` so operators can `tail -f`
  the batch log and watch progress through the 6 transfer phases.
- Per-N-files progress logging in `_download_all` (`PROGRESS_INTERVAL=10`,
  module-level constant): emits a `[<completed>/<total>] progress in <dir>`
  INFO line every 10 files and at the final file.
- Batch boundary INFO logs (`batch started`, `starting study K/N`,
  `batch finished`) in `run_batch`.
- Per-study `transfer_report` email dispatched in `transfer batch`
  for every `succeeded` or `failed` item, mirroring the single-study
  CLI behavior. Operators running a multi-study batch now receive
  N+1 emails (one per study + one final batch summary) instead of
  only the final summary.

### Changed

- `BatchItemResult` (in `atomx_toolkit.transfer.batch`) gains 5 new
  optional fields: `started_at`, `completed_at`, `file_count`,
  `total_bytes`, `failure_phase`. All default to `None` and are
  populated by `run_batch` on the relevant code paths
  (success / KeyboardInterrupt / generic Exception). `LockHeldError`
  and the post-abort tail leave them `None` because those items
  never actually ran a pipeline.

### Fixed

- v0.3.0 produced an empty batch log file even after hours of real
  download work, because `run_pipeline` and `run_batch` emitted no
  INFO-level log records on the happy path. The new phase and
  progress INFO logs fix that.
- v0.3.0 sent only one email at the very end of a batch run,
  delaying operator feedback by hours. The new per-study
  `transfer_report` dispatch in `batch_cmd` restores per-study
  email visibility.

### Notes

- No CLI surface change.
- No new runtime dependency.
- Existing v0.3.0 installs work unchanged; this is a drop-in upgrade.

## [0.3.0] - 2026-05-12

### Added

- Runtime dependency on
  [`jianglab-name-standard`](https://github.com/wuwenrui555/jianglab-name-standard)
  `@v0.1.1` for the lab-wide CosMx naming standard.
- `parse_jobs_tsv` and the `transfer run` CLI now validate the
  `name_local` column against `jianglab_name_standard.CosmxRunName`:
  5 underscore-separated fields, real calendar date, and an
  `atomx_version` of the form `v<major>-<minor>-<patch>`. Invalid
  names are rejected before any disk write or SFTP connection, with
  a message that includes the failing rule ID and the jianglab hint.

### Changed

- `name_local` values that previously parsed without complaint but
  did not match `CosmxRunName` are now rejected. `name_remote` is
  unchanged (still free-form, since AtoMx-side names are out of our
  control).

### Migration notes

- Existing operators with a `jobs.tsv` written against v0.2.0 should
  preview their file with `atomx-toolkit transfer plan <path>`:
  validation errors surface in the plan dry-run with no transfer
  attempted. Rewrite any rejected `name_local` to the 5-field form,
  for example `20260211_WW_ACLF_run1_v2-2-1`. The AtoMx-generated
  folder name is already in this shape, so the simplest fix is
  "use the AtoMx folder name verbatim as `name_local`."

## [0.2.0] - 2026-05-12

### Added

- `notify/dedup.py` module: `DedupState` and `should_send_toolkit_error`
  extracted from the deleted `notify/send.py`.
- New `tests/test_notify/test_dispatch.py` covering dispatch wiring
  (enabled/disabled, missing creds, no recipients, send-email call).
- Runtime dependency on
  [`pingme`](https://github.com/wuwenrui555/pingme) `@v0.1.2` for the
  underlying SMTP transport.

### Changed

- **SMTP send and recipient resolution now delegate to `pingme`.**
  `notify/recipients.py` and `notify/send.py` are removed; callers
  import `resolve_recipients` and `send_email` from `pingme`.
- `notify/credentials.py` is now a thin adapter: it reads the same
  `ATOMX_SMTP_*` env vars and `~/.config/atomx-toolkit/smtp.env` as
  before, but returns `pingme.SmtpCredentials`. Operator-facing env
  names are unchanged.
- Default SMTP port flipped `587` → `465` in the install template
  (`atomx-toolkit install init`) to match the adapter's hardcoded
  `transport="ssl"`. STARTTLS is no longer supported by this version.
- `ALL_EVENTS` moved from the deleted `notify/recipients.py` into
  `notify/events.py`.

### Removed

- `notify/recipients.py` (replaced by `pingme.resolve_recipients`).
- `notify/send.py` (SMTP path replaced by `pingme.send_email`; dedup
  pieces moved to `notify/dedup.py`).
- `tests/test_notify/{test_recipients.py,test_send.py,conftest.py}`
  (the equivalent unit tests live in pingme).

### Migration notes

- The `SmtpCredentials` dataclass shape changed: the field used to
  be `password`; it is now `app_password` (it comes from pingme).
  This only affects downstream code that constructs the dataclass
  directly. Reading `ATOMX_SMTP_APP_PASSWORD` from env or dotenv is
  unchanged.
- If your operator config pinned `ATOMX_SMTP_PORT=587`, remove that
  override or change it to `465`. Gmail's port 587 expects STARTTLS,
  which this version no longer issues; sends on 587 will fail at
  connect time.
