#!/usr/bin/env bash
# Browser checks for the shared full-screen control and the hub sidebar.
#
#   tests/browser/run.sh
#
# Every line of output should start with PASS. A block that reports nothing is
# reported as a failure rather than passing silently, which is a mistake this
# runner made once already.
#
# There is no headless browser on this machine except Chrome through its
# Flatpak, and `grim` cannot photograph a GNOME session (no wlr-screencopy),
# so this is the route. --virtual-time-budget is what gets past the async boot
# these pages do; a capture at the load event sees an empty page.
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
# --no-documents-portal: with the document portal not mounted, bwrap refuses
# to start Chrome at all ("Can't find source path /run/user/1000/doc/by-app").
CHROME=(flatpak run --no-documents-portal --share=network --filesystem="$HERE"
  --command=/app/extra/google-chrome com.google.Chrome
  --headless=new --disable-gpu --no-sandbox --virtual-time-budget=6000 --dump-dom)

failures=0

# Pull the PASS/FAIL lines out of a dumped page, and treat an empty block as a
# failure: a 404 or a script error otherwise looks exactly like success.
report() {
  local name="$1" dump="$2" lines
  echo "--- $name"
  lines="$(printf '%s' "$dump" | sed -n '/<pre id=/,/<\/pre>/p' \
            | grep -o "^\(PASS\|FAIL\) :: .*" | sed 's/&lt;/</g; s/&amp;/\&/g')"
  if [ -z "$lines" ]; then
    echo "FAIL :: $name reported nothing at all (page did not load, or its script threw)"
    failures=$((failures + 1))
    return
  fi
  echo "$lines"
  failures=$((failures + $(printf '%s\n' "$lines" | grep -c '^FAIL')))
}

# The two ForgeChrome pages load /shared/forge_chrome.js over http, exactly as
# an app does, so they need a server rooted where that path resolves. The port
# is picked free: a stale server from an earlier run would otherwise serve its
# own directory and 404 everything here.
tmp="$(mktemp -d)"
PORT="$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')"
cp "$HERE"/forge_chrome.html "$HERE"/forge_chrome_injected.html "$HERE"/forge_chrome_embedded.html "$HERE"/forge_chrome_child.html "$HERE"/forge_chrome_child_plain.html "$tmp"/
cp "$HERE"/forge_media_parent.html "$HERE"/forge_media_child.html "$tmp"/
# Draggable, resizable cards (shared/forge_panels.js, used by AI Studio).
cp "$HERE"/forge_panels.html "$tmp"/
# 30 s of quiet tone for forge_media_parent (8 kHz, 8-bit mono, ~240 KB)
python3 -c "import wave,math,sys; w=wave.open(sys.argv[1],'wb'); w.setnchannels(1); w.setsampwidth(1); w.setframerate(8000); w.writeframes(bytes(128+int(3*math.sin(i/4)) for i in range(240000))); w.close()" "$tmp/tone.wav"
ln -s /home/ejb/Forge/shared "$tmp/shared"
(cd "$tmp" && exec python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1) &
server=$!
# Copies of the real hub sit in $HERE and load ../shared/forge_particles.js;
# the sandboxed Chrome only sees $HERE, so that script goes beside them.
mkdir -p "$HERE/shared" && cp "$HERE/../../shared/forge_particles.js" "$HERE/../../shared/forge_visual.js" "$HERE/../../shared/forge_widgets.js" "$HERE/../../shared/forge_widgets.css" "$HERE/../../shared/forge_framecap.js" "$HERE/../../shared/forge_power.js" "$HERE/../../shared/forge_depth.js" "$HERE/../../shared/forge_glass.js" "$HERE/../../shared/forge_icons.js" "$HERE/shared/" && cp -r "$HERE/../../shared/glass" "$HERE/shared/"
trap 'kill "$server" 2>/dev/null; rm -rf "$tmp" "$HERE/shared"' EXIT

ready=0
for _ in $(seq 50); do
  if curl -sf -o /dev/null "http://127.0.0.1:$PORT/forge_chrome.html"; then ready=1; break; fi
  sleep 0.2
done
if [ "$ready" != 1 ]; then
  echo "FAIL :: the test server never came up on 127.0.0.1:$PORT"
  exit 1
fi

for page in forge_chrome forge_chrome_injected forge_chrome_embedded; do
  report "$page" "$("${CHROME[@]}" "http://127.0.0.1:$PORT/$page.html" 2>/dev/null)"
