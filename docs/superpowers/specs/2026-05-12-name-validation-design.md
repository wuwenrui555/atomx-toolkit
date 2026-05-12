# Name Validation via `jianglab-name-standard` — Design Spec

**Date:** 2026-05-12
**Status:** Draft, awaiting user review
**Target version:** atomx-toolkit v0.3.0
**Dependency added:** `jianglab-name-standard @ v0.1.1`

## 1. Overview

atomx-toolkit transfers CosMx AtoMx SIP study folders from a remote
SFTP host into a local backup directory. The local destination
folder name (`name_local`) is currently a free-form string. This
change makes `name_local` conform to the lab-wide CosMx naming
standard at every entry point, rejecting non-conforming inputs
before any transfer work begins.

The rule comes from [`jianglab-name-standard`](https://github.com/wuwenrui555/jianglab-name-standard)'s
`CosmxRunName`:

```
YYYYMMDD_<user>_<project>_<custom>_<atomx_version>
e.g.  20260211_WW_ACLF_run1_v2-2-1
```

5 underscore-separated fields, field charset `[A-Za-z0-9-]`, real
calendar date, `atomx_version` literally `v<major>-<minor>-<patch>`.

`name_remote` is **not** validated. AtoMx-side names may carry legacy
or operator-typed values; only what we write to local disk and hand
to downstream pipelines is the lab's responsibility to keep clean.

## 2. Goals & Non-goals

### Goals

- Reject non-conforming `name_local` at every input boundary before
  any disk write, SFTP connection, or batch iteration.
- Surface the failing rule (`R1`), the offending name, and the
  jianglab-supplied hint to the operator, with enough context to find
  the offending row.
- Use the existing atomx-toolkit error-type vocabulary (`JobsTsvError`
  for TSV input, `typer.BadParameter` for CLI args) so the operator
  experience is uniform with current parse-time failures.

### Non-goals

- No validation of `name_remote`. AtoMx server names are out of our
  control.
- No `--allow-non-standard` escape hatch. Operators with legacy names
  edit the TSV or rename the AtoMx target. YAGNI: add the flag only
  when a concrete operator request appears.
- No structural validation (folder layout, file pairing, scan-data
  presence). atomx-toolkit's transfer pipeline already owns
  per-study artifact checks (`md5sum_pass`, lock files).
- No CLI for "validate this jobs.tsv without running" beyond what
  `transfer plan` already offers: `plan` already parses the TSV, so
  it surfaces validation errors for free.
- No backport. v0.2.x stays as-is; operators must bump to v0.3.0 to
  get the check.

## 3. Behavior changes

### 3.1 `transfer/batch.py::parse_jobs_tsv`

Today's parse_jobs_tsv raises `JobsTsvError` on:
- file not found
- wrong field count
- duplicate `name_local`

This change adds one more cause: invalid `name_local` per
`CosmxRunName`. Insertion point is **immediately after the duplicate
check**, so the operator sees errors in source-line order.

Resulting error message (single physical line, wrapped here for display):

```
JobsTsvError: /path/to/jobs.tsv line 3: invalid name_local 'bad_name':
  [R1] run_name 'bad_name' does not match YYYYMMDD_<user>_<project>_<custom>_<atomx_version>
  (5 fields; atomx_version = vMAJOR-MINOR-PATCH, digits only).
  | hint: Use 5 '_'-separated fields: 8-digit date, user, project, custom,
  atomx_version. Example: 20260211_WW_ACLF_run1_v2-2-1.
```

The literal `|` separates the rule message from the hint, mirroring
how other `JobsTsvError` lines pack multiple facts onto one line.

The original `NameValidationError` is set as `__cause__` (`raise
JobsTsvError(...) from e`) so tracebacks preserve the upstream
context for debugging.

### 3.2 `transfer/cli.py::run_cmd` (Typer `transfer run` command)

Today's `transfer run <name_remote> <name_local>` takes two positional
`str` arguments and dispatches to `run_pipeline`. This change inserts
a `CosmxRunName(name_local)` check at function entry, **before**
`load_config` (no config needs to be loaded to know the name is bad,
and we don't want config errors to mask name errors).

`batch_cmd` (Typer `transfer batch`) and `plan_cmd` (Typer
`transfer plan`) both go through `parse_jobs_tsv`, so they inherit
the validation from §3.1 with no extra hook.

Resulting Typer behavior: exit code 2, stderr renders Typer's
parameter-error template:

```
Usage: atomx-toolkit transfer run [OPTIONS] NAME_REMOTE NAME_LOCAL
Try 'atomx-toolkit transfer run --help' for help.

Error: Invalid value for 'NAME_LOCAL': [R1] run_name 'bad_name' does not match ...
hint: Use 5 '_'-separated fields ...
```

### 3.3 `transfer plan`

`transfer plan` already calls `parse_jobs_tsv` for its dry-run output.
No additional code path. Operators who want to vet a TSV without
running anything use `transfer plan <jobs.tsv>` and the new validation
errors surface there too.

### 3.4 Other entry points

- `dispatch_*_report` and other notify-side code only consume
  `name_remote` / `name_local` that were already validated upstream.
  No new check needed.
- `install init` writes template files only, no name input.

## 4. Implementation surface

### Files modified

| File | Change |
|---|---|
| `pyproject.toml` | Add `jianglab-name-standard @ git+https://github.com/wuwenrui555/jianglab-name-standard.git@v0.1.1` to `dependencies` |
| `uv.lock` | Refreshed by `uv lock` |
| `src/atomx_toolkit/transfer/batch.py` | Import `CosmxRunName`, `NameValidationError`; add validation block in `parse_jobs_tsv` after the duplicate-local check |
| `src/atomx_toolkit/transfer/cli.py` | Import `CosmxRunName`, `NameValidationError`; add validation block at the top of `run_cmd` (the `@app.command("run")` function). Also apply to `batch_cmd` only indirectly via `parse_jobs_tsv`; no separate hook needed there. |
| `tests/test_transfer/test_batch.py` | Add tests covering valid name passes, invalid name raises `JobsTsvError` with line number + `R1` + hint |
| `tests/test_cli.py` | Add test covering `transfer run remote bad_local` exits 2 with stderr containing `R1` |
| `pyproject.toml` (version) | `0.2.0` → `0.3.0` |
| `src/atomx_toolkit/__init__.py` | `__version__` bump |
| `CHANGELOG.md` | New `[0.3.0]` section with Added / Changed / Migration notes |
| `docs/setup-host.md` | Update install-pin examples `@v0.2.0` → `@v0.3.0` |

### Code shape (illustrative, not the final wording)

```python
# transfer/batch.py — inside parse_jobs_tsv, after the duplicate check
from jianglab_name_standard import CosmxRunName, NameValidationError

try:
    CosmxRunName(local)
except NameValidationError as e:
    raise JobsTsvError(
        f"{path} line {lineno}: invalid name_local {local!r}: "
        f"[{e.rule_id}] {e.message} | hint: {e.hint}"
    ) from e
```

```python
# transfer/cli.py — at the top of the transfer run command body
import typer
from jianglab_name_standard import CosmxRunName, NameValidationError

try:
    CosmxRunName(name_local)
except NameValidationError as e:
    raise typer.BadParameter(
        f"[{e.rule_id}] {e.message}\nhint: {e.hint}",
        param_hint="'NAME_LOCAL'",
    ) from e
```

No new module, no helper. Two five-line blocks at two existing entry
points.

## 5. Test plan

### TSV path (`tests/test_transfer/test_batch.py`)

1. Valid 5-field CosmxRunName-formatted `name_local` parses without
   error.
2. Invalid `name_local` (e.g. `bad_name`) raises `JobsTsvError` whose
   message contains:
   - the source path
   - the line number
   - the offending `name_local`
   - the substring `[R1]`
   - the substring `hint:`
3. Duplicate-then-invalid ordering: a TSV whose earlier line has a
   duplicate `name_local` and whose later line has an invalid
   `name_local` raises the **duplicate** error (because the
   duplicate check runs first in the current parse_jobs_tsv loop).
   The new validation must be inserted after the duplicate check
   so this ordering invariant holds.

### CLI path (`tests/test_cli.py` or new `tests/test_transfer/test_cli.py`)

1. `transfer run good_remote 20260211_WW_ACLF_run1_v2-2-1` does not
   exit 2 due to name validation. (May still fail on other paths;
   the test only asserts the name check passed. Use the existing
   subprocess pattern in `test_cli.py`.)
2. `transfer run good_remote bad_local` exits 2; stderr contains
   `[R1]` and `hint:`.

## 6. Versioning

v0.2.0 → **v0.3.0**.

Rationale:

- New runtime dependency (`jianglab-name-standard`).
- Inputs previously accepted (`name_local` not matching the 5-field
  CosMx standard) are now rejected. Pre-1.0 minor break per
  [Semantic Versioning](https://semver.org).

CHANGELOG entry sections:

- **Added**: dependency on jianglab-name-standard@v0.1.1; CosmxRunName
  validation in parse_jobs_tsv and `transfer run` CLI.
- **Changed**: invalid `name_local` is now rejected at parse / CLI
  parse time.
- **Migration notes**: example invalid → valid name rewrite; pointer
  to `CosmxRunName` shape; mention that `transfer plan` is the cheap
  dry-run way to vet a TSV before bumping versions.

## 7. Git-flow

The atomx-toolkit repo is branch-protected on `main` with the
PR-based release flow (see `managing-git-branches` skill).

1. **Spec commit** (this document) goes directly to `dev` so it's
   reviewable on its own, before any implementation.
2. **Feature branch** `feature/validate-name-local` cut from `dev`:
   - add dependency + `uv lock`
   - insert validation at the two sites
   - add tests
   - run pre-push checks (`ruff check`, `ruff format --check`,
     `pyright`, `pytest`)
   - merge `--no-ff` into `dev`, push `dev`
3. **Release** `release/v0.3.0` cut from `dev`:
   - bump `pyproject.toml` version
   - bump `__version__`
   - update CHANGELOG
   - update docs install-pin
   - pre-push checks
   - push, open PR base=main, wait for CI green
   - `gh pr merge --merge`
   - `git tag v0.3.0`, push tags
   - back-merge release into `dev`

## 8. Migration notes for operators

A jobs.tsv that worked on v0.2.0 may now fail at parse time. To check
without running a transfer:

```bash
atomx-toolkit transfer plan path/to/jobs.tsv
```

If any line is rejected, rewrite the `name_local` column to the
5-field form. The AtoMx-generated study folder already follows this
shape, so the typical fix is "use the AtoMx folder name verbatim as
`name_local`."

## 9. Out of scope

- Add a `name-check` Typer command. `transfer plan` covers this for
  TSV input, and a single-name check is trivial enough for the
  operator to do with `python -c "from jianglab_name_standard import
  CosmxRunName; CosmxRunName('...')"`.
- Validate `name_remote`. See §2 Non-goals.
- Configurable rule set. atomx-toolkit is CosMx-only; only
  `CosmxRunName` applies.
