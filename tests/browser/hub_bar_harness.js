// Appended to a copy of the REAL hub/index.html by run.sh. The bar's Full
// screen and Close for the open app (S2, A16), with a fake forge.py channel.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  try {
    T("no app controls on the home screen", $("app-ctl").hidden);
    const key = order[0];
    selectWorkspace(key);
    await wait(100);
    T("an open app shows Full screen and Close on the bar", !$("app-ctl").hidden && $("full-btn").offsetWidth > 0 && $("close-btn").offsetWidth > 0);
    const t = $("title").getBoundingClientRect(), c = $("app-ctl").getBoundingClientRect();
    T("they sit beside the title", Math.abs(c.left - t.right) < 20 && Math.abs((c.top + c.bottom) / 2 - (t.top + t.bottom) / 2) < 6, `title right ${Math.round(t.right)}, controls left ${Math.round(c.left)}`);
    $("full-btn").click();
    T("Full screen asks forge.py for the window", sent.some((m) => m.window === true), JSON.stringify(sent.filter((m) => "window" in m)));
    window.forgeSetFullscreen(true);
    T("in full screen the button offers the way back", $("full-btn").textContent.includes("Exit full screen"));
    T("and the bar gets out of the way", document.body.classList.contains("chromeless"));
    $("full-btn").click();
    T("Exit full screen asks for the window back", sent.filter((m) => "window" in m).pop().window === false);
    window.forgeSetFullscreen(false);
    $("close-btn").click();
    await wait(100);
    T("Close goes home", current === null);
    T("and stops the app's backend", sent.some((m) => m.stop === key), JSON.stringify(sent.filter((m) => m.stop)));
    T("the controls hide again at home", $("app-ctl").hidden);

    // A13 + A11: the row of open apps, and Alt+1..9 / Alt+Left/Right along it.
    const [a, b] = order;
    selectWorkspace(a); await wait(60);
    selectWorkspace(b); await wait(60);
    const row = rowKeys();
    T("the bar shows each open app once, in a row", row.length === 2 && row[0] === a && row[1] === b, row.join(","));
    const wsA = parts[a].ws;
    T("a marker is the app's icon, not a number",
      (wsA.querySelector("svg.forge-glyph") || wsA.textContent === iconFor(infoFor(a), a)) && !/^[0-9]+$/.test(wsA.textContent), wsA.innerHTML.slice(0, 60));
    T("its tooltip names the app and its key", wsA.title === `${infoFor(a).label} (Alt+1)`, wsA.title);
    T("the app in front has a glow ring", getComputedStyle(parts[b].ws).boxShadow !== "none");
    window.forgeKey("app-1");
    T("Alt+1 opens the first app in the row", current === a);
    window.forgeKey("next-app");
    T("Alt+Right steps along the row", current === b);
    window.forgeKey("next-app");
    T("and wraps round at the end", current === a);
    window.forgeKey("prev-app");
    T("Alt+Left steps back (wrapping)", current === b);
    window.forgeKey("app-9");
    T("an Alt+number past the row does nothing", current === b);
    const frameA = parts[a].inner.querySelector("iframe");
    dispatchEvent(new MessageEvent("message", { data: { forge: "news", on: true }, source: frameA.contentWindow }));
    T("an app behind can flag news on its icon", wsA.classList.contains("news"));
    dispatchEvent(new MessageEvent("message", { data: { forge: "busy", on: true }, source: frameA.contentWindow }));
    T("and say it is busy", wsA.classList.contains("busy"));
    window.forgeKey("app-1");
    T("opening it clears the news", !wsA.classList.contains("news"));
    selectWorkspace(null);
    await wait(60);
    applyTheme({ hub_keys: { overview: "Alt+Down" } });
    T("new Forge keys from Settings go to forge.py at once", sent.some((m) => m.keys && m.keys.overview === "Alt+Down"));
    const n = sent.filter((m) => m.keys).length;
    applyTheme({ accent: "#88a7d3" });
    T("an unrelated theme change does not resend them", sent.filter((m) => m.keys).length === n);
  } catch (e) {
    T("bar harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
