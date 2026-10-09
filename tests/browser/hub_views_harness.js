// Appended to a copy of the REAL hub/index.html by run.sh, beside the
// hub_immersive fixtures. Checks that an app's native web views
// (forge_views.py) go away with the page that made them: closing the app,
// reloading it, or mounting a fresh frame must send close-owner, or the old
// pages stay alive and visible over the new one (Browser A8, 2026-09-26).
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // Stand-in for forge.py's message channel: record what the hub sends.
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (s) => {
    const m = JSON.parse(s);
    if (m.view) sent.push(m.view);
  } } } };
  const frameOf = (key) => parts[key].inner.querySelector("iframe");
  const fromApp = (key, data) => dispatchEvent(new MessageEvent("message",
    { data: Object.assign({ forge: "view" }, data), source: frameOf(key).contentWindow }));
  const closes = (key) => sent.filter((m) => m.op === "close-owner" && m.owner === key).length;

  try {
    selectWorkspace("tool", { instant: true });
    await wait(50);
    fromApp("tool", { op: "create", id: "a", url: "https://example.com/", rect: [0, 0, 100, 100] });
    const made = sent.find((m) => m.op === "create");
    T("a view request reaches forge.py stamped with its app", made && made.owner === "tool", JSON.stringify(made));

    remount("tool");
    await wait(50);
    T("reloading the app closes the views of the old page", closes("tool") === 1, closes("tool"));

    fromApp("tool", { op: "create", id: "b", url: "https://example.com/", rect: [0, 0, 100, 100] });
    closeWorkspace("tool");
    await wait(50);
    T("closing the app closes its views", closes("tool") === 2, closes("tool"));

    selectWorkspace("prefs", { instant: true });
    remount("prefs");
    closeWorkspace("prefs");
    await wait(50);
    T("an app that never made views sends nothing", closes("prefs") === 0, closes("prefs"));

    selectWorkspace("tool", { instant: true });
    await wait(50);
    T("opening the app again starts clean (no stray close)", closes("tool") === 2, closes("tool"));
  } catch (e) {
    T("harness ran without throwing", false, e && e.stack);
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = out.join("\n");
  document.body.appendChild(pre);
}, 400));
