# Getting the laptop back from the Rescue drive

date: 2026-10-08 · for: both (Emerson, or a Claude session helping him)

This guide also lives on the drive itself at `forge-backup-tool/RESTORE.md`
on **both** partitions, so it is there even if the laptop is gone.

## What is on the drive

| Partition | Size | Holds |
|---|---|---|
| `Rescue` (ext4) | 260 GB | `system/<date>/` = the whole laptop: `root/` (everything on `/`, incl. home), `boot/`, `efi/` |
| `Vault` (ext4) | 206 GB | `claude/`, `forge/`, `projects/`, `app-data/`, `files/` dated snapshots, and `git/*.git` offline mirrors |

A folder named like `2026-10-08_213559` is a **complete** snapshot. A name
ending in `.partial` is an unfinished one; ignore it. Each snapshot is a plain
folder: you can just browse it and copy single files back with any file manager.

Not copied (re-creatable): `~/.cache`, the trash, pacman's package cache,
`/tmp`, `/proc`, `/sys`, `/dev`, `/run`.

## Just one file or folder back

Plug the drive in. It mounts at `/run/media/ejb/Rescue` (or `/mnt/forge-drive/rescue`).

```sh
ls /run/media/ejb/Rescue/system/                      # pick a date
sudo cp -a /run/media/ejb/Rescue/system/<date>/root/home/ejb/<path> ~/<path>
```

Claude/Forge work with more history: `/run/media/ejb/Vault/<set>/<date>/`.
A git project: `git clone /run/media/ejb/Vault/git/Forge.git`.

## Whole laptop (new SSD, or the old one wiped)

The laptop's layout was: GPT disk, `p1` 2 GB FAT32 at `/efi`, `p2` 2 GB ext4
at `/boot`, `p3` the rest ext4 at `/`. Bootloader GRUB (UEFI).

1. Boot an Arch Linux install USB (archlinux.org/download, write it with
   `dd` or Ventoy). Plug in the backup drive.
2. Find the disks: `lsblk`. Below, the laptop SSD is `/dev/nvme0n1`;
   check yours. **Make sure you are not about to format the backup drive**
   (that is the ~466 GB one with `Rescue` and `Vault` labels).
3. Partition and format the SSD:
   ```sh
   sfdisk /dev/nvme0n1 <<'X'
   label: gpt
   size=2GiB, type=uefi
   size=2GiB, type=linux
   type=linux
   X
   mkfs.fat -F32 /dev/nvme0n1p1
   mkfs.ext4 -L boot /dev/nvme0n1p2
   mkfs.ext4 -L root /dev/nvme0n1p3
   ```
4. Mount everything:
   ```sh
   mount /dev/nvme0n1p3 /mnt
   mkdir -p /mnt/boot /mnt/efi /rescue
   mount /dev/nvme0n1p2 /mnt/boot
   mount /dev/nvme0n1p1 /mnt/efi
   mount /dev/disk/by-label/Rescue /rescue
   ls /rescue/system/          # newest name without .partial
   S=/rescue/system/<that date>
   ```
5. Copy back (an hour or two over USB):
   ```sh
   rsync -aAXH --numeric-ids --info=progress2 $S/root/ /mnt/
   rsync -aAXH --numeric-ids $S/boot/ /mnt/boot/
   rsync -rt $S/efi/ /mnt/efi/
   ```
6. New partitions have new IDs, so rewrite the mount table:
   ```sh
   cp /mnt/etc/fstab /mnt/etc/fstab.old
   genfstab -U /mnt | grep -v -e zram -e '/rescue' > /mnt/etc/fstab
   ```
   Compare with `fstab.old` (old options were `noatime,nodiscard`, `/efi`
   had `umask=0077`, `/tmp` was a tmpfs line; copy those across).
7. Boot loader and startup image:
   ```sh
   arch-chroot /mnt
   grub-install --target=x86_64-efi --efi-directory=/efi --bootloader-id=GRUB
   grub-mkconfig -o /boot/grub/grub.cfg
   mkinitcpio -P
   exit
   ```
8. `umount -R /mnt`, unplug the USB stick, reboot. Everything (Forge, Claude
   memory, venvs, Hyprland) is as it was on the snapshot date.

If the new SSD is smaller than what is used (about 150 GB in Oct 2026), the
copy in step 5 runs out of space: delete `~/Downloads` or `~/Games` from the
copy list by restoring with `--exclude=/home/ejb/Games` and copy them later.

## For Claude

The tool is `~/Forge/apps/backup/backup.py` (copy also on the drive in
`forge-backup-tool/`). What gets copied is `sets.json`. To check on it:
`forge-backup status`, `journalctl -u 'forge-backup-*'`,
`/var/lib/forge-backup/status.json`, `<drive>/last-run.json`.
