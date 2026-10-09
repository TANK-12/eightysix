// Appended to a copy of the REAL hub/index.html by run.sh, which loads it at
// the CSS widths App size produces (1400 and 390 window pixels at 100, 125 and
// 150%). Checks App size goes to forge.py as window zoom rather than to the
// apps as CSS zoom, and that nothing on the page runs off its sides.
addEventListener("load", () => setTimeout(() => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const w = innerWidth;
  try {
    const sent = [];
    window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
    applyTheme({ ui_scale: 1.25 });
    T(`[${w}px] App size goes to forge.py as window zoom`, sent.some((m) => m.zoom === 1.25), JSON.stringify(sent));
    applyTheme({ ui_scale: 1.25 });
    T(`[${w}px] an unchanged size is not sent again`, sent.filter((m) => "zoom" in m).length === 1);
    T(`[${w}px] apps are not handed a CSS zoom`, !("ui_scale" in appTheme()));
    applyTheme({ ui_scale: 1 });

    const doc = document.documentElement;
    T(`[${w}px] no sideways scroll`, doc.scrollWidth <= doc.clientWidth, `scrollWidth=${doc.scrollWidth} clientWidth=${doc.clientWidth}`);
    const off = [...document.querySelectorAll("#bar *, #home *")].filter((el) => {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height || getComputedStyle(el).visibility === "hidden") return false;
      return r.right > w + 1 || r.left < -1;
    });
    T(`[${w}px] nothing on the bar or home screen runs off the sides`, off.length === 0,
      off.slice(0, 3).map((el) => (el.id || el.className || el.tagName) + "@" + Math.round(el.getBoundingClientRect().right)).join(", "));
  } catch (e) {
    T(`[${w}px] harness ran`, false, String(e));
  }
  if (w < 1400) return finish();

  // Text size, Icon size and the Aa panel: once, at full width.
  (async () => {
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const sent = [];
    window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
    try {
      const px = (el) => parseFloat(getComputedStyle(el).fontSize);
      const clock = $("clock"), tile = document.querySelector(".tile"), icon = document.querySelector(".tile .icon");
      const f0 = px(clock), tw0 = tile.getBoundingClientRect().width, iw0 = icon.getBoundingClientRect().width;
      applyTheme({ text_scale: 1.3 });
      await wait(50);
      T("Text size grows the letters", Math.abs(px(clock) - f0 * 1.3) < 0.6, `${f0}px -> ${px(clock)}px`);
      T("Text size leaves the boxes alone", Math.abs(tile.getBoundingClientRect().width - tw0) < 1, `${tw0} -> ${tile.getBoundingClientRect().width}`);
      T("apps are handed the text size", appTheme().text_scale === 1.3);
      applyTheme({ text_scale: 1, icon_scale: 1.5 });
      await wait(50);
      T("Icon size grows the tile icons", Math.abs(icon.getBoundingClientRect().width - iw0 * 1.5) < 1, `${iw0} -> ${icon.getBoundingClientRect().width}`);
      T("Text size back at 1 restores the letters", Math.abs(px(clock) - f0) < 0.3, `${px(clock)}px`);
      applyTheme({ icon_scale: 1, ui_scale: 1, size_presets: [
        { name: "Small", ui_scale: 0.9, text_scale: 0.9, icon_scale: 0.9 },
        { name: "Default", ui_scale: 1, text_scale: 1, icon_scale: 1 },
        { name: "Extra large", ui_scale: 1.25, text_scale: 1.4, icon_scale: 1.4 }] });

      $("size-btn").click();
      T("the Aa button opens the size panel", !$("size-panel").hidden);
      T("the panel shows the preset in use", $("sz-preset-name").textContent === "Default", $("sz-preset-name").textContent);
      const range = $("sz-preset");
      // Dragged, a preset only previews: no zoom, nothing saved (2026-10-07).
      range.value = 2; range.dispatchEvent(new Event("input"));
      await wait(400);
      T("a dragged preset shows its name", $("sz-preset-name").textContent === "Extra large", $("sz-preset-name").textContent);
      T("a dragged preset neither zooms nor saves", !sent.some((m) => "zoom" in m || m.settings), JSON.stringify(sent));
      T("a dragged preset leaves the theme alone", theme.ui_scale === 1);
      range.dispatchEvent(new Event("change"));
      await wait(700); // applied 150 ms after release, saved 250 ms after that
      T("a preset sets all three sizes", theme.ui_scale === 1.25 && theme.text_scale === 1.4 && theme.icon_scale === 1.4);
      const saved = sent.filter((m) => m.settings).map((m) => m.settings);
      T("the preset is saved through forge.py", saved.some((b) => b.ui_scale === 1.25 && b.text_scale === 1.4 && b.icon_scale === 1.4), JSON.stringify(saved));
      T("and App size goes to the window zoom", sent.some((m) => m.zoom === 1.25));
      $("sz-text_scale-n").value = "1.2"; $("sz-text_scale-n").dispatchEvent(new Event("change"));
      T("a typed size moves off the preset", $("sz-preset-name").textContent === "Your own mix");
      $("sz-name").value = "Night reading";
      $("sz-save").dispatchEvent(new Event("submit", { cancelable: true }));
      await wait(400);
      const mine = theme.size_presets.filter((p) => p.mine);
      T("Save as custom adds your mix to the list", mine.length === 1 && mine[0].name === "Night reading" && mine[0].text_scale === 1.2);
      T("and saves it without the marker", sent.some((m) => m.settings && Array.isArray(m.settings.size_presets) && m.settings.size_presets[0].name === "Night reading" && !("mine" in m.settings.size_presets[0])));
      T("the panel now names it", $("sz-preset-name").textContent === "Night reading");
      if (!location.hash.includes("shot")) { $("size-btn").click(); }
    } catch (e) {
      T("size harness ran", false, String(e && e.stack || e));
    }
    finish();
  })();
  return;
  function finish() {
  // Headless Chrome will not open a window under 500px, so phone widths run
  // in frames of hub_scale_narrow.html, which collects these lines.
  if (parent !== window) parent.postMessage({ hubScale: out }, "*");
  document.body.insertAdjacentHTML("beforeend", "<pre id='results'>RESULTS\n" + out.join("\n") + "\n</pre>");
  }
}, 300));
