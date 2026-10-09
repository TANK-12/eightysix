"""The desktop's widgets and visualiser (S25): desktop/particles.py runs for
any of the three On the desktop switches, keeps the widget layout in its own
file, wakes for alarms, and only takes clicks where the page says."""

import importlib.util
import json
import os
import signal
import sys
from datetime import datetime
from pathlib import Path

FORGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FORGE / "shared"))
spec = importlib.util.spec_from_file_location(
    "particles", FORGE / "desktop" / "particles.py"
)
assert spec and spec.loader
particles = importlib.util.module_from_spec(spec)
spec.loader.exec_module(particles)

import forge_theme  # noqa: E402


def test_any_of_the_three_switches_starts_it():
    assert not particles.wanted({})
    assert not particles.wanted(
        {"desktop_particles": False, "desktop_visualiser": "off"}
    )
    assert particles.wanted({"desktop_particles": True})
    assert particles.wanted({"desktop_widgets": True})
    assert particles.wanted({"desktop_visualiser": "terrain"})


def test_the_extension_starts_it_by_the_same_rule():
    js = (
        FORGE / "desktop/gnome-extension/forge-desktop-particles@forge/extension.js"
    ).read_text()
    for key in ("desktop_particles", "desktop_widgets", "desktop_visualiser"):
        assert key in js


def test_the_layout_is_kept_whole_in_its_own_file(tmp_path):
    path = tmp_path / "forge" / "desktop-widgets.json"
    assert particles.load_layout(path) is None
    layout = {"pages": [{"name": "Desk", "items": [{"kind": "clock"}]}], "page": 0}
    assert particles.save_layout(layout, path)
    assert particles.load_layout(path) == layout
    assert not particles.save_layout({"nope": 1}, path)
    assert not particles.save_layout("pages", path)
    assert particles.load_layout(path) == layout
    path.write_text("{broken")
    assert particles.load_layout(path) is None
    assert not list(path.parent.glob(".*.tmp"))


def test_it_wakes_for_an_alarm_or_a_timer_that_is_due():
    now = datetime(2026, 9, 28, 7, 30, 20)
    alarm = {"t": "07:30", "on": True}
    layout = {"pages": [{"items": [{"kind": "alarms", "o": {"alarms": [alarm]}}]}]}
    assert particles.alarm_due(layout, now)
    assert not particles.alarm_due(layout, datetime(2026, 9, 28, 7, 31))
    alarm["last"] = "2026-09-28"  # it rang already today
    assert not particles.alarm_due(layout, now)
    alarm["last"], alarm["on"] = "", False
    assert not particles.alarm_due(layout, now)
    ms = now.timestamp() * 1000
    timers = {"kind": "alarms", "o": {"timers": [{"end": ms + 60000}]}}
    layout = {"pages": [{"items": [timers]}]}
    assert not particles.alarm_due(layout, now)
    timers["o"]["timers"][0]["end"] = ms - 1
    assert particles.alarm_due(layout, now)
    assert not particles.alarm_due(None, now)
    assert not particles.alarm_due(
        {"pages": [{"items": ["junk", {"kind": "clock"}]}]}, now
    )


def test_click_areas_are_whole_pixels_inside_the_window():
    rects = [
        [10.4, 20, 100, 50],
        [1900, 1000, 100, 200],
        [-5, -5, 20, 20],
        "x",
        [1, 2, 3],
    ]
    assert particles.clean_rects(rects, 1920, 1080) == [
        (10, 20, 100, 50),
        (1900, 1000, 20, 80),
        (0, 0, 20, 20),
    ]
    assert particles.clean_rects(None, 1920, 1080) == []
    assert particles.clean_rects([[0, 0, 0, 10]], 100, 100) == []


def test_edit_asks_the_running_one(tmp_path, monkeypatch, capsys):
    pid_file, edit_file = tmp_path / "pid", tmp_path / "edit"
    assert particles.ask_to_edit(pid_file, edit_file) == 1
    assert "not running" in capsys.readouterr().err
    probed = []
    monkeypatch.setattr(os, "kill", lambda pid, sig: probed.append((pid, sig)))
    pid_file.write_text("4242")
    assert particles.ask_to_edit(pid_file, edit_file) == 0
    assert probed == [(4242, 0)]  # only asks whether it is alive
    assert edit_file.exists()  # the running one watches this file


