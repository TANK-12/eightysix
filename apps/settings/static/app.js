/* Settings frontend.
 *
 * Every control carries data-key naming a setting in shared/forge_theme.py.
 * A change is saved (debounced), the backend answers with the theme it
 * produces, and that theme is posted to the Forge hub, which applies it at
 * once and passes it on to every open app.
 */

const $ = (id) => document.getElementById(id);
const state = { settings: null, fields: null, theme: null, walls: [], pending: {}, timer: null, section: "", onBattery: null, dragging: false, previewing: {}, saving: false, again: false, resetting: false, epoch: 0 };

// An error says whether it is worth trying again: `offline` when the backend
// did not answer (stopped, restarting) rather than refused the request.
async function api(path, options) {
  let r;
  try {
    r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  } catch (e) {
    throw Object.assign(new Error("the Settings backend is not answering"), { offline: true });
  }
  if (!r.ok) {
    let detail = r.statusText;
    try {
      const d = (await r.json()).detail;
      if (typeof d === "string") detail = d;
      else if (Array.isArray(d)) detail = d.map((x) => x.msg).join("; ");
    } catch (e) {}
    throw Object.assign(new Error(detail || `error ${r.status}`), { status: r.status, offline: r.status >= 502 });
  }
  return r.json();
}

function saidStatus(text) {
  $("saved").textContent = text;
  $("saved").title = text;
}

function tellHub(theme) {
  try { window.parent.postMessage({ forge: "theme", theme }, "*"); } catch (e) {}
}

function thumbUrl(name) { return `/api/wallpapers/${encodeURIComponent(name)}/thumb`; }

function change(key, value) {
  state.settings[key] = value;
  state.pending[key] = value;
  saidStatus("Saving…");
  clearTimeout(state.timer);
  state.timer = setTimeout(flush, 180);
  renderControls();
}

/* One save at a time, so answers cannot arrive out of order and put back an
   older value; changes made meanwhile go in the next one. When the backend
   is away the change is kept, not dropped, and sent again with a growing
   wait (2 s up to 30 s) that rests while Settings is hidden. Returns false
   when it could not save. */
let retry = null;
async function flush() {
  clearTimeout(state.timer);
  if (state.resetting) return true;  // the reset decides what is kept
  if (state.saving) { state.again = true; return true; }
  const body = state.pending;
  if (!Object.keys(body).length) { stopRetry(); return true; }
  state.pending = {};
  state.saving = true;
  const epoch = state.epoch;
  let ok = true;
  try {
    const r = await api("/api/settings", { method: "POST", body: JSON.stringify(body) });
    stopRetry();
    if (epoch !== state.epoch) return true;  // a reset answered since: its values stand
    accept(r);
    saidStatus(Object.keys(state.pending).length ? "Saving…" : "Saved");
  } catch (e) {
    ok = false;
    if (e.offline) {
      state.pending = { ...body, ...state.pending };
      saidStatus("Not saved yet: the backend is not answering. Trying again by itself…");
      startRetry();
    } else {
      saidStatus("Not saved: " + e.message);
    }
  } finally {
    state.saving = false;
  }
  const more = state.again || Object.keys(state.pending).length;
  state.again = false;
  if (ok && more) return flush();
  if (!ok && !retry) refreshSoon();  // refused: show what is really stored
  return ok;
}

function startRetry() {
  if (retry || !window.ForgeIdle) return;
  retry = ForgeIdle.poll(flush, 2000, { backoff: 2, maxMs: 30000 });
}

function stopRetry() {
  if (retry) retry.stop();
  retry = null;
}

function accept(r) {
  // Anything changed or dragged here since the request left stays as it is.
  state.settings = Object.assign(r.settings, state.previewing, state.pending);
  state.theme = r.theme;
  tellHub(r.theme);
  render();
}

/* ------------------------------------------------------------- wallpaper */

// A thumbnail that cannot be had (a desktop picture outside the wallpaper
// folder, a file gone since the listing) shows the plain tile, not a broken
// image: an empty picture keeps the tile's size, border and background.
const NO_THUMB = "data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==";
function noThumb(img) {
  if (img.getAttribute("src") !== NO_THUMB) img.src = NO_THUMB;
}

