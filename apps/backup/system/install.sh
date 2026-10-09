#!/bin/sh
# Installs the Forge backup units, plug-in trigger and permission rule. Run with sudo.
set -e
here=$(dirname "$(readlink -f "$0")")
install -m644 "$here"/forge-backup-auto@.service "$here"/forge-backup-now@.service "$here"/forge-backup.timer /etc/systemd/system/
install -m644 "$here"/90-forge-backup.rules /etc/udev/rules.d/
install -m644 "$here"/50-forge-backup.rules /etc/polkit-1/rules.d/
mkdir -p /var/lib/forge-backup
systemctl daemon-reload
udevadm control --reload
systemctl enable --now forge-backup.timer