def test_no_signal_that_webkit_needs():
    """S26: the desktop script took SIGUSR1 for --edit. WebKit's JavaScript
    engine on Linux stops threads with SIGUSR1 while it collects garbage, so
    its first collection in the window's process deadlocked: the window froze
    and one core ran at 100% (seen live 2026-09-28, 14 minutes of it)."""
    src = (FORGE / "desktop" / "particles.py").read_text()
    ext = (
        FORGE / "desktop/gnome-extension/forge-desktop-particles@forge/extension.js"
    ).read_text()
    for name in ("SIGUSR1", "SIGUSR2"):
        assert f"signal.{name}" not in src
    assert "send_signal(10)" not in ext and "send_signal(12)" not in ext


def test_the_desktop_settings_exist_with_safe_defaults():
    s = forge_theme.SETTINGS
    group = forge_theme.DESKTOP_PARTICLES
    for key in (
        "desktop_widgets",
        "desktop_edit_button",
        "desktop_widget_scale",
        "desktop_visualiser",
        "desktop_visualiser_size",
        "desktop_visualiser_fps",
    ):
        assert s[key]["group"] == group, key
    assert s["desktop_widgets"]["default"] is False
    assert s["desktop_visualiser"]["default"] == "off"
    assert set(s["desktop_visualiser"]["choices"]) == {
        "off",
        *forge_theme.VISUALISER_LABELS,
    }
    theme = forge_theme.theme(forge_theme.load(Path("/nonexistent/settings.json")))
    assert particles.wanted(theme) is False


def test_the_page_loads_the_shared_widgets_and_visualiser():
    page = (FORGE / "desktop" / "particles.html").read_text()
    for src in (
        "../shared/forge_visual.js",
        "../shared/forge_widgets.js",
        "forge_desktop.js",
    ):
        assert f'<script src="{src}"></script>' in page
    assert 'id="widgets"' in page and 'id="visual"' in page and 'id="dk-edit"' in page
    assert json.loads('{"ok": true}')["ok"]


# --- S24: one desktop window per screen --------------------------------------


def test_each_screen_has_a_title_the_extension_reads_back():
    assert particles.window_title(0) == "forge-desktop-particles"  # as before
    for n in range(4):
        assert particles.screen_of(particles.window_title(n)) == n
    assert particles.screen_of("forge-desktop-particles #x") is None
    assert particles.screen_of("Firefox") is None


def test_the_extension_parses_titles_the_same_way():
    """extension.js matches /^forge-desktop-particles(?: #(\\d+))?$/."""
    src = (
        FORGE / "desktop/gnome-extension/forge-desktop-particles@forge/extension.js"
    ).read_text()
    assert "/^forge-desktop-particles(?: #(\\d+))?$/" in src
    assert particles.TITLE == "forge-desktop-particles"


def test_each_screen_keeps_its_own_layout(tmp_path):
    base = tmp_path / "desktop-widgets.json"
    assert particles.layout_path(0, base) == base  # the first file stays
    assert particles.layout_path(2, base) == tmp_path / "desktop-widgets-2.json"
    one = {"pages": [{"name": "Main", "items": []}]}
    two = {"pages": [{"name": "Side", "items": []}]}
    assert particles.save_layout(one, particles.layout_path(0, base))
    assert particles.save_layout(two, particles.layout_path(1, base))
    assert particles.load_layout(particles.layout_path(0, base)) == one
    assert particles.load_layout(particles.layout_path(1, base)) == two


def test_a_window_per_monitor_unless_the_setting_is_off():
    assert particles.screen_count({}, 3) == 3
    assert particles.screen_count({"desktop_all_screens": True}, 2) == 2
    assert particles.screen_count({"desktop_all_screens": False}, 3) == 1
    assert particles.screen_count({}, 0) == 1  # no monitor known: still one


def test_the_every_screen_setting_is_in_the_desktop_group():
    spec = forge_theme.SETTINGS["desktop_all_screens"]
    assert spec["default"] is True and spec["group"] == forge_theme.DESKTOP_PARTICLES


def test_the_desktop_settings_button_opens_a_page_that_needs_no_forge():
    assert particles.settings_command("gnome-extension") == [
        "gnome-extensions",
        "prefs",
        "forge-desktop-particles@forge",
    ]
    assert particles.settings_command("layer-shell")[-2:] == ["--app", "settings"]