done
report forge_media "$("${CHROME[@]}" --autoplay-policy=no-user-gesture-required "http://127.0.0.1:$PORT/forge_media_parent.html" 2>/dev/null)"
report forge_panels "$("${CHROME[@]}" "http://127.0.0.1:$PORT/forge_panels.html" 2>/dev/null)"

# The hub shell runs from file://, as it does for real.
report hub_adds_a_tool "$("${CHROME[@]}" "file://$HERE/hub_adds_a_tool.html" 2>/dev/null)"

# The REAL hub/index.html, with fixture status.js and theme.js beside it and
# the harness appended. Built inside $HERE because the Flatpak browser can
# only read that folder.
hub_copy="$HERE/.hub_immersive"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_immersive_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_immersive "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

# The same real hub with a group: one Pixel games tile, the chooser inside it,
# and its games still opening as their own windows.
hub_copy="$HERE/.hub_groups"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_groups_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_groups_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_groups "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

# Settings > Icons (2026-10-07): the real hub with every real app, switched
# New -> Classic -> New live; no repeats in either style, tooltips survive.
hub_copy="$HERE/.hub_icons"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_icon_style_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/../../hub/status.js" "$hub_copy/status.js"
{ cat "$HERE/hub_immersive_theme.js"; printf '\nFORGE_THEME.app_folders = {"tools": {"label": "Tools", "members": ["board", "calendar"]}};\n'; } > "$hub_copy/theme.js"
report hub_icon_style "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

# The organised home screen: sections, chips, recent row, numbers only for
# opened apps, particle kinds.
hub_copy="$HERE/.hub_sections"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_sections_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_sections_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_sections "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

# Background music and the visualiser's system-audio source: a fake forge.py
# message channel, levels pushed as forge_music.py would, the note button's
# panel and "add from a YouTube link".
hub_copy="$HERE/.hub_music"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_music_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_music "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

hub_copy="$HERE/.hub_media"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_media_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_media "$("${CHROME[@]}" "file://$hub_copy/index.html" 2>/dev/null)"
rm -rf "$hub_copy"

# Offline audio rendering never finishes on Chrome's virtual clock, and
# --timeout dumps at page load, so this one runs in off-screen WebKit (the
# engine Forge itself uses) through tests/page_probe.py.
hub_copy="$HERE/.hub_level"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_level_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_level "<pre id=results>$(timeout 60 /usr/bin/python3 "$HERE/../page_probe.py" "file://$hub_copy/index.html" "" \
  "(document.getElementById('results') || {}).textContent || 'no results'" 6 "$hub_copy/shot.png" 2>/dev/null)</pre>"
rm -rf "$hub_copy"

# App size: window zoom through forge.py, and no sideways scroll at the CSS
# widths 1400 and 390 window pixels become at 100, 125 and 150%.
# Served from the temp root, where shared/ sits beside it as it does in Forge
# (the hub loads ../shared/forge_textsize.js).
hub_copy="$tmp/hub"
mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_scale_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
cp "$HERE/hub_scale_narrow.html" "$hub_copy/"
for size in 1400,900 1120,720 933,600; do
  report "hub_scale $size" "$("${CHROME[@]}" --window-size="$size" "http://127.0.0.1:$PORT/hub/index.html" 2>/dev/null)"
done
report "hub_scale 390/312/260" "$("${CHROME[@]}" "http://127.0.0.1:$PORT/hub/hub_scale_narrow.html" 2>/dev/null)"

# The bar's Full screen and Close for the open app.
mkdir -p "$tmp/hub_bar"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_bar_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_bar/index.html"
cp "$HERE/hub_immersive_status.js" "$tmp/hub_bar/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_bar/theme.js"
report hub_bar "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_bar/index.html" 2>/dev/null)"

# Thirty open apps: the icons scroll in their strip and the tray stays on the
# bar (Emerson, 2026-10-07). 500 px is as narrow as headless Chrome goes.
mkdir -p "$tmp/hub_bar_overflow"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_bar_overflow_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_bar_overflow/index.html"
cp "$HERE/hub_bar_many_status.js" "$tmp/hub_bar_overflow/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_bar_overflow/theme.js"
for size in 1400,900 800,600 500,700; do
  report "hub_bar_overflow $size" "$("${CHROME[@]}" --virtual-time-budget=30000 --window-size="$size" "http://127.0.0.1:$PORT/hub_bar_overflow/index.html" 2>/dev/null)"
done