function thumbInto(img, name, tile) {
  img.addEventListener("error", () => {
    noThumb(img);
    if (tile) tile.classList.add("no-thumb");
  });
  img.src = thumbUrl(name);
}

function buildWalls() {
  const grid = $("walls");
  grid.innerHTML = "";
  state.walls.forEach((w) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "wall";
    item.dataset.name = w.name;
    item.title = w.name;
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "";
    thumbInto(img, w.name, item);
    const label = document.createElement("span");
    label.className = "name";
    label.textContent = w.name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    item.append(img, label);
    item.addEventListener("click", () => change("wallpaper", w.name));
    grid.appendChild(item);
  });
}

function renderWallpaper() {
  const t = state.theme;
  const name = t.wallpaper_name || "";
  $("current-name").textContent = name ? name.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ") : "No wallpaper found";
  $("current-note").textContent = t.follows_desktop
    ? "Following your desktop — it changes when the desktop's does."
    : `Chosen here · ${name}`;
  const thumb = $("current-thumb");
  if (name !== thumb.dataset.name) {
    thumb.dataset.name = name;
    if (name) thumb.src = thumbUrl(name);
    else noThumb(thumb);
  }
  $("follow-desktop").checked = !!t.follows_desktop;
  document.querySelectorAll(".wall").forEach((item) =>
    item.classList.toggle("on", item.dataset.name === name));
}

// Favourites are starred in the Wallpapers app; they are re-read whenever this
// page comes back into view, so a star added there shows here.
async function loadFavourites() {
  let names = [];
  try { names = (await api("/api/favourites")).favourites; } catch (e) {}
  const box = $("favs");
  box.replaceChildren();
  if (!names.length) {
    const hint = document.createElement("div");
    hint.className = "muted small";
    hint.textContent = "No favourites yet: star wallpapers in the Wallpapers app to keep them here.";
    box.appendChild(hint);
    return;
  }
  names.forEach((name) => {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "wall fav";
    item.dataset.name = name;
    item.title = name;
    const img = document.createElement("img");
    img.loading = "lazy";
    img.alt = "";
    thumbInto(img, name, item);
    const label = document.createElement("span");
    label.className = "name";
    label.textContent = name.split("/").pop().replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");
    item.append(img, label);
    item.addEventListener("click", () => change("wallpaper", name));
    box.appendChild(item);
  });
  if (state.theme) renderWallpaper();
}

$("current-thumb").addEventListener("error", (e) => noThumb(e.target));

$("open-wallpapers").addEventListener("click", () => {
  if (window.parent !== window) {
    window.parent.postMessage({ forge: "open", role: "wallpapers" }, "*");
  } else {
    window.open("http://127.0.0.1:8442/", "_blank");
  }
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadFavourites(); });

/* Settings are also changed elsewhere: the Power app's frame-rate sliders, the
   bar's size panel. The hub passes every new theme to each open app, and says
   whether the laptop is on battery, so this page re-reads the settings then,
   and when it comes back into view. Not while a change of its own is saving. */
let refreshTimer = 0;
function refreshSoon() {
  clearTimeout(refreshTimer);
  refreshTimer = setTimeout(async () => {
    const busy = () => state.dragging || state.saving || Object.keys(state.pending).length;
    if (!state.settings || busy()) return;
    try {
      const s = await api("/api/settings");
      if (busy()) return;
      state.settings = s.settings;
      state.theme = s.theme;
      render();
    } catch (e) {}
  }, 300);
}
window.addEventListener("message", (event) => {
  const msg = event.data;
  if (event.source !== window.parent || window.parent === window || !msg || msg.forge !== "theme") return;
  // forge_chrome.js has just applied the hub's text size: keep a drag's preview.
  if (state.dragging) showPreviews(state.previewing);
  if (msg.theme && typeof msg.theme.on_battery === "boolean" && msg.theme.on_battery !== state.onBattery) {
    state.onBattery = msg.theme.on_battery;
    markPowerNow();
  }
  refreshSoon();
});
document.addEventListener("visibilitychange", () => { if (!document.hidden) refreshSoon(); });
document.addEventListener("forge-visible", (e) => { if (e.detail && e.detail.visible) refreshSoon(); });
window.addEventListener("focus", loadFavourites);