def test_hyprland_waits_for_its_own_switch():
    """Emerson 2026-09-28: the desktop on GNOME and Hyprland, but off by
    default on Hyprland. GNOME's rule (and the extension's) is unchanged."""
    on = {"desktop_particles": True}
    assert particles.wanted(on, "gnome-extension")
    assert not particles.wanted(on, "layer-shell")
    assert particles.wanted({**on, "desktop_on_hyprland": True}, "layer-shell")
    assert not particles.wanted({"desktop_on_hyprland": True}, "layer-shell")
    spec = forge_theme.SETTINGS["desktop_on_hyprland"]
    assert spec["default"] is False
    assert spec["group"] == forge_theme.DESKTOP_PARTICLES


def test_the_hyprland_watcher_starts_it_only_while_wanted():
    themes = iter(
        [
            {"desktop_particles": True},  # on, but Hyprland's switch is off
            {"desktop_particles": True, "desktop_on_hyprland": True},
            {"desktop_particles": True, "desktop_on_hyprland": True},
        ]
    )
    lives = iter([True, True, True, False])
    started, slept = [], []
    assert (
        particles.watch(
            "layer-shell",
            alive=lambda: next(lives),
            read=lambda: next(themes),
            start=lambda: started.append(1),
            sleep=slept.append,
        )
        == 0
    )
    # two starts; each child quit at once, so each is followed by a long rest
    assert started == [1, 1]
    assert slept == [2.0, particles.WATCH_BACKOFF, 2.0, particles.WATCH_BACKOFF, 2.0]


def test_the_watcher_ends_with_its_session(tmp_path):
    env = {"XDG_RUNTIME_DIR": str(tmp_path), "WAYLAND_DISPLAY": "wayland-7"}
    assert not particles.session_alive(env)
    (tmp_path / "wayland-7").touch()
    assert particles.session_alive(env)
    env["HYPRLAND_INSTANCE_SIGNATURE"] = "abc"
    assert not particles.session_alive(env)  # that Hyprland is gone
    (tmp_path / "hypr" / "abc").mkdir(parents=True)
    assert particles.session_alive(env)


def test_the_overview_keeps_the_desktop_layer():
    """Emerson 2026-09-28: Super's overview should not make the widgets,
    particles and visualiser vanish."""
    spec = forge_theme.SETTINGS["desktop_in_overview"]
    assert spec["default"] is True
    assert spec["group"] == forge_theme.DESKTOP_PARTICLES
    js = (
        FORGE / "desktop/gnome-extension/forge-desktop-particles@forge/extension.js"
    ).read_text()
    assert "desktop_in_overview" in js and "WorkspaceBackground" in js


def test_the_overview_copy_does_not_stretch_the_card():
    """Emerson 2026-09-29: the desktop in Super's overview was squished. A
    plain Clutter.Clone asks for the monitor's width, which widens the card."""
    js = (
        FORGE / "desktop/gnome-extension/forge-desktop-particles@forge/extension.js"
    ).read_text()
    assert "new Clutter.Clone(" not in js
    assert "class CardClone extends Clutter.Clone" in js
    assert "vfunc_get_preferred_width" in js and "vfunc_get_preferred_height" in js


def test_the_visualiser_rests_through_silence():
    """Emerson 2026-09-29: the visualiser popped in and out. cava sends one
    silent frame, so a stale silent frame must still be drawn."""
    js = (FORGE / "desktop/forge_desktop.js").read_text()
    body = js[js.index("    levels() {") :]
    body = body[: body.index("\n    },") + 7]
    # levels() eases through ForgeVisual.follow (task 56)
    visual = json.dumps(str(FORGE / "shared/forge_visual.js"))
    run = f"""
    global.window = global; require({visual});
    let now = 0; Date.now = () => now;
    const D = {{ raw: null, smooth: null, levelsAt: 0, wantLevelsAt: 0, askedLevels: 1e12,
      visFps() {{ return 30; }}, {body} }};
    const out = [];
    now = 1000; D.raw = [0, 0, 0]; D.levelsAt = now; now = 10000; out.push(D.levels() !== null);
    D.raw = [5, 9, 2]; D.levelsAt = now; now = 20000; out.push(D.levels() === null);
    console.log(JSON.stringify(out));
    """
    import subprocess

    res = subprocess.run(["node", "-e", run], capture_output=True, text=True)
    assert res.returncode == 0, res.stderr
    assert json.loads(res.stdout) == [True, True]
