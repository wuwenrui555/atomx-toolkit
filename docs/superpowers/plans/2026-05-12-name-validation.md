# Name Validation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or executing-plans-test-first to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make atomx-toolkit reject any `name_local` input that does not conform to `jianglab_name_standard.CosmxRunName`, at both the TSV-parse entry point and the single-study CLI command.

**Architecture:** Two inline `try / except NameValidationError` blocks at the two existing user-input boundaries — `transfer.batch.parse_jobs_tsv` and `transfer.cli.run_cmd`. Each translates jianglab's `NameValidationError` into the atomx-native error type that already exists at that boundary (`JobsTsvError` for TSV, `typer.BadParameter` for CLI). No helper module, no shared validator. Released as v0.3.0 via PR-based git-flow.

**Tech Stack:** Python 3.12+, uv, ruff, pyright (strict), pytest, Typer, gh CLI, the existing atomx-toolkit toolchain. New runtime dep: `jianglab-name-standard @ git+https://github.com/wuwenrui555/jianglab-name-standard.git@v0.1.1`.

**Spec:** `docs/superpowers/specs/2026-05-12-name-validation-design.md`

---

## Task 1: Create feature branch and add `jianglab-name-standard` dependency

**Files:**
- Modify: `pyproject.toml`
- Modify: `uv.lock` (refreshed automatically)

- [ ] **Step 1: Confirm `dev` is up-to-date and cut feature branch**

```bash
cd ~/projects/atomx-toolkit
git fetch origin
git checkout dev
git pull --ff-only origin dev
git checkout -b feature/validate-name-local dev
```

Expected: `Switched to a new branch 'feature/validate-name-local'`.

- [ ] **Step 2: Add the new dependency to `pyproject.toml`**

Edit `pyproject.toml`. Locate the `dependencies = [...]` block under `[project]` (currently 4 entries ending with `"pingme @ ..."`). Append one entry so the block becomes:

```toml
dependencies = [
    "paramiko>=3,<5",
    "typer>=0.12",
    "rich>=15.0.0",
    "pingme @ git+https://github.com/wuwenrui555/pingme.git@v0.1.2",
    "jianglab-name-standard @ git+https://github.com/wuwenrui555/jianglab-name-standard.git@v0.1.1",
]
```

- [ ] **Step 3: Refresh `uv.lock` and re-sync the environment**

```bash
uv lock
uv sync --all-extras --dev
```

Expected: `uv lock` reports `Added jianglab-name-standard v0.1.1 (...)`. `uv sync` installs it.

- [ ] **Step 4: Confirm the package is importable**

```bash
uv run python -c "from jianglab_name_standard import CosmxRunName, NameValidationError; print(CosmxRunName('20260211_WW_ACLF_run1_v2-2-1'))"
```

Expected: prints a `CosmxRunName(...)` repr line, no traceback.

- [ ] **Step 5: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: add jianglab-name-standard@v0.1.1 dependency"
```

---

## Task 2: Refactor existing parse_jobs_tsv tests to use valid CosmxRunName values (behavior-preserving)

**Files:**
- Modify: `tests/test_transfer/test_batch.py`

**Why this task exists:** The current tests use placeholder names like `localA`, `local`, `l1` for `name_local`. Once Task 3 adds CosmxRunName validation, every one of those tests will fail at parse time on a validation error rather than for the reason the test was originally written. Updating them now (in isolation) keeps the suite green and makes Task 3's diff small and focused.

- [ ] **Step 1: Add a test-local helper that returns valid CosmxRunName-shaped names**

Edit `tests/test_transfer/test_batch.py`. Just below the existing `_write` helper (around line 26), add:

```python
def _local(suffix: str) -> str:
    """Return a CosmxRunName-conformant name_local for tests. Stable date/user."""
    return f"20260101_T_D_s{suffix}_v1-0-0"