// Stop following = keep the desktop's current picture, which only works when
// that picture is in the wallpaper folder; otherwise say so and open the picker.
$("follow-desktop").addEventListener("change", (e) => {
  if (e.target.checked) return change("wallpaper", "");
  const name = state.theme.wallpaper_name || "";
  if (state.walls.some((w) => w.name === name)) return change("wallpaper", name);
  e.target.checked = true;
  $("current-note").textContent = "Your desktop's picture is not in the wallpaper folder: pick one below to stop following it.";
  document.querySelector("details.quick").open = true;
});

$("wall-filter").addEventListener("input", (e) => {
  const needle = e.target.value.trim().toLowerCase();
  document.querySelectorAll(".wall").forEach((item) =>
    item.classList.toggle("hidden", !!needle && !item.dataset.name.toLowerCase().includes(needle)));
});

/* ---------------------------------------------------------------- colour */

function renderSwatches() {
  const box = $("swatches");
  box.innerHTML = "";
  const chosen = state.settings.accent;
  const auto = document.createElement("button");
  auto.type = "button";
  auto.className = "swatch auto" + (chosen ? "" : " on");
  auto.textContent = "Automatic";
  auto.style.background = state.theme.accent;
  auto.style.color = state.theme.on_accent;
  auto.title = "Take the colour from the wallpaper";
  auto.addEventListener("click", () => change("accent", ""));
  box.appendChild(auto);
  (state.theme.swatches || []).forEach((colour) => {
    const swatch = document.createElement("button");
    swatch.type = "button";
    swatch.className = "swatch" + (chosen === colour ? " on" : "");
    swatch.style.background = colour;
    swatch.title = colour;
    swatch.addEventListener("click", () => change("accent", colour));
    box.appendChild(swatch);
  });
  $("custom-accent").value = state.theme.accent;
}

$("custom-accent").addEventListener("change", (e) => change("accent", e.target.value));

/* -------------------------------------------------------------- controls */

// How a number is printed beside its slider, by the setting's `unit`.
const UNITS = {
  percent: (v) => `${Math.round(v * 100)}%`,
  whole_percent: (v) => `${Math.round(v)}%`,
  solid: (v) => `${Math.round(v * 100)}% solid`,
  px: (v) => `${v} px`,
  ms: (v) => `${v} ms`,
  fps: (v) => `${v} fps`,
  s: (v) => `${v} s`,
  "%": (v) => `${v}%`,
  times: (v) => `${Number(v).toFixed(2)}×`,
};

function formatValue(key, value) {
  const unit = (state.fields[key] || {}).unit;
  return UNITS[unit] ? UNITS[unit](value) : String(value);
}

/* A presets slider: steps through named sets of the settings in spec.sets
   (built-ins, then the user's own, as the theme lists them), with a box to
   save the current mix under a name. */
function presetRow(key, spec) {
  const row = document.createElement("div");
  row.className = "slider presets item";
  row.dataset.presets = key;
  row.dataset.search = "preset size small default comfortable large";
  row.innerHTML = `<label for="preset-${key}">Preset</label><input type="range" id="preset-${key}" min="0" step="1"><output></output>
    <form class="preset-save"><input type="text" placeholder="Name this mix" maxlength="30" spellcheck="false"><button class="btn">Save as custom</button></form>`;
  const list = () => ((state.theme || {})[key] || []);
  // A preset sets App size too, so like that slider it previews while
  // dragged and is applied once, on release (see wireInput).
  const range = row.querySelector("input[type=range]");
  range.addEventListener("input", () => {
    const p = list()[Number(range.value)];
    if (p) preview(Object.fromEntries(spec.sets.map((k) => [k, Number(p[k]) || 1])), row);
  });
  range.addEventListener("change", () => {
    endPreview();
    const p = list()[Number(range.value)];
    if (p) spec.sets.forEach((k) => change(k, Number(p[k]) || 1));
  });
  row.querySelector("form").addEventListener("submit", (e) => {
    e.preventDefault();
    const box = row.querySelector("input[type=text]");
    const name = box.value.trim().slice(0, 30);
    if (!name) return;
    const mine = list().filter((p) => p.mine && p.name !== name).map(({ mine: _, ...p }) => p);
    mine.push(Object.assign({ name }, Object.fromEntries(spec.sets.map((k) => [k, state.settings[k]]))));
    change(key, mine);
    box.value = "";
  });
  return row;
}

