#!/usr/bin/env bash
# One-time setup for PulseForge.
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="$(command -v python3)"

echo "==> PulseForge setup in $HERE"

# --system-site-packages: reuse the system numpy / Pillow / pycairo rather than
# re-downloading them (the machine is short on disk). Only the web framework is
# installed into the venv.
[ -d "$VENV" ] || "$PY" -m venv --system-site-packages "$VENV"

"$VENV/bin/pip" -q install --upgrade pip
"$VENV/bin/pip" -q install fastapi "uvicorn[standard]" python-multipart
# v8: the AMV studio. scipy solves the shot assignment (Hungarian algorithm);
# opencv-headless measures what is in each clip. Headless is deliberate -- the
# GUI build pulls in Qt for no reason here.
"$VENV/bin/pip" -q install scipy opencv-python-headless
"$VENV/bin/pip" -q install pytest || echo "   (pytest failed -- tests won't run)"

MISS=""
command -v ffmpeg  >/dev/null || MISS="$MISS ffmpeg"
command -v ffprobe >/dev/null || MISS="$MISS ffmpeg"
[ -n "$MISS" ] && echo "==> !! install ffmpeg:  sudo pacman -S ffmpeg"

echo "==> verifying"
"$VENV/bin/python" - <<'PY'
import numpy, PIL, fastapi, uvicorn
print("   numpy", numpy.__version__, "| Pillow", PIL.__version__,
      "| fastapi", fastapi.__version__)
try:
    import cv2, scipy
    print("   opencv", cv2.__version__, "| scipy", scipy.__version__)
except Exception as e:
    print("   !! the AMV studio needs opencv + scipy:", e)
try:
    import cairo  # noqa
    print("   pycairo: ok")
except Exception:
    print("   pycairo: MISSING (optional, scenes fall back to Pillow)")
from pulseforge.scenes import scenes_as_list
print("   scenes:", ", ".join(s["id"] for s in scenes_as_list()))
PY

echo "==> icon + desktop entry"
ICONDIR="$HOME/.local/share/icons"; APPS="$HOME/.local/share/applications"
mkdir -p "$ICONDIR" "$APPS"
"$VENV/bin/python" "$HERE/assets/make_icon.py" "$ICONDIR/pulseforge.png" || true
cat > "$APPS/pulseforge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PulseForge
GenericName=Music Video Studio
Comment=Music-reactive videos, visualisers and beat-cut montages
Exec=$VENV/bin/python $HERE/run.py
Path=$HERE
Icon=$ICONDIR/pulseforge.png
Terminal=false
NoDisplay=true
Categories=AudioVideo;Video;
StartupWMClass=PulseForge
EOF
update-desktop-database "$APPS" 2>/dev/null || true

echo
echo "==> Done.  Launched from Forge, or standalone:"
echo "    $VENV/bin/python $HERE/run.py"
