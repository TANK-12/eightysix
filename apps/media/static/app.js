/* Media frontend: the library player, YouTube and Crunchyroll as native views
 * (the hub's view protocol, the same one the Browser app uses), and the
 * yt-dlp downloader. Helpers toast/initTabs/forgeStreamInto/ForgeMode come from
 * /shared/forge.js; the Full screen button from /shared/forge_chrome.js. */

const $ = (id) => document.getElementById(id);
const inForge = window.parent !== window;
const HEADERS = { "Content-Type": "application/json" };
const SITES = {
  youtube: { home: "https://www.youtube.com/", search: (q) => `https://www.youtube.com/results?search_query=${encodeURIComponent(q)}` },
  crunchyroll: { home: "https://www.crunchyroll.com/", search: (q) => `https://www.crunchyroll.com/search?q=${encodeURIComponent(q)}` },
};

async function api(path, body) {
  let r;
  try { r = await fetch(path, body === undefined ? {} : { method: "POST", headers: HEADERS, body: JSON.stringify(body) }); }
  catch (e) { throw new Error("the Media server is not answering"); }
  if (!r.ok) { let d = r.statusText; try { d = (await r.json()).detail || d; } catch (e) {} throw new Error(d); }
  return r.json();
}
const fmtTime = (s) => { s = Math.max(0, Math.floor(s || 0)); const m = Math.floor(s / 60), h = Math.floor(m / 60);
  return h ? `${h}:${String(m % 60).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${m}:${String(s % 60).padStart(2, "0")}`; };

/* ------------------------------------------------------------------ tabs */
let currentTab = "library";
const selectTab = initTabs((name) => { currentTab = name; syncViews(); if (name === "youtube" || name === "crunchyroll") ensureView(name); });

/* --------------------------------------------------------------- library */
const lib = { files: [], shown: [], kind: "", q: "", index: -1, shuffle: false, repeat: false, order: [] };
const media = $("media");

// One scan at a time: a Rescan pressed (or a download finishing) mid-scan
// runs once more after it rather than stacking requests.
const scan = { busy: false, again: false };

async function loadLibrary() {
  if (scan.busy) { scan.again = true; return true; }
  scan.busy = true; $("rescan").disabled = true;
  $("count").textContent = "scanning…";
  if (!lib.files.length) listNote("Reading your folders…");
  let ok = true;
  try {
    const r = await api("/api/library");
    lib.files = r.files;
    renderList();
  } catch (e) {
    ok = false;
    if (lib.files.length) { renderList(); toast("Could not read the library: " + e.message, "err"); }
    else { $("count").textContent = ""; listNote("Could not read the library: " + e.message + ".", true); }
  } finally {
    scan.busy = false; $("rescan").disabled = false;
  }
  if (scan.again) { scan.again = false; return loadLibrary(); }
  return ok;
}

// The list's own message: loading, nothing found, or an error with a way out.
function listNote(text, retry) {
  const box = $("list");
  box.innerHTML = "";
  const note = document.createElement("div");
  note.className = "empty";
  note.textContent = text;
  if (retry) {
    const b = document.createElement("button");
    b.className = "btn"; b.type = "button"; b.textContent = "Try again";
    b.addEventListener("click", () => (boot.retry ? boot.retry.now() : loadLibrary()));
    note.append(" ", b);
  }
  box.appendChild(note);
}

function renderList() {
  const q = lib.q.toLowerCase();
  lib.shown = lib.files.filter((f) => (!lib.kind || f.kind === lib.kind) && (!q || (f.name + " " + f.folder).toLowerCase().includes(q)));
  const box = $("list");
  box.innerHTML = "";
  const frag = document.createDocumentFragment();
  lib.shown.forEach((f, i) => {
    const row = document.createElement("div");
    row.className = "item" + (lib.index >= 0 && lib.files[lib.index] === f ? " playing" : "");
    row.innerHTML = `<span class="icon">${f.kind === "video" ? "🎬" : "🎵"}</span><span class="name"></span><span class="meta"></span>`;
    row.querySelector(".name").textContent = f.name;
    row.querySelector(".meta").textContent = (f.folder ? f.folder + " · " : "") + f.ext + " · " + (f.size / 1048576).toFixed(1) + " MB";
    row.addEventListener("click", () => playFile(f));
    frag.appendChild(row);
  });
  box.appendChild(frag);
  $("count").textContent = `${lib.shown.length} of ${lib.files.length}`;
  if (!lib.files.length) listNote("Nothing here yet. Media plays what is in the folders listed in Settings and the download folder: add a folder there, or save something from Download.");
  else if (!lib.shown.length) listNote(lib.q ? `Nothing matches "${lib.q}".` : "Nothing of this kind in the library.");
}

