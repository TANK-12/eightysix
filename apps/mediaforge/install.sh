#!/usr/bin/env bash
# One-time setup for MediaForge.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="$(command -v python3)"

echo "==> MediaForge setup in $HERE"
[ -d "$VENV" ] || "$PY" -m venv --system-site-packages "$VENV"

echo "==> core dependencies"
"$VENV/bin/pip" -q install --upgrade pip
"$VENV/bin/pip" -q install customtkinter darkdetect pillow pypdf requests \
    imagehash anitopy pymupdf

echo "==> optional dependencies (translation / transcription / manga / metadata)"
"$VENV/bin/pip" -q install deep-translator faster-whisper selenium || \
    echo "   (some optional deps failed — those modules will show install hints)"

MISS=""
command -v ffmpeg  >/dev/null || MISS="$MISS ffmpeg"
command -v ffprobe >/dev/null || MISS="$MISS ffmpeg"
[ -n "$MISS" ] && echo "==> !! install ffmpeg:  sudo pacman -S ffmpeg"

echo "==> verifying"
"$VENV/bin/python" - <<'PY'
import customtkinter, PIL, requests
mods = {}
for m in ("fitz","imagehash","anitopy","selenium","faster_whisper","deep_translator"):
    try: __import__(m); mods[m]="ok"
    except Exception: mods[m]="MISSING (optional)"
print("   customtkinter", customtkinter.__version__)
for k,v in mods.items(): print(f"   {k}: {v}")
PY

echo "==> icon + desktop entry"
ICONDIR="$HOME/.local/share/icons"; APPS="$HOME/.local/share/applications"
mkdir -p "$ICONDIR" "$APPS"
"$VENV/bin/python" "$HERE/assets/make_icon.py" "$ICONDIR/mediaforge.png" || true
cat > "$APPS/mediaforge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=MediaForge
GenericName=Media Workshop
Comment=Subtitles, video, downloads, dedupe, library organiser
Exec=$VENV/bin/python $HERE/run.py
Path=$HERE
Icon=$ICONDIR/mediaforge.png
Terminal=false
Categories=AudioVideo;Video;Utility;
Keywords=subtitle;hardbake;ffmpeg;anime;organize;manga;translate;
StartupWMClass=MediaForge
EOF
update-desktop-database "$APPS" 2>/dev/null || true

echo
echo "==> Done.  Search 'MediaForge' in your app menu, or:"
echo "    $VENV/bin/python $HERE/run.py"
