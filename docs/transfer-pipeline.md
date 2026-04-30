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
