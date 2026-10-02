#!/bin/sh
# Installs Eighty Six on a Mac: copies the app to Applications and lifts the "downloaded from the internet"
# block (the game is not notarised by Apple, so macOS would otherwise refuse to open it).
# Run it from Terminal: type  sh  and a space, drag this file into the window, press Return.
here="$(cd "$(dirname "$0")" && pwd)"
dest="/Applications"
[ -w "$dest" ] || { dest="$HOME/Applications"; mkdir -p "$dest"; }
rm -rf "$dest/Eighty Six.app"
cp -R "$here/Eighty Six.app" "$dest/" || { echo "Could not copy Eighty Six.app to $dest"; exit 1; }
xattr -dr com.apple.quarantine "$dest/Eighty Six.app" 2>/dev/null
echo "Installed to $dest/Eighty Six.app; opening it now."
open "$dest/Eighty Six.app"