/* Forge's own keys: one box per action, showing its default until changed.
   Several keys for one action are separated by commas ("Alt+F, F11"). */
function keysTable(key, spec) {
  const box = document.createElement("div");
  box.className = "keys";
  box.dataset.keys = key;
  Object.entries(spec.defaults).forEach(([action, fallback]) => {
    const label = document.createElement("label");
    label.className = "item";
    label.textContent = (spec.labels || {})[action] || action;
    label.dataset.search = `${label.textContent} ${fallback} key shortcut`;
    const input = document.createElement("input");
    input.type = "text";
    input.spellcheck = false;
    input.placeholder = fallback;
    input.dataset.action = action;
    input.addEventListener("change", () => {
      const next = Object.assign({}, state.settings[key]);
      if (input.value.trim()) next[action] = input.value.trim();
      else delete next[action];
      change(key, next);
    });
    label.appendChild(input);
    box.appendChild(label);
  });
  const note = document.createElement("div");
  note.className = "muted small note";
  note.textContent = "Write keys like Alt+F or Ctrl+Alt+3; separate two with a comma. Empty means the default shown. These work inside every app.";
  box.appendChild(note);
  return box;
}

function renderKeys() {
  document.querySelectorAll("[data-keys]").forEach((box) => {
    const keys = state.settings[box.dataset.keys] || {};
    box.querySelectorAll("input[data-action]").forEach((input) => {
      if (document.activeElement !== input) input.value = keys[input.dataset.action] || "";
    });
  });
}

function renderPresets() {
  document.querySelectorAll("[data-presets]").forEach((row) => {
    const key = row.dataset.presets, spec = state.fields[key] || {};
    const list = (state.theme || {})[key] || [];
    const i = list.findIndex((p) => spec.sets.every((k) => Math.abs((Number(p[k]) || 1) - Number(state.settings[k])) < 0.001));
    const range = row.querySelector("input[type=range]");
    range.max = Math.max(0, list.length - 1);
    // No exact match: sit on the nearest preset, named as your own mix.
    const gap = (p) => spec.sets.reduce((sum, k) => sum + Math.abs((Number(p[k]) || 1) - Number(state.settings[k])), 0);
    range.value = i >= 0 ? i : list.reduce((best, p, j) => (gap(p) < gap(list[best]) ? j : best), 0);
    row.querySelector("output").textContent = i >= 0 ? list[i].name : "Your own mix";
  });
}

function renderControls() {
  markPowerNow();
  renderPresets();
  renderKeys();
  document.querySelectorAll("[data-key]").forEach((input) => {
    const key = input.dataset.key, value = state.settings[key];
    if (input.type === "checkbox") input.checked = !!value;
    else if (document.activeElement !== input) input.value = value;
    // a dot beside the name of anything changed from its default
    const spec = (state.fields || {})[key], row = input.closest(".item");
    if (row && spec && "default" in spec) row.classList.toggle("changed", JSON.stringify(value) !== JSON.stringify(spec.default));
  });
  document.querySelectorAll("output[data-for]").forEach((out) => {
    out.textContent = formatValue(out.dataset.for, state.settings[out.dataset.for]);
  });
}

// What a setting with "preview" in its spec shows on this page while its
// slider is dragged, before it is applied everywhere on release.
const PREVIEWS = {
  text_size: (value) => window.ForgeChrome && ForgeChrome.previewTextSize && ForgeChrome.previewTextSize(value),
};

// A dragged "apply on release" slider: the value shows here (its number, the
// preset name, the setting's own preview) and nothing is saved or sent. Its
// own row keeps its text size: bigger letters there would move the slider
// under the pointer, the App size problem over again.
function preview(values, row) {
  if (row && !row.hasAttribute("data-pinned")) {
    row.setAttribute("data-pinned", "");
    row.style.setProperty("--forge-text", String((window.ForgeText && ForgeText.scale) || 1));
  }
  state.dragging = true;
  Object.assign(state.previewing, values);
  Object.assign(state.settings, values);
  showPreviews(values);
  renderControls();
}

