// Appended to a copy of the REAL hub/index.html by run.sh, beside the two
// fixture files renamed to status.js and theme.js. Checks automatic full
// screen, the top-edge reveal, the dock setting, tinted surfaces, and one app
// opening another by role.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const cls = document.body.classList;
  const bar = document.getElementById("bar");
  const dock = document.getElementById("dock");
  const edge = document.getElementById("bar-edge");
  const style = (el) => getComputedStyle(el);
  const shown = (el) => style(el).display !== "none" && style(el).opacity === "1"
    && style(el).visibility !== "hidden";
  const touchTop = async () => {
    edge.dispatchEvent(new MouseEvent("mouseenter"));
    await wait(theme.reveal_delay + 80);
  };

  try {
    T("the top edge exists", !!edge);

    selectWorkspace("game", { instant: true });
    T("smart: a game opens immersive", cls.contains("immersive"));
    T("smart: the bar is out of the way", !shown(bar), style(bar).opacity);
    T("smart: the dock is out of the way", !shown(dock), style(dock).opacity);

    await touchTop();
    T("touching the top edge brings the bar back", cls.contains("reveal") && shown(bar), style(bar).opacity);
    const numbers = [...document.querySelectorAll("#workspaces .ws")].map((n) => n.dataset.key).join(",");
    T("the revealed bar has every app's icon", numbers === order.join(","), numbers);
    T("the revealed bar shows the clock", /\d/.test(document.getElementById("clock").textContent));
    bar.dispatchEvent(new MouseEvent("mouseleave"));
    await wait(700);
    T("leaving the bar hides it again", !cls.contains("reveal") && !shown(bar));

    selectWorkspace("tool", { instant: true });
    T("smart: a tool keeps its bar", !cls.contains("immersive") && shown(bar));
    selectWorkspace(null, { instant: true });
    T("home is never immersive", !cls.contains("immersive") && shown(bar));

    applyTheme({ auto_fullscreen: "always" });
    selectWorkspace("tool", { instant: true });
    T("always: a tool is immersive too", cls.contains("immersive"));

    applyTheme({ auto_fullscreen: "off" });
    selectWorkspace("game", { instant: true });
    T("off: even a game keeps the bar", !cls.contains("immersive") && shown(bar));

    applyTheme({ auto_fullscreen: "smart" });
    T("changing the setting re-applies to the open app", cls.contains("immersive"));

    applyTheme({ reveal_bar: false });
    await touchTop();
    T("with reveal off the top edge does nothing", !cls.contains("reveal") && !shown(bar));
    applyTheme({ reveal_bar: true });

    const root = style(document.documentElement);
    T("tinted surfaces reach the hub", root.getPropertyValue("--panel").trim() === theme.surfaces.panel,
      root.getPropertyValue("--panel"));

    selectWorkspace("tool", { instant: true });
    applyTheme({ dock: "always" });
    T("dock always: it stays in an app", shown(dock), style(dock).opacity);
    applyTheme({ dock: "hidden" });
    selectWorkspace(null, { instant: true });
    T("dock hidden: not even on home", !shown(dock), style(dock).opacity);
    applyTheme({ dock: "auto" });
    T("dock auto: back on home", shown(dock), style(dock).opacity);

    window.postMessage({ forge: "open", role: "settings" }, "*");
    await wait(60);
    T("an app can open another by role", current === "prefs", current);

    window.postMessage({ forge: "chrome", hidden: true }, "*");
    await wait(60);
    T("an app's own full screen hides the bar", cls.contains("chromeless") && !shown(bar));
    await touchTop();
    T("and the top edge still reveals it", shown(bar), style(bar).opacity);
    window.postMessage({ forge: "chrome", hidden: false }, "*");
    await wait(60);

    // Start apps on demand: opening an app that has not started asks forge.py
    // for it, once, and shows the starting card meanwhile.
    const asked = [];
    window.webkit = { messageHandlers: { forge: { postMessage: (m) => asked.push(JSON.parse(m)) } } };
    forgeSetStatus({ later: { available: false, state: "idle", label: "Later", tagline: "", url: "about:blank",
                              accent: "", icon: "L", role: "", fullscreen: "" } });
    T("an idle app is not asked for before it is opened", asked.length === 0);
    selectWorkspace("later", { instant: true });
    const starts = () => asked.filter((m) => m.start);
    T("opening an idle app asks forge.py to start it",
      starts().length === 1 && starts()[0].start === "later", JSON.stringify(starts()));
    const box = document.querySelector('.workspace[data-workspace="later"]');
    T("it shows the starting card meanwhile", !!box.querySelector(".spinner"));
    forgeSetStatus({ later: { state: "starting" } });
    selectWorkspace("tool", { instant: true });
    selectWorkspace("later", { instant: true });
    T("it is asked for only once", starts().length === 1, starts().length);
    forgeSetStatus({ later: { state: "up", available: true } });
    T("it mounts the app when forge.py reports it up", !!box.querySelector("iframe"));

    // Real web views: an app's request reaches forge.py as that app, with its
    // rect moved into window coordinates; showing is the hub's decision.
    selectWorkspace("tool", { instant: true });
    await wait(60);
    const frame = document.querySelector('.workspace[data-workspace="tool"] iframe');
    asked.length = 0;
    frame.contentWindow.eval('parent.postMessage({forge: "view", op: "create", id: "t1", owner: "someone-else", url: "https://a.org/", rect: [5, 6, 100, 50]}, "*")');
    await wait(80);
    const create = asked.map((m) => m.view).filter((v) => v && v.op === "create")[0];
    const fr = frame.getBoundingClientRect();
    T("an app's view request reaches forge.py as that app", !!create && create.owner === "tool", JSON.stringify(create));
    T("its rect is moved into window coordinates",
      !!create && create.rect[0] === 5 + fr.left && create.rect[1] === 6 + fr.top && create.rect[2] === 100,
      JSON.stringify(create && create.rect));
    asked.length = 0;
    frame.contentWindow.eval('parent.postMessage({forge: "view", op: "owner", owner: "tool"}, "*")');
    await wait(80);
    T("an app cannot choose whose views are shown", !asked.some((m) => m.view && m.view.op === "owner"));
    selectWorkspace(null, { instant: true });
    T("leaving the app hides its views",
      asked.some((m) => m.view && m.view.op === "owner" && m.view.owner === null), JSON.stringify(asked));
    selectWorkspace("tool", { instant: true });
    T("opening it shows them again", asked.some((m) => m.view && m.view.op === "owner" && m.view.owner === "tool"));
    const got = [];
    frame.contentWindow.addEventListener("message", (e) => got.push(e.data));
    forgeViewEvent({ event: "state", id: "t1", owner: "tool", title: "A page" });
    forgeViewEvent({ event: "cookies", id: "", owner: "", count: 3 });
    await wait(80);
    T("page events reach the app that owns the view",
      got.some((d) => d.forge === "view-event" && d.event.title === "A page"), JSON.stringify(got));
    T("profile-wide events reach apps with views",
      got.some((d) => d.forge === "view-event" && d.event.count === 3));
    asked.length = 0;
    peekDock(true);
    T("the peeking dock pushes views up", asked.some((m) => m.view && m.view.op === "inset" && m.view.bottom > 0),
      JSON.stringify(asked));
  } catch (e) {
    T("the harness ran without throwing", false, String(e && e.stack || e));
  }

  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
