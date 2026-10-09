#!/usr/bin/env bash
# Removes what install.sh added. Run: sudo bash ~/Forge/apps/power/helper/uninstall.sh [--restore-services]
# Kept on purpose: freed disk space, the package cache trim and cleared crash dumps cannot be undone,
# and auto-cpufreq is not reinstalled (reinstall with: sudo pacman -S auto-cpufreq).
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo: sudo bash $0"
  exit 1
fi

HOME_DIR="$(getent passwd "${SUDO_USER:-ejb}" | cut -d: -f6)"
BACKUP="$HOME_DIR/Forge/backups/throttled.conf.pre-power"

systemctl disable forge-power-restore.service >/dev/null 2>&1
rm -f /etc/systemd/system/forge-power-restore.service /etc/sudoers.d/forge-power /usr/local/bin/forge-power
rm -rf /var/lib/forge-power
echo "power helper, sudoers rule and boot service removed"

systemctl disable --now earlyoom.service >/dev/null 2>&1
rm -f /etc/systemd/zram-generator.conf /etc/systemd/coredump.conf.d/50-forge-power.conf
systemctl daemon-reload
swapoff /dev/zram0 >/dev/null 2>&1
echo "earlyoom stopped, zram swap and crash-dump cap removed (packages left installed)"

if [ -f "$BACKUP" ] && ! cmp -s "$BACKUP" /etc/throttled.conf; then
  install -o root -g root -m 0644 "$BACKUP" /etc/throttled.conf
  systemctl restart throttled.service
  echo "restored /etc/throttled.conf from $BACKUP"
fi

if [ "${1:-}" = "--restore-services" ]; then
  for s in i8kmon pacman-init grub-btrfsd choose-mirror livecd-alsa-unmuter livecd-talk \
           vboxservice ModemManager NetworkManager-wait-online haveged; do
    systemctl enable --now "$s.service" >/dev/null 2>&1 && echo "  back on: $s" || echo "  could not re-enable: $s"
  done
fi