mkdir -p "$tmp/hub_polish"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_polish_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_polish/index.html"
cp "$HERE/hub_polish_status.js" "$tmp/hub_polish/status.js"
cp -r "$HERE/../../hub/looks" "$tmp/hub_polish/looks"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_polish/theme.js"
report hub_polish "$("${CHROME[@]}" --virtual-time-budget=12000 --window-size=1400,900 "http://127.0.0.1:$PORT/hub_polish/index.html" 2>/dev/null)"

# Native web views go away with the page that made them (close, reload).
mkdir -p "$tmp/hub_views"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_views_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_views/index.html"
cp "$HERE/hub_immersive_status.js" "$tmp/hub_views/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_views/theme.js"
report hub_views "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_views/index.html" 2>/dev/null)"

# Zen mode (A14): Alt+Z hides the bar, tiles and dock; Esc leaves.
mkdir -p "$tmp/hub_zen"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_zen_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_zen/index.html"
cp "$HERE/hub_immersive_status.js" "$tmp/hub_zen/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_zen/theme.js"
report hub_zen "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_zen/index.html" 2>/dev/null)"

# B40: background mode's entrance and the Alt+V pulse.
mkdir -p "$tmp/hub_pulse"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_pulse_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_pulse/index.html"
cp "$HERE/hub_immersive_status.js" "$tmp/hub_pulse/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_pulse/theme.js"
report hub_pulse "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_pulse/index.html" 2>/dev/null)"

# S21: Alt+Space's app search.
mkdir -p "$tmp/hub_ov_search"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_overview_search_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_ov_search/index.html"
cp "$HERE/hub_immersive_status.js" "$tmp/hub_ov_search/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_ov_search/theme.js"
report hub_ov_search "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_ov_search/index.html" 2>/dev/null)"

# Folders: drag an app onto another (forty-app fixture, two sections).
mkdir -p "$tmp/hub_folders"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_folders_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_folders/index.html"
cp "$HERE/hub_polish_status.js" "$tmp/hub_folders/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_folders/theme.js"
cp -r "$HERE/../../hub/looks" "$tmp/hub_folders/looks"
report hub_folders "$("${CHROME[@]}" --virtual-time-budget=8000 --window-size=1400,900 "http://127.0.0.1:$PORT/hub_folders/index.html" 2>/dev/null)"

mkdir -p "$tmp/hub_music_fix"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_music_fix_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_music_fix/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_music_fix/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_music_fix/theme.js"
report hub_music_fix "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_music_fix/index.html" 2>/dev/null)"

mkdir -p "$tmp/hub_popup_blur"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_popup_blur_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_popup_blur/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_popup_blur/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_popup_blur/theme.js"
report hub_popup_blur "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_popup_blur/index.html" 2>/dev/null)"

# Offline audio never finishes on Chrome's virtual clock, so the skip fade
# (and the Folder button) is checked in off-screen WebKit like hub_level.
hub_copy="$HERE/.hub_music_skip"
rm -rf "$hub_copy" && mkdir -p "$hub_copy"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_music_skip_harness.js"; printf '</script>\n'; } \
  > "$hub_copy/index.html"
cp "$HERE/hub_immersive_status.js" "$hub_copy/status.js"
cp "$HERE/hub_immersive_theme.js" "$hub_copy/theme.js"
report hub_music_skip "<pre id=results>$(timeout 60 /usr/bin/python3 "$HERE/../page_probe.py" "file://$hub_copy/index.html" "" \
  "(document.getElementById('results') || {}).textContent || 'no results'" 6 "$hub_copy/shot.png" 2>/dev/null)</pre>"
rm -rf "$hub_copy"

mkdir -p "$tmp/hub_effects"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_effects_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_effects/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_effects/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_effects/theme.js"
report hub_effects "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_effects/index.html" 2>/dev/null)"

# Home widgets and Relax (B20): the real hub with the widget checks appended
mkdir -p "$tmp/hub_widgets"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_widgets_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_widgets/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_widgets/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_widgets/theme.js"
report hub_widgets "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_widgets/index.html" 2>/dev/null)"

# The S25 widgets: weather (stubbed), media player, calendar, disk, network,
# Jan, alarms, visualiser, the ⚙ options and the store hook.
mkdir -p "$tmp/hub_widgets2"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_widgets2_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_widgets2/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_widgets2/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_widgets2/theme.js"
report hub_widgets2 "$("${CHROME[@]}" --window-size=1400,1000 "http://127.0.0.1:$PORT/hub_widgets2/index.html" 2>/dev/null)"

