// Appended to a copy of the REAL apps/settings/static/index.html by run.sh,
// served with fixed /api answers made from shared/forge_theme.py. A7: the
// settings are split into sections listed on the left, one page at a time,
// with a search across all of them, and nothing is lost on the way.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const shown = () => sections().filter((s) => !s.hidden).map((s) => s.dataset.title);
  const navBtn = (title) => [...document.querySelectorAll("#nav-list button[data-section]")].find((b) => b.textContent === title);
  try {
    const names = [...document.querySelectorAll("#nav-list button[data-section]")].map((b) => b.textContent);
    T("the list names every section, hand-made and from the table", names[0] === "Wallpaper" && names[1] === "Colour"
      && names.includes("Zen mode") && names.includes("Size") && names[names.length - 1] === "About", names.join(", "));
    T("one section shows at a time", shown().length === 1 && shown()[0] === "Wallpaper", shown().join(", "));
    const missing = Object.entries(state.fields)
      .filter(([k, spec]) => !spec.custom && spec.group && spec.kind !== "keys" && spec.kind !== "presets")
      .filter(([k]) => !document.querySelector(`[data-key="${k}"]`)).map(([k]) => k);
    T("every setting in the table still has its control", missing.length === 0, missing.join(", "));
    navBtn("Zen mode").click();
    T("a click opens that section's page", shown().join() === "Zen mode" && navBtn("Zen mode").classList.contains("on"));
    T("the zen page has its five switches", document.querySelectorAll('section[data-section="zen-mode"] input[type=checkbox]').length === 5);
    T("the address remembers the page", location.hash === "#zen-mode", location.hash);
    const box = $("search");
    box.value = "timer"; box.dispatchEvent(new Event("input"));
    const zen = document.querySelector('section[data-section="zen-mode"]');
    const zenVisible = [...zen.querySelectorAll(".item")].filter((i) => !i.classList.contains("miss")).map((i) => i.textContent.trim());
    T("search shows only matching settings", zenVisible.join() === "Focus timer", zenVisible.join(" | "));
    T("and marks the sections that have a match", navBtn("Zen mode").classList.contains("hit") && !navBtn("Colour").classList.contains("hit"));
    box.value = "accent"; box.dispatchEvent(new Event("input"));
    T("hand-made sections are found by their words", shown().includes("Colour"), shown().join(", "));
    box.value = "size"; box.dispatchEvent(new Event("input"));
    const sizeSec = document.querySelector('section[data-section="size"]');
    T("a section's name shows all of it", !sizeSec.hidden && !sizeSec.querySelector(".item.miss"));
    box.value = "qqzzxx"; box.dispatchEvent(new Event("input"));
    T("no match says so", !$("no-match").hidden && shown().length === 0);
    box.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    T("Esc clears the search and goes back to the page", box.value === "" && shown().join() === "Zen mode" && $("no-match").hidden
      && !document.querySelector(".miss"));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "f", ctrlKey: true, bubbles: true }));
    T("Ctrl+F jumps to the search box", document.activeElement === box);
    box.blur();
    navBtn("Size").click();
    // S12 (2026-09-27): "make the settings app a better layout or customizable"
    const wait = (ms) => new Promise((r) => setTimeout(r, ms));
    const seg = (pref, v) => document.querySelector(`#layout-panel .seg[data-pref="${pref}"] button[data-v="${v}"]`);
    // Emerson (2026-09-27): the Layout menu floated over the top right; it is a section now.
    T("no floating Layout menu in the header", !$("layout-btn") && !document.querySelector("header #layout-panel"));
    navBtn("Layout").click();
    T("Layout is a section of its own", !$("layout-panel").hidden && $("layout-panel").matches('.settings section[data-section="layout"]'));
    seg("nav", "tabs").click();
    const nav = $("nav").getBoundingClientRect(), body = document.querySelector(".settings").getBoundingClientRect();
    T("Tabs puts the sections along the top", document.body.classList.contains("nav-tabs") && nav.bottom <= body.top + 1 && nav.width > body.width * 0.9,
      `nav ${Math.round(nav.width)}x${Math.round(nav.height)} settings top ${Math.round(body.top)}`);
    seg("nav", "page").click();
    const shownNow = [...document.querySelectorAll(".settings section[data-section]")].filter((s) => !s.hidden).length;
    T("One page shows every section", shownNow === document.querySelectorAll(".settings section[data-section]").length && shownNow > 5, shownNow);
    seg("density", "compact").click();
    seg("width", "wide").click();
    T("Compact and Wide apply", document.body.classList.contains("dense") && document.body.classList.contains("wide"));
    const zenPin = [...document.querySelectorAll("#nav-list .item")].find((it) => it.firstChild.textContent === "Zen mode").querySelector(".pin");
    zenPin.click();
    T("a pinned section goes to the top of the list", document.querySelector("#nav-list button[data-section]").textContent === "Zen mode");
    const saved = JSON.parse(localStorage.getItem("forge.settings.layout"));
    T("the layout is remembered", saved.nav === "page" && saved.density === "compact" && saved.pins.length === 1, JSON.stringify(saved));
    $("layout-reset").click();
    T("Reset layout goes back to the sidebar with nothing pinned", !document.body.classList.contains("nav-tabs") && !document.body.classList.contains("nav-page")
      && document.querySelector("#nav-list button[data-section]").textContent !== "Zen mode"
      && [...document.querySelectorAll(".settings section[data-section]")].filter((s) => !s.hidden).length === 1);
    await wait(10);
  } catch (e) {
    T("settings harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 400));
