# Backup: work in progress

## 2026-10-08: built (CLI tool, no hub page yet)

**Verified**
- External Toshiba drive repartitioned (it held only the factory autorun
  icon): GPT, `sda1` ext4 `Rescue` 260 GiB, `sda2` ext4 `Vault` 205.8 GiB.
- `tests/test_backup.py`: 9 pass (real rsync + git on temp folders): copy +
  excludes, hard links between snapshots, resuming a `.partial`, prune never
  drops the newest, refusing to delete non-snapshot paths, due logic, git
  mirror create + update, config shape.
- black clean, pyright 0 errors (`--pythonpath ./.venv/bin/python`).
- Units, timer, udev and polkit rules installed via `sudo system/install.sh`;
  timer enabled. `forge-backup now all` started as ejb with no password
  (polkit rule works) and the root unit began copying.
- First full run: see the bottom of this file.

**Not verified (reasoned only)**
- The plug-in udev trigger (needs a real unplug/replug).
- A full bare-metal restore per RESTORE.md (needs a spare SSD or VM);
  single-file restore from a snapshot is easy to check by hand.

**Next**
- Relay task 117: the Forge hub app (offline GitHub, snapshot browser,
  status, help), built into this folder. Done: see the next section.

## 2026-10-08: the Backup page in Forge (Relay task 117)

New files: `browse.py` (drive status, snapshot browsing, compare with the
laptop, restore copies, read-only git plumbing on the bare mirrors; it
imports `backup.py` for `find_mount`, `snapshots`, `is_due` and the rest),
`web_app.py` (FastAPI, port 8468, local-only guard), `static/` (Code,
Snapshots, Status, Help pages on the shared Forge kit), `forge_app.json`
(System section, order 23), `tests/test_browse.py`, `test_edges.py`,
`test_web.py`. `backup.py` gained `parse_stamp` (bad snapshot names are
skipped), an `eject()` that checks the drive really unmounted and says the
sudo step when Rescue is root-mounted, and `run()` unmounting only what it
mounted itself.

**Verified**
- 46 pytest pass (`.venv/bin/python -m pytest -q tests`), including the 9
  original backup tests. black clean, pyright 0 errors. The 10 tests added
  for critic 2's findings were run against the code before the fix and all
  failed there.
- Against the real drive (scratch server, curl and headless Chrome
  screenshots looked at): the Code page lists the mirrors in Vault/git
  (Forge, Games__eightysix, anime-codec-lab, which is empty and says "no
  commits yet"), a repo's branches, history, a commit's diff, tree and
  README; the Snapshots page browses Rescue `system/<date>/root`, shows
  "needs admin" on root-owned folders like `root/root` and `etc/shadow`,
  compares `etc/hostname` with the laptop (identical); Status shows free
  space, sets, ages and last run.
- Forge's `discover_backends()` lists Backup; a headless shot of a copy of
  the hub with freshly written status shows the Backup tile in System.
- Symlinks inside a snapshot are listed, never followed; non-UTF-8 names
  are listed with the bad bytes replaced and cannot be opened; restores go
  to `~/Restored/<date>/<set>/...` with a -2, -3 suffix rather than
  overwriting, never through a link already there, and keep 5 GB free (unit
  tests on a temp fake drive).
- Back up now: start, refusal while a run is active, and the progress read
  are tested with systemctl and journalctl mocked.

- Two critic passes (fresh Opus agents). Critic 1: 14 defects, all fixed.
  Critic 2: 12 findings, none high: fixed a 500 on a link whose target is
  not UTF-8, one unreadable set no longer blocks the whole area, 16px text
  raised to 17px, Eject no longer re-mounted by the next page load and waits
  for a running copy back, Compare says needs admin instead of "gone" when
  it cannot look, unreadable `Vault/git` and unreadable entries say needs
  admin, due shown per set, the last run's git results shown, stale Code
  page replies dropped, Help links no longer show raw brackets (web links
  open), copies go under the set name and never through a link; plus a
  stray "null" and one-paragraph-per-line in Help, found on the screenshots.
  Screenshots of Status, Help, Code and a commit after these fixes looked at.

**Not verified (reasoned only)**
- Web links in rendered markdown open with window.open; inside the Forge
  window that path was not clicked.
- Pressing Back up now and Eject for real (not done on purpose: a backup
  was running, and ejecting would have cut it off).
- The live Forge window picking Backup up without a restart (the hub
  rescans apps every 15 s; its `status.js` file is only rewritten when an
  app changes state, so a page reload before that shows the old list).

**Known gaps**
- Root-owned Rescue folders say "needs admin"; there is no sudo helper to
  open them from the page.
- No search inside a snapshot or a repo yet.
- The small "Close app" button in the header comes from the shared
  `forge_chrome.js`, so it is the same small size in every app.


## 2026-10-08: first full run

`forge-backup now all` started 21:35 and finished about 22:15: Rescue holds
one system snapshot (`system/2026-10-08_213559`), Vault holds the five sets
and three git mirrors (Forge, Games__eightysix, anime-codec-lab).

## 2026-10-08: first full run (verified)

- `forge-backup now all` 21:35-22:15, systemd Result=success, every rsync
  exit 0. Rescue 30 min (root snapshot 133 GB, 117.5 GB left free);
  Vault 9.5 min; git mirrors Forge.git, anime-codec-lab.git,
  Games__eightysix.git created.
- Restore check: `/etc/fstab` in the Rescue snapshot is byte-identical to
  the live one; newest Vault `Forge/forge.py` identical to the live one.
- Second `now vault` run: about 11 s; 15,287 of 15,419 Forge files are hard
  links to the first snapshot. The tool and guides were copied to
  `forge-backup-tool/` on the drive.
- Gotcha: a oneshot unit shows ActiveState=activating while running, so
  `systemctl is-active` says "not active". Check
  `systemctl show -p ActiveState --value <unit>` instead.
