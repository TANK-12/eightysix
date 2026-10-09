// Appended to a copy of the REAL hub/index.html by run.sh. B40: Alt+B's
// entrance and the Alt+V pulse (forge.py sends forgeKey("pulse")): the
// wallpaper swells and brightens on a beat, the edges glow, it fades after.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // the pulse's values live on its layers (MOVING_LAYERS), not on <html>
  const cs = (n) => getComputedStyle($("pulse-glow")).getPropertyValue(n).trim();
  const has = (c) => document.body.classList.contains(c);
  try {
    T("the pulse is off at start", !Pulse.on && !has("pulse") && getComputedStyle($("pulse-glow")).display === "none");
    theme.animations = true; // the test theme has them off, and no-anim stops CSS animations
    const noAnim = has("no-anim");
    document.body.classList.remove("no-anim");
    window.forgeKey("pulse");
    await wait(100);
    theme.animations = false;
    T("Alt+V turns background mode on with the pulse", Ambient.on && Pulse.on && has("pulse"));
    T("background mode plays its entrance", has("ambient-enter") && getComputedStyle($("pulse-light")).animationName === "ambient-in", getComputedStyle($("pulse-light")).animationName);
    T("and leaves the wallpaper's drift alone", getComputedStyle($("wall")).animationName !== "ambient-in");
    const quiet = new Float32Array(32).fill(0.02);
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    const before = Number(cs("--pulse-k"));
    const loud = new Float32Array(32).fill(0.05);
    for (let i = 0; i < 4; i++) loud[i] = 0.9;
    Pulse.feed(loud);
    const hit = Number(cs("--pulse-k"));
    T("a kick in the lows swells the pulse", before < 0.05 && hit > 0.5, `${before} -> ${hit}`);
    T("the beat restyles only the layers, never the whole page (task 71)",
      document.documentElement.style.getPropertyValue("--pulse-k") === "" && getComputedStyle($("wall")).getPropertyValue("--pulse-p").trim() !== "",
      document.documentElement.style.cssText.slice(0, 80));
    await wait(1500);
    T("the entrance settles", !has("ambient-enter"));
    document.body.classList.toggle("no-anim", noAnim);
    const ws = getComputedStyle($("wall")).scale;
    T("the wallpaper punches in on the beat", Number(String(ws).split(" ")[0]) > 1.07, ws);
    T("the wallpaper takes no per-frame filter (that dropped frames)", getComputedStyle($("wall")).filter === "none", getComputedStyle($("wall")).filter);
    T("the edges glow", parseFloat(getComputedStyle($("pulse-glow")).opacity) > 0.5, getComputedStyle($("pulse-glow")).opacity);
    T("a colour flash", Number(cs("--pulse-f")) > 0.5 && parseFloat(getComputedStyle($("pulse-flash")).opacity) > 0.15, cs("--pulse-f"));
    T("the colour split shows the wallpaper twice", has("pulse-chroma") && Number(cs("--pulse-ch")) > 0.5 && getComputedStyle($("chroma-r")).display === "block");
    T("a shockwave ring starts", Pulse.rings.length === 1, Pulse.rings.length);
    T("the particles surge", Particles.surge > 0.5, Particles.surge);
    const fx = Pulse.fxc.getImageData(0, 0, Pulse.fx.width, Pulse.fx.height).data;
    let lit = 0;
    for (let i = 3; i < fx.length; i += 4 * 97) if (fx[i] > 0) lit++;
    T("the rings and stage lights are drawn", lit > 50, lit);
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    T("and it fades after the beat", Number(cs("--pulse-k")) < 0.05, cs("--pulse-k"));
    T("the flash and split fade too", Number(cs("--pulse-f")) < 0.05 && Number(cs("--pulse-ch")) < 0.05, cs("--pulse-f") + " " + cs("--pulse-ch"));
    // raw levels: a beat in the unsmoothed levels lands even while the smoothed ones lag
    const smooth = new Float32Array(32).fill(0.03), raw = new Float32Array(32).fill(0.05);
    for (let i = 0; i < 4; i++) raw[i] = 0.9;
    Pulse.feed(smooth, raw);
    T("the beat is read from the raw levels, on the same frame", Number(cs("--pulse-k")) > 0.5, cs("--pulse-k"));
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    theme.pulse_sensitivity = 0.5;
    const soft = new Float32Array(32).fill(0.02);
    for (let i = 0; i < 4; i++) soft[i] = 0.16;
    Pulse.last = 0; Pulse.lastBeat = 0;
    Pulse.feed(soft);
    T("low sensitivity waits for the big beats", Number(cs("--pulse-k")) < 0.1, cs("--pulse-k"));
    theme.pulse_sensitivity = 2;
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    Pulse.lastBeat = 0;
    Pulse.feed(soft);
    T("high sensitivity catches soft ones", Number(cs("--pulse-k")) > 0.15, cs("--pulse-k"));
    delete theme.pulse_sensitivity;
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    theme.pulse_rings = false; theme.pulse_flash = false; theme.pulse_burst = false;
    Pulse.rings = []; Particles.surge = 0; Pulse.lastBeat = 0;
    Pulse.feed(loud);
    T("each effect has its own switch", Pulse.rings.length === 0 && Pulse.flash < 0.01 && Particles.surge === 0, `${Pulse.rings.length} ${Pulse.flash} ${Particles.surge}`);
    delete theme.pulse_rings; delete theme.pulse_flash; delete theme.pulse_burst;
    theme.pulse_punch = false;
    Pulse.lastBeat = 0;
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    Pulse.lastBeat = 0;
    Pulse.feed(loud);
    T("Beat punch off keeps the kick gentle", Number(cs("--pulse-p")) < 0.3 && Number(cs("--pulse-k")) > 0.5, cs("--pulse-p"));
    delete theme.pulse_punch;
    for (let i = 0; i < 40; i++) Pulse.feed(quiet);
    // on time: past the frame-rate cap while pulsing, unless Full frame rate is off
    let used = "";
    const realRaw = ForgeFrameCap.raw, realRaf = window.requestAnimationFrame;
    ForgeFrameCap.raw = () => { used = "raw"; return 0; };
    window.requestAnimationFrame = () => { used = "capped"; return 0; };
    Visual.next(() => {});
    T("the pulse draws past the frame-rate cap", used === "raw", used);
    theme.pulse_full_fps = false;
    Visual.next(() => {});
    T("Full frame rate off keeps the cap", used === "capped", used);
    delete theme.pulse_full_fps;
    ForgeFrameCap.raw = realRaw; window.requestAnimationFrame = realRaf;
    // the two new visualisers draw something from levels
    for (const style of ["orbit", "terrain"]) {
      const cv = document.createElement("canvas");
      cv.width = 800; cv.height = 500;
      const g = cv.getContext("2d"), lv = new Float32Array(32).map((_, i) => 0.3 + 0.5 * Math.abs(Math.sin(i)));
      for (let f = 0; f < 5; f++) Visual.STYLES[style](g, 800, 500, lv, 1, "#8ab4ff", "#ff8ad8");
      const px = g.getImageData(0, 0, 800, 500).data;
      let on = 0;
      for (let i = 3; i < px.length; i += 4 * 53) if (px[i] > 0) on++;
      T(`the ${style} visualiser draws`, on > 100, on);
    }
    theme.pulse_glow = false;
    window.forgeKey("pulse");
    T("Alt+V again stops the pulse and stays in background mode", !Pulse.on && Ambient.on && !has("pulse"));
    window.forgeKey("pulse");
    T("Edge glow off hides the glow", getComputedStyle($("pulse-glow")).display === "none");
    delete theme.pulse_glow;
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wait(50);
    T("Esc leaves background mode and the pulse together", !Ambient.on && !Pulse.on && !has("pulse"));
    theme.ambient_entrance = false;
    window.forgeKey("ambient");
    T("Entrance animation off skips it", Ambient.on && !has("ambient-enter"));
    window.forgeKey("ambient");
    delete theme.ambient_entrance;
  } catch (e) {
    T("pulse harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