function showPreviews(values) {
  Object.entries(values).forEach(([key, value]) => {
    const show = PREVIEWS[(state.fields[key] || {}).preview];
    if (show) show(value);
  });
}

function endPreview() {
  state.dragging = false;
  state.previewing = {};
  document.querySelectorAll("[data-pinned]").forEach((row) => {
    row.removeAttribute("data-pinned");
    row.style.removeProperty("--forge-text");
  });
}

function wireInput(input) {
  const key = input.dataset.key;
  const read = () => {
    const kind = (state.fields[key] || {}).kind;
    let value = input.type === "checkbox" ? input.checked : input.value;
    if (kind === "number" || kind === "int") value = Number(value);
    return value;
  };
  // A setting whose spec says "apply": "release" (App size, Text size, Icon
  // size) only previews while its slider is dragged and is applied once, on
  // release. App size zooms the whole Forge window, this page included, so
  // applying it mid-drag moved the slider under the pointer, which read a
  // new value and zoomed again: the size flip-flopped (Emerson, 2026-10-07).
  const onRelease = () => input.type === "range" && (state.fields[key] || {}).apply === "release";
  input.addEventListener(input.type === "range" ? "input" : "change", () => {
    if (onRelease()) preview({ [key]: read() }, input.closest(".item"));
    else change(key, read());
  });
  if (input.type === "range") {
    input.addEventListener("change", () => {
      if (!onRelease()) return;
      endPreview();
      change(key, read());
    });
  }
}
// A drag let go where it started fires no change: stop counting it as a drag.
document.addEventListener("pointerup", () => setTimeout(endPreview, 0), true);

document.querySelectorAll("[data-key]").forEach(wireInput);

// One card per group from the settings table. Sliders first, then switches
// and choices, in the table's order.
function buildGroups() {
  const box = $("groups");
  box.replaceChildren();
  const groups = new Map();
  const add = (name, item) => {
    if (!groups.has(name)) groups.set(name, []);
    groups.get(name).push(item);
  };
  Object.entries(state.fields).forEach(([key, spec]) => {
    if ((spec.custom && spec.kind !== "presets" && spec.kind !== "keys") || !spec.group) return;
    add(spec.group, [key, spec]);
  });
  // `also`: the same control again in another card (Speed and detail collects
  // every frame rate and detail slider), after that card's own, named with
  // the page it comes from. Both controls follow one setting.
  Object.entries(state.fields).forEach(([key, spec]) => {
    (spec.also || []).forEach((name) => {
      add(name, [key, Object.assign({}, spec, { label: `${spec.group}: ${spec.label}`, copyIn: name })]);
    });
  });
  groups.forEach((items, name) => {
    items.sort((a, b) => (b[1].kind === "presets") - (a[1].kind === "presets") || !!a[1].copyIn - !!b[1].copyIn);
    const card = document.createElement("section");
    card.className = "card gen";
    card.dataset.section = name.toLowerCase().replace(/[^a-z0-9]+/g, "-");
    card.dataset.title = name;
    const head = document.createElement("div");
    head.className = "card-head";
    const title = document.createElement("h3");
    title.textContent = name;
    // Reset puts this page's own settings back to their defaults; a second
    // press within three seconds does it, so a stray click changes nothing.
    const reset = document.createElement("button");
    reset.type = "button";
    reset.className = "btn reset-sec";
    reset.textContent = "Reset";
    reset.title = `Put every setting on this page back to its default`;
    let unsure = 0;
    reset.addEventListener("click", () => {
      if (!reset.classList.contains("sure")) {
        reset.classList.add("sure");
        reset.textContent = "Press again to reset";
        unsure = setTimeout(() => { reset.classList.remove("sure"); reset.textContent = "Reset"; }, 3000);
        return;
      }
      clearTimeout(unsure);
      reset.classList.remove("sure");
      reset.textContent = "Reset";
      items.filter(([, spec]) => !spec.copyIn && spec.kind !== "keys" && spec.kind !== "presets")
        .forEach(([key, spec]) => change(key, spec.default));
    });
    head.append(title, reset);
    card.appendChild(head);

    // One row per setting: its name and help on the left, the control on
    // the right, so each help line sits under the thing it explains.
    const what = (key, spec) => {
      const box = document.createElement("div");
      box.className = "what";
      const label = document.createElement("label");
      label.htmlFor = controlId(key, spec);
      label.textContent = spec.label;
      box.appendChild(label);
      if (spec.help) {
        const help = document.createElement("small");
        help.className = "muted";
        help.textContent = spec.help;
        box.appendChild(help);
      }
      return box;
    };

    items.forEach(([key, spec]) => {
      if (spec.kind === "presets") {
        card.appendChild(presetRow(key, spec));
        return;
      }
      if (spec.kind === "keys") {
        card.appendChild(keysTable(key, spec));
        return;
      }
      const row = document.createElement("div");
      row.dataset.search = searchText(key, spec);
      let input;
      if (spec.kind === "number" || spec.kind === "int") {
        row.className = "slider item";
        input = document.createElement("input");
        input.type = "range";
        input.min = spec.min;
        input.max = spec.max;
        input.step = spec.step || (spec.kind === "int" ? 1 : 0.01);
        const out = document.createElement("output");
        out.dataset.for = key;
        row.append(what(key, spec), input, out);
      } else {
        row.className = "set-row item";
        if (spec.kind === "bool") {
          input = document.createElement("input");
          input.type = "checkbox";
          input.className = "toggle";
        } else if (spec.kind === "text") {
          input = document.createElement("input");
          input.type = "text";
          input.spellcheck = false;
        } else {
          input = document.createElement("select");
          spec.choices.forEach((choice) => {
            const option = document.createElement("option");
            option.value = choice;
            option.textContent = (spec.labels || {})[choice] || choice;
            input.appendChild(option);
          });
        }
        row.append(what(key, spec), input);
      }
      input.id = controlId(key, spec);
      input.dataset.key = key;
      card.appendChild(row);
      wireInput(input);
    });
    box.appendChild(card);
  });
}