function playFile(f) {
  lib.index = lib.files.indexOf(f);
  document.body.classList.toggle("video", f.kind === "video");
  media.src = "/api/file?path=" + encodeURIComponent(f.path);
  media.play().catch(() => {});
  $("now-title").textContent = f.name;
  $("now-sub").textContent = f.folder || f.library;
  $("art-note").textContent = f.name;
  document.querySelectorAll("#list .item").forEach((el, i) => el.classList.toggle("playing", lib.shown[i] === f));
}

function step(dir) {
  const pool = lib.shown.length ? lib.shown : lib.files;
  if (!pool.length) return;
  const cur = lib.index >= 0 ? pool.indexOf(lib.files[lib.index]) : -1;
  let next;
  if (lib.shuffle) next = Math.floor(Math.random() * pool.length);
  else next = (cur + dir + pool.length) % pool.length;
  playFile(pool[next]);
}

$("play").addEventListener("click", () => { if (!media.src) return step(1); media.paused ? media.play() : media.pause(); });
$("prev").addEventListener("click", () => step(-1));
$("next").addEventListener("click", () => step(1));
$("shuffle").addEventListener("click", () => { lib.shuffle = !lib.shuffle; $("shuffle").classList.toggle("on", lib.shuffle); });
$("repeat").addEventListener("click", () => { lib.repeat = !lib.repeat; $("repeat").classList.toggle("on", lib.repeat); media.loop = lib.repeat; });
media.addEventListener("play", () => { $("play").innerHTML = "&#10074;&#10074;"; });
media.addEventListener("pause", () => { $("play").innerHTML = "&#9654;"; });
media.addEventListener("ended", () => { if (!lib.repeat) step(1); });
media.addEventListener("timeupdate", () => {
  $("time").textContent = `${fmtTime(media.currentTime)} / ${fmtTime(media.duration)}`;
  if (media.duration) $("seek").value = Math.round(1000 * media.currentTime / media.duration);
});
media.addEventListener("error", () => toast("This file would not play: it may have moved (press Rescan), or its codec is not supported here", "err"));
$("seek").addEventListener("input", () => { if (media.duration) media.currentTime = media.duration * $("seek").value / 1000; });

function setVolume(v, save) {
  v = Math.max(0, Math.min(100, Math.round(Number(v) || 0)));
  media.volume = v / 100; $("vol").value = v; $("vol-n").value = v;
  if (save) { clearTimeout(setVolume.t); setVolume.t = setTimeout(() => api("/api/settings", { volume: v }).catch(() => {}), 400); }
}
$("vol").addEventListener("input", () => setVolume($("vol").value, true));
$("vol-n").addEventListener("change", () => setVolume($("vol-n").value, true));

// a library can hold 5000 files: redraw once typing pauses, not per key
$("q").addEventListener("input", () => { clearTimeout(renderList.t); renderList.t = setTimeout(() => { lib.q = $("q").value; renderList(); }, 120); });
document.querySelectorAll("#kind button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#kind button").forEach((x) => x.classList.toggle("on", x === b));
  lib.kind = b.dataset.kind; renderList();
}));
$("rescan").addEventListener("click", loadLibrary);

