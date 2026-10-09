// Appended to a copy of the REAL hub/index.html by run.sh, with thirty apps
// (hub_bar_many_status.js). Emerson (2026-10-07): opening many apps pushed
// the clock, settings and the other tray buttons off the right of the bar.
// The open-app icons now scroll sideways inside their strip, and a "+N"
// button beside it says how many are out of sight and opens the overview.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + innerWidth + "px " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const box = (n) => n.getBoundingClientRect();
  const seen = (n) => { const b = box(n); return b.width > 0 && b.left >= 0 && b.right <= innerWidth + 0.5 && b.top >= 0; };
  // inside the strip, keeping `edge` px clear of an end that fades (".ws-more-l/r" on the bar)
  const inStrip = (n, edge = 0) => {
    const s = box($("workspaces")), b = box(n), c = $("bar").classList;
    const l = c.contains("ws-more-l") ? edge : 0, r = c.contains("ws-more-r") ? edge : 0;
    return b.left >= s.left + l - 3 && b.right <= s.right - r + 3; // 3: the front icon's 1.08 scale
  };
  const clearOfFade = (n) => strip.clientWidth < n.offsetWidth + 2 * Strip.fade() || inStrip(n, Strip.fade());
  const outCount = () => rowKeys().filter((k) => !inStrip(parts[k].ws, Strip.fade() / 2)).length;
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  const strip = $("workspaces"), more = $("ws-more");
  try {
    T("no '+N' button with nothing open", more.hidden || more.offsetWidth === 0);
    selectWorkspace(order[0], { instant: true });
    selectWorkspace(order[1], { instant: true });
    await wait(60);
    if (innerWidth >= 800) {
      T("two open apps fit: no '+N' button", more.offsetWidth === 0, more.textContent);
      T("and no fade at either end", !$("bar").classList.contains("ws-more-l") && !$("bar").classList.contains("ws-more-r"));
    }
    for (const k of order) { selectWorkspace(k, { instant: true }); await wait(5); }
    await wait(400); // past the icon's pop-in
    const last = order[order.length - 1];
    T("all thirty apps are open on the bar", rowKeys().length === 30, rowKeys().length);
    const bar = box($("bar"));
    T("the bar is no wider than the window", bar.right <= innerWidth + 0.5, Math.round(bar.right));
    for (const id of ["home-btn", "tray", "clock", "size-btn", "settings-btn", "full-btn", "close-btn"])
      T(`#${id} stays on screen`, seen($(id)), JSON.stringify(box($(id))).slice(0, 80));
    T("the tray ends inside the bar", box($("tray")).right <= bar.right + 0.5, `${Math.round(box($("tray")).right)} vs ${Math.round(bar.right)}`);
    T("the icons scroll inside their strip instead", strip.scrollWidth > strip.clientWidth, `${strip.scrollWidth} > ${strip.clientWidth}`);
    T("the app in front is scrolled into view, clear of the fade", clearOfFade(parts[last].ws), strip.clientWidth);
    const hiddenCount = outCount();
    T("a '+N' button shows how many are out of sight", more.offsetWidth > 0 && seen(more) && more.textContent === "+" + hiddenCount,
      `"${more.textContent}" for ${hiddenCount}`);
    T("the strip fades at the end with more icons", $("bar").classList.contains("ws-more-l"));
    if (innerWidth >= 800) T("the title keeps some room", box($("title")).width >= 60, Math.round(box($("title")).width));
    window.forgeKey("app-1");
    await wait(1200); // a smooth scroll the whole strip long
    T("Alt+1 brings the first icon back into view", current === order[0] && clearOfFade(parts[order[0]].ws), strip.clientWidth);
    T("the fade moves to the other end", $("bar").classList.contains("ws-more-r") && !$("bar").classList.contains("ws-more-l"), $("bar").className + " sl " + strip.scrollLeft);
    const x = strip.scrollLeft;
    strip.dispatchEvent(new WheelEvent("wheel", { deltaY: 120, bubbles: true, cancelable: true }));
    await wait(400);
    T("the mouse wheel scrolls the icons sideways", strip.scrollLeft > x, `${x} -> ${strip.scrollLeft}`);
    // Alt+Left from the first app wraps to the last, then steps back along
    // icons that were out of sight: each one lands clear of the fades
    const bad = [];
    for (let i = 0; i < 6; i++) {
      window.forgeKey("prev-app");
      await wait(1200);
      if (!clearOfFade(parts[current].ws)) bad.push(current);
    }
    T("Alt+Left lands each app clear of the fades", !bad.length, bad.join(","));
    window.forgeKey("app-1");
    await wait(1200);

    // a hidden app with news or a failed backend marks the "+N" button
    const far = parts[order[order.length - 2]].ws;
    far.classList.add("news");
    await wait(60);
    T("news on an app out of sight puts a dot on '+N'", more.classList.contains("news") && /news/.test(more.title), more.className);
    far.classList.remove("news");
    far.classList.add("failed");
    await wait(60);
    T("so does a failed one", more.classList.contains("failed") && !more.classList.contains("news"), more.className);
    far.classList.remove("failed");
    await wait(60);
    T("and the dot goes when they clear", !more.classList.contains("failed"), more.className);

    // bigger icons: the strip keeps its box, the count must still follow
    applyTheme({ icon_scale: 1.6 });
    await wait(100);
    T("'+N' follows a bigger icon size", more.textContent === "+" + outCount(), `"${more.textContent}" for ${outCount()}`);
    applyTheme({ icon_scale: 1 });
    await wait(100);

    // every bar width from 500 px up, at text size 1 and 1.5: the tray and
    // the clock stay inside the bar (the bar is narrowed in place; a window
    // narrower than 500 px is not possible headless)
    const fails = [];
    const right0 = getComputedStyle($("bar")).right;
    for (const text of [1, 1.5]) {
      if (window.ForgeText) ForgeText.apply(text);
      for (let w = 500; w <= Math.min(innerWidth, 1400); w += 20) {
        $("bar").style.right = (innerWidth - 10 - w) + "px";
        Strip.measure();
        const b = box($("bar"));
        for (const id of ["tray", "clock", "settings-btn", "size-btn", "home-btn"]) {
          const r = box($(id));
          if (r.width === 0 || r.right > b.right + 0.5 || r.left < b.left - 0.5) fails.push(`${id}@${w}x${text}`);
        }
      }
    }
    if (window.ForgeText) ForgeText.apply(1);
    $("bar").style.right = "";
    Strip.measure();
    T("at every width from 500 px and text size 1 and 1.5 the tray stays in the bar", !fails.length, fails.slice(0, 12).join(" ") + " right0 " + right0);
    T("widest: nothing tucked away", innerWidth < 1400 || !$("bar").className.includes("tight-"), $("bar").className);

    more.click();
    await wait(1600);
    T("'+N' opens the overview of every open app", Overview.open);
    if (Overview.open) Overview.close();
  } catch (e) {
    T("bar overflow harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
