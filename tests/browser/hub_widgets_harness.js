// Appended to a copy of the REAL hub/index.html by run.sh. B20 (2026-09-27),
// Emerson: "make widgets and a customizable home and widget pages and a cool
// relax thing", "like MD3, or like 5 made by you". Checks ForgeWidgets.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const esc = () => document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
  try {
    const W = window.ForgeWidgets;
    localStorage.removeItem("forge.widgets");
    W.load();
    W.edit(false);
    T("the first five widgets, one registry entry each", ["clock", "nowplaying", "system", "notes", "breathe"].every((k) => W.KINDS[k]), Object.keys(W.KINDS).join(","));
    T("a fresh home gets a starter set on two pages", W.pages.length === 2 && document.querySelectorAll("#widgets .wg").length === 4,
      `${W.pages.length} pages, ${document.querySelectorAll("#widgets .wg").length} cards`);
    T("they sit on the home screen above the app tiles", $("home").contains($("widgets")) && !!($("widgets").compareDocumentPosition($("tiles")) & Node.DOCUMENT_POSITION_FOLLOWING));
    T("Material look by default", $("widgets").dataset.look === "material", $("widgets").dataset.look);
    T("the widget styles loaded", getComputedStyle(document.querySelector("#widgets .wg")).borderRadius === "28px", getComputedStyle(document.querySelector("#widgets .wg")).borderRadius);
    window.forgeSetStats({ cpu: 42, mem: 61, battery: 80, charging: false });
    T("System shows the bar's numbers", document.querySelector("#widgets .wg-system").textContent.includes("42%"), document.querySelector("#widgets .wg-system").textContent);
    // every player on the laptop: a desktop player (MPRIS) shows in the widget
    NowPlaying.sysIn([{ bus: "org.mpris.MediaPlayer2.qbz", title: "Desktop song", artist: "Some band", state: "playing", canNext: true, canPrev: true, current: 5, duration: 200 }]);
    W.tick();
    T("Now playing shows a desktop player too", document.querySelector("#widgets .wg-nowplaying").textContent.includes("Desktop song"),
      document.querySelector("#widgets .wg-nowplaying").textContent.slice(0, 80));
    T("the clock shows the time", /\d/.test(document.querySelector("#widgets .wg-clock .wg-big").textContent), document.querySelector("#widgets .wg-clock .wg-big").textContent);
    applyTheme({ widget_look: "glass", widget_scale: 1.5 });
    T("Glass look and Widget size apply", $("widgets").dataset.look === "glass" && $("widgets").style.getPropertyValue("--widget-row") === "96px", $("widgets").style.getPropertyValue("--widget-row"));
    applyTheme({ widget_look: "material", widget_scale: 1 });

    W.edit(true);
    T("Edit shows remove buttons and resize grips", document.querySelectorAll("#widgets .wg-x").length === 4 && document.querySelectorAll("#widgets .wg-grip").length === 4);
    const page0 = () => W.pages[0].items, find = (k) => page0().find((i) => i.kind === k);
    const clock = find("clock");
    W.place(clock, 3, 0);
    T("dropping onto another widget moves that one down", clock.x === 3 && clock.y === 0 && find("nowplaying").y >= 2, JSON.stringify(find("nowplaying")));
    W.place(clock, 20, 0);
    T("places snap inside the 12 columns", clock.x + clock.w === 12, clock.x);
    W.place(clock, 0, 0, 1, 1);
    T("a widget can't shrink below its smallest size", clock.w === 2 && clock.h === 2, `${clock.w}x${clock.h}`);
    // a real pointer drag: two cells to the right
    const card = document.querySelector("#widgets .wg-clock"), grid = document.querySelector("#widgets .wg-grid").getBoundingClientRect();
    const cell = (grid.width + 12) / 12, r = card.getBoundingClientRect();
    const pe = (type, x, y) => card.dispatchEvent(new PointerEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0, pointerId: 1 }));
    pe("pointerdown", r.left + 20, r.top + 20);
    pe("pointermove", r.left + 20 + cell * 2, r.top + 20);
    pe("pointerup", r.left + 20 + cell * 2, r.top + 20);
    T("dragging a widget moves it by whole cells", find("clock").x === 2 && find("clock").y === 0, JSON.stringify(find("clock")));
    const added = W.add("notes");
    T("Add puts a new widget on the page", page0().includes(added) && document.querySelectorAll("#widgets .wg").length === 5);
    W.remove(added.id);
    T("× removes it", !page0().includes(added) && document.querySelectorAll("#widgets .wg").length === 4);
    W.addPage();
    T("+ Page adds a page and shows it", W.pages.length === 3 && W.page === 2 && !!document.querySelector("#widgets .wg-empty"));
    W.removePage();
    T("Remove page takes it away", W.pages.length === 2);
    esc();
    T("Esc stops editing", !W.editing && !document.querySelector("#widgets .wg-x"));
    document.querySelectorAll("#widgets .wg-dot")[1].click();
    T("the dots switch pages", W.page === 1 && !!document.querySelector("#widgets .wg-notes"));
    const saved = JSON.parse(localStorage.getItem("forge.widgets"));
    T("the layout is saved", saved.pages.length === 2 && saved.page === 1);
    W.load();
    T("and comes back after a reload", W.page === 1 && W.pages[0].items.find((i) => i.kind === "clock").x === 2);

    W.go(0);
    document.querySelector("#widgets .wg-breathe button").click();
    T("Relax opens full-screen breathing", $("relax").classList.contains("on") && document.body.classList.contains("relaxing"));
    T("it starts by breathing in", $("relax").querySelector(".rx-word").textContent === "Breathe in", $("relax").querySelector(".rx-word").textContent);
    T("in, hold, out, hold at the set pace", ["Breathe in", "Hold", "Breathe out", "Hold", "Breathe in"].every((w, k) => W.phase(k * 4000 + 100).word === w));
    applyTheme({ breath_seconds: 6 });
    T("Breathing pace changes the length", W.phase(4100).word === "Breathe in" && W.phase(6100).word === "Hold");
    applyTheme({ breath_seconds: 4 });
    esc();
    T("Esc leaves Relax", !$("relax").classList.contains("on") && !document.body.classList.contains("relaxing"));
    applyTheme({ widgets: false });
    T("Widgets off hides them", $("widgets").hidden);
    applyTheme({ widgets: true });
    T("and on shows them again", !$("widgets").hidden);
  } catch (e) {
    T("the checks ran without an error", false, e && e.stack);
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 600));
