// Appended to a copy of the REAL hub/index.html by run.sh. Zen mode (A14):
// Alt+Z (forge.py sends forgeKey("zen")) hides the bar, tiles and dock and
// shows the clock, intention and focus timer; Esc or Alt+Z leaves.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const seen = (id) => parseFloat(getComputedStyle($(id)).opacity) > 0.5 && getComputedStyle($(id)).pointerEvents !== "none";
  try {
    T("zen is off at start", !Zen.on && !seen("zen") && seen("bar"));
    selectWorkspace(order[0]);
    await wait(60);
    window.forgeKey("zen");
    await wait(400);
    T("Alt+Z turns zen on", Zen.on && document.body.classList.contains("zen"));
    T("and goes home, leaving the app open behind", current === null && !!parts[order[0]].inner.querySelector("iframe"));
    T("the bar, tiles and dock are out of the way", !seen("bar") && !seen("home") && !seen("dock"));
    T("the zen screen shows", seen("zen"));
    T("with the big clock", /\d/.test($("zen-clock").textContent) && $("zen-clock").offsetHeight > 60, $("zen-clock").textContent);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true }));
    T("typing does not jump into the hidden search box", document.activeElement !== $("search"));
    Zen.setLength(15);
    T("a timer length can be picked", $("zen-timer").textContent === "15:00");
    Zen.start();
    T("the timer starts", Zen.running && $("zen-go").textContent === "Pause");
    Zen.left = 1; Zen.stop(); Zen.start();
    await wait(1600);
    T("and finishes at 00:00", !Zen.running && $("zen-timer").textContent === "00:00", $("zen-timer").textContent);
    $("zen-reset").click();
    T("Reset puts the length back", $("zen-timer").textContent === "15:00");
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wait(400);
    // Emerson (2026-09-29): Alt+B and Alt+Z take him back to the app he was in
    T("Esc leaves zen, back in the app it was started from", !Zen.on && !seen("zen") && seen("bar") && current === order[0], current);
    selectWorkspace(null);
    await wait(300);
    $("zen-btn").click();
    T("the bar's moon button enters it", Zen.on);
    window.forgeKey("zen");
    T("Alt+Z again leaves, staying home when it was started there", !Zen.on && current === null, current);
    selectWorkspace(order[0]);
    window.forgeKey("ambient");
    T("Alt+B from an app goes home into background mode", Ambient.on && current === null);
    window.forgeKey("ambient");
    T("Alt+B again goes back to that app", !Ambient.on && current === order[0], current);
    window.forgeKey("pulse");
    window.forgeKey("pulse");
    window.forgeKey("ambient");
    T("so does leaving after Alt+V", !Ambient.on && !Pulse.on && current === order[0], current);
    window.forgeKey("zen");
    window.forgeKey("ambient");
    window.forgeKey("ambient");
    T("zen, then background mode, still goes back to the app", !Ambient.on && !Zen.on && current === order[0], current);
    window.forgeKey("ambient");
    window.forgeKey("home");
    T("Alt+H leaves background mode for the home screen, not the app", !Ambient.on && current === null, current);
    selectWorkspace(order[0]);
    window.forgeKey("home");
    T("and from an app it goes home", current === null, current);
    const settingsKey = order.find((k) => (status[k] || {}).role === "settings");
    window.forgeKey("zen");
    window.forgeKey("settings");
    T("Alt+S opens Settings, leaving zen", !Zen.on && !!settingsKey && current === settingsKey, `${settingsKey} ${current}`);
    selectWorkspace(null);
    Zen.setLength(25);
    Zen.toggle(true);
    const shown = (el) => el.offsetParent !== null || getComputedStyle(el).position === "fixed" && getComputedStyle(el).display !== "none";
    T("everything shows by default", shown($("zen-clock")) && shown($("zen-intent")) && shown($("zen-timer")) && shown($("zen-lengths")));
    Object.assign(theme, { zen_clock: false, zen_intention: false, zen_timer: false, zen_effects: false });
    Zen.draw();
    T("Settings can hide the clock, intention and timer",
      !shown($("zen-clock")) && !shown($("zen-intent")) && !shown($("zen-timer")) && !shown($("zen-lengths")));
    await wait(700);
    T("and still the wallpaper effects", document.body.classList.contains("zen-still")
      && parseFloat(getComputedStyle($("particles")).opacity) === 0 && parseFloat(getComputedStyle($("visual")).opacity) === 0);
    Object.assign(theme, { zen_clock: true, zen_intention: true, zen_timer: true, zen_effects: true });
    Zen.draw();
    T("turning them back on shows them again", shown($("zen-clock")) && shown($("zen-timer")) && !document.body.classList.contains("zen-still"));
  } catch (e) {
    T("zen harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
