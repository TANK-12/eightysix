# Backup drive: layout and how to use it

date: 2026-10-08 · for: both

- Drive: Toshiba MQ01ABD050 500 GB, USB. Was exFAT "External HD" with only a
  factory autorun icon; reformatted 2026-10-08.
- `Rescue` 260 GiB ext4: whole-system snapshots every 48 h, keep 8.
- `Vault` 205.8 GiB ext4: Claude, Forge, projects, app data, Documents,
  Desktop, Pictures, Hyprland config every 24 h, keep 30; git mirrors of
  Forge, anime-codec-lab, eightysix.
- Laptop used 147 GB of 230 GB on the day; first Rescue copy is about that size.
- Tool: `~/Forge/apps/backup` (README.md, RESTORE.md). Command `forge-backup
  status | now | eject`. Timer every 6 h and on plug-in.
