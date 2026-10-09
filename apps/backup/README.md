# Forge backup

Backs the laptop up onto the external USB drive (Toshiba 500 GB), split in two:

- **Rescue** (260 GB): the whole system, every 2 days, newest 8 kept.
  Enough to rebuild the laptop exactly: see [RESTORE.md](RESTORE.md).
- **Vault** (206 GB): Claude stuff (`~/.claude`, `~/.claude.json`), `~/Forge`
  (without venvs and caches), your projects, app data folders, Documents,
  Desktop, Pictures and the Hyprland config, every day, newest 30 kept; plus
  offline git mirrors (every branch and commit) of Forge, anime-codec-lab
  and eightysix in `git/`.

## Using it

```sh
forge-backup status        # what is on the drive, how old, free space
forge-backup now           # back up everything now (also: now rescue / now vault)
forge-backup eject         # unmount both parts and power the drive down to unplug
journalctl -fu forge-backup-now@all.service    # watch a running backup
```

Nothing to remember otherwise: a timer checks every 6 hours, and plugging
the drive in checks right away. Whatever is due (Rescue older than 48 h,
Vault older than 24 h) runs in the background at the lowest priority. If the
drive is not plugged in, nothing happens.

## The Backup page in Forge

The **Backup** tile (System section, 💾) opens four tabs over the same drive.
None of them deletes a snapshot or a mirror.

- **Code**: your offline GitHub. Every mirror in `Vault/git/` with its last
  commit; per project the branches and tags, the history (50 at a time), a
  commit's message and coloured diff, the files at any commit (a "Browse
  files at this commit" button), a file's own history, and the README shown
  rendered under each folder.
- **Snapshots**: pick Rescue or Vault, a set and a date. Browse folders,
  read text files and pictures, **Compare with the laptop** (identical,
  changed with a line-by-line diff, or gone), and **Copy back**: the file or
  folder goes to `~/Restored/<date>/<set>/<path>`, never over anything (a
  second copy becomes `name-2`). Folders owned by root show **needs admin**; open
  those with sudo as in RESTORE.md. A date marked *unfinished* is a copy
  still running or one that stopped.
- **Status**: plugged in or not, free space, every set's snapshots and age,
  due or not, the last run; **Back up now** (everything, Rescue or Vault),
  which starts the root unit and shows its journal live; **Eject drive**.
  Both buttons wait while a backup runs (Eject also waits for a copy back).
  After Eject the page does not mount the drive again until it is
  unplugged and plugged back in.
- **Help**: RESTORE.md and this file, rendered, so the fix steps are one
  click away even with the drive unplugged.

Without the drive every page says so plainly and offers Check again.

Code: `browse.py` (reads the drive, imports `backup.py` for mounts,
snapshots and due logic), `web_app.py` (FastAPI on port 8468; every `/api`
call needs `X-Forge: 1` and a local Host), `static/`. Run it alone with
`FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app
--host 127.0.0.1 --port 8468`. `BACKUP_DRIVE_DIR=<dir>` makes `<dir>/rescue`
and `<dir>/vault` stand in for the drive (tests, screenshots);
`BACKUP_RESTORE_DIR` moves `~/Restored`.

## How it works

- `backup.py`: stdlib Python. Each snapshot is a dated folder made by
  `rsync --link-dest`: unchanged files are hard links to the previous
  snapshot, so each extra snapshot costs only what changed. Written as
  `<date>.partial` and renamed when done; an interrupted run is resumed.
  Old snapshots are dropped past `keep`, or early if free space falls below
  `min_free_gb` (never the newest one).
- `sets.json`: the registry. **To back up something new, add an item to a set
  there** (or a new set); nothing else changes. `git` lists repos to mirror.
- `system/`: systemd units (`forge-backup-auto@.service`,
  `forge-backup-now@.service`, `forge-backup.timer`), the udev plug-in rule,
  and the polkit rule letting `ejb` start these units with no password.
  `sudo system/install.sh` installs them all.
- Runs as root (needed to read the whole system). `forge-backup now` as a
  normal user asks systemd to start the root unit.
- Each run copies this folder (minus the venv) to `forge-backup-tool/` on
  both partitions, with RESTORE.md.

Tests: `.venv/bin/python -m pytest -q tests` (real rsync and git on temp
folders; the page's tests use a fake drive and never call systemctl).