document.addEventListener("keydown", (e) => {
  const typing = ["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName);
  if (e.key === "/" && !typing) { e.preventDefault(); selectTab("library"); $("q").focus(); return; }
  if (typing || currentTab !== "library") return;
  if (e.code === "Space") { e.preventDefault(); $("play").click(); }
  else if (e.key === "ArrowRight" && e.shiftKey) step(1);
  else if (e.key === "ArrowLeft" && e.shiftKey) step(-1);
  else if (e.key === "ArrowRight") media.currentTime += 10;
  else if (e.key === "ArrowLeft") media.currentTime -= 10;
  else if (e.key === "ArrowUp") { e.preventDefault(); setVolume(Number($("vol").value) + 5, true); }
  else if (e.key === "ArrowDown") { e.preventDefault(); setVolume(Number($("vol").value) - 5, true); }
});

/* ------------------------------------------------------ the site views */
const views = {}; // name -> {id, url, title, back, forward}

function view(op, extra = {}) { if (inForge) window.parent.postMessage({ forge: "view", op, ...extra }, "*"); }

function rectOf(name) {
  const r = $("view-" + name).getBoundingClientRect();
  const z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
  return [r.left * z, r.top * z, r.width * z, r.height * z];
}

function ensureView(name) {
  if (!inForge) return;
  if (!views[name]) {
    views[name] = { id: "media-" + name, url: SITES[name].home };
    view("create", { id: views[name].id, url: SITES[name].home, rect: rectOf(name) });
    $("view-" + name).querySelector(".placeholder").hidden = true;
  }
  view("rect", { id: views[name].id, rect: rectOf(name) });
}

// only the open tab's page is visible; the others are hidden, not closed,
// so YouTube keeps playing its audio when you flip to the library
function syncViews() {
  Object.entries(views).forEach(([name, v]) => view(currentTab === name ? "show" : "hide", { id: v.id }));
  if (views[currentTab]) view("rect", { id: views[currentTab].id, rect: rectOf(currentTab) });
}
new ResizeObserver(() => syncViews()).observe(document.body);
addEventListener("message", (e) => {
  const m = e.data || {};
  if (m.forge === "view-layout") syncViews();
  if (m.forge === "view-event" && m.event && m.event.event === "state") {
    const name = Object.keys(views).find((n) => views[n].id === m.event.id);
    if (!name) return;
    Object.assign(views[name], { url: m.event.url || views[name].url, title: m.event.title });
    if (document.activeElement !== $("addr-" + name)) $("addr-" + name).value = views[name].url;
  }
});

function siteGo(name, text) {
  ensureView(name);
  text = (text || "").trim();
  const url = !text ? SITES[name].home : /^https?:\/\//i.test(text) ? text : /^[\w.-]+\.[a-z]{2,}(\/|$)/i.test(text) ? "https://" + text : SITES[name].search(text);
  view("navigate", { id: views[name].id, url });
}
document.querySelectorAll(".addr").forEach((inp) => inp.addEventListener("keydown", (e) => {
  if (e.key === "Enter") siteGo(inp.id.replace("addr-", ""), inp.value);
}));
document.querySelectorAll("[data-home]").forEach((b) => b.addEventListener("click", () => siteGo(b.dataset.home, "")));
document.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => {
  const v = views[b.dataset.site]; if (v) view(b.dataset.nav, { id: v.id });
}));
document.querySelectorAll("[data-firefox]").forEach((b) => b.addEventListener("click", async () => {
  const name = b.dataset.firefox;
  const url = (views[name] && views[name].url) || $("addr-" + name).value || SITES[name].home;
  try { await api("/api/open-firefox", { url }); toast("Opened in Firefox", "ok"); } catch (e) { toast(e.message, "err"); }
}));
document.querySelectorAll("[data-download]").forEach((b) => b.addEventListener("click", () => {
  const v = views[b.dataset.download];
  const url = (v && v.url) || $("addr-" + b.dataset.download).value;
  if (!/watch\?v=|youtu\.be\//.test(url || "")) return toast("Open a video first, then press Download", "err");
  $("dl-text").value = url; selectTab("download"); $("dl-find").click();
}));

/* -------------------------------------------------------------- download */
let picks = []; // {id,title,url,duration,uploader,channel_url,on}
let dlJob = null;
let lastChannel = "";

$("dl-find").addEventListener("click", async () => {
  const text = $("dl-text").value.trim();
  if (!text) return toast("Paste a link or type a channel name", "err");
  $("dl-find").disabled = true; $("dl-found").textContent = "asking YouTube…";
  const log = $("dl-findlog"); log.textContent = "";
  let job;
  const limit = Math.min(500, Math.max(1, parseInt($("dl-limit").value) || 60));
  try { job = await api("/api/yt/list", { text, limit }); }
  catch (e) { $("dl-find").disabled = false; $("dl-found").textContent = ""; return toast(e.message, "err"); }
  forgeStreamInto(job.job_id, log, {
    onDone: async () => {
      $("dl-find").disabled = false;
      let j;
      try { j = await api(`/api/jobs/${job.job_id}`); }
      catch (e) { $("dl-found").textContent = ""; return toast("Could not read the list: " + e.message, "err"); }
      const r = j.result || { entries: [] };
      picks = r.entries.map((e) => ({ ...e, on: true }));
      lastChannel = r.channel_url || (picks[0] && picks[0].channel_url) || "";
      const chanBtn = $("dl-channel");
      chanBtn.hidden = !lastChannel || /\/videos$/.test(r.target || "");
      chanBtn.textContent = `List all of ${r.uploader || picks[0]?.uploader || "this channel"}'s videos`;
      $("dl-found").textContent = r.title ? `${r.title}: ${picks.length} item(s)` : `${picks.length} item(s)`;
      renderPicks();
    },
    onError: (m) => { $("dl-find").disabled = false; $("dl-found").textContent = ""; toast("Search failed: " + m, "err"); },
  });
});
$("dl-channel").addEventListener("click", () => { if (lastChannel) { $("dl-text").value = lastChannel; $("dl-find").click(); } });

function renderPicks() {
  const box = $("dl-list"); box.innerHTML = "";
  picks.forEach((p) => {
    const row = document.createElement("label"); row.className = "item";
    const cb = document.createElement("input"); cb.type = "checkbox"; cb.checked = p.on;
    cb.addEventListener("change", () => { p.on = cb.checked; countPicks(); });
    const name = document.createElement("span"); name.className = "name"; name.textContent = p.title; name.title = p.title;
    const meta = document.createElement("span"); meta.className = "meta"; meta.textContent = (p.duration ? fmtTime(p.duration) + " · " : "") + (p.uploader || "");
    row.append(cb, name, meta); box.appendChild(row);
  });
  countPicks();
}
function countPicks() {
  const n = picks.filter((p) => p.on).length;
  $("dl-count").textContent = picks.length ? `${n} of ${picks.length} selected` : "";
  $("dl-go").textContent = `⇣ Download ${n ? n + " selected" : "selected"}`;
}
$("dl-all").addEventListener("click", () => { picks.forEach((p) => { p.on = true; }); renderPicks(); });
$("dl-none").addEventListener("click", () => { picks.forEach((p) => { p.on = false; }); renderPicks(); });

$("dl-go").addEventListener("click", async () => {
  const urls = picks.filter((p) => p.on && p.url).map((p) => p.url);
  if (!urls.length) return toast("Find something and tick it first", "err");
  if ($("dl-go").disabled) return;
  $("dl-go").disabled = true; // a double click starts one download, not two
  let job;
  try { job = await api("/api/yt/download", { urls, kind: $("dl-kind").value, folder: $("dl-folder").value.trim() || null }); }
  catch (e) { $("dl-go").disabled = false; return toast(e.message, "err"); }
  dlJob = job.job_id;
  const prog = $("dl-progress"); prog.value = 0; prog.style.display = "";
  $("dl-go").disabled = true; $("dl-stop").disabled = false;
  const box = $("dl-log"); box.textContent = "";
  const finish = () => { $("dl-go").disabled = false; $("dl-stop").disabled = true; dlJob = null; loadLibrary(); };
  forgeStreamInto(dlJob, box, {
    onProgress: (e) => { prog.value = e.frac; },
    onDone: () => { finish(); prog.value = 1; toast("Download finished -- it is in the library", "ok"); },
    onError: (m) => { finish(); toast("Download failed: " + m, "err"); },
  });
});
$("dl-stop").addEventListener("click", () => { if (dlJob) api(`/api/jobs/${dlJob}/stop`, {}).catch((e) => toast("Could not stop: " + e.message, "err")); });

/* -------------------------------------------------------------- settings */
async function loadSettings() {
  const s = await api("/api/settings");
  $("set-folders").value = (s.folders || []).join("\n");
  $("set-download").value = s.download_folder || "";
  $("dl-folder").placeholder = s.download_folder || "~/Music/Forge";
  setVolume(s.volume ?? 80, false);
  ForgeMode.init(!!s.advanced_mode);
  $("tools").textContent = `yt-dlp ${s.ytdlp ? "found" : "missing (pacman -S yt-dlp)"} · ffmpeg ${s.ffmpeg ? "found" : "missing"} · Firefox ${s.firefox ? "found" : "missing"}`;
  if (!s.ytdlp) toast("yt-dlp is not installed, so Download will not work", "err");
}
$("set-save").addEventListener("click", async () => {
  const folders = $("set-folders").value.split("\n").map((s) => s.trim()).filter(Boolean);
  $("set-save").disabled = true;
  try {
    await api("/api/settings", { folders, download_folder: $("set-download").value.trim() || "~/Music/Forge" });
    $("set-note").textContent = "Saved"; loadLibrary();
  } catch (e) { $("set-note").textContent = "Not saved: " + e.message; }
  finally { $("set-save").disabled = false; }
});
// ForgeMode.set posts {values:{advanced_mode}}; this backend takes the flat
// form, so mirror the change here as well.
document.querySelectorAll("#modeSimple, #modeAdvanced").forEach((b) => b.addEventListener("click", () =>
  api("/api/settings", { advanced_mode: b.id === "modeAdvanced" }).catch(() => {})));

initClearButtons();

// Start: settings, then the library. A server that is not up yet gets a calm
// note in the list and a retry that slows from 2 s to 30 s, only while the
// page is in view; it stops once the settings arrive.
async function boot() {
  try { await loadSettings(); }
  catch (e) {
    listNote("Can't reach the Media server. Trying again by itself…", true);
    if (!boot.retry) boot.retry = ForgeIdle.poll(boot, 2000, { backoff: 2, maxMs: 30000 });
    return false;
  }
  if (boot.retry) { boot.retry.stop(); boot.retry = null; }
  await loadLibrary();
}
boot();

// #download and friends open on that tab, for links from other apps. Last,
// because switching tabs touches `views`, declared further down: run at the
// top it threw and took the whole page down (2026-09-25).
if (/^#(library|youtube|crunchyroll|download|settings)$/.test(location.hash)) selectTab(location.hash.slice(1));
