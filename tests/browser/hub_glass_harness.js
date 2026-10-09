// Appended to a copy of the REAL hub by run.sh. S26 (2026-09-28), Emerson
// (S22): "more glass: liquid glass (bright edges, a slight bend) and frosted,
// on tiles, bar, widgets and app frames, with a strength slider". A glass
// kind is one file in shared/glass/, loaded by shared/forge_glass.js.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const loaded = (link) => new Promise((r) => {
    if (link.sheet && link.sheet.cssRules.length) return r(true);
    link.addEventListener("load", () => r(true), { once: true });
    link.addEventListener("error", () => r(false), { once: true });
    setTimeout(() => r(!!(link.sheet && link.sheet.cssRules.length)), 2000);
  });
  const blurOf = (el) => { const cs = getComputedStyle(el); return cs.backdropFilter || cs.webkitBackdropFilter || ""; };
  // task 63: live blur on every tile froze WebKitGTK, so only single panes
  // (bar, search, dock, popups) may blur; tiles, chips and widgets draw theirs
  const blurred = () => [...document.querySelectorAll("body *")].filter((e) => /blur/.test(blurOf(e)) && e.getClientRects().length);
  const singlesOnly = (kind) => {
    const on = blurred(), tiles = document.querySelectorAll(".tile").length;
    T(`${kind} blurs only single panes, no tile, chip or widget (${tiles} tiles shown)`,
      tiles > 0 && on.length > 0 && on.length <= 8 && !on.some((e) => e.matches(".tile, .fchip, .wg")),
      on.map((e) => e.id || e.className).join(", "));
  };
  try {
    const bar = document.getElementById("bar");
    T("Flat is the default: no glass class, no stylesheet", ![...document.body.classList].some((c) => c.startsWith("glass-"))
      && !document.getElementById("glass-css").getAttribute("href"));
    T("and the bar has no live blur", !/blur/.test(blurOf(bar)), blurOf(bar));

    applyTheme(Object.assign({}, theme, { glass_style: "liquid", glass_strength: 1 }));
    const link = document.getElementById("glass-css");
    T("Liquid loads its own stylesheet", /shared\/glass\/liquid\.css$/.test(link.href), link.href);
    T("and its sheet loads", await loaded(link));
    await wait(50);
    T("the page wears body.glass-liquid", document.body.classList.contains("glass-liquid"));
    T("the bar blurs what is behind it (strength 1: 28 px x .45)", /blur\(12\.6px\)/.test(blurOf(bar)), blurOf(bar));
    singlesOnly("Liquid");
    const tile = document.querySelector(".tile");
    T("app tiles get the bright rim", !!tile && /inset/.test(getComputedStyle(tile).boxShadow), tile && getComputedStyle(tile).boxShadow.slice(0, 80));
    const on = document.querySelector(".fchip.on");
    T("the chosen filter chip keeps its accent fill", !on || getComputedStyle(on).backgroundColor === getComputedStyle(on).getPropertyValue("--accent").trim()
      || !/rgba\(\d+, \d+, \d+, 0\.\d+\)/.test(getComputedStyle(on).backgroundColor), on ? getComputedStyle(on).backgroundColor : "no chip");
    const ws = document.querySelector(".workspace");
    T("so does the frame round an open app", !ws || /inset/.test(getComputedStyle(ws).boxShadow), ws ? getComputedStyle(ws).boxShadow.slice(0, 80) : "no frame open");

    applyTheme(Object.assign({}, theme, { glass_style: "liquid", glass_strength: 0.5 }));
    await wait(30);
    T("the strength slider sets the blur", getComputedStyle(document.documentElement).getPropertyValue("--glass-blur").trim() === "14px",
      getComputedStyle(document.documentElement).getPropertyValue("--glass-blur"));

    applyTheme(Object.assign({}, theme, { glass_style: "frosted", glass_strength: 0.5 }));
    T("Frosted swaps the stylesheet", /frosted\.css$/.test(link.href) && await loaded(link));
    await wait(50);
    T("and the class, leaving no Liquid behind", document.body.classList.contains("glass-frosted") && !document.body.classList.contains("glass-liquid"));
    T("Frosted blurs at the full strength value", /blur\(14px\)/.test(blurOf(bar)), blurOf(bar));
    singlesOnly("Frosted");

    // Emerson (2026-09-29): leaving Alt+B or Alt+V, the glass widgets took
    // half a second to turn to glass. A pane can only blur what is inside a
    // parent that is fading (opacity < 1), so the home screen's own fade hid
    // the wallpaper from every pane until it ended. The home screen now comes
    // back at full opacity at once and the panes fade in themselves.
    const home = document.getElementById("home");
    // how long the opacity transition on an element is, in seconds
    const fadeOf = (el) => {
      const cs = getComputedStyle(el), props = cs.transitionProperty.split(", "), times = cs.transitionDuration.split(", ");
      const i = props.findIndex((p) => p === "opacity" || p === "all");
      return i < 0 ? 0 : parseFloat(times[i % times.length]);
    };
    // the fixture has animations off; this is about the fade, so on for it
    applyTheme(Object.assign({}, theme, { glass_style: "frosted", glass_strength: 0.5, animations: true }));
    for (const [name, into, out] of [
      ["background mode (Alt+B)", () => Ambient.toggle(true), () => Ambient.toggle(false)],
      ["the pulse (Alt+V)", () => Pulse.toggle(true), () => Ambient.toggle(false)],
    ]) {
      into();
      await wait(400);
      T(`${name} still fades the home screen out`, fadeOf(home) > 0,
        `${getComputedStyle(home).opacity}, fade ${fadeOf(home)} s`);
      out();
      await wait(60);
      T(`leaving ${name}, the home screen comes back at full opacity at once, so the glass sees the wallpaper`,
        fadeOf(home) === 0, `${getComputedStyle(home).opacity}, fade ${fadeOf(home)} s`);
      const panes = [...home.querySelectorAll(".tile, .widgets .wg, #search")];
      // 2026-10-08: the panes move in without a fade (home-in), so their
      // glass is drawn from the first frame
      T(`and its glass panes move in themselves`, panes.length > 0 && panes.every((p) => getComputedStyle(p).animationName === "home-in"),
        panes.filter((p) => getComputedStyle(p).animationName !== "home-in").map((p) => p.className || p.id).slice(0, 4).join(", ") + ` of ${panes.length}`);
      await wait(700);
    }
    T("the widgets were on the page for that check", !!home.querySelector(".widgets .wg"));

    applyTheme(Object.assign({}, theme, { glass_style: "../evil", glass_strength: 0.5 }));
    T("a strange name falls back to Flat", !document.body.classList.contains("glass-frosted") && !link.getAttribute("href"));
    applyTheme(Object.assign({}, theme, { glass_style: "flat" }));
    await wait(30);
    T("Flat again: no blur on the bar", !/blur/.test(blurOf(bar)), blurOf(bar));
  } catch (e) {
    T("the checks ran without an error", false, e && (e.message + " " + (e.stack || "").split("\n")[1]));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 600));
