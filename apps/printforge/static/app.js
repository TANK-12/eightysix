// PrintForge page logic: library list, loading, info panel and settings.
import { Viewer, parseSTL } from "/viewer.js";

const $ = (id) => document.getElementById(id);
const viewer = new Viewer($("view"));
const COLOURS = ["#c9c3b5", "#e8e4da", "#9aa0a8", "#4a4f57", "#b8a47a", "#7a8f5a", "#d9824a"];
let settings = {};
let files = [];
let current = null;
let loading = null; // AbortController of the download in flight

const mb = (b) => (b / 1e6).toFixed(1) + " MB";
const num = (x) => Number(x).toLocaleString();
const esc = (t) => String(t).replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);

async function api(path, opts) {
  let r;
  try {
    r = await fetch(path, opts);
  } catch (e) {
    if (e.name === "AbortError") throw e;
    throw new Error("the PrintForge server is not answering");
  }
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || r.statusText);
  return r.json();
}

// Saves and says so when it could not; true when the save went through.
async function saveSettings(values) {
  try {
    settings = await api("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: { ...values, advanced_mode: ForgeMode.on } }),
    });
    return true;
  } catch (e) {
    toast("Could not save: " + e.message, "err");
    return false;
  }
}

// One save after the last change of a slider, not one per step of the drag.
function saveLater(values) {
  saveLater.pending = { ...saveLater.pending, ...values };
  clearTimeout(saveLater.t);
  saveLater.t = setTimeout(() => {
    const v = saveLater.pending;
    saveLater.pending = {};
    saveSettings(v);
  }, 400);
}

// Runs a button's job once at a time, so a double click does it once.
function once(button, job) {
  button.onclick = async () => {
    if (button.disabled) return;
    button.disabled = true;
    try {
      await job();
    } finally {
      button.disabled = false;
    }
  };
}

function renderLibrary() {
  const q = $("search").value.trim().toLowerCase();
  const box = $("files");
  box.innerHTML = "";
  let lastProj = null;
  let lastFold = null;
  const shown = files.filter((f) => !q || (f.project + " " + f.folder + " " + f.name).toLowerCase().includes(q));
  for (const f of shown) {
    if (f.project !== lastProj) {
      box.insertAdjacentHTML("beforeend", `<div class="proj"></div>`);
      box.lastChild.textContent = f.project;
      lastProj = f.project;
      lastFold = null;
    }
    if (f.folder !== lastFold) {
      if (f.folder) {
        box.insertAdjacentHTML("beforeend", `<div class="fold"></div>`);
        box.lastChild.textContent = f.folder;
      }
      lastFold = f.folder;
    }
    const b = document.createElement("button");
    b.className = "file" + (current && current.path === f.path ? " on" : "");
    b.textContent = f.name.replace(/_/g, " ");
    const small = document.createElement("small");
    small.textContent = [mb(f.bytes), f.triangles ? num(f.triangles) + " triangles" : "", f.scale ? "scale " + f.scale : ""].filter(Boolean).join(" · ");
    b.appendChild(small);
    b.onclick = () => openFile(f);
    box.appendChild(b);
  }
  if (!shown.length) {
    box.innerHTML = `<div class="hint"></div>`;
    box.firstChild.textContent = files.length ? `No print matches "${$("search").value.trim()}".` : "No STL files found in these folders.";
  }
  $("rootsHint").textContent = "Searching: " + (settings.roots || []).join(", ");
}

async function fetchWithProgress(url, signal, onProgress) {
  const r = await fetch(url, { signal });
  if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || "the server said " + r.status);
  const total = +r.headers.get("Content-Length") || 0;
  const reader = r.body.getReader();
  const parts = [];
  let got = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    parts.push(value);
    got += value.length;
    if (total) onProgress(got / total);
  }
  const out = new Uint8Array(got);
  let o = 0;
  for (const p of parts) {
    out.set(p, o);
    o += p.length;
  }
  return out.buffer;
}

function status(text, frac) {
  $("status").firstChild.textContent = text;
  $("status").style.display = text ? "" : "none";
  $("bar").style.display = frac === undefined ? "none" : "block";
  if (frac !== undefined) $("bar").firstChild.style.width = Math.round(frac * 100) + "%";
}

