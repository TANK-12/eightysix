#!/usr/bin/env bash
# One-time setup for NovelForge:
#   * a dedicated venv (.venv) that can see the system packages
#     (tkinter, requests, pypdf, reportlab) and adds customtkinter,
#     EbookLib + Pillow (export & covers) and piper-tts (offline audiobooks)
#   * a desktop launcher so "NovelForge" shows up in your app search
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="$HERE/.venv"
PY="$(command -v python3)"

echo "==> NovelForge setup in $HERE"

if [ ! -d "$VENV" ]; then
  echo "==> creating venv (with system site-packages)"
  "$PY" -m venv --system-site-packages "$VENV"
fi

echo "==> installing/refreshing Python deps"
"$VENV/bin/pip" install --quiet --upgrade pip
# customtkinter is the only thing usually not on the system; the rest are
# no-ops if already provided by system site-packages.
"$VENV/bin/pip" install --quiet --upgrade customtkinter darkdetect
"$VENV/bin/pip" install --quiet requests pypdf reportlab psutil || true
# export + audiobook: EbookLib (EPUB), Pillow (covers), piper-tts (offline TTS).
# piper pulls onnxruntime, so it's the big one -- ~60 MB of wheels.
"$VENV/bin/pip" install --quiet EbookLib Pillow || true
"$VENV/bin/pip" install --quiet piper-tts || echo "    (piper-tts failed — audiobooks will be off)"
# kokoro-onnx is the realistic-voice engine; piper alone still works without it
"$VENV/bin/pip" install --quiet kokoro-onnx || echo "    (kokoro-onnx failed — only Piper voices)"

echo "==> verifying"
"$VENV/bin/python" - <<'PYEOF'
import customtkinter, requests, tkinter
try:
    import pypdf; pdf = pypdf.__version__
except Exception: pdf = "MISSING (PDF reading off)"
try:
    import reportlab; rl = reportlab.Version
except Exception: rl = "MISSING (PDF export off)"
try:
    import psutil; ps = psutil.__version__
except Exception: ps = "MISSING (RAM guard off)"
try:
    import ebooklib; eb = ".".join(str(x) for x in ebooklib.VERSION)
except Exception: eb = "MISSING (EPUB export off)"
try:
    import PIL; im = PIL.__version__
except Exception: im = "MISSING (cover art off)"
try:
    import importlib.util as _u
    tts = "ok" if _u.find_spec("piper") else "MISSING (audiobooks off)"
    kok = "ok" if _u.find_spec("kokoro_onnx") else "MISSING (only Piper voices)"
except Exception: tts = kok = "unknown"
import shutil
print(f"    customtkinter {customtkinter.__version__}")
print(f"    requests {requests.__version__}  tkinter {tkinter.TkVersion}")
print(f"    pypdf {pdf}  reportlab {rl}  psutil {ps}")
print(f"    EbookLib {eb}  Pillow {im}")
print(f"    piper-tts {tts}  kokoro-onnx {kok}")
print(f"    ffmpeg {shutil.which('ffmpeg') or 'MISSING (audiobook stitching off)'}")
PYEOF

# ---- desktop entry ----
APPS_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons"
mkdir -p "$APPS_DIR" "$ICON_DIR"

echo "==> generating icon"
"$VENV/bin/python" "$HERE/assets/make_icon.py" "$ICON_DIR/novelforge.png" || true

DESKTOP="$APPS_DIR/novelforge.desktop"
cat > "$DESKTOP" <<EOF
[Desktop Entry]
Type=Application
Name=NovelForge
GenericName=Novel Writing Studio
Comment=Write long-form novels with your local Jan.ai models
Exec=$VENV/bin/python $HERE/run.py
Path=$HERE
Icon=$ICON_DIR/novelforge.png
Terminal=false
Categories=Office;WordProcessor;Utility;
Keywords=novel;writing;ai;llm;jan;story;book;
StartupWMClass=NovelForge
EOF
chmod +x "$DESKTOP"
update-desktop-database "$APPS_DIR" 2>/dev/null || true

echo
echo "==> Done."
echo "    Launch from your app menu (search 'NovelForge'), or run:"
echo "        $VENV/bin/python $HERE/run.py"
