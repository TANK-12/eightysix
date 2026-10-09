/* Wallpapers frontend.
 *
 * One list from /api/wallpapers, filtered and sorted here. While the backend
 * is still indexing (reading sizes and fingerprints) the list is fetched
 * again every two seconds, so resolutions and hidden copies fill in live.
 * Setting a wallpaper in Forge hands the new theme to the hub by postMessage,
 * the same way the Settings app does.
 */

const $ = (id) => document.getElementById(id);
const state = {
  rows: [], forge: "", desktop: "", folder: "", index: {},
  view: "all", selected: null, timer: null,
  kinds: {}, picks: {},
};
// Forge looks a wallpaper's particle pick up by its file name
const fileName = (name) => name.split("/").pop();

async function api(path, options) {
  const r = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

const thumbUrl = (name) => `/api/thumb?name=${encodeURIComponent(name)}`;
const previewUrl = (name) => `/api/preview?name=${encodeURIComponent(name)}`;
const pretty = (name) => name.split("/").pop().replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ");

function resLabel(w) {
  if (!w.width) return "";
  // Named by the long side, the way monitors are: a 4096x1728 ultrawide is a
  // 4K-wide picture, not a 1440p one.
  const long = Math.max(w.width, w.height);
  const tag = long >= 7680 ? "8K" : long >= 5120 ? "5K" : long >= 3840 ? "4K"
    : long >= 2560 ? "1440p" : long >= 1920 ? "1080p" : "";
  return tag ? `${tag} · ${w.width}×${w.height}` : `${w.width}×${w.height}`;
}

function megabytes(bytes) { return `${(bytes / 1048576).toFixed(1)} MB`; }

/* ---------------------------------------------------------------- the list */

function visible() {
  const needle = $("search").value.trim().toLowerCase();
  const copies = $("show-copies").checked;
  const shape = $("shape").value;
  const minres = Number($("minres").value);
  const rows = state.rows.filter((w) => {
    if (w.duplicate_of && !copies) return false;
    if (state.view === "favourites" && !w.favourite) return false;
    if (state.view === "current" && w.name !== state.forge && w.name !== state.desktop) return false;
    if (needle && !w.name.toLowerCase().replace(/[-_]+/g, " ").includes(needle)
        && !w.name.toLowerCase().includes(needle)) return false;
    if (minres && w.width && Math.max(w.width, w.height) < minres) return false;
    if (shape && w.width) {
      const ratio = w.width / w.height;
      if (shape === "wide" && !(ratio > 1.05 && ratio < 2.1)) return false;
      if (shape === "ultrawide" && ratio < 2.1) return false;
      if (shape === "tall" && ratio > 1.05) return false;
    }
    return true;
  });
  const by = $("sort").value;
  const cmp = {
    name: (a, b) => a.name.localeCompare(b.name),
    resolution: (a, b) => b.width * b.height - a.width * a.height || a.name.localeCompare(b.name),
    newest: (a, b) => b.mtime - a.mtime,
    size: (a, b) => b.bytes - a.bytes,
  }[by];
  // Favourites first in every view, so they are easy to find again.
  return rows.sort((a, b) => (b.favourite - a.favourite) || cmp(a, b));
}

function card(w) {
  const item = document.createElement("div");
  item.className = "wall" + (w.duplicate_of ? " copy" : "") + (w.name === state.selected ? " selected" : "");
  item.tabIndex = 0;
  item.dataset.name = w.name;
  item.title = w.name;

  const img = document.createElement("img");
  img.loading = "lazy";
  img.alt = "";
  img.src = thumbUrl(w.name);

  const badges = document.createElement("div");
  badges.className = "badges";
  if (w.name === state.forge) badges.appendChild(badge("Forge"));
  if (w.name === state.desktop) badges.appendChild(badge("Desktop"));
  if (w.duplicate_of) badges.appendChild(badge("Copy", true));

  const star = document.createElement("button");
  star.type = "button";
  star.className = "star" + (w.favourite ? " on" : "");
  star.textContent = w.favourite ? "★" : "☆";
  star.title = w.favourite ? "Remove from favourites" : "Add to favourites";
  star.addEventListener("click", (e) => { e.stopPropagation(); toggleFavourite(w.name); });

  const cap = document.createElement("div");
  cap.className = "cap";
  const nm = document.createElement("span");
  nm.className = "nm";
  nm.textContent = pretty(w.name);
  const res = document.createElement("span");
  res.className = "res";
  res.textContent = resLabel(w);
  cap.append(nm, res);

  item.append(img, badges, star, cap);
  item.addEventListener("click", () => select(w.name));
  item.addEventListener("keydown", (e) => { if (e.key === "Enter") select(w.name); });
  return item;
}

function badge(text, alt) {
  const b = document.createElement("span");
  b.className = "badge" + (alt ? " alt" : "");
  b.textContent = text;
  return b;
}

function render() {
  const rows = visible();
  const grid = $("grid");
  const fragment = document.createDocumentFragment();
  rows.forEach((w) => fragment.appendChild(card(w)));
  grid.replaceChildren(fragment);
  $("empty").classList.toggle("hidden", rows.length > 0);

  const shown = state.rows.filter((w) => !w.duplicate_of);
  $("count-all").textContent = shown.length;
  $("count-fav").textContent = state.rows.filter((w) => w.favourite).length || "";
  const copies = state.rows.length - shown.length;
  $("count-copies").textContent = copies ? `(${copies})` : "";
  renderPanel();
}

function renderIndexNote() {
  const i = state.index;
  if (i.running) {
    $("index-note").textContent = i.total
      ? `Indexing ${i.done} of ${i.total}… resolutions and copies fill in as it goes`
      : "Indexing…";
  } else if (i.stale) {
    $("index-note").textContent = `${i.stale} not indexed yet`;
  } else {
    $("index-note").textContent = `${state.rows.length} pictures in ${state.folder}`;
  }
}

async function load() {
  const body = await api("/api/wallpapers");
  state.rows = body.wallpapers;
  state.forge = body.forge;
  state.desktop = body.desktop;
  state.folder = body.folder;
  state.index = body.index;
  const scroll = $("scroller").scrollTop;
  render();
  $("scroller").scrollTop = scroll;
  renderIndexNote();
  clearTimeout(state.timer);
  if (body.index.running) state.timer = setTimeout(load, 2000);
}

/* ---------------------------------------------------------------- the panel */

function select(name) {
  state.selected = name;
  document.querySelectorAll(".wall").forEach((n) => n.classList.toggle("selected", n.dataset.name === name));
  $("p-result").textContent = "";
  renderPanel(true);
}

function renderPanel(fresh) {
  const w = state.rows.find((r) => r.name === state.selected);
  $("panel").classList.toggle("hidden", !w);
  if (!w) return;
  $("p-title").textContent = pretty(w.name);
  if (fresh) {
    // The thumbnail at once, then the uncropped preview when it is ready.
    $("p-img").src = thumbUrl(w.name);
    const full = new Image();
    full.onload = () => { if (state.selected === w.name) $("p-img").src = full.src; };
    full.src = previewUrl(w.name);
  }
  const bits = [w.name, resLabel(w) || "size not read yet", megabytes(w.bytes),
    new Date(w.mtime * 1000).toLocaleDateString()];
  $("p-meta").textContent = bits.join(" · ");
  const tags = $("p-tags");
  tags.replaceChildren();
  if (w.name === state.forge) tags.appendChild(badge("Forge's wallpaper"));
  if (w.name === state.desktop) tags.appendChild(badge("Desktop wallpaper"));
  if (w.duplicate_of) tags.appendChild(badge(`Copy of ${pretty(w.duplicate_of)}`, true));
  $("p-star").textContent = w.favourite ? "★ Favourite" : "☆ Favourite";
  const pick = state.picks[fileName(w.name)] || "";
  if (pick) tags.appendChild(badge(`Particles: ${state.kinds[pick] || pick}`));
  $("p-particles").value = pick;

  const copies = state.rows.filter((r) => r.duplicate_of === w.name);
  const box = $("p-copies");
  box.replaceChildren();
  if (copies.length) {
    box.append(`Hidden lower-resolution ${copies.length === 1 ? "copy" : "copies"} of this picture:`);
    const list = document.createElement("ul");
    copies.forEach((c) => {
      const li = document.createElement("li");
      li.textContent = `${c.name} (${resLabel(c) || "?"}, ${megabytes(c.bytes)})`;
      list.appendChild(li);
    });
    box.appendChild(list);
  }
}

async function toggleFavourite(name) {
  const w = state.rows.find((r) => r.name === name);
  if (!w) return;
  try {
    const body = await api("/api/favourite", { method: "POST", body: JSON.stringify({ name, on: !w.favourite }) });
    const stars = new Set(body.favourites);
    state.rows.forEach((r) => { r.favourite = stars.has(r.name); });
    render();
  } catch (e) {
    $("p-result").textContent = "Not saved: " + e.message;
  }
}

/* ------------------------------------------------- this wallpaper's particles */

async function loadParticles() {
  const body = await api("/api/particles");
  state.kinds = body.kinds;
  state.picks = body.picks;
  const box = $("p-particles");
  const keep = box.options[0];
  box.replaceChildren(keep);
  for (const [k, label] of Object.entries(body.kinds)) {
    if (k === "off") continue;
    box.add(new Option(label, k));
  }
  box.add(new Option("Off (no particles on this wallpaper)", "off"));
  renderPanel();
}

async function setParticles(kind) {
  const name = state.selected;
  if (!name) return;
  try {
    const body = await api("/api/particles", { method: "POST", body: JSON.stringify({ name, kind }) });
    state.picks = body.picks;
    if (body.theme) {
      try { window.parent.postMessage({ forge: "theme", theme: body.theme }, "*"); } catch (e) {}
    }
    $("p-result").textContent = kind ? `Particles set: ${state.kinds[kind] || kind}.` : "Particles match the wallpaper again.";
    renderPanel();
  } catch (e) {
    $("p-result").textContent = "Not saved: " + e.message;
  }
}

async function applySelected(target) {
  const name = state.selected;
  if (!name) return;
  const desktop = target === "both" || target === "desktop";
  const forge = target === "both" || target === "forge";
  $("p-result").textContent = "Setting…";
  try {
    const body = await api("/api/apply", { method: "POST", body: JSON.stringify({ name, desktop, forge }) });
    if (body.theme) {
      try { window.parent.postMessage({ forge: "theme", theme: body.theme }, "*"); } catch (e) {}
    }
    const said = [body.desktop && body.desktop.message, body.forge && body.forge.message].filter(Boolean);
    $("p-result").textContent = said.join(". ") + ".";
    await load();
  } catch (e) {
    $("p-result").textContent = "Not set: " + e.message;
  }
}

/* ------------------------------------------------ particles on the desktop */

async function deskParticles(on) {
  const box = $("desk-particles");
  try {
    const body = on === undefined
      ? await api("/api/desktop-particles")
      : await api("/api/desktop-particles", { method: "POST", body: JSON.stringify({ on }) });
    box.checked = !!body.on;
    if (body.theme) {
      try { window.parent.postMessage({ forge: "theme", theme: body.theme }, "*"); } catch (e) {}
    }
  } catch (e) {
    box.title = "Could not change it: " + e.message;
  }
}

/* ---------------------------------------------------------------- wiring */

$("desk-particles").addEventListener("change", (e) => deskParticles(e.target.checked));
$("p-particles").addEventListener("change", (e) => setParticles(e.target.value));
loadParticles().catch(() => {});
deskParticles();

document.querySelectorAll("[data-apply]").forEach((b) =>
  b.addEventListener("click", () => applySelected(b.dataset.apply)));
$("p-star").addEventListener("click", () => state.selected && toggleFavourite(state.selected));
$("p-close").addEventListener("click", () => select(null));

$("view").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-view]");
  if (!b) return;
  state.view = b.dataset.view;
  $("view").querySelectorAll("button").forEach((n) => n.classList.toggle("on", n === b));
  render();
});

