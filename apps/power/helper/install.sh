#!/usr/bin/env bash
# One-time setup for the Forge Power app. Run: sudo bash ~/Forge/apps/power/helper/install.sh
# Safe to run again (every step checks before it acts). Re-run after editing forge_power.py.
set -uo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "Run it with sudo: sudo bash $0"
  exit 1
fi

HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$(dirname "$HERE")"
USER_NAME="${SUDO_USER:-}"
if ! [[ "$USER_NAME" =~ ^[a-z_][a-z0-9_-]*$ ]]; then
  echo "Could not tell which user to allow; run it through sudo from your own account."
  exit 1
fi
problems=0
step() { echo; echo "== $1 =="; }
warn() { echo "  problem: $1"; problems=$((problems + 1)); }

step "Power helper"
install -o root -g root -m 0755 "$HERE/forge_power.py" /usr/local/bin/forge-power && echo "  /usr/local/bin/forge-power (root-owned)"

step "Passwordless rule for that one file"
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
echo "$USER_NAME ALL=(root) NOPASSWD: /usr/local/bin/forge-power" > "$tmp"
if visudo -cf "$tmp" >/dev/null; then
  install -o root -g root -m 0440 "$tmp" /etc/sudoers.d/forge-power && echo "  /etc/sudoers.d/forge-power"
else
  warn "sudoers rule failed its syntax check, not installed"
fi

step "Re-apply the last mode at boot"
install -o root -g root -m 0644 "$HERE/forge-power-restore.service" /etc/systemd/system/forge-power-restore.service
systemctl daemon-reload
systemctl enable forge-power-restore.service >/dev/null 2>&1 && echo "  forge-power-restore.service enabled"

step "Removing auto-cpufreq and undoing what it changed"
if pacman -Q auto-cpufreq >/dev/null 2>&1; then
  systemctl disable --now auto-cpufreq.service >/dev/null 2>&1
  # Plain -R: its Python dependencies may be used by other tools here, so they stay.
  pacman -R --noconfirm auto-cpufreq >/dev/null && echo "  auto-cpufreq removed" || warn "pacman could not remove auto-cpufreq"
else
  echo "  auto-cpufreq already removed"
fi
rm -rf /opt/auto-cpufreq && echo "  its forced-mode and turbo override files are gone"
if [ -L /etc/systemd/system/power-profiles-daemon.service ]; then
  systemctl unmask power-profiles-daemon.service >/dev/null 2>&1 && echo "  power-profiles-daemon is no longer blocked"
fi
systemctl daemon-reload
settings="$(/usr/bin/python3 -I -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["settings"]))' "$APP/modes/auto.json")"
if printf '%s' "$settings" | /usr/local/bin/forge-power apply --mode auto >/dev/null; then
  echo "  CPU put back to normal: Auto mode applied (turbo on, no frequency cap, balanced)"
else
  warn "could not apply Auto mode"
fi

if [ "${1:-}" != "--no-cleanup" ]; then
  step "Turning off services that do nothing useful on this laptop"
  for s in i8kmon pacman-init grub-btrfsd choose-mirror livecd-alsa-unmuter livecd-talk \
           vboxservice ModemManager NetworkManager-wait-online haveged; do
    if ! systemctl is-enabled "$s.service" >/dev/null 2>&1; then
      echo "  already off: $s"
    elif systemctl disable --now "$s.service" >/dev/null 2>&1; then
      echo "  off: $s"
    else
      warn "could not turn off $s (left as it was)"
    fi
  done
  systemctl reset-failed
  echo "  undo list: ~/Forge/backups/enabled-services.pre-power.txt"
fi

step "Crash dumps"
before="$(du -sh /var/lib/systemd/coredump 2>/dev/null | cut -f1)"
find /var/lib/systemd/coredump -maxdepth 1 -type f -name 'core.*' -delete
mkdir -p /etc/systemd/coredump.conf.d
printf '[Coredump]\nMaxUse=500M\n' > /etc/systemd/coredump.conf.d/50-forge-power.conf
echo "  cleared ${before:-0} of crash dumps; future dumps capped at 500 MB"

step "Package cache"
if command -v paccache >/dev/null; then
  paccache -rk1 | tail -1
  paccache -ruk0 | tail -1
else
  warn "paccache not found (pacman-contrib), cache left alone"
fi

step "Memory: compressed RAM swap and early out-of-memory rescue"
if pacman -S --needed --noconfirm earlyoom zram-generator >/dev/null; then
  echo "  earlyoom and zram-generator installed"
  printf '[zram0]\nzram-size = min(ram / 2, 8192)\ncompression-algorithm = zstd\nswap-priority = 100\n' \
    > /etc/systemd/zram-generator.conf
  systemctl daemon-reload
  systemctl start systemd-zram-setup@zram0.service && echo "  zram swap on: $(swapon --show=NAME,SIZE --noheadings | tr '\n' ' ')"
  # Rescue at 4% free memory and 10% free swap. Prefer closing the local LLM server or a
  # browser tab; never the desktop itself.
  cat > /etc/default/earlyoom <<'EOF'
EARLYOOM_ARGS="-m 4 -s 10 -r 3600 --prefer ^(llama-server|Isolated.Web.Co|chrome)$ --avoid ^(Hyprland|qs|quickshell|Xwayland|gdm.*|systemd.*|pipewire.*|wireplumber|dbus.*|sshd)$"
EOF
  systemctl enable --now earlyoom.service >/dev/null 2>&1 && echo "  earlyoom running" || warn "earlyoom did not start"
else
  warn "could not install earlyoom and zram-generator (no network?)"
fi

echo
if [ "$problems" -eq 0 ]; then
  echo "All done."
else
  echo "Done with $problems problem(s); see the lines marked 'problem' above."
fi
echo "Check the passwordless rule with: sudo -k; sudo -n /usr/local/bin/forge-power measure --seconds 5"