// A control's id: set-<key>, and for its copy in another card the card's name too.
function controlId(key, spec) {
  return spec.copyIn ? `set-${key}-in-${spec.copyIn.toLowerCase().replace(/[^a-z0-9]+/g, "-")}` : `set-${key}`;
}

// Plugged in or on battery, as the hub last said (null standalone): the rows
// of Speed and detail that apply now are marked, from the theme's power_pairs.
function markPowerNow() {
  document.querySelectorAll(".item.now").forEach((row) => row.classList.remove("now"));
  if (state.onBattery === null) return;
  Object.entries((state.theme || {}).power_pairs || {}).forEach(([key, [twin]]) => {
    const live = state.onBattery ? twin : key;
    document.querySelectorAll(`[data-key="${live}"]`).forEach((input) => {
      const row = input.closest(".item");
      if (row) row.classList.add("now");
    });
  });
}

// What a search matches for one setting: its label, help, choices and key.
function searchText(key, spec) {
  return [spec.label, spec.help, key.replace(/_/g, " "), ...Object.values(spec.labels || {})]
    .filter(Boolean).join(" ");
}

/* -------------------------------------------------------------- sections */

// Every card with a data-section is a page of its own, listed on the left in
// page order: the hand-made ones and one per group, so a new group in the
// settings table gets its page with no change here.
const sections = () => [...document.querySelectorAll(".settings section[data-section]")];

/* How Settings itself is laid out (the Layout section): the section list as a sidebar, tabs or
   one long page; density; width; pinned sections first. Emerson
   (2026-09-27): "make the settings app a better layout or customizable".
   Kept in this browser only, like the open section. */