["search", "sort", "shape", "minres", "show-copies"].forEach((id) =>
  $(id).addEventListener(id === "search" ? "input" : "change", render));

function applyTileSize(px) {
  $("grid").style.setProperty("--tile", `${px}px`);
  try { localStorage.setItem("wallpapers.tile", String(px)); } catch (e) {}
}
$("tile-size").addEventListener("input", (e) => applyTileSize(e.target.value));

// Remembered per viewer: sort, filters and tile size.
function restore() {
  try {
    const saved = JSON.parse(localStorage.getItem("wallpapers.view") || "{}");
    ["sort", "shape", "minres"].forEach((id) => { if (saved[id] !== undefined) $(id).value = saved[id]; });
    const tile = localStorage.getItem("wallpapers.tile");
    if (tile) { $("tile-size").value = tile; applyTileSize(tile); }
  } catch (e) {}
}
["sort", "shape", "minres"].forEach((id) => $(id).addEventListener("change", () => {
  try {
    localStorage.setItem("wallpapers.view", JSON.stringify(
      { sort: $("sort").value, shape: $("shape").value, minres: $("minres").value }));
  } catch (e) {}
}));

document.addEventListener("keydown", (e) => {
  const typing = /^(INPUT|TEXTAREA|SELECT)$/.test((e.target && e.target.tagName) || "");
  if (e.key === "/" && !typing) { e.preventDefault(); $("search").focus(); }
  if (e.key === "Escape" && state.selected && !typing) select(null);
});

// #favourites opens on the favourites view (the Settings app links here so).
if (location.hash === "#favourites") {
  state.view = "favourites";
  $("view").querySelectorAll("button").forEach((n) => n.classList.toggle("on", n.dataset.view === "favourites"));
}

restore();
load().catch((e) => { $("index-note").textContent = "Could not load: " + e.message; });