# Effect keys, the Alt+V controls and the visuals popup (S25): the real hub,
# with the popup's rows made from shared/forge_theme.py's own table.
mkdir -p "$tmp/hub_fx"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_fx_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_fx/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_fx/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_fx/theme.js"
python3 -c "import json, sys; sys.path.insert(0, '/home/ejb/Forge/shared'); import forge_theme as t; print(json.dumps(t.popup_rows(t.VISUALS_POPUP)))" > "$tmp/hub_fx/fx_rows.json"
report hub_fx "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_fx/index.html" 2>/dev/null)"

# Easing off and the Alt+V fixes (Emerson, 2026-09-29): GPU load and a flat
# battery step the effects down; Alt+V runs at full rate; its keys survive a
# focus left in the search box or the closed popup; a dropdown keeps the
# visuals popup open.
mkdir -p "$tmp/hub_ease"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_ease_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_ease/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_ease/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_ease/theme.js"
cp "$tmp/hub_fx/fx_rows.json" "$tmp/hub_ease/fx_rows.json"
report hub_ease "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_ease/index.html" 2>/dev/null)"

# Glass kinds (S26): Flat, Frosted and Liquid on the real hub, from
# shared/glass/ through shared/forge_glass.js, with the strength slider.
mkdir -p "$tmp/hub_glass"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_glass_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_glass/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_glass/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_glass/theme.js"
report hub_glass "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_glass/index.html" 2>/dev/null)"

# 2.5D wallpapers (S23): the subject layer over the particles, its parallax
# and its beat, on the real hub (shared/forge_layers.py makes the files).
mkdir -p "$tmp/hub_layers"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_layers_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_layers/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_layers/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_layers/theme.js"
report hub_layers "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_layers/index.html" 2>/dev/null)"

# Settings sections (A7): the real Settings page with fixed /api answers
# built from shared/forge_theme.py's own table, so a new setting is covered.
mkdir -p "$tmp/settings" "$tmp/api"
cp "$HERE"/../../apps/settings/static/app.css "$HERE"/../../apps/settings/static/app.js "$tmp/settings/"
{ cat "$HERE/../../apps/settings/static/index.html"; printf '<script>\n'; cat "$HERE/settings_sections_harness.js"; printf '</script>\n'; } \
  > "$tmp/settings/index.html"
python3 - "$tmp/api" <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "/home/ejb/Forge/shared")
import forge_theme as t
api = Path(sys.argv[1])
settings = t.load(api / "none.json")
theme = {**settings, "accent": t.FALLBACK_ACCENT, "on_accent": "#0b1220", "swatches": ["#6ea8fe", "#e0a060"],
         "wallpaper_name": "", "follows_desktop": True, "size_presets": t.size_presets(settings)}
(api / "settings").write_text(json.dumps({"settings": settings, "fields": t.describe(), "theme": theme,
                                          "config": "(test)", "cache": "(test)"}))
(api / "wallpapers").write_text(json.dumps({"wallpapers": [], "folder": "(test)"}))
(api / "favourites").write_text(json.dumps({"favourites": []}))
PY
report settings_sections "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/settings/index.html" 2>/dev/null)"

# Desktop particles (S18): the real page with its own settings over the home
# screen's, read from a test hub/theme.js beside it.
mkdir -p "$tmp/desktop" "$tmp/hub"
cp "$HERE/../../desktop/forge_desktop.js" "$tmp/desktop/"
{ cat "$HERE/../../desktop/particles.html"; printf '<script>\n'; cat "$HERE/desktop_particles_harness.js"; printf '</script>\n'; } \
  > "$tmp/desktop/particles.html"
printf 'window.FORGE_THEME = %s;\n' '{"animations": true, "particles": "snow", "particle_amount": 2, "desktop_particles": true, "desktop_particle_kind": "same", "desktop_particle_amount": 0.5, "desktop_particle_fps": 20, "max_fps": 60}' \
  > "$tmp/hub/theme.js"
report desktop_particles "$("${CHROME[@]}" --window-size=1200,800 "http://127.0.0.1:$PORT/desktop/particles.html" 2>/dev/null)"

# The desktop's widgets and visualiser (S25): the real page, with
# desktop/particles.py stood in for by a message handler in the harness.
mkdir -p "$tmp/desktop_w/desktop" "$tmp/desktop_w/hub"
ln -s /home/ejb/Forge/shared "$tmp/desktop_w/shared"
cp "$HERE/../../desktop/forge_desktop.js" "$tmp/desktop_w/desktop/"
{ cat "$HERE/../../desktop/particles.html"; printf '<script>\n'; cat "$HERE/desktop_widgets_harness.js"; printf '</script>\n'; } \
  > "$tmp/desktop_w/desktop/particles.html"
