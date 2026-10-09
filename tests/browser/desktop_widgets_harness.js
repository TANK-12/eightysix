// Appended to a copy of the REAL desktop/particles.html by run.sh. S25
// (2026-09-28), Emerson: "bring over to the extension for desktop: particles,
// the widgets, and a way to actually add the widgets", "let me also add
// visualisers to the desktop extension". desktop/particles.py is stood in for
// by a message handler that records what the page asks.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { desktop: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const last = (key) => [...sent].reverse().find((m) => key in m);
  const $ = (id) => document.getElementById(id);
  try {
    const W = ForgeWidgets, D = ForgeDesktop;
    // this copy's hub/theme.js has the widgets and a bars visualiser on
    T("the widgets start with a column down the right", W.pages.length === 1 && W.pages[0].items.map((i) => i.kind).join() === "clock,weather,player",
      W.pages[0] && W.pages[0].items.map((i) => i.kind).join());
    T("on a 24-column grid over the screen", W.cols === 24 && W.pages[0].items[0].x === 17);
    T("the edit button shows", !$("dk-edit").hidden);
    D.clickable(); D.lastRects = ""; D.clickable();
    const rects = last("rects").rects;
    T("only the cards and the two corner buttons take clicks", rects.length === 5 && rects.every((r) => r[2] < innerWidth), JSON.stringify(rects));
    T("the settings button shows", !$("dk-settings").hidden);
    sent.length = 0;
    $("dk-settings").click();
    T("⚙ asks the desktop window to open the settings", sent.some((m) => m.settings === true), JSON.stringify(sent));
    T("the rest of the screen lets clicks through", !rects.some((r) => r[0] === 0 && r[1] === 0 && r[2] === innerWidth));
    $("dk-edit").click();
    T("the button starts editing", W.editing && document.body.classList.contains("editing"));
    T("the window is told, to take the keyboard", last("editing").editing === true);
    T("editing takes clicks everywhere, to move cards anywhere", JSON.stringify(last("rects").rects) === JSON.stringify([[0, 0, innerWidth, innerHeight]]));
    const pick = document.querySelector("#widgets .wg-add"), list = document.querySelector("#widgets .wg-addlist");
    T("the Add menu starts closed", list && list.hidden);
    pick.click();
    const kinds = [...list.querySelectorAll(".wg-addkind")];
    T("the Add button opens a list of every widget", !list.hidden && kinds.length === Object.keys(W.KINDS).length, kinds.length);
    // 2026-09-29: the old <select> list was white text on white on the desktop
    const ink = getComputedStyle(kinds[0]).color, paper = getComputedStyle(list).backgroundColor;
    T("the list is light text on a dark background", /^rgb\(2[0-9]{2}, 2[0-9]{2}, 2[0-9]{2}/.test(ink) && /rgba?\(1[0-9], 1[0-9], 2[0-9]/.test(paper), `${ink} on ${paper}`);
    kinds.find((b) => b.dataset.kind === "network").click();
    const saved = last("save");
    T("an added widget is saved through the desktop window, not localStorage", saved && saved.save.pages[0].items.some((i) => i.kind === "network")
      && localStorage.getItem("forge.widgets") === null);
    T("its size is scaled to the finer grid", saved.save.pages[0].items.find((i) => i.kind === "network").w === 6);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    T("Esc ends editing", !W.editing && !document.body.classList.contains("editing") && last("editing").editing === false);
    T("and clicks go through again", last("rects").rects.length === 6, JSON.stringify(last("rects").rects));

    // 2026-10-07, Emerson: "make the widget page swipeable by 2 finger just
    // like in forge cause 3 fingers is desktop swiping". With two pages the
    // whole widget area takes input, so a swipe over bare desktop reaches it.
    W.pages.push({ name: "Two", items: [] }); W.render(); D.lastRects = ""; D.clickable();
    const area = $("widgets").getBoundingClientRect();
    T("with two pages the widget area takes the swipe", last("rects").rects.some((r) => r[0] === Math.floor(area.left) && r[2] === Math.ceil(area.width)),
      JSON.stringify(last("rects").rects));
    const wheel = (dx, dy) => $("widgets").dispatchEvent(new WheelEvent("wheel", { deltaX: dx, deltaY: dy || 0, bubbles: true }));
    W.go(0);
    for (let k = 0; k < 8; k++) { wheel(12); await wait(16); } // a slow two-finger swipe: small steps
    T("a slow two-finger swipe turns the page", W.page === 1, W.page);
    for (let k = 0; k < 10; k++) { wheel(20); await wait(16); } // the same swipe's glide after the fingers lift
    T("one swipe turns one page, glide included", W.page === 1, W.page);
    await wait(350);
    for (let k = 0; k < 8; k++) { wheel(-12); await wait(16); }
    T("swiping back turns it back", W.page === 0, W.page);
    await wait(350);
    for (let k = 0; k < 8; k++) { wheel(6, 30); await wait(16); }
    T("an up-down scroll leaves the page alone", W.page === 0, W.page);
    await wait(350);
    W.pages.pop(); W.go(0); D.clickable();
    T("one page again: clicks go through again", last("rects").rects.length === 6, JSON.stringify(last("rects").rects));

    // the data comes from desktop/particles.py
    window.forgeDesktop({ stats: { cpu: 12, mem: 40, battery: 70, charging: false, net: { down: 2048, up: 10, ifaces: ["wlan0"], wifi: "home" } } });
    window.forgeDesktop({ players: [{ bus: "org.mpris.MediaPlayer2.qbz", name: "Qobuz", title: "Desk song", artist: "Band", state: "playing", position: 40, duration: 180, volume: 0.4, canNext: true, canPrev: true }] });
    W.tick();
    T("the network card shows the desktop's own numbers", /2 KB\/s/.test(document.querySelector(".wg-network").textContent), document.querySelector(".wg-network").textContent.slice(0, 50));
    T("the player card shows a player on the laptop", /Desk song/.test(document.querySelector(".wg-player").textContent));
    sent.length = 0;
    document.querySelector('.wg-player [title="Next"]').click();
    T("its buttons go to that player", sent.some((m) => m.media && m.media.op === "next" && m.media.bus === "org.mpris.MediaPlayer2.qbz"), JSON.stringify(sent));
    document.querySelector(".wg-player .wg-btn.ghost").click();
    T("Go to player asks the desktop to show it", sent.some((m) => m.media && m.media.op === "raise"));
    const vol = document.querySelector(".wg-player .wg-vol input");
    vol.value = 80; vol.dispatchEvent(new Event("input"));
    T("volume goes as 0-1, as MPRIS wants", sent.some((m) => m.media && m.media.op === "volume" && Math.abs(m.media.value - 0.8) < 1e-9));

    // the visualiser: asks for levels, draws them
    sent.length = 0;
    D.askedLevels = 0;
    D.frame(); // headless Chrome gives this page no animation frames of its own
    T("the visualiser asks for the sound", sent.some((m) => m.levels && m.levels.on === true), JSON.stringify(sent.filter((m) => m.levels)));
    for (let k = 0; k < 6; k++) { window.forgeDesktop({ levels: Array.from({ length: 32 }, (_, i) => 0.3 + 0.5 * Math.abs(Math.sin(i))) }); await wait(40); }
    // headless Chrome gives this page no animation frames, so step one by hand
    D.frame();
    const cv = $("visual"), px = cv.getContext("2d").getImageData(0, 0, cv.width, cv.height).data;
    let lit = 0;
    for (let i = 3; i < px.length; i += 4 * 16) if (px[i] > 0) lit++;
    T("and draws them on the desktop", D.style === "bars" && lit > 50, `${D.style} ${lit}`);
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_visualiser: "off" }));
    T("Visualiser off clears it", D.style === "off" && !D.raf);
    T("and cava is let go at once when nothing else draws", sent.some((m) => m.levels && m.levels.on === false), JSON.stringify(sent.filter((m) => m.levels)));

    // the switches
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_particles: false, desktop_visualiser: "off" }));
    T("particles off on the desktop, widgets still there", Particles.level === "off" && !$("widgets").hidden);
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_widgets: false, desktop_particles: true }));
    T("widgets off hides them and their button", $("widgets").hidden && $("dk-edit").hidden && Particles.level !== "off");
    T("the settings button stays, for the particles", !$("dk-settings").hidden);
    T("and nothing else takes clicks", last("rects").rects.length === 1, JSON.stringify(last("rects").rects));
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_widgets: true, desktop_edit_button: false }));
    T("the corner buttons can be hidden", $("dk-edit").hidden && $("dk-settings").hidden && !$("widgets").hidden);
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_widgets: true, desktop_particles: true, desktop_particle_fps: 20, desktop_visualiser: "wave", desktop_visualiser_fps: 45, max_fps: 60 }));
    T("the frame rate is the fastest thing moving", ForgeFrameCap.fps === 45, ForgeFrameCap.fps);
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_visualiser: "wave", desktop_visualiser_fps: 45, max_fps: 24 }));
    T("never above the Speed page's cap", ForgeFrameCap.fps === 24, ForgeFrameCap.fps);
    // the Alt+P switch is the hub's: the desktop has its own
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { particles_shown: false, desktop_particles: true, particles: "snow", desktop_particle_kind: "same" }));
    T("the hub's Alt+P leaves the desktop's particles alone", Particles.level === "snow", Particles.level);
    // a layout the desktop window saved earlier
    window.FORGE_DESKTOP = { layout: { pages: [{ name: "Mine", items: [{ id: "a", kind: "calendar", x: 0, y: 0, w: 8, h: 4 }] }], page: 0 } };
    W.load(); W.render();
    T("a saved layout comes back as it was", W.pages[0].name === "Mine" && !!document.querySelector(".wg-calendar"));
    window.forgeDesktop({ edit: true });
    T("the extension's Edit desktop widgets starts editing", W.editing);
    W.edit(false);
  } catch (e) {
    T("the checks ran without an error", false, e && (e.message + " " + (e.stack || "").split("\n")[1]));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 500));