async function openFile(f) {
  current = f;
  renderLibrary();
  $("title").textContent = f.name.replace(/_/g, " ");
  $("facts").innerHTML = "";
  $("fitsBox").innerHTML = "";
  $("openFolder").disabled = false;
  status(`Loading ${mb(f.bytes)}`, 0);
  const q = "?path=" + encodeURIComponent(f.path);
  if (loading) loading.abort();
  const mine = (loading = new AbortController());
  try {
    const buf = await fetchWithProgress("/api/stl" + q, mine.signal, (x) => status(`Loading ${mb(f.bytes)}`, x));
    if (current !== f) return;
    status("Building the view");
    await new Promise((r) => setTimeout(r, 0));
    if (current !== f) return;
    const positions = parseSTL(buf);
    if (positions.length < 9 || !positions.every(Number.isFinite)) {
      status(positions.length < 9 ? "This file has no triangles to show" : "This file looks damaged: some corners are not numbers");
    } else {
      viewer.setMesh(positions);
      status("");
    }
  } catch (e) {
    if (e.name !== "AbortError" && current === f) status("Could not open this file: " + e.message);
    return;
  } finally {
    if (loading === mine) loading = null;
  }
  $("facts").innerHTML = `<tr><td>Checking</td><td>reading every triangle</td></tr>`;
  try {
    const info = await api("/api/info" + q);
    if (current === f) showInfo(info);
  } catch (e) {
    if (current !== f) return;
    $("facts").innerHTML = `<tr><td>Check failed</td><td></td></tr>`;
    $("facts").querySelector("td:last-child").textContent = e.message;
  }
}

