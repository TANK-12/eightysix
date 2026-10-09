// Appended to a copy of the REAL hub/index.html by run.sh. S15 (2026-09-27),
// B7: "background effects: pointer parallax and a time-of-day tint, each a
// setting". Checks WallFx: the tint's colour by the hour, both settings, and
// that the parallax moves the wallpaper and then stops asking for frames.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  document.head.appendChild(document.createElement("style")).textContent = "* { transition: none !important; }";
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  try {
    const alpha = (c) => c[3];
    // more sliders (S18): tint strength, particle size/speed/frame rate
    applyTheme(Object.assign({}, theme, { wall_tint: true, wall_tint_strength: 0.5 }));
    WallFx.tint(new Date(2026, 0, 1, 23, 30));
    const half = parseFloat(getComputedStyle($("wall-tint")).backgroundColor.split(",")[3]);
    T("Tint strength 0.5 halves the tint", Math.abs(half - WallFx.tintAt(23.5)[3] * 0.5) < 0.01, half);
    const mean = (f) => Particles.dots.reduce((a, d) => a + f(d), 0) / Particles.dots.length;
    applyTheme(Object.assign({}, theme, { animations: true, particles: "snow", particle_amount: 2, particle_size: 1, particle_speed: 1 }));
    Particles.apply();
    const r1 = mean((d) => d.r), v1 = mean((d) => Math.abs(d.vy));
    applyTheme(Object.assign({}, theme, { animations: true, particles: "snow", particle_amount: 2, particle_size: 2, particle_speed: 2 }));
    Particles.apply();
    const r2 = mean((d) => d.r), v2 = mean((d) => Math.abs(d.vy));
    T("Particle size 2 makes them about twice as big", r2 / r1 > 1.5 && r2 / r1 < 2.6, (r2 / r1).toFixed(2));
    T("Particle speed 2 makes them about twice as fast", v2 / v1 > 1.5 && v2 / v1 < 2.6, (v2 / v1).toFixed(2));
    applyTheme(Object.assign({}, theme, { animations: true, particles: "snow", particle_fps: 10 }));
    Particles.apply();
    Particles.drawn = 1000;
    Particles.frame(1050);
    T("at 10 fps a frame 50 ms after the last is skipped", Particles.drawn === 1000, Particles.drawn);
    Particles.frame(1110);
    T("and one 110 ms after is drawn", Particles.drawn === 1110, Particles.drawn);
    cancelAnimationFrame(Particles.raf); Particles.raf = 0;
    applyTheme(Object.assign({}, theme, { particle_fps: 60, particle_size: 1, particle_speed: 1, wall_tint_strength: 1 }));
    // the tint by the hour
    const noon = WallFx.tintAt(12), night = WallFx.tintAt(23.5), evening = WallFx.tintAt(18.5), dawn = WallFx.tintAt(6.5);
    T("no tint at midday", alpha(noon) < 0.02, noon.join(","));
    T("night is a blue tint", alpha(night) > 0.1 && night[2] > night[0], night.join(","));
    T("early evening is a warm tint", alpha(evening) > 0.08 && evening[0] > evening[2], evening.join(","));
    T("dawn is a warm tint", alpha(dawn) > 0.05 && dawn[0] > dawn[2], dawn.join(","));
    const a = WallFx.tintAt(20.99), b = WallFx.tintAt(21.01);
    T("the tint blends between times, no jumps", Math.abs(alpha(a) - alpha(b)) < 0.01, a.join(",") + " / " + b.join(","));
    T("midnight wraps to the night tint", Math.abs(alpha(WallFx.tintAt(0)) - alpha(WallFx.tintAt(24))) < 0.001);

    // the tint setting
    applyTheme(Object.assign({}, theme, { animations: true, wall_tint: true, wall_parallax: 0 }));
    WallFx.tint(new Date(2026, 8, 27, 23, 30));
    const bg = () => getComputedStyle($("wall-tint")).backgroundColor;
    T("tint on: the layer is coloured at night", bg() !== "rgba(0, 0, 0, 0)" && getComputedStyle($("wall-tint")).display !== "none", bg());
    applyTheme(Object.assign({}, theme, { animations: true, wall_tint: false, wall_parallax: 0 }));
    T("tint off: the layer is gone", getComputedStyle($("wall-tint")).display === "none");

    // the parallax setting
    selectWorkspace(null, { instant: true });
    applyTheme(Object.assign({}, theme, { animations: true, wall_tint: false, wall_parallax: 2 }));
    const tr = () => getComputedStyle($("wall")).translate;
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 0, clientY: 0, bubbles: true }));
    // headless Chrome runs about one animation frame in its virtual time, so
    // step the frames by hand until the parallax says it has settled
    let frames = 0;
    while (WallFx.raf && frames < 500) { cancelAnimationFrame(WallFx.raf); WallFx.frame(); frames++; }
    const moved = tr();
    T("parallax on: the wallpaper moves against the pointer", moved !== "none" && moved !== "0px" && !moved.startsWith("-") && parseFloat(moved) > 20, moved);
    T("parallax on: the wallpaper is scaled up so no edge shows", parseFloat(getComputedStyle($("wall")).scale) > 1.03, getComputedStyle($("wall")).scale);
    T("parallax settles and stops asking for frames", WallFx.raf === 0 && frames < 120, frames + " frames");
    applyTheme(Object.assign({}, theme, { animations: true, wall_tint: false, wall_parallax: 0 }));
    await wait(50);
    T("parallax off: the wallpaper is back in place", ["none", "0px", "0px 0px"].includes(tr()) && ["none", "1"].includes(getComputedStyle($("wall")).scale), tr());
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 900, clientY: 700, bubbles: true }));
    T("parallax off: the pointer asks for no frames", WallFx.raf === 0);
    // particles behind open apps (Emerson: "even when I have apps open ... particles still work")
    const firstApp = Object.keys(parts)[0];
    applyTheme(Object.assign({}, theme, { animations: true, particles: "soft", particles_in_apps: true, wall_parallax: 0 }));
    selectWorkspace(firstApp, { instant: true });
    await wait(50);
    const pop = () => getComputedStyle($("particles")).opacity;
    T("with an app open the particles keep drawing", Particles.showing() && $("particles").dataset.running === "1", $("particles").dataset.running);
    T("with an app open the particles stay visible behind it", pop() === "1", pop());
    applyTheme(Object.assign({}, theme, { animations: true, particles: "soft", particles_in_apps: false, wall_parallax: 0 }));
    await wait(50);
    T("setting off: they stop while an app is open", !Particles.showing() && $("particles").dataset.running === "0" && pop() === "0", `${$("particles").dataset.running} ${pop()}`);
    selectWorkspace(null, { instant: true });
    await wait(50);
    T("setting off: they come back on the home screen", $("particles").dataset.running === "1");
    cancelAnimationFrame(Particles.raf); Particles.raf = 0;
  } catch (e) {
    T("effects harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