printf 'window.FORGE_THEME = %s;\n' '{"animations": true, "particles": "snow", "desktop_particles": true, "desktop_widgets": true, "desktop_visualiser": "bars", "desktop_particle_fps": 30, "max_fps": 60, "accent": "#8ab4ff"}' \
  > "$tmp/desktop_w/hub/theme.js"
report desktop_widgets "$("${CHROME[@]}" --window-size=1600,900 "http://127.0.0.1:$PORT/desktop_w/desktop/particles.html" 2>/dev/null)"

# White on white (QUICKSTART item 2, 2026-10-07): every shown text on the
# real hub and desktop page keeps 3:1 against what is behind it, on a dark
# and a bright wallpaper, in each look and glass kind (contrast_sweep.js).
mkdir -p "$tmp/hub_contrast"
ln -s /home/ejb/Forge/hub/looks "$tmp/hub_contrast/looks"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/contrast_sweep.js" "$HERE/hub_contrast_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_contrast/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_contrast/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_contrast/theme.js"
report hub_contrast "$("${CHROME[@]}" --virtual-time-budget=30000 --window-size=1400,900 "http://127.0.0.1:$PORT/hub_contrast/index.html" 2>/dev/null)"
mkdir -p "$tmp/desktop_c/desktop" "$tmp/desktop_c/hub"
ln -s /home/ejb/Forge/shared "$tmp/desktop_c/shared"
cp "$HERE/../../desktop/forge_desktop.js" "$tmp/desktop_c/desktop/"
{ cat "$HERE/../../desktop/particles.html"; printf '<script>\n'; cat "$HERE/contrast_sweep.js" "$HERE/desktop_contrast_harness.js"; printf '</script>\n'; } \
  > "$tmp/desktop_c/desktop/particles.html"
printf 'window.FORGE_THEME = %s;\n' '{"animations": false, "particles": "off", "desktop_particles": false, "desktop_widgets": true, "accent": "#8ab4ff"}' \
  > "$tmp/desktop_c/hub/theme.js"
report desktop_contrast "$("${CHROME[@]}" --virtual-time-budget=20000 --window-size=1600,900 "http://127.0.0.1:$PORT/desktop_c/desktop/particles.html" 2>/dev/null)"

# Frame cap on battery (#199): the real hub drops to battery_fps unplugged.
mkdir -p "$tmp/hub_battery"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'; cat "$HERE/hub_battery_fps_harness.js"; printf '</script>\n'; } \
  > "$tmp/hub_battery/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_battery/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_battery/theme.js"
report hub_battery_fps "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_battery/index.html" 2>/dev/null)"

# Speed and detail (2026-09-27): the hub applies every battery twin from the
# theme's power_pairs and tells forge.py what applies now.
mkdir -p "$tmp/hub_power"
{ cat "$HERE/../../hub/index.html"; printf '<script>\n'
  python3 -c "import sys, json; sys.path.insert(0, '/home/ejb/Forge/shared'); import forge_theme as t; print('window.TEST_PAIRS = ' + json.dumps({k: list(v) for k, v in t.POWER_PAIRS.items()}) + ';')"
  cat "$HERE/hub_power_harness.js"; printf '</script>\n'; } > "$tmp/hub_power/index.html"
cp "$HERE/hub_sections_status.js" "$tmp/hub_power/status.js"
cp "$HERE/hub_immersive_theme.js" "$tmp/hub_power/theme.js"
report hub_power "$("${CHROME[@]}" --window-size=1400,900 "http://127.0.0.1:$PORT/hub_power/index.html" 2>/dev/null)"

# Claude panel (#185): streamed text is drawn in batches, not per word.
cp "$HERE/claude_stream.html" "$HERE/../../apps/claude/static/claude_common.js" "$HERE/../../shared/forge_convo.js" "$tmp"/
report claude_stream "$("${CHROME[@]}" "http://127.0.0.1:$PORT/claude_stream.html" 2>/dev/null)"
cp "$HERE/claude_pic_tag.html" "$tmp"/
report claude_pic_tag "$("${CHROME[@]}" "http://127.0.0.1:$PORT/claude_pic_tag.html" 2>/dev/null)"

echo
if [ "$failures" = 0 ]; then echo "ALL PASS"; else echo "$failures FAILED"; fi
exit $((failures > 0))
