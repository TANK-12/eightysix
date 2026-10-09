// Appended to a copy of the REAL hub/index.html by run.sh, with the live
// hub/status.js (every real app) beside it. Checks Settings > Icons: the
// switch between the drawn icons (New) and the emoji (Classic) repaints every
// icon at once with no reload, no two apps share an icon in either style, and
// the dock's tooltips and the folders' member grids come through each switch.
// With #shot-new or #shot-classic in the address it only sets that style and
// opens a few apps, for a screenshot.
addEventListener("load", () => setTimeout(async () => {
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const shot = location.hash.match(/^#shot-(new|classic)$/);
  if (shot) {
    applyTheme({ icon_style: shot[1] });
    for (const k of ["mission", "claude", "jan-tune", "power", "janhollow", "files", "dossier", "terminal", "keymap"]) {
      if (parts[k] || infoFor(k).label) { try { selectWorkspace(k, { instant: true }); } catch (e) {} await wait(60); }
    }
    selectWorkspace(null, { instant: true });
    return;
  }
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const marked = () => [...document.querySelectorAll("[data-icon]")];
  const tiles = () => [...document.querySelectorAll("#tiles .tile[data-key]:not(.folder)")]
    .map((t) => [t.dataset.key, t.querySelector(".icon")]);
  const faceOf = (el) => (el.querySelector(":scope > svg.forge-glyph") ? el.querySelector(":scope > svg.forge-glyph").outerHTML
    : [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(""));
  const repeats = (pairs) => {
    const seen = {}, dup = [];
    for (const [k, face] of pairs) {
      const bare = face.replace(/️/g, "");
      if (seen[bare]) dup.push(seen[bare] + "=" + k); else seen[bare] = k;
    }
    return dup;
  };
  const tips = () => [...document.querySelectorAll("#dock .dock-item[data-app]")].every((d) => d.querySelector(".tip"));
  const folders = () => [...document.querySelectorAll(".folder .folder-icons")].length;

  try {
    const keys = Object.keys(window.FORGE_STATUS || {});
    for (const k of ["mission", "jan-tune", "power"]) if (keys.includes(k)) selectWorkspace(k);
    await wait(200);
    const folderCount = folders();
    T("the test folder is there, its grid unmarked", folderCount >= 1
      && [...document.querySelectorAll(".folder .icon, .dock-item.folder")].every((n) => n.dataset.icon === undefined), folderCount);
    // the music box: an app's icon, then album art; a broken picture falls back
    const np = make("div"), np2 = make("div");
    document.body.append(np, np2);
    NowPlaying.art(np, { id: "a", key: "power", kind: "app" });
    NowPlaying.art(np, { id: "a", key: "power", kind: "app", artwork: "data:image/gif;base64,R0lGODlhAQABAAAAACw=" });
    const sys = make("div"); document.body.appendChild(sys);
    NowPlaying.art(sys, { id: "b", key: "power", kind: "app" });
    NowPlaying.art(sys, { id: "c", kind: "sys", video: true });
    window.__stillHere = 1;
    T("the hub starts in the New style", ForgeIcons.style() === "new" && tiles().every(([, i]) => i.querySelector("svg.forge-glyph")),
      tiles().filter(([, i]) => !i.querySelector("svg.forge-glyph")).map(([k]) => k).join(","));
    T("there are app tiles to check", tiles().length >= 10, tiles().length);
    T("New: no two tiles share an icon", repeats(tiles().map(([k, i]) => [k, faceOf(i)])).length === 0,
      repeats(tiles().map(([k, i]) => [k, faceOf(i)])).join(" "));

    applyTheme({ icon_style: "classic" });
    const svgs = marked().filter((el) => el.querySelector(":scope > svg.forge-glyph"));
    T("Classic: every painted icon is an emoji, none drawn", ForgeIcons.style() === "classic" && svgs.length === 0,
      svgs.map((e) => e.dataset.icon).join(","));
    const wrong = tiles().filter(([k, i]) => faceOf(i) !== (ForgeIcons.classic(k.replace(GROUP, "")) || iconFor(infoFor(k), k)));
    T("Classic: each tile shows its app's classic emoji", wrong.length === 0, wrong.map(([k, i]) => k + ":" + faceOf(i)).join(","));
    T("Classic: no two tiles share an icon", repeats(tiles().map(([k, i]) => [k, faceOf(i)])).length === 0,
      repeats(tiles().map(([k, i]) => [k, faceOf(i)])).join(" "));
    const ws = (k) => parts[k] && faceOf(parts[k].ws);
    T("Classic: the top bar shows Jan Tune, Power and Mission Control apart",
      ws("jan-tune") === ForgeIcons.classic("jan-tune") && ws("power") === "⚡" && ws("mission") === ForgeIcons.classic("mission")
      && new Set([ws("jan-tune"), ws("power"), ws("mission")]).size === 3, [ws("jan-tune"), ws("power"), ws("mission")].join(" "));
    T("Classic: switched with no reload (the page kept its state)", window.__stillHere === 1 && !!parts["power"]);
    T("Classic: album art is left alone, no icon added beside it",
      np.childNodes.length === 1 && np.firstChild.tagName === "IMG", [...np.childNodes].map((n) => n.nodeName).join(","));
    T("Classic: a system track keeps its film mark", sys.textContent === "🎬" && !sys.querySelector("svg"), sys.textContent);
    np2.appendChild(make("img"));
    setIcon(np2, infoFor("power"), "power");
    T("an icon painted over a broken picture replaces it", np2.childNodes.length === 1 && np2.textContent === "⚡",
      [...np2.childNodes].map((n) => n.nodeName).join(","));
    AppMenu.open("jan-tune", 50, 50);
    const amIcon = document.querySelector(".am-title i");
    T("Classic: the right-click menu title shows the classic icon", !!amIcon && amIcon.textContent === ForgeIcons.classic("jan-tune"),
      amIcon && amIcon.innerHTML.slice(0, 30));
    applyTheme({ icon_style: "new" });
    T("the open menu title follows the switch", !!amIcon && !!amIcon.querySelector("svg.forge-glyph"));
    applyTheme({ icon_style: "classic" });
    T("Classic: dock tooltips and folder grids stay", tips() && folders() === folderCount, folders() + "/" + folderCount);

    applyTheme({ accent: "#ff8800" });
    T("another theme change keeps Classic", ForgeIcons.style() === "classic" && faceOf(parts["power"].ws) === "⚡");

    applyTheme({ icon_style: "new" });
    const back = tiles().filter(([, i]) => !i.querySelector(":scope > svg.forge-glyph"));
    T("back to New: every tile is drawn again", ForgeIcons.style() === "new" && back.length === 0, back.map(([k]) => k).join(","));
    T("back to New: the top bar is drawn again", ["jan-tune", "power", "mission"].every((k) => !parts[k] || parts[k].ws.querySelector("svg.forge-glyph")));
    T("back to New: dock tooltips and folder grids stay", tips() && folders() === folderCount);
    const docks = [...document.querySelectorAll("#dock .dock-item[data-app]:not(.folder)")];
    T("back to New: each dock item holds one icon, not two",
      docks.every((d) => d.querySelectorAll(":scope > svg.forge-glyph").length === 1 && ![...d.childNodes].some((n) => n.nodeType === 3 && n.textContent)),
      docks.filter((d) => d.querySelectorAll(":scope > svg.forge-glyph").length !== 1).map((d) => d.dataset.app).join(","));
  } catch (e) {
    T("harness ran without throwing", false, String(e && e.stack || e));
  }
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.insertAdjacentHTML("beforeend", "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>");
}, 600));