const LAYOUT_KEY = "forge.settings.layout";
// Compact by default (Emerson, 2026-09-28: "settings more compact but still there")
const LAYOUT_DEFAULT = { nav: "sidebar", density: "compact", width: "normal", pins: [] };
function layout() {
  try { return { ...LAYOUT_DEFAULT, ...JSON.parse(localStorage.getItem(LAYOUT_KEY) || "{}") }; } catch (e) { return { ...LAYOUT_DEFAULT }; }
}
function setLayout(changes) {
  const next = { ...layout(), ...changes };
  try { localStorage.setItem(LAYOUT_KEY, JSON.stringify(next)); } catch (e) {}
  applyLayout();
}
function applyLayout() {
  const l = layout(), b = document.body.classList;
  b.toggle("nav-tabs", l.nav === "tabs");
  b.toggle("nav-page", l.nav === "page");
  b.toggle("dense", l.density === "compact");
  b.toggle("wide", l.width === "wide");
  document.querySelectorAll("#layout-panel .seg").forEach((seg) => {
    seg.querySelectorAll("button").forEach((btn) => btn.classList.toggle("on", l[seg.dataset.pref] === btn.dataset.v));
  });
  if (sections().length) { buildNav(); showSection(state.section); }
}
let layoutWired = false;
function wireLayout() {
  if (layoutWired) return applyLayout();
  layoutWired = true;
  // Its own section in the list (it used to float over the top right).
  const panel = $("layout-panel");
  panel.querySelectorAll(".seg button").forEach((b) => b.addEventListener("click", () => setLayout({ [b.parentElement.dataset.pref]: b.dataset.v })));
  $("layout-reset").addEventListener("click", () => { try { localStorage.removeItem(LAYOUT_KEY); } catch (e) {} applyLayout(); });
  applyLayout();
}

function buildNav() {
  const list = $("nav-list");
  list.replaceChildren();
  const pins = layout().pins.filter((id) => sections().some((s) => s.dataset.section === id));
  const ordered = [...pins.map((id) => sections().find((s) => s.dataset.section === id)),
    ...sections().filter((s) => !pins.includes(s.dataset.section))];
  ordered.forEach((sec, i) => {
    const id = sec.dataset.section, item = document.createElement("div");
    item.className = "item";
    const b = document.createElement("button");
    b.type = "button";
    b.textContent = sec.dataset.title;
    b.dataset.section = id;
    b.addEventListener("click", () => {
      $("search").value = "";
      showSection(id, true);
    });
    const pin = document.createElement("button");
    pin.type = "button";
    pin.className = "pin" + (pins.includes(id) ? " on" : "");
    pin.textContent = pins.includes(id) ? "★" : "☆";
    pin.title = pins.includes(id) ? "Unpin" : "Pin to the top";
    pin.setAttribute("aria-label", `${pin.title}: ${sec.dataset.title}`);
    pin.addEventListener("click", () => {
      const now = layout().pins;
      setLayout({ pins: now.includes(id) ? now.filter((p) => p !== id) : [...now, id] });
    });
    item.append(b, pin);
    list.appendChild(item);
    if (pins.length && i === pins.length - 1) list.appendChild(Object.assign(document.createElement("div"), { className: "pins-end" }));
  });
}

function showSection(id, jump) {
  const all = sections();
  if (!all.some((sec) => sec.dataset.section === id)) id = all[0].dataset.section;
  state.section = id;
  document.body.classList.remove("searching");
  $("no-match").hidden = true;
  document.querySelectorAll(".miss").forEach((el) => el.classList.remove("miss"));
  const page = layout().nav === "page";
  all.forEach((sec) => (sec.hidden = !page && sec.dataset.section !== id));
  if (page && jump) {
    const sec = all.find((s) => s.dataset.section === id);
    sec.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start" });
    sec.classList.add("flash");
    setTimeout(() => sec.classList.remove("flash"), 900);
  }
  document.querySelectorAll("#nav-list button").forEach((b) => {
    b.classList.remove("hit");
    b.classList.toggle("on", b.dataset.section === id);
    if (b.dataset.section === id) b.setAttribute("aria-current", "page");
    else b.removeAttribute("aria-current");
  });
  try { history.replaceState(null, "", "#" + id); } catch (e) {}
  try { localStorage.setItem("forge.settings.section", id); } catch (e) {}
}

// Searching leaves the one-page view: every section with a match shows, with
// only its matching settings (all of them when the section's name matches).
function search(text) {
  const needle = text.trim().toLowerCase();
  if (!needle) return showSection(state.section);
  document.body.classList.add("searching");
  let any = false;
  sections().forEach((sec) => {
    const whole = sec.dataset.title.toLowerCase().includes(needle);
    const items = [...sec.querySelectorAll(".item")];
    let hits = 0;
    items.forEach((item) => {
      const hit = whole || (item.dataset.search || item.textContent).toLowerCase().includes(needle);
      item.classList.toggle("miss", !hit);
      hits += hit;
    });
    const show = whole || hits > 0 || (!items.length && (sec.dataset.keywords || "").includes(needle));
    sec.hidden = !show;
    any = any || show;
    const b = document.querySelector(`#nav-list button[data-section="${sec.dataset.section}"]`);
    if (b) { b.classList.remove("on"); b.classList.toggle("hit", show); }
  });
  $("no-match").hidden = any;
}