```

- [ ] **Step 2: Update every `parse_jobs_tsv` test to use `_local(...)`**

Apply the following exact replacements within `tests/test_transfer/test_batch.py`:

In `test_parse_simple`:

```python
def test_parse_simple(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", f"remoteA\t{_local('A')}\nremoteB\t{_local('B')}\n")
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", _local("A")), ("remoteB", _local("B"))]
```

In `test_parse_skips_comments_and_blanks`:

```python
def test_parse_skips_comments_and_blanks(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        f"# header\n\nremoteA\t{_local('A')}\n  # indented comment\nremoteB\t{_local('B')}\n",
    )
    jobs = parse_jobs_tsv(p)
    assert jobs == [("remoteA", _local("A")), ("remoteB", _local("B"))]
```

In `test_parse_tolerates_bom`:

```python
def test_parse_tolerates_bom(tmp_path: Path) -> None:
    p = tmp_path / "j.tsv"
    name = _local("A")
    p.write_bytes(b"\xef\xbb\xbfremoteA\t" + name.encode("utf-8") + b"\n")
    assert parse_jobs_tsv(p) == [("remoteA", name)]
```

(Keeps the explicit BOM byte literal from the original test; only the `name_local` value changes.)

In `test_parse_accepts_arbitrary_whitespace`:

```python
def test_parse_accepts_arbitrary_whitespace(tmp_path: Path) -> None:
    p = _write(
        tmp_path / "j.tsv",
        f"remoteA    {_local('A')}\nremoteB\t\t{_local('B')}\n",
    )
    assert parse_jobs_tsv(p) == [("remoteA", _local("A")), ("remoteB", _local("B"))]
```

In `test_parse_duplicate_local_raises`:

```python
def test_parse_duplicate_local_raises(tmp_path: Path) -> None:
    p = _write(tmp_path / "j.tsv", f"r1\t{_local('Dup')}\nr2\t{_local('Dup')}\n")
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)
```

The other three parse tests (`test_parse_empty_after_filter_raises`, `test_parse_one_field_raises`, `test_parse_three_fields_raises`) do not contain `name_local` values that reach the duplicate or validation checks (they fail earlier on field count or emptiness), so they are unchanged.

- [ ] **Step 3: Run the test suite to confirm no regression**

```bash
uv run pytest tests/test_transfer/test_batch.py -v
```

Expected: every test in the file passes (no behavior change yet — validation is still not present).

- [ ] **Step 4: Commit**

```bash
git add tests/test_transfer/test_batch.py
git commit -m "test(batch): use CosmxRunName-conformant name_local in parse tests"
```

---

## Task 3: Add CosmxRunName validation in `parse_jobs_tsv` (TDD)

**Files:**
- Modify: `src/atomx_toolkit/transfer/batch.py:62-85` (the `parse_jobs_tsv` function)
- Modify: `tests/test_transfer/test_batch.py` (add new tests)

- [ ] **Step 1: Write a failing test for the rejection path**

Append to `tests/test_transfer/test_batch.py`, after `test_parse_duplicate_local_raises`:

```python
def test_parse_rejects_invalid_name_local(tmp_path: Path) -> None:
    """name_local that does not match CosmxRunName raises JobsTsvError with
    line number, the bad name, the rule_id, and the jianglab hint."""
    p = _write(tmp_path / "j.tsv", "remoteA\tbad_name\n")
    with pytest.raises(JobsTsvError) as excinfo:
        parse_jobs_tsv(p)
    msg = str(excinfo.value)
    assert "line 1" in msg
    assert "bad_name" in msg
    assert "[R1]" in msg
    assert "hint:" in msg


def test_parse_duplicate_check_runs_before_validation(tmp_path: Path) -> None:
    """When a TSV has both a duplicate name_local AND an invalid one further
    down, the duplicate error wins (because the duplicate check runs first)."""
    p = _write(
        tmp_path / "j.tsv",
        f"r1\t{_local('A')}\nr2\t{_local('A')}\nr3\tbad_name\n",
    )
    with pytest.raises(JobsTsvError, match="duplicate"):
        parse_jobs_tsv(p)


def test_parse_valid_cosmx_name_local_passes(tmp_path: Path) -> None:
    """A canonical 5-field CosmxRunName parses fine."""
    name = "20260211_WW_ACLF_run1_v2-2-1"
    p = _write(tmp_path / "j.tsv", f"remoteA\t{name}\n")
    assert parse_jobs_tsv(p) == [("remoteA", name)]
```

- [ ] **Step 2: Run the new tests to confirm they fail**

```bash
uv run pytest tests/test_transfer/test_batch.py::test_parse_rejects_invalid_name_local tests/test_transfer/test_batch.py::test_parse_duplicate_check_runs_before_validation tests/test_transfer/test_batch.py::test_parse_valid_cosmx_name_local_passes -v
```

Expected: `test_parse_rejects_invalid_name_local` FAILS (no exception is raised because validation is not implemented yet; the test fails inside `pytest.raises`). The other two should PASS by accident (the duplicate test already passes; the valid-name test passes because there is no validator yet).

- [ ] **Step 3: Implement the validation in `parse_jobs_tsv`**

Edit `src/atomx_toolkit/transfer/batch.py`. At the top of the file, add the import (alongside the existing imports, after the `from atomx_toolkit...` lines):

```python
from jianglab_name_standard import CosmxRunName, NameValidationError
```

Then inside the `parse_jobs_tsv` function, locate the existing block:

```python
        remote, local = fields[0], fields[1]
        if local in seen_locals:
            raise JobsTsvError(f"{path} line {lineno}: duplicate name_local {local!r}")
        seen_locals.add(local)
        jobs.append((remote, local))
