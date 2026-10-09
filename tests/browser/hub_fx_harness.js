// Appended to a copy of the REAL hub/index.html by run.sh. S25 (2026-09-28):
// Alt+E turns the visualiser off, then the particles, then both back; Alt+P
// and Alt+M flip one each; inside the Alt+V pulse the arrows, Shift+arrows,
// PgUp/PgDn and 1-9 change the visuals and Alt+M opens the visuals popup,
// which is built from forge_theme.py VISUALS_POPUP (fx_rows.json beside this).
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  document.head.appendChild(document.createElement("style")).textContent = "* { transition: none !important; }";
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const press = (key, opts = {}) => {
    const e = new KeyboardEvent("keydown", Object.assign({ key, bubbles: true, cancelable: true }, opts));
    document.dispatchEvent(e);
    return e;
  };
  try {
    const rows = await (await fetch("fx_rows.json")).json();
    applyTheme({ visuals_popup: rows, animations: true, visualiser: "bars", ambient_visualiser: "keep", particles: "snow",
      visualiser_shown: true, particles_shown: true, visualiser_source: "system", pulse_strength: 1, pulse_glow: true,
      particle_amount: 1, visualiser_gain: 1, fx_hud: true });
    T("the visualiser runs to start with", Visual.style === "bars", Visual.style);
    T("and the particles", Particles.level === "snow", Particles.level);

    // Alt+E: visualiser off, then particles off, then both back
    window.forgeKey("effects");
    T("Alt+E once: visualiser off, particles still on", theme.visualiser_shown === false && theme.particles_shown !== false
      && Visual.style === "off" && Particles.level === "snow", `${Visual.style} ${Particles.level}`);
    T("it says so at the top", $("fx-hud").classList.contains("show") && /Visualiser off/.test($("fx-hud").textContent), $("fx-hud").textContent);
    window.forgeKey("effects");
    T("Alt+E twice: particles off too", theme.particles_shown === false && Particles.level === "off", Particles.level);
    window.forgeKey("effects");
    T("Alt+E three times: both back", theme.visualiser_shown === true && theme.particles_shown === true
      && Visual.style === "bars" && Particles.level === "snow", `${Visual.style} ${Particles.level}`);
    T("the picked style and kind were kept", theme.visualiser === "bars" && theme.particles === "snow");
    applyTheme({ visualiser: "off" });
    window.forgeKey("effects");
    T("with no visualiser picked, Alt+E goes straight to the particles", theme.particles_shown === false, String(theme.particles_shown));
    window.forgeKey("effects");
    applyTheme({ visualiser: "bars" });

    // Alt+P and Alt+M (outside Alt+V)
    window.forgeKey("particles-toggle");
    T("Alt+P turns the particles off", theme.particles_shown === false && Particles.level === "off");
    window.forgeKey("particles-toggle");
    T("and on again", theme.particles_shown === true && Particles.level === "snow");
    window.forgeKey("visualiser-toggle");
    T("Alt+M turns the visualiser off", theme.visualiser_shown === false && Visual.style === "off", Visual.style);
    window.forgeKey("visualiser-toggle");
    T("and on again", theme.visualiser_shown === true && Visual.style === "bars", Visual.style);
    T("the popup stays shut outside Alt+V", $("fx-panel").hidden);
    await wait(400);
    const saves = sent.filter((m) => m.settings).map((m) => m.settings);
    T("each change is saved to forge.py", saves.length > 0 && "visualiser_shown" in Object.assign({}, ...saves), JSON.stringify(saves).slice(0, 120));

    // inside the Alt+V pulse
    window.forgeKey("pulse");
    T("Alt+V starts the pulse", Pulse.on && Ambient.on);
    T("with the keys shown at the top", /←\/→ visualiser/.test($("fx-hud").textContent), $("fx-hud").textContent);
    press("ArrowRight");
    T("→ picks the next visualiser", theme.visualiser === "ring" && Visual.style === "ring", `${theme.visualiser} ${Visual.style}`);
    press("ArrowLeft"); press("ArrowLeft");
    T("← goes back, wrapping round through Off", theme.visualiser === "off", theme.visualiser);
    press("ArrowRight");
    press("ArrowUp");
    T("↑ raises the pulse strength a step", theme.pulse_strength === 1.25, theme.pulse_strength);
    press("ArrowDown"); press("ArrowDown");
    T("↓ lowers it", theme.pulse_strength === 0.75, theme.pulse_strength);
    press("ArrowRight", { shiftKey: true });
    T("Shift+→ picks the next particles", theme.particles !== "snow" && Particles.level !== "snow", theme.particles);
    press("ArrowUp", { shiftKey: true });
    T("Shift+↑ adds particles", theme.particle_amount === 1.25, theme.particle_amount);
    press("PageUp");
    T("PgUp makes the visualiser more sensitive", theme.visualiser_gain === 1.1, theme.visualiser_gain);
    const first = Fx.effects()[0];
    T("1-9 are the beat effects, from the table", Fx.effects().length >= 8 && first.key === "pulse_glow", Fx.effects().map((r) => r.key).join(","));
    const e1 = press("1");
    T("1 flips the edge glow off at once", theme.pulse_glow === false && document.body.classList.contains("pulse-no-glow") && e1.defaultPrevented);
    press("1");
    T("and on", theme.pulse_glow === true && !document.body.classList.contains("pulse-no-glow"));
    T("the digits don't reach the home screen's search", document.activeElement !== $("search"));
    window.forgeKey("visualiser-toggle");
    T("Alt+M inside Alt+V opens the visuals popup", !$("fx-panel").hidden);
    const keys = [...$("fx-list").querySelectorAll("[id^=fx-]")].map((x) => x.dataset.key);
    T("the popup has a control for every row in the table", rows.every((r) => keys.includes(r.key)), `${keys.length}/${rows.length}`);
    const sel = $("fx-visualiser");
    sel.value = "terrain"; sel.dispatchEvent(new Event("change"));
    T("a change in the popup applies at once", theme.visualiser === "terrain" && Visual.style === "terrain", Visual.style);
    const box = $("fx-pulse_rings");
    box.checked = false; box.dispatchEvent(new Event("change"));
    T("a switch in the popup applies at once", theme.pulse_rings === false);
    press("Escape");
    T("Esc closes the popup", $("fx-panel").hidden || $("fx-panel").classList.contains("closing"));
    T("but leaves the pulse running", Pulse.on && Ambient.on);
    window.forgeKey("visuals");
    T("Alt+Shift+M opens it too", !$("fx-panel").hidden && !$("fx-panel").classList.contains("closing"));
    Fx.open(false);
    window.forgeKey("pulse");
    Ambient.toggle(false);
    T("arrows do nothing special outside Alt+V", (() => { const v = theme.visualiser; press("ArrowRight"); return theme.visualiser === v; })());

    // the visualiser styles live in shared/forge_visual.js now
    T("the hub draws with the shared styles", Visual.STYLES === ForgeVisual.STYLES && Object.keys(ForgeVisual.STYLES).length === 9,
      Object.keys(ForgeVisual.STYLES).join(","));
    T("terrain reacts 20% more", ForgeVisual.TERRAIN_GAIN === 1.2);
    const st = {}, cv = document.createElement("canvas");
    cv.width = 300; cv.height = 200;
    ForgeVisual.draw(cv.getContext("2d"), 300, 200, "bars", Float32Array.from([0.2, 0.4, 0.5]), { gain: 2, st });
    T("sensitivity multiplies the levels", Math.abs(st.gained[0] - 0.4) < 1e-6 && Math.abs(st.gained[1] - 0.8) < 1e-6, Array.from(st.gained).join(","));
    let drew = 0;
    for (const style of ForgeVisual.names()) {
      try { ForgeVisual.draw(cv.getContext("2d"), 300, 200, style, Float32Array.from({ length: 32 }, () => 0.5), { scheme: "rainbow", st: {} }); drew++; } catch (err) { T(`style ${style} draws`, false, err.message); }
    }
    T("every style draws, with a colour scheme", drew === ForgeVisual.names().length, drew);

    // levels for the Visualiser widget, with the background visualiser off
    applyTheme({ visualiser: "off" });
    T("no background visualiser: nothing runs", Visual.style === "off");
    T("the widget asks: levels start flowing (quiet)", Visual.levelsFor() === null && Visual.style === "quiet", Visual.style);
    Visual.levelsIn(Array.from({ length: 32 }, () => 0.5));
    cancelAnimationFrame(Visual.raf); Visual.raf = 0;
    Visual.at = performance.now() - 1000 / 60; // a frame's time: levels ease in by elapsed time
    Visual.frame();
    const lv = Visual.levelsFor();
    T("and it gets them", lv && lv.length === 32 && lv[0] > 0, lv && lv.length);
    Visual.demandAt = 0;
    cancelAnimationFrame(Visual.raf); Visual.raf = 0;
    Visual.frame();
    T("once it stops asking, they stop", Visual.style === "off", Visual.style);
  } catch (e) {
    T("the harness ran", false, e.message + " " + (e.stack || "").split("\n")[1]);
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = out.join("\n");
  document.body.appendChild(pre);
}, 300));
