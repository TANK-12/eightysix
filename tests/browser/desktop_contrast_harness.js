// Appended to a copy of the REAL desktop/particles.html by run.sh, after
// contrast_sweep.js. QUICKSTART item 2 (Emerson, 2026-10-02): white-on-white
// text in the desktop widget app. The desktop has no dim layer of its own, so
// the bright runs measure against a white wallpaper: no text may sit under
// 3:1 there, resting, in the widget editor or with a widget's options open.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  window.webkit = { messageHandlers: { desktop: { postMessage: () => {} } } };
  try {
    const W = ForgeWidgets, D = ForgeDesktop;
    T("the sweep is loaded", typeof forgeContrastSweep === "function");
    const base = Object.assign({}, D.theme, { widget_look: "material", glass_style: "flat", glass_strength: 0.6, glass: 0.46 });
    const variants = [];
    for (const [name, wall_light, wall] of [["dark", 0.2, "rgb(20, 22, 28)"], ["bright", 0.84, "rgb(255, 255, 255)"]]) {
      variants.push({ name: `${name} wallpaper, material widgets`, theme: { wall_light }, wall });
      variants.push({ name: `${name} wallpaper, glass widgets`, theme: { wall_light, widget_look: "glass", glass: 0.3 }, wall });
      for (const glass_style of ["frosted", "liquid"]) {
        variants.push({ name: `${name} wallpaper, ${glass_style} glass at full strength`, theme: { wall_light, widget_look: "glass", glass_style, glass_strength: 1 }, wall });
      }
    }
    const states = [
      ["resting", async () => {}],
      ["widget editor", async () => {
        W.edit(true); await wait(30);
        const add = document.querySelector(".wg-add"); if (add) add.click();
      }, () => W.edit(false)],
      ["widget options", async () => {
        W.edit(true); await wait(30);
        const cfg = document.querySelector(".wg-cfg"); if (cfg) cfg.click();
      }, () => W.edit(false)],
    ];
    for (const v of variants) {
      D.apply(Object.assign({}, base, v.theme));
      await wait(120);
      for (const [state, open, close] of states) {
        let found;
        try {
          await open(); await wait(80);
          found = forgeContrastSweep(document.body, { base: v.wall });
        } catch (e) {
          T(`${v.name} / ${state} opens`, false, String(e));
          continue;
        } finally {
          try { if (close) close(); } catch (e) { /* the next state starts clean anyway */ }
          await wait(40);
        }
        const seen = new Set();
        const lines = found.filter((f) => { const k = f.where + f.fg + f.bg; if (seen.has(k)) return false; seen.add(k); return true; })
          .map((f) => `${f.where} "${f.text}" ${f.fg} on ${f.bg} = ${f.ratio}:1`);
        T(`${v.name} / ${state}: no text under 3:1`, !lines.length, lines.slice(0, 6).join(" | ") + (lines.length > 6 ? ` | and ${lines.length - 6} more` : ""));
      }
    }
  } catch (e) {
    T("harness ran", false, String(e && e.stack || e));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.append(pre);
}, 400));
