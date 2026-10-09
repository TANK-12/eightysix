// Appended to a copy of the REAL hub/index.html by run.sh. S21 (2026-09-27),
// Emerson: "make the alt space thing also have an app search so i can open
// apps from inside it". Fixture: tool, game, prefs (hub_immersive_status.js).
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const keys = (sel) => [...document.querySelectorAll(sel)].map((c) => c.dataset.key);
  const type = (text) => { $("ov-search").value = text; $("ov-search").dispatchEvent(new Event("input")); };
  const press = (key) => document.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true }));
  try {
    Overview.show();
    await wait(50);
    T("Alt+Space opens with a search box", Overview.open && !!$("ov-search"));
    T("with nothing open it lists every app to start", keys("#ov-apps .ov-card").sort().join() === "game,prefs,tool", keys("#ov-apps .ov-card").join());
    press("g");
    T("a letter jumps into the search", document.activeElement === $("ov-search"));
    type("ga");
    T("typing narrows it to the matches", keys("#ov-apps .ov-card").join() === "game", keys("#ov-apps .ov-card").join());
    type("settings");
    T("a tagline matches too", keys("#ov-apps .ov-card").join() === "prefs", keys("#ov-apps .ov-card").join());
    type("zzz");
    T("no match says so", /No app by that name/.test($("ov-grid").textContent));
    press("Escape");
    T("Esc first clears the search", Overview.open && $("ov-search").value === "" && keys("#ov-apps .ov-card").length === 3);
    type("tool");
    press("Enter");
    await wait(300);
    T("Enter opens the best match", !Overview.open && current === "tool", String(current));
    Overview.show();
    await wait(300);
    T("an open app shows as a card, the rest wait for a search", keys("#ov-grid .ov-card").join() === "tool" && keys("#ov-apps .ov-card").length === 0,
      keys("#ov-grid .ov-card").join() + " / " + keys("#ov-apps .ov-card").join());
    type("g");
    T("a search lists open apps and the others that match", keys("#ov-apps .ov-card").join() === "game", keys("#ov-apps .ov-card").join());
    press("Escape"); press("Escape");
    T("Esc twice closes it", !Overview.open);
  } catch (e) {
    T("overview search harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