```

Replace with:

```python
        remote, local = fields[0], fields[1]
        if local in seen_locals:
            raise JobsTsvError(f"{path} line {lineno}: duplicate name_local {local!r}")
        try:
            CosmxRunName(local)
        except NameValidationError as exc:
            raise JobsTsvError(
                f"{path} line {lineno}: invalid name_local {local!r}: "
                f"[{exc.rule_id}] {exc.message} | hint: {exc.hint}"
            ) from exc
        seen_locals.add(local)
        jobs.append((remote, local))
```

- [ ] **Step 4: Run the new tests to confirm they all pass**

```bash
uv run pytest tests/test_transfer/test_batch.py::test_parse_rejects_invalid_name_local tests/test_transfer/test_batch.py::test_parse_duplicate_check_runs_before_validation tests/test_transfer/test_batch.py::test_parse_valid_cosmx_name_local_passes -v
```

Expected: all three PASS.

- [ ] **Step 5: Run the whole batch-test file to confirm no regression**

```bash
uv run pytest tests/test_transfer/test_batch.py -v
```

Expected: every test PASS.

- [ ] **Step 6: Commit**

```bash
git add src/atomx_toolkit/transfer/batch.py tests/test_transfer/test_batch.py
git commit -m "feat(transfer): validate name_local in parse_jobs_tsv via CosmxRunName"
```

---

## Task 4: Add CosmxRunName validation in `run_cmd` CLI (TDD)

**Files:**
- Modify: `src/atomx_toolkit/transfer/cli.py:66-90` (the `run_cmd` function entry block)
- Modify: `tests/test_cli.py` (update one existing test, add one new test)

- [ ] **Step 1: Patch the pre-existing CLI test that uses a non-conformant name_local**

The existing `test_transfer_run_requires_config` passes `local` as `name_local`. After we add validation, that input will fail validation **before** the config check, breaking the test's intent. Update it to use a CosmxRunName-valid value so the test still exercises the config-error path.

Edit `tests/test_cli.py`, replace:

```python
def test_transfer_run_requires_config() -> None:
    # No config file present in default location should yield exit 2
    result = _run("transfer", "run", "remote", "local", "--config", "/nonexistent/c.toml")
    assert result.returncode == 2
    assert "config" in (result.stdout + result.stderr).lower()
```

with:

```python
def test_transfer_run_requires_config() -> None:
    # No config file present in default location should yield exit 2
    result = _run(
        "transfer",
        "run",
        "remote",
        "20260101_T_D_sA_v1-0-0",
        "--config",
        "/nonexistent/c.toml",
    )
    assert result.returncode == 2
    assert "config" in (result.stdout + result.stderr).lower()
```

- [ ] **Step 2: Run the existing test suite to confirm it still passes**

```bash
uv run pytest tests/test_cli.py::test_transfer_run_requires_config -v
```

Expected: PASS (no behavior change yet — validation is not added).

- [ ] **Step 3: Write a failing test for the new rejection path**

Append to `tests/test_cli.py`, just after `test_transfer_run_requires_config`:

```python
def test_transfer_run_rejects_invalid_name_local() -> None:
    """transfer run with a non-CosmxRunName name_local must exit 2 with [R1]
    in the rendered error, BEFORE any config / SFTP / md5sum check."""
    result = _run(
        "transfer",
        "run",
        "remote",
        "bad_name",
        "--config",
        "/nonexistent/c.toml",
    )
    assert result.returncode == 2
    combined = (result.stdout + result.stderr).lower()
    assert "[r1]" in combined
    assert "hint:" in combined
    # Validation must precede the config check.
    assert "config" not in combined
