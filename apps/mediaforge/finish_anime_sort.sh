#!/usr/bin/env bash
# finish_anime_sort.sh — resume the anime consolidation once the external drive
# is mounted. Wraps tools/anime_sorter.py, which NEVER deletes or overwrites and
# writes a revertible manifest for every move (competing encodes / identical
# files go to <library>/_DUPLICATES/<original path> for you to clear by hand;
# an .mkv and .mp4 of the same episode are both kept).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY="$HERE/.venv/bin/python"
DRIVE_UUID="14DE4324DE42FD8C"
MNT="/run/media/ejb/$DRIVE_UUID"
LIB="$MNT/Anime"

if [ ! -d "$MNT" ]; then
  echo "The external drive ($DRIVE_UUID) is not mounted."
  echo
  if lsblk -no UUID /dev/sda1 2>/dev/null | grep -q "$DRIVE_UUID"; then
    echo "It is plugged in as /dev/sda1 but won't mount (NTFS left dirty by Windows"
    echo "fast-startup, or the kernel ntfs3 driver choking). Fix and mount with:"
    echo
    echo "    sudo ntfsfix -d /dev/sda1        # clear the dirty flag"
    echo "    udisksctl mount -b /dev/sda1     # or: sudo mount -t ntfs-3g /dev/sda1 $MNT"
  else
    echo "Plug the drive in, then re-run this script."
  fi
  exit 1
fi

# Everywhere anime video might still be scattered. Add/remove as needed.
SCAN=(
  "$MNT/sorted"
  "$MNT/Downloads"
  "$MNT/downloads"
  "$MNT/Anime_unsorted"
  "$MNT/torrents"
  "$HOME/Downloads"
  "$HOME/Videos"
)
EXIST=()
for d in "${SCAN[@]}"; do [ -d "$d" ] && EXIST+=("$d"); done
if [ ${#EXIST[@]} -eq 0 ]; then
  echo "None of the usual scatter folders exist under $MNT — edit SCAN[] in this script."
  echo "Checked: ${SCAN[*]}"
  exit 1
fi

echo "==> library : $LIB"
echo "==> scanning: ${EXIST[*]}"
echo

MODE="${1:-dry}"
if [ "$MODE" = "apply" ]; then
  "$PY" "$HERE/tools/anime_sorter.py" --scan "${EXIST[@]}" --library "$LIB" --apply
  echo
  echo "Done. Undo with:  $PY $HERE/tools/anime_sorter.py --revert <manifest.json>"
  echo "Manifests: ~/MediaForgeData/manifests/"
else
  "$PY" "$HERE/tools/anime_sorter.py" --scan "${EXIST[@]}" --library "$LIB"
  echo
  echo "That was a DRY RUN. Review the plan above, then:  bash $0 apply"
fi
