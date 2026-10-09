// Appended to a copy of the REAL hub/index.html by run.sh. S7 polish pass:
// typing into text boxes, hidden and archived apps, the media popup, zen.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const press = (el, key) => el.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true }));
  try {
    // A13: a text box in a panel keeps its own typing.
    $("size-btn").click();
    await wait(50);
    $("sz-name").focus();
    press($("sz-name"), "a");
    T("typing in the preset name box stays in that box", document.activeElement === $("sz-name"), document.activeElement && document.activeElement.id);
    $("sz-name").blur();
    $("size-btn").click();
    await wait(50);
    document.body.focus();
    press(document.body, "n");
    T("typing on the bare home screen still goes to search", document.activeElement === $("search"));
    $("search").blur();

    // A25: popups close on a click outside or Esc, with a short fade.
    applyTheme({ animations: true });
    $("size-btn").click();
    await wait(60);
    T("the size panel opens", !$("size-panel").hidden);
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    T("a click outside starts it fading", $("size-panel").classList.contains("closing") && !$("size-panel").hidden);
    await wait(400);
    T("and then it is gone", $("size-panel").hidden && !$("size-panel").classList.contains("closing"));
    $("size-btn").click();
    await wait(60);
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wait(400);
    T("Esc closes it too", $("size-panel").hidden);
    applyTheme({ animations: false });

    // A6: hide and archive.
    const [k1, k2, k3] = ["app01", "app02", "app03"];
    applyTheme({ hidden_apps: [k1], archived_apps: [k2] });
    await wait(30);
    const hiddenBox = $("tiles").querySelector('[data-section="__hidden"]');
    T("a hidden app's tile moves to the Hidden section", !!hiddenBox && hiddenBox.contains(parts[k1].tile));
    T("which starts folded away", hiddenBox && hiddenBox.classList.contains("collapsed"));
    T("a hidden app leaves the dock", getComputedStyle(parts[k1].dock).display === "none");
    T("an archived app's tile is gone", parts[k2].tile.offsetParent === null);
    T("and its dock icon", getComputedStyle(parts[k2].dock).display === "none");
    T("archived apps drop out of numbers and keys", !shown().includes(k2) && shown().includes(k1));
    $("search").value = "App 1"; filterTiles("App 1");
    T("search still finds a hidden app", parts[k1].tile.offsetParent !== null && !parts[k1].tile.classList.contains("nomatch"));
    $("search").value = "App 2"; filterTiles("App 2");
    T("but not an archived one", parts[k2].tile.offsetParent === null);
    $("search").value = ""; filterTiles("");

    // The right-click menu.
    sent.length = 0;
    parts[k3].tile.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 200, clientY: 300 }));
    await wait(30);
    const menu = $("app-menu");
    T("right-click on a tile opens its menu", menu && !menu.hidden);
    const items = menu ? [...menu.querySelectorAll("button")].map((b) => b.textContent) : [];
    T("with Hide and Archive", items.some((t) => /Hide from home/.test(t)) && items.some((t) => /Archive/.test(t)), items.join(" | "));
    T("and Pop out (A22)", items.some((t) => /Pop out/.test(t)), items.join(" | "));
    [...menu.querySelectorAll("button")].find((b) => /Hide from home/.test(b.textContent)).click();
    await wait(300);
    T("Hide from home saves the list", sent.some((m) => m.settings && Array.isArray(m.settings.hidden_apps) && m.settings.hidden_apps.includes(k3)), JSON.stringify(sent));
    T("and the menu closes", menu.hidden);
    selectWorkspace(k3);
    await wait(60);
    parts[k3].dock.dispatchEvent(new MouseEvent("contextmenu", { bubbles: true, clientX: 300, clientY: 800 }));
    await wait(30);
    [...menu.querySelectorAll("button")].find((b) => /^Archive/.test(b.textContent)).click();
    await wait(300);
    T("archiving the open app closes it and goes home", current === null && sent.some((m) => m.stop === k3));
    T("and saves the archive list", sent.some((m) => m.settings && (m.settings.archived_apps || []).includes(k3)));
    applyTheme({ hidden_apps: [], archived_apps: [] });

    // A23: the dock fits, and its pop-up can be turned off or waits a moment.
    applyTheme({ icon_scale: 1.6, dock: "always" });
    await wait(60);
    const d = $("dock").getBoundingClientRect();
    T("a full dock at the biggest icons stays on screen", d.left >= 0 && d.right <= innerWidth + 0.5, `${Math.round(d.left)}..${Math.round(d.right)} of ${innerWidth}`);
    applyTheme({ icon_scale: 1, dock: "hidden" });
    selectWorkspace("app05");
    await wait(60);
    $("dock-edge").dispatchEvent(new MouseEvent("mouseenter"));
    await wait(80);
    T("brushing the bottom edge does not pop the dock at once", !$("dock").classList.contains("peek"));
    await wait(600);
    T("resting there does", $("dock").classList.contains("peek"));
    $("dock").dispatchEvent(new MouseEvent("mouseleave"));
    await wait(700);
    applyTheme({ dock: "off" });
    $("dock-edge").dispatchEvent(new MouseEvent("mouseenter"));
    await wait(700);
    T("with the dock off it never pops up", !$("dock").classList.contains("peek") && getComputedStyle($("dock-edge")).display === "none");
    selectWorkspace(null);
    await wait(60);
    T("and it stays off on the home screen too", getComputedStyle($("dock")).display === "none" || getComputedStyle($("dock")).opacity === "0");

    // A16: full screen fills the window whatever look is on. Material and
    // Brain move the app area down for their own bar, and used to win, which
    // left an empty band at the top in full screen.
    for (const look of ["classic", "material", "brain", "hyprland", "minimal"]) {
      applyTheme({ look });
      await wait(150);
      selectWorkspace("app06");
      window.forgeSetFullscreen(true);
      await wait(60);
      const st = $("stage").getBoundingClientRect();
      T(`full screen fills the window in the ${look} look`, Math.abs(st.top) < 0.5 && Math.abs(st.left) < 0.5 && Math.abs(st.bottom - innerHeight) < 0.5 && Math.abs(st.right - innerWidth) < 0.5,
        `${Math.round(st.left)},${Math.round(st.top)} ${Math.round(st.right)}x${Math.round(st.bottom)} of ${innerWidth}x${innerHeight}`);
      const ws = getComputedStyle(parts.app06.box);
      T(`and no frame is left round the app in the ${look} look`, parseFloat(ws.paddingTop) === 0 && parseFloat(ws.borderTopLeftRadius) === 0, `${ws.paddingTop} ${ws.borderTopLeftRadius}`);
      window.forgeSetFullscreen(false);
      selectWorkspace(null);
    }
    applyTheme({ look: "classic" });

    // A9/A30: Now playing, for every player in Forge and on the desktop.
    const mk = "app08";
    selectWorkspace(mk); await wait(60); selectWorkspace(null); await wait(30);
    const mframe = parts[mk].inner.querySelector("iframe");
    const got = [];
    mframe.contentWindow.postMessage = (m) => got.push(m);
    dispatchEvent(new MessageEvent("message", { source: mframe.contentWindow, data: { forge: "media",
      state: "playing", title: "Lofi mix", artist: "daymoon", current: 10, duration: 100, volume: 1,
      canBoost: true, canNext: false, canPrev: true, kind: "video" } }));
    await wait(30);
    T("an app playing lights the bar's music button", !$("music-btn").hidden && $("music-btn").classList.contains("on") && /Lofi mix/.test($("music-btn").title), $("music-btn").title);
    $("music-btn").click(); await wait(60);
    T("the popup names what is playing and where", /Lofi mix/.test($("np-title").textContent) && /App 8/.test($("np-sub").textContent), $("np-sub").textContent);
    $("np-toggle").click();
    T("its pause goes to that app", got.some((m) => m.forge === "media-cmd" && m.op === "toggle"), JSON.stringify(got));
    $("np-seek").value = "500"; $("np-seek").dispatchEvent(new Event("change"));
    T("seeking sends a time", got.some((m) => m.op === "seek" && Math.abs(m.time - 50) < 1), JSON.stringify(got));
    T("an app's own media can be turned up past 100%", Number($("np-vol").max) === 200);
    $("np-vol").value = "150"; $("np-vol").dispatchEvent(new Event("input"));
    T("and the volume goes to the app", got.some((m) => m.op === "volume" && Math.abs(m.volume - 1.5) < 0.01));
    $("np-go").click(); await wait(250);
    T("Go to it opens the app and closes the popup", current === mk && $("music-panel").hidden);
    selectWorkspace(null); await wait(30);
    window.forgeMediaSys([{ bus: "org.mpris.MediaPlayer2.firefox.instance_1", name: "Firefox", desktop: "firefox",
      state: "playing", title: "A video", artist: "", artwork: "", duration: 60, position: 5, volume: 1,
      canRaise: false, canNext: true, canPrev: true, canSeek: true }]);
    sent.length = 0;
    $("music-btn").click(); await wait(60);
    T("opening it asks forge.py for the desktop's players", sent.some((m) => m.media && m.media.op === "list"));
    const row = [...$("np-list").querySelectorAll(".np-row")].find((r) => /Firefox/.test(r.textContent))
      || ($("np-sub").textContent.includes("Firefox") ? $("np-main") : null);
    T("other players on the desktop show too", !!row);
    const tg = [...$("np-list").querySelectorAll(".np-row")].find((r) => /Firefox/.test(r.textContent));
    if (tg) tg.querySelector(".np-row-toggle").click(); else $("np-toggle").click();
    T("and can be paused from here", sent.some((m) => m.media && m.media.op === "toggle" && /firefox/.test(m.media.bus)), JSON.stringify(sent));
    dispatchEvent(new MessageEvent("message", { source: mframe.contentWindow, data: { forge: "media", state: "gone" } }));
    await wait(30);
    T("an app that goes away leaves the list", !NowPlaying.sources["app:" + mk]);
    Popup.close($("music-panel")); await wait(250);
    window.forgeMediaSys([]);

    // Tools' ask: one app opening another at a place.
    const target = "app07";
    dispatchEvent(new MessageEvent("message", { data: { forge: "open", app: target, hash: "cwd=/home/ejb/x y" } }));
    await wait(60);
    const tf = parts[target].inner.querySelector("iframe");
    T("an open request with a hash opens the app at that place", current === target && tf && tf.src.endsWith("#cwd=/home/ejb/x y".replace(/ /g, "%20")), tf && tf.src);
    selectWorkspace(null);
  } catch (e) {
    T("polish harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