```

- [ ] **Step 4: Run the new test to confirm it fails**

```bash
uv run pytest tests/test_cli.py::test_transfer_run_rejects_invalid_name_local -v
```

Expected: FAIL — current `run_cmd` reaches the config-load branch first, so stderr says `config error: ...` and `[R1]` is absent.

- [ ] **Step 5: Implement the validation in `run_cmd`**

Edit `src/atomx_toolkit/transfer/cli.py`. Add the import near the top of the file (after the existing `from atomx_toolkit.transfer.batch ...` and other in-tree imports):

```python
from jianglab_name_standard import CosmxRunName, NameValidationError
```

Inside `run_cmd` (currently starting at line 67), insert the validation block as the **first** statement in the function body, before `cfg_path = config or _default_config_path()`:

```python
@app.command("run")
def run_cmd(
    ctx: typer.Context,
    name_remote: Annotated[str, typer.Argument(help="Remote study directory name")],
    name_local: Annotated[str, typer.Argument(help="Local destination directory name")],
    config: Annotated[Path | None, typer.Option("--config", help="config.toml path")] = None,
) -> None:
    """Download a single study, with double-MD5 verification."""
    try:
        CosmxRunName(name_local)
    except NameValidationError as exc:
        raise typer.BadParameter(
            f"[{exc.rule_id}] {exc.message}\nhint: {exc.hint}",
            param_hint="'NAME_LOCAL'",
        ) from exc
    cfg_path = config or _default_config_path()
    smtp_env_path = _default_smtp_env_path()
    # ... rest of function unchanged
```

- [ ] **Step 6: Run the new test to confirm it passes**

```bash
uv run pytest tests/test_cli.py::test_transfer_run_rejects_invalid_name_local -v
```

Expected: PASS.

- [ ] **Step 7: Run the whole CLI-test file and the prior batch-test file to confirm no regression**

```bash
uv run pytest tests/test_cli.py tests/test_transfer/test_batch.py -v
```

Expected: every test PASS.

- [ ] **Step 8: Commit**

```bash
git add src/atomx_toolkit/transfer/cli.py tests/test_cli.py
git commit -m "feat(transfer): validate name_local in 'transfer run' CLI via CosmxRunName"
```

---

## Task 5: Pre-push checks and merge feature → dev

**Files:** none modified.

- [ ] **Step 1: Run the full lint / format / type / test gauntlet**

```bash
cd ~/projects/atomx-toolkit
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/ tests/
uv run pytest
```

Expected: all four green. If `ruff check` reports fixable issues, run `uv run ruff check --fix src/ tests/` and re-stage. If `ruff format --check` reports drift, run `uv run ruff format src/ tests/` and re-stage. If pyright or pytest fail, stop and debug.

- [ ] **Step 2: Switch to `dev` and merge the feature branch (no fast-forward)**

```bash
git checkout dev
git merge feature/validate-name-local --no-ff
```

When the editor opens, accept the default merge message (`Merge branch 'feature/validate-name-local' into dev`) and save / exit.

- [ ] **Step 3: Delete the local feature branch and push `dev`**

```bash
git branch -d feature/validate-name-local
git push origin dev
```

Expected: `dev` advances on origin; the remote feature branch (if previously pushed) gets auto-deleted on next prune.

---

## Task 6: Cut `release/v0.3.0` and prepare release artifacts

**Files:**
- Modify: `pyproject.toml` (version)
- Modify: `src/atomx_toolkit/__init__.py` (`__version__`)
- Modify: `CHANGELOG.md` (new `[0.3.0]` section)
- Modify: `docs/setup-host.md` (install-pin examples)

- [ ] **Step 1: Cut the release branch from the just-merged `dev`**

```bash
git checkout -b release/v0.3.0 dev
```

- [ ] **Step 2: Bump `pyproject.toml` version**

In `pyproject.toml`, change:

```toml
version = "0.2.0"
```

to:

```toml
version = "0.3.0"
```

- [ ] **Step 3: Bump `__version__` in the package**

In `src/atomx_toolkit/__init__.py`, change:

```python
__version__ = "0.2.0"
```

to:

```python
__version__ = "0.3.0"
```

- [ ] **Step 4: Add the `[0.3.0]` CHANGELOG entry**

In `CHANGELOG.md`, insert a new section **directly under** the top heading (above the existing `[0.2.0]` section):

```markdown
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
```

- [ ] **Step 5: Update install-pin examples in `docs/setup-host.md`**

Replace every occurrence of `@v0.2.0` with `@v0.3.0` in `docs/setup-host.md`:

```bash
sed -i 's/@v0\.2\.0/@v0.3.0/g' docs/setup-host.md
```

Then sanity-check there are no stragglers:

```bash
grep -n "@v0\." docs/setup-host.md
```

Expected: only `@v0.3.0` lines remain.

- [ ] **Step 6: Re-run the full pre-push gauntlet against the release branch**

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
uv run pyright src/ tests/
uv run pytest
```

