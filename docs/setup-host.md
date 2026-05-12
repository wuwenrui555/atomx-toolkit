# Host setup

Run on a Linux host with Python 3.12+, `md5sum`, and outbound network
to AtoMx and SMTP.

## 1. Install Python and md5sum

```bash
# Debian/Ubuntu
sudo apt install python3.12 python3.12-venv coreutils

# Fedora
sudo dnf install python3.12 coreutils
```

## 2. Install atomx-toolkit

```bash
pip install --user git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.3.0
```

Or use `uv`:
```bash
uv tool install git+https://github.com/wuwenrui555/atomx-toolkit.git@v0.3.0
```

## 3. Initialize config

```bash
atomx-toolkit install init
```

This creates `~/.config/atomx-toolkit/`:
```
config.toml         # paths, hostname, [notify] toggle
sftp.env            # ATOMX_SFTP_USER / ATOMX_SFTP_PASSWORD
smtp.env            # ATOMX_SMTP_USER / ATOMX_SMTP_APP_PASSWORD
recipients/         # per-event subscriber lists
state/              # runtime dedup state (managed automatically)
```

## 4. Edit config.toml

```toml
[paths]
log_root = "/data/log/atomx"
backup_root = "/data/backup/atomx"
```

`backup_root` must have free space >= the largest expected study size,
because each study is downloaded twice (then the second copy is removed
on success).

## 5. Set credentials

`sftp.env`:
```env
ATOMX_SFTP_USER=your_atomx_username
ATOMX_SFTP_PASSWORD=your_atomx_password
```

`smtp.env` (for Gmail; generate an app password at <https://myaccount.google.com/apppasswords>):
```env
ATOMX_SMTP_USER=youraccount@gmail.com
ATOMX_SMTP_APP_PASSWORD=xxxxxxxxxxxxxxxx
```

Alternative: set the same names as environment variables (env wins
over the dotenv file).

## 6. Subscribe recipients

`~/.config/atomx-toolkit/recipients/transfer_report.txt`:
```
you@example.com
```

`~/.config/atomx-toolkit/recipients/batch_report.txt`:
```
you@example.com
```

`~/.config/atomx-toolkit/recipients/toolkit_error.txt`:
```
you@example.com
```

(default.txt is a fallback; leave empty if event-specific files cover
your needs.)

If you pass `--config <path>` to a command, the recipients directory
defaults to `<path>'s parent>/recipients`. The default config location
`~/.config/atomx-toolkit/config.toml` therefore yields
`~/.config/atomx-toolkit/recipients/`, which is what `install init`
populates. If you point `--config` at a custom location like
`/etc/atomx-toolkit/config.toml`, you'll need to either populate
`/etc/atomx-toolkit/recipients/` yourself or set
`[notify].recipients_dir` explicitly in the TOML.

## 7. Test the pipeline

```bash
atomx-toolkit notify test --event transfer_report --dry-run
atomx-toolkit notify test --event transfer_report
# check your inbox

atomx-toolkit transfer plan example_jobs.tsv
```
