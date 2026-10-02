#!/bin/sh
# Installs Eighty Six for this user: the game into ~/.local/share/eightysix and an entry in the app menu.
# Run it from the unzipped folder: sh install.sh
set -e
here="$(cd "$(dirname "$0")" && pwd)"
data="${XDG_DATA_HOME:-$HOME/.local/share}"
dest="$data/eightysix"
mkdir -p "$dest" "$data/applications"
cp "$here/eightysix.x86_64" "$here/eightysix.pck" "$here/icon.svg" "$dest/"
chmod +x "$dest/eightysix.x86_64"
cat > "$data/applications/eightysix.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Eighty Six
Comment=Juggernaut walker game
Exec="$dest/eightysix.x86_64"
Path=$dest
Icon=$dest/icon.svg
Categories=Game;
Terminal=false
DESKTOP
echo "Installed to $dest"
echo "Start it from your app menu (Eighty Six) or run: $dest/eightysix.x86_64"