Expected: all green. The `test_version_flag_prints_version` test reads `__version__` dynamically (per the v0.2.0 fix), so it picks up the bump automatically.

- [ ] **Step 7: Commit the release-prep changes**

```bash
git add pyproject.toml src/atomx_toolkit/__init__.py CHANGELOG.md docs/setup-host.md
git commit -m "chore: bump version to 0.3.0 and update CHANGELOG"
```

---

## Task 7: Open the release PR, wait for CI, merge, tag, back-merge

**Files:** none modified locally. This task drives the GitHub release flow.

- [ ] **Step 1: Push the release branch**

```bash
export PATH=$HOME/.local/bin:$PATH   # ensure real `gh` (not /opt/miniforge3/bin/gh) is on PATH
git push -u origin release/v0.3.0
```

- [ ] **Step 2: Open the PR with the new CHANGELOG section as the body**

```bash
gh pr create --base main --head release/v0.3.0 \
  --title "Release v0.3.0" \
  --body "$(cat <<'EOF'
## [0.3.0] - 2026-05-12

### Added

- Runtime dependency on [`jianglab-name-standard`](https://github.com/wuwenrui555/jianglab-name-standard) `@v0.1.1` for the lab-wide CosMx naming standard.
- `parse_jobs_tsv` and the `transfer run` CLI now validate the `name_local` column against `jianglab_name_standard.CosmxRunName`: 5 underscore-separated fields, real calendar date, and an `atomx_version` of the form `v<major>-<minor>-<patch>`. Invalid names are rejected before any disk write or SFTP connection, with a message that includes the failing rule ID and the jianglab hint.

### Changed

- `name_local` values that previously parsed without complaint but did not match `CosmxRunName` are now rejected. `name_remote` is unchanged (still free-form, since AtoMx-side names are out of our control).

### Migration notes

- Existing operators with a `jobs.tsv` written against v0.2.0 should preview their file with `atomx-toolkit transfer plan <path>`: validation errors surface in the plan dry-run with no transfer attempted. Rewrite any rejected `name_local` to the 5-field form, for example `20260211_WW_ACLF_run1_v2-2-1`. The AtoMx-generated folder name is already in this shape, so the simplest fix is "use the AtoMx folder name verbatim as `name_local`."
EOF
)"
```

Expected: prints the PR URL. Capture the PR number from the URL.

- [ ] **Step 3: Wait for CI to finish on the PR**

```bash
gh pr checks <PR#> --watch
```

Expected: the `test` check finishes with `pass`. If it fails, stop and debug; do not proceed.

- [ ] **Step 4: Merge via PR (forces `--no-ff` per repo setup)**

```bash
gh pr merge <PR#> --merge
```

Expected: succeeds. The release branch is auto-deleted on the remote per the repo's `delete_branch_on_merge=true` setting.

- [ ] **Step 5: Pull the merge commit on `main` and tag**

```bash
git checkout main
git pull --ff-only origin main
git tag v0.3.0 -m "v0.3.0: validate name_local via jianglab-name-standard"
git push origin --tags
```

Expected: `* [new tag] v0.3.0 -> v0.3.0`.

- [ ] **Step 6: Back-merge the release into `dev`**

```bash
git checkout dev
git merge release/v0.3.0 --no-ff
```

Accept the default merge message.

- [ ] **Step 7: Push `dev` and clean up local branches**

```bash
git push origin dev
git branch -d release/v0.3.0
git fetch --prune origin
```

Expected: `release/v0.3.0` deleted locally; pruned from the remote-tracking refs.

- [ ] **Step 8: Verify final state**

```bash
git log --oneline --decorate --all -8
```

Expected output shape:

```
<sha> (HEAD -> dev, origin/dev) Merge branch 'release/v0.3.0' into dev
<sha> (tag: v0.3.0, origin/main, main) Merge pull request #N from wuwenrui555/release/v0.3.0
<sha> chore: bump version to 0.3.0 and update CHANGELOG
<sha> Merge branch 'feature/validate-name-local' into dev
<sha> feat(transfer): validate name_local in 'transfer run' CLI ...
<sha> feat(transfer): validate name_local in parse_jobs_tsv ...
<sha> test(batch): use CosmxRunName-conformant name_local in parse tests
<sha> chore: add jianglab-name-standard@v0.1.1 dependency
```

---

## Done.

The repo is at v0.3.0, tagged on `main`, with `dev` back in sync. Operators install with:

```bash
pip install --user git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.3.0
```
