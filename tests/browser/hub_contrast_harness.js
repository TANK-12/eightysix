// Appended to a copy of the REAL hub by run.sh, after contrast_sweep.js.
// QUICKSTART item 2 (Emerson, 2026-10-02): "white-on-white text in the Forge
// hub and the desktop widget app". Every look, glass kind and a pale, a
// yellow and a blue accent, on the home screen and with each popup, the app
// overview, zen mode and the widget editor open: no text may sit under 3:1
// against the colours the CSS puts behind it. Then the same on a near-white
// wallpaper (theme.wall_light .84, as the brightest one in his cache): the
// text that sits straight on the picture was white on white there.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const looks = ["classic", "material", "minimal", "brain", "hyprland"];
  const accents = {
    blue: { accent: "#5b6ee8", accent_2: "#3f55e3", on_accent: "#ffffff" },
    yellow: { accent: "#e8d36b", accent_2: "#e3c83f", on_accent: "#0b1220" },
    pale: { accent: "#f4f1ea", accent_2: "#e6dfd0", on_accent: "#0b1220" },
  };
  const variants = [];
  for (const look of looks) variants.push({ name: look, theme: { look } });
  for (const glass_style of ["frosted", "liquid"]) variants.push({ name: "glass " + glass_style, theme: { glass_style, glass_strength: 1 } });
  for (const [name, a] of Object.entries(accents)) variants.push({ name: "accent " + name, theme: a });
  variants.push({ name: "widgets glass, pale accent", theme: Object.assign({ widget_look: "glass" }, accents.pale) });
  // the wallpaper under the dim layer: white for the bright runs
  const bright = { wall_light: 0.84, dim: 0.22 };
  const white = () => { const d = Number(getComputedStyle(document.documentElement).getPropertyValue("--dim")) || 0; const v = Math.round(255 * (1 - d)); return `rgb(${v}, ${v}, ${v})`; };
  variants.push({ name: "bright wallpaper", theme: bright, base: white });
  variants.push({ name: "bright wallpaper, glass widgets", theme: Object.assign({ widget_look: "glass", glass: 0.3 }, bright), base: white });
  for (const glass_style of ["frosted", "liquid"]) {
    variants.push({ name: `bright wallpaper, ${glass_style} glass at full strength`, theme: Object.assign({ glass_style, glass_strength: 1 }, bright), base: white });
  }

  const W = window.ForgeWidgets;
  const firstKey = () => (document.querySelector(".tile[data-key]") || {}).dataset?.key;
  const states = [
    ["home", async () => {}],
    ["Aa panel", async () => { Sizes.panel(true); }, () => Sizes.panel(false)],
    ["music panel", async () => { Music.panel(true); }, () => Music.panel(false)],
    ["effects panel", async () => { Fx.open(true); }, () => Fx.open(false)],
    ["app menu", async () => { const k = firstKey(); if (k) AppMenu.open(k, 300, 300); }, () => { $("app-menu").hidden = true; }],
    ["toast", async () => { toast("Moved NovelForge to the hidden apps", () => {}); }, () => { $("toast").hidden = true; }],
    ["overview", async () => { Overview.show(); }, () => Overview.close()],
    ["zen", async () => { Zen.toggle(true); }, () => Zen.toggle(false)],
    ["widget editor", async () => {
      W.edit(true); await wait(30);
      const add = document.querySelector(".wg-add"); if (add) add.click(); await wait(30);
    }, () => W.edit(false)],
    ["widget options", async () => {
      W.edit(true); await wait(30);
      const cfg = document.querySelector(".wg-cfg"); if (cfg) cfg.click();
    }, () => W.edit(false)],
  ];

  try {
    T("the sweep is loaded", typeof forgeContrastSweep === "function");
    T("and measures: white on white is 1:1", Math.abs(forgeContrastRatio("rgb(255,255,255)", "rgb(255,255,255)") - 1) < 1e-9);
    T("black on white is 21:1", Math.round(forgeContrastRatio("rgb(0,0,0)", "rgb(255,255,255)")) === 21);
    // applyTheme() merges into the theme it has, so every variant starts
    // from the same settings or one variant's glass leaks into the next
    const base = Object.assign({}, theme, { look: "classic", glass_style: "flat", glass_strength: 0.6, glass: 0.62,
      widget_look: "material", wall_light: 0.2, dim: 0.18 }, { accent: theme.accent, accent_2: theme.accent_2, on_accent: theme.on_accent });
    applyTheme(Object.assign({}, base, bright));
    T("the bright wallpaper deepens the pool behind the home clock", getComputedStyle(document.documentElement).getPropertyValue("--wall-light").trim() === "0.84"
      && /rgba\(0, 0, 0, 0\.5[78]/.test(getComputedStyle(document.querySelector("#home .hero > div"), "::before").backgroundImage),
      getComputedStyle(document.querySelector("#home .hero > div"), "::before").backgroundImage);
    T("a near-white wallpaper lifts the dim to .38", getComputedStyle(document.documentElement).getPropertyValue("--dim").trim() === "0.38");
    applyTheme(Object.assign({}, base, { wall_light: 0.5, dim: 0.22 }));
    T("a mid-bright one keeps the dim that was set", getComputedStyle(document.documentElement).getPropertyValue("--dim").trim() === "0.22");
    const keep = (t) => { applyTheme(Object.assign({}, base, t)); const cs = getComputedStyle(document.documentElement);
      return [cs.getPropertyValue("--glass-keep").trim(), cs.getPropertyValue("--glass-pane").trim()]; };
    T("full-strength glass on a dark wallpaper stays clear (keeps 45%)", keep({ glass_style: "liquid", glass_strength: 1, wall_light: 0.2 })[0] === "45%");
    T("on a near-white one the panes keep all of their fill", keep({ glass_style: "liquid", glass_strength: 1, wall_light: 0.84 })[0] === "100%");
    T("and the widgets' own glass is at least .6 opaque there", keep({ glass: 0.3, wall_light: 0.84 })[1] === "0.600", keep({ glass: 0.3, wall_light: 0.84 })[1]);
    T("a setting above the floor is kept", keep({ glass: 0.8, wall_light: 0.84 })[1] === "0.800");
    for (const v of variants) {
      applyTheme(Object.assign({}, base, v.theme));
      await wait(120);
      for (const [state, open, close] of states) {
        let found;
        try {
          await open(); await wait(80);
          found = forgeContrastSweep(document.body, v.base ? { base: v.base() } : {});
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
