# Backup app: offline GitHub and rescue browser in Forge

date: 2026-10-08 · for: both

The Forge app `apps/backup` (tile "Backup", System section, port 8468) is the
page over the backup drive described in `2026-10-08-backup-drive.md`.

## What it does

- **Code**: browse the bare git mirrors in `Vault/git/` like GitHub, offline:
  branches, tags, history, a commit's diff, files at any commit, README.
- **Snapshots**: Rescue or Vault, set, date; browse, view, compare a file or
  folder with the laptop, copy back to `~/Restored/<date>/<set>/<path>`.
- **Status**: drive, free space, sets, due, last run; Back up now with the
  live journal; Eject.
- **Help**: RESTORE.md and README.md rendered.

## Decisions (Relay task 117, made unattended)

- The drive logic stays in `backup.py`; the page's `browse.py` imports it.
- Nothing deletes. A restore never overwrites: an existing target becomes
  `name-2`, `name-3`. Restores of folders run in the background and report
  files that needed admin as skipped.
- Links inside a snapshot are listed, never followed on the server (an
  absolute link would lead onto the laptop). Relative ones (`bin -> usr/bin`)
  open their target in the same snapshot.
- Unfinished `.partial` snapshots are listed and browsable, marked
  "unfinished"; the newest complete one is picked by default.
- Root-owned Rescue folders show "needs admin" rather than an error; there is
  no sudo helper in the app (by design, for now).
- After Eject the app stops mounting the drive on page loads until it is
  unplugged (otherwise the next Status refresh would mount it again).
- A copy back never writes through a link already in `~/Restored`.
- Back up now and Eject refuse while a backup runs (Eject also while a copy
  back is reading the drive). Every `/api` route needs
  `X-Forge: 1` and a local Host, since the snapshots hold everything.

## Verified

See `apps/backup/WIP.md`, section "2026-10-08: the Backup page in Forge", for the test
count, the real-drive checks and the screenshots.