function showInfo(i) {
  if (!i.triangles) {
    $("facts").innerHTML = `<tr><td>Triangles</td><td><span class="badge bad">none: the file is empty</span></td></tr><tr><td>File</td><td>${mb(i.bytes)}</td></tr>`;
    return;
  }
  const s = i.size_mm || [0, 0, 0];
  const rows = [
    ["Size", `${s[0]} × ${s[1]} × ${s[2]} mm`],
    ["Scale", i.scale || "as modelled"],
    ["Triangles", num(i.triangles)],
    ["File", mb(i.bytes)],
    ["Volume", `${i.volume_cm3} cm³ (about ${Math.round(i.volume_cm3)} ml of resin if solid)`],
    ["Surface", `${i.area_cm2} cm²`],
    ["Watertight", i.watertight ? `<span class="badge good">yes</span>` : i.open_edges ? `<span class="badge bad">no: ${num(i.open_edges)} open edges</span>` : `<span class="badge bad">almost: ${num(i.repeated_edges)} edges where two parts touch along a line</span>`],
    ["Pieces", i.shells === 1 ? `<span class="badge good">one piece</span>` : `<span class="badge bad">${i.shells} separate pieces</span>`],
  ];
  if (i.inside_out) rows.push(["Normals", `<span class="badge bad">inside out</span>`]);
  $("facts").innerHTML = rows.map(([k, v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join("");
  const fits = i.fits || {};
  $("fitsBox").innerHTML =
    `<h3>Fits these beds</h3>` +
    Object.entries(fits)
      .map(([name, f]) => {
        const tag = f.upright ? `<span class="badge good">standing</span>` : f.any_orientation ? `<span class="badge good">laid over</span>` : `<span class="badge bad">too big</span>`;
        return `<div class="pair"><label style="width:auto;flex:1">${esc(name)}</label>${tag}</div>`;
      })
      .join("");
}

function bedSize() {
  return settings.beds[settings.bed] || Object.values(settings.beds)[0];
}

function fillBeds() {
  const sel = $("bed");
  sel.innerHTML = "";
  for (const [name, d] of Object.entries(settings.beds)) {
    const o = document.createElement("option");
    o.value = name;
    o.textContent = `${name} (${d.join(" × ")})`;
    sel.appendChild(o);
  }
  sel.value = settings.bed in settings.beds ? settings.bed : Object.keys(settings.beds)[0];
  const [x, y, z] = bedSize();
  for (const [id, v] of [["bx", x], ["by", y], ["bz", z]]) {
    $(id).value = v;
    $(id + "N").value = v;
  }
}

function pair(id, onChange) {
  const r = $(id);
  const n = $(id + "N");
  r.addEventListener("input", () => { n.value = r.value; onChange(+r.value); });
  n.addEventListener("change", () => { r.value = n.value; onChange(+n.value); });
}

async function loadLibrary() {
  const lib = await api("/api/library");
  files = lib.files;
  renderLibrary();
}

// A library read that fails retries by itself through ForgeIdle.poll: 2 s
// doubling to 30 s, resting while the page is hidden, ended by a read that
// works or by the next rescan (so Save and rescan never waits on it).
let libraryRetry = null;
function libraryFailed(e) {
  $("files").innerHTML = `<div class="hint"></div>`;
  $("files").firstChild.textContent = `Could not read the library: ${e.message}. Trying again by itself; fix the folders below and press Save and rescan.`;
}
async function loadLibraryUntilItWorks() {
  if (libraryRetry) libraryRetry.stop();
  libraryRetry = null;
  try {
    await loadLibrary();
    return true;
  } catch (e) {
    libraryFailed(e);
  }
  const retry = ForgeIdle.poll(async () => {
    try {
      await loadLibrary();
    } catch (e) {
      if (libraryRetry === retry) libraryFailed(e);
      return false;
    }
    retry.stop();
    if (libraryRetry === retry) libraryRetry = null;
    return true;
  }, 2000, { backoff: 2, maxMs: 30000 });
  libraryRetry = retry;
  return false;
}

async function start(wait = 2000) {
  try {
    settings = await api("/api/settings");
  } catch (e) {
    status(`PrintForge could not start: ${e.message}. Trying again in ${Math.round(wait / 1000)} s.`);
    setTimeout(() => start(Math.min(wait * 2, 30000)), wait);
    return;
  }
  status("Pick a print on the left");
  await main();
}

async function main() {
  ForgeMode.init(settings.advanced_mode);
  fillBeds();
  viewer.setBed(bedSize(), true);
  viewer.setColor(settings.color);
  viewer.setLight(settings.light);
  $("light").value = $("lightN").value = settings.light;
  $("roots").value = settings.roots.join("\n");
  for (const c of COLOURS) {
    const d = document.createElement("div");
    d.className = "swatch" + (c === settings.color ? " on" : "");
    d.style.background = c;
    d.title = c;
    d.onclick = () => {
      document.querySelectorAll(".swatch").forEach((x) => x.classList.remove("on"));
      d.classList.add("on");
      viewer.setColor(c);
      saveLater({ color: c });
    };
    $("swatches").appendChild(d);
  }
  document.querySelectorAll("[data-view]").forEach((b) => (b.onclick = () => viewer.setView(b.dataset.view)));
  let spin = false;
  $("spin").onclick = () => { spin = !spin; viewer.setAutoRotate(spin); $("spin").classList.toggle("on", spin); };
  let wire = false;
  $("wire").onclick = () => { wire = !wire; viewer.setWireframe(wire); $("wire").classList.toggle("on", wire); };
  let bedOn = true;
  $("bedToggle").classList.add("on");
  $("bedToggle").onclick = () => { bedOn = !bedOn; viewer.setBed(bedSize(), bedOn); $("bedToggle").classList.toggle("on", bedOn); };
  $("bed").onchange = () => { settings.bed = $("bed").value; fillBeds(); viewer.setBed(bedSize(), bedOn); saveSettings({ bed: settings.bed }); };
  pair("light", (v) => { viewer.setLight(v); saveLater({ light: v }); });
  const custom = () => [+$("bx").value, +$("by").value, +$("bz").value];
  for (const id of ["bx", "by", "bz"]) pair(id, () => viewer.setBed(custom(), bedOn));
  once($("bedSave"), async () => {
    if (!(await saveSettings({ beds: { ...settings.beds, custom: custom() }, bed: "custom" }))) return;
    fillBeds();
    viewer.setBed(bedSize(), bedOn);
  });
  once($("rootsSave"), async () => {
    const roots = $("roots").value.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!(await saveSettings({ roots }))) return;
    $("files").innerHTML = `<div class="hint">Looking for STL files</div>`;
    await loadLibraryUntilItWorks();
  });
  once($("openFolder"), async () => {
    if (!current) return;
    try {
      await api("/api/open-folder", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ path: current.path }) });
    } catch (e) {
      toast("Could not open the folder: " + e.message, "err");
    }
  });
  $("shot").onclick = () => {
    const a = document.createElement("a");
    a.href = viewer.snapshot();
    a.download = (current ? current.name : "printforge") + ".png";
    a.click();
  };
  $("search").addEventListener("input", renderLibrary);
  document.addEventListener("keydown", (e) => {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    if (e.key === "f") viewer.fit();
    if (e.key === "w") $("wire").click();
    if (e.key === "r") $("spin").click();
  });
  await loadLibraryUntilItWorks();
  const want = new URLSearchParams(location.search).get("open");
  const first = files.find((f) => want && f.path.includes(want));
  if (first) {
    openFile(first);
    const view = new URLSearchParams(location.search).get("view");
    if (view) setTimeout(() => viewer.setView(view), 0);
  }
}

start();