$("search").addEventListener("input", (e) => search(e.target.value));
$("search").addEventListener("keydown", (e) => {
  if (e.key === "Escape" && e.target.value) { e.preventDefault(); e.target.value = ""; search(""); }
});
document.addEventListener("keydown", (e) => {
  if ((e.ctrlKey && e.key === "f") || (e.key === "/" && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName))) {
    e.preventDefault();
    $("search").focus();
    $("search").select();
  }
});

// Like each page's Reset, a second press within three seconds does it, so a
// stray click cannot wipe every setting; it is locked while it runs.
let resetUnsure = 0;
$("reset").addEventListener("click", async () => {
  const b = $("reset");
  if (b.disabled) return;
  if (!b.classList.contains("sure")) {
    b.classList.add("sure");
    b.textContent = "Press again to reset everything";
    resetUnsure = setTimeout(() => { b.classList.remove("sure"); b.textContent = "Reset to defaults"; }, 3000);
    return;
  }
  clearTimeout(resetUnsure);
  b.classList.remove("sure");
  b.textContent = "Resetting…";
  b.disabled = true;
  clearTimeout(state.timer);
  stopRetry();
  // A save already on its way lands first, so its late answer cannot put an
  // old value back over the defaults; a change not yet saved is only dropped
  // once the reset has worked.
  state.resetting = true;
  for (let i = 0; state.saving && i < 100; i++) await new Promise((ok) => setTimeout(ok, 100));
  try {
    const r = await api("/api/settings/reset", { method: "POST", body: "{}" });
    state.epoch++;
    state.pending = {};
    state.resetting = false;
    accept(r);
    saidStatus("Everything is back to its default");
  } catch (e) {
    state.resetting = false;
    saidStatus("Not reset: " + e.message);
    if (Object.keys(state.pending).length) {
      if (e.offline) startRetry();
      else flush();
    }
  } finally {
    state.resetting = false;
    b.disabled = false;
    b.textContent = "Reset to defaults";
  }
});

function render() {
  renderWallpaper();
  renderSwatches();
  renderControls();
}

/* The first load. Until it works the page shows a calm card instead of empty
   sections, and tries again by itself (2 s, growing to 30 s, resting while
   hidden) when the backend is not up yet. */
let booter = null;
async function boot() {
  if (state.fields) return true;
  try {
    const [s, w] = await Promise.all([api("/api/settings"), api("/api/wallpapers")]);
    state.settings = s.settings;
    state.fields = s.fields;
    state.theme = s.theme;
    state.walls = w.wallpapers;
    $("wall-filter").placeholder = `Search ${w.wallpapers.length} wallpapers in ${w.folder}…`;
    $("where").textContent = `Settings are kept in ${s.config}. Wallpaper copies and thumbnails `
      + `are cached in ${s.cache} and can be deleted at any time.`;
    buildGroups();
    buildNav();
    wireLayout();
    let first = decodeURIComponent(location.hash.slice(1));
    try { first = first || localStorage.getItem("forge.settings.section") || ""; } catch (e) {}
    showSection(first);
    buildWalls();
    render();
    loadFavourites();
    document.body.classList.remove("booting");
    if (booter) booter.stop();
    booter = null;
    return true;
  } catch (e) {
    state.fields = null;
    $("boot-title").textContent = "Settings is not reachable yet";
    $("boot-text").textContent = (e.offline ? "Its backend is not answering, probably still starting."
      : `The backend said: ${e.message}.`) + " Trying again by itself…";
    $("boot-retry").hidden = false;
    if (!booter && window.ForgeIdle) booter = ForgeIdle.poll(boot, 2000, { backoff: 2, maxMs: 30000 });
    return false;
  }
}

$("boot-retry").addEventListener("click", () => booter && booter.now());
boot();
