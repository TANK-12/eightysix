/* Browser frontend: tabs, address bar, bookmarks, history, the Firefox import,
 * and the command loop the Claude panel drives.
 *
 * The pages are real WebKit views owned by forge.py (forge_views.py). This page
 * asks for them by postMessage {forge: "view", op, ...}; the hub adds this app's
 * name, moves the rect into window coordinates, and hands it on. What happens in
 * a page comes back as {forge: "view-event", event}. Outside Forge there are no
 * views, and the page says so.
 */

const $ = (id) => document.getElementById(id);
const inForge = window.parent !== window;
const HEADERS = { "Content-Type": "application/json", "X-Forge": "1" };
const state = { tabs: [], active: null, prefs: {}, bookmarks: [], top: [], serial: 1 };
const covers = new Set(); // things drawn over the page area: the menu, the dialogs
const closedTabs = []; // the newest last, for Ctrl+Shift+T
let offline = false; // this app's own server is not answering
const readWaiters = new Map();
let cookieWaiter = null;

async function api(path, options = {}) {
  const r = await fetch(path, { ...options, headers: { ...HEADERS, ...(options.headers || {}) } });
  if (r.status === 204) return null;
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

function note(text) {
  const box = $("note");
  box.textContent = text;
  box.classList.remove("hidden");
  clearTimeout(note.timer);
  note.timer = setTimeout(() => box.classList.add("hidden"), 3500);
}

// Why a request failed, for a note: the server being away is said calmly.
const why = (e) => (offline || e instanceof TypeError ? "the server is not answering" : e.message);

const isBlank = (url) => !url || url === "about:blank";
const hostOf = (url) => { try { return new URL(url).host; } catch (e) { return ""; } };
const initial = (text) => (text || "?").replace(/^www\./, "").trim().charAt(0).toUpperCase() || "?";

/* --------------------------------------------------------------- the views */

function view(op, extra = {}) {
  if (inForge) window.parent.postMessage({ forge: "view", op, ...extra }, "*");
}

function viewportRect() {
  const r = $("viewport").getBoundingClientRect();
  // Settings' "size inside apps" zooms this page; the rect must be in the
  // window's own pixels.
  const z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
  return [r.left * z, r.top * z, r.width * z, r.height * z];
}

function sendRects() {
  const rect = viewportRect();
  state.tabs.forEach((t) => view("rect", { id: t.id, rect }));
}
new ResizeObserver(sendRects).observe($("viewport"));
addEventListener("resize", sendRects);
// A reload from inside this page is invisible to the hub, and a message sent
// while the page unloads never arrives. So the page keeps its view ids in
// sessionStorage, which survives the reload, and closes the old page's views
// when it boots; otherwise they would show over the new one.
const LIVE_VIEWS = "browser.views";
function rememberViews() {
  try { sessionStorage.setItem(LIVE_VIEWS, JSON.stringify(state.tabs.map((t) => t.id))); } catch (e) {}
}
function closeLeftoverViews() {
  let ids = [];
  try { ids = JSON.parse(sessionStorage.getItem(LIVE_VIEWS) || "[]"); } catch (e) {}
  (Array.isArray(ids) ? ids : []).forEach((id) => view("close", { id: String(id) }));
}

const tabById = (id) => state.tabs.find((t) => t.id === id);
const activeTab = () => tabById(state.active);

// A page shows only for the open tab, only once it has an address, and never
// under the menu or a dialog (a native view would cover them).
function syncVisibility() {
  state.tabs.forEach((t) => {
    const show = t.id === state.active && !isBlank(t.url) && covers.size === 0;
    if (t.shown !== show) {
      t.shown = show;
      view(show ? "show" : "hide", { id: t.id });
    }
  });
  const t = activeTab();
  $("start").classList.toggle("hidden", !!t && !isBlank(t.url));
}

function cover(name, on) {
  if (on) covers.add(name); else covers.delete(name);
  syncVisibility();
}

/* ---------------------------------------------------------------- tabs */

function newTab(url = "about:blank", { activate = true, title = "" } = {}) {
  const id = `tab-${Date.now().toString(36)}-${state.serial++}`;
  const tab = { id, url, title: title || (isBlank(url) ? "New tab" : url), loading: !isBlank(url),
    progress: 0, back: false, forward: false, shown: true, zoom: 1 };
  state.tabs.push(tab);
  view("create", { id, url, rect: viewportRect(), ...pageKeys() });
  rememberViews();
  if (activate) selectTab(id); else { syncVisibility(); renderTabs(); }
  saveSessionSoon();
  return tab;
}

function selectTab(id) {
  if (!tabById(id)) return;
  state.active = id;
  syncVisibility();
  renderTabs();
  renderToolbar();
  saveSessionSoon();
}

function closeTab(id) {
  const at = state.tabs.findIndex((t) => t.id === id);
  if (at < 0) return;
  view("close", { id });
  const [gone] = state.tabs.splice(at, 1);
  if (!isBlank(gone.url)) {
    closedTabs.push({ url: gone.url, title: gone.title });
    if (closedTabs.length > 20) closedTabs.shift();
  }
  rememberViews();
  if (!state.tabs.length) {
    newTab();
    return;
  }
  if (state.active === id) selectTab(state.tabs[Math.min(at, state.tabs.length - 1)].id);
  renderTabs();
  saveSessionSoon();
}

// The server's store.resolve, for when the server is not answering: an
// address as typed, a path on this computer as a file:/// address, a host
// with the scheme added, or a search. ~ needs the home folder from the
// records, so before they ever loaded ~/x is a search.
const HOSTLIKE = /^(localhost|[\w-]+(\.[\w-]+)+|\d{1,3}(\.\d{1,3}){3})(:\d+)?(\/.*)?$/;
function resolveHere(text) {
  const s = String(text || "").trim();
  if (!s) return "about:blank";
  if (/^https?:\/\//i.test(s) || s.startsWith("file:///") || s === "about:blank") return s;
  const home = state.homeDir;
  if (s.startsWith("/") || (home && (s === "~" || s.startsWith("~/")))) {
    const path = s.startsWith("/") ? s : home + s.slice(1);
    return "file://" + path.split("/").map(encodeURIComponent).join("/");
  }
  if (!/\s/.test(s) && HOSTLIKE.test(s)) return `${/^(localhost|127\.)/.test(s) ? "http" : "https"}://${s}`;
  const template = (state.search || {})[state.prefs.engine] || "https://duckduckgo.com/?q={q}";
  return template.replace("{q}", encodeURIComponent(s).replace(/%20/g, "+"));
}

async function resolve(text) {
  if (!offline) {
    try { return (await api(`/api/resolve?text=${encodeURIComponent(text)}`)).url; } catch (e) { /* below */ }
  }
  return resolveHere(text);
}

function reopenTab() {
  const t = closedTabs.pop();
  if (t) newTab(t.url, { title: t.title });
  else note("No closed tab to reopen");
}

async function go(text, tab) {
  const t = tab || activeTab() || newTab();
  const url = await resolve(text);
  t.url = url;
  t.title = url;
  t.loading = !isBlank(url);
  view("navigate", { id: t.id, url });
  syncVisibility();
  renderTabs();
  renderToolbar();
  saveSessionSoon();
  return t;
}

function renderTabs() {
  const strip = $("tabs");
  strip.querySelectorAll(".tab").forEach((n) => n.remove());
  state.tabs.forEach((t) => {
    const b = document.createElement("div");
    b.className = "tab" + (t.id === state.active ? " active" : "") + (t.loading ? " loading" : "");
    b.title = `${t.title}\n${t.url}`;
    const ico = document.createElement("span");
    ico.className = "ico";
    ico.textContent = t.loading ? "" : initial(hostOf(t.url) || t.title);
    const label = document.createElement("span");
    label.className = "t";
    label.textContent = t.title || "New tab";
    const x = document.createElement("button");
    x.type = "button";
    x.className = "x";
    x.textContent = "×";
    x.title = "Close tab (Ctrl+W)";
    x.addEventListener("click", (e) => { e.stopPropagation(); closeTab(t.id); });
    b.append(ico, label, x);
    b.addEventListener("click", () => selectTab(t.id));
    b.addEventListener("auxclick", (e) => { if (e.button === 1) closeTab(t.id); });
    strip.insertBefore(b, $("new-tab"));
  });
  // A strip wider than the window: the tab just picked scrolls into view, clear
  // of the + that stays pinned at the right.
  const a = strip.querySelector(".tab.active");
  if (a && renderTabs.active !== state.active) {
    const s = strip.getBoundingClientRect();
    const r = a.getBoundingClientRect();
    const room = $("new-tab").offsetWidth + 8;
    if (r.left < s.left) strip.scrollLeft -= s.left - r.left + 8;
    else if (r.right > s.right - room) strip.scrollLeft += r.right - (s.right - room);
  }
  renderTabs.active = state.active;
}

function renderToolbar() {
  const t = activeTab();
  $("back").disabled = !t || !t.back;
  $("forward").disabled = !t || !t.forward;
  if (document.activeElement !== $("address")) $("address").value = t && !isBlank(t.url) ? t.url : "";
  $("lock").textContent = t && t.url.startsWith("https://") ? "🔒" : "";
  const marked = t && state.bookmarks.some((b) => b.url === t.url);
  $("star").textContent = marked ? "★" : "☆";
  $("star").classList.toggle("on", !!marked);
  $("star").disabled = !t || !/^https?:/.test(t.url);
  const bar = $("progress").firstElementChild;
  bar.style.width = t && t.loading ? `${Math.max(8, Math.round((t.progress || 0) * 100))}%` : "0";
  $("zoom-level").textContent = `${Math.round(((t && t.zoom) || 1) * 100)}%`;
}

/* ------------------------------------------------------------- page events */

addEventListener("message", (e) => {
  if (e.source !== window.parent) return;
  const m = e.data || {};
  if (m.forge === "view-event" && m.event) onViewEvent(m.event);
  if (m.forge === "view-layout") sendRects();
});

function onViewEvent(ev) {
  if (ev.event === "state") {
    const t = tabById(ev.id);
    if (!t) return;
    const wasLoading = t.loading;
    Object.assign(t, { title: ev.title || t.title, url: ev.url || t.url, loading: ev.loading,
      progress: ev.progress, back: ev.back, forward: ev.forward });
    if (wasLoading && !ev.loading && /^https?:/.test(t.url) && t.visited !== t.url) {
      t.visited = t.url;
      api("/api/visit", { method: "POST", body: JSON.stringify({ url: t.url, title: t.title }) }).catch(() => {});
    }
    syncVisibility();
    renderTabs();
    if (t.id === state.active) renderToolbar();
    saveSessionSoon();
  } else if (ev.event === "open") {
    newTab(ev.url);
  } else if (ev.event === "read") {
    const done = readWaiters.get(ev.request);
    if (done) { readWaiters.delete(ev.request); done(ev.page); }
  } else if (ev.event === "cookies") {
    if (cookieWaiter) { cookieWaiter(ev.count); cookieWaiter = null; }
  } else if (ev.event === "download") {
    note(ev.done ? `Saved ${String(ev.file).split("/").pop()} to Downloads` : `Download failed: ${ev.error}`);
  } else if (ev.event === "key") {
    // A shortcut pressed while a page had the keyboard; forge.py gave the
    // keyboard to the hub, and a shortcut that leaves you on a page hands it
    // back to that page.
    const s = SHORTCUTS[ev.combo];
    if (!s) return;
    s.run();
    const t = activeTab();
    if (s.page && t && !isBlank(t.url)) view("focus", { id: t.id });
  } else if (ev.event === "unshown") {
    note(`${decodeURIComponent(String(ev.url).split("/").pop())} can't be shown here (${ev.mime || "unknown type"})`);
  } else if (ev.event === "crashed") {
    const t = tabById(ev.id);
    if (!t) return;
    const name = t.title && t.title !== t.url ? t.title : hostOf(t.url) || "A page";
    note(ev.reloaded ? `${name} stopped working, so it was loaded again`
      : `${name} stopped working again. Press reload to try once more`);
  }
}

/* ------------------------------------------------------ bookmarks and history */

function siteButton(item, cls = "site") {
  const b = document.createElement("button");
  b.type = "button";
  b.className = cls;
  b.title = item.url;
  const ico = document.createElement("span");
  ico.className = "ico";
  ico.textContent = initial(hostOf(item.url));
  const words = document.createElement("span");
  words.className = "words";
  const title = document.createElement("div");
  title.textContent = item.title || hostOf(item.url) || item.url;
  const host = document.createElement("div");
  host.className = "host";
  host.textContent = hostOf(item.url);
  words.append(title, host);
  b.append(ico, words);
  b.addEventListener("click", () => go(item.url));
  return b;
}

function renderStart() {
  const now = new Date();
  $("start-clock").textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  $("start-top").replaceChildren(...state.top.slice(0, 8).map((i) => siteButton(i)));
  $("start-marks").replaceChildren(...state.bookmarks.slice(0, 16).map((i) => siteButton(i)));
  $("top-label").classList.toggle("empty", !state.top.length);
  $("marks-label").classList.toggle("empty", !state.bookmarks.length);
  const bar = $("bookmark-bar");
  bar.replaceChildren(...state.bookmarks.map((b) => {
    const el = document.createElement("button");
    el.type = "button";
    el.textContent = b.title || hostOf(b.url);
    el.title = b.url;
    el.addEventListener("click", () => go(b.url));
    return el;
  }));
}
ForgeIdle.poll(renderStart, 30000);

let starBusy = false; // a second click before the first is saved does nothing
async function toggleBookmark() {
  const t = activeTab();
  if (starBusy || !t || !/^https?:/.test(t.url)) return;
  starBusy = true;
  const marked = state.bookmarks.some((b) => b.url === t.url);
  try {
    const body = marked
      ? await api(`/api/bookmarks?url=${encodeURIComponent(t.url)}`, { method: "DELETE" })
      : await api("/api/bookmarks", { method: "POST", body: JSON.stringify({ url: t.url, title: t.title }) });
    state.bookmarks = body.bookmarks;
    renderToolbar();
    renderStart();
    if (side.kind === "bookmarks") renderSide();
    note(marked ? "Bookmark removed" : "Bookmarked");
  } catch (e) {
    note(`Could not ${marked ? "remove" : "save"} the bookmark: ${why(e)}`);
  } finally {
    starBusy = false;
  }
}

const side = { kind: null };

function openSide(kind) {
  side.kind = side.kind === kind ? null : kind;
  $("side").classList.toggle("hidden", !side.kind);
  $("side-search").value = "";
  if (side.kind) renderSide();
}

function sideMessage(text) {
  const p = document.createElement("p");
  p.className = "side-empty";
  p.textContent = text;
  $("side-list").replaceChildren(p);
}

let sideSeq = 0; // typing fast: only the newest search may fill the list
async function renderSide() {
  const typed = $("side-search").value.trim();
  const q = typed.toLowerCase();
  const kind = side.kind;
  const seq = ++sideSeq;
  $("side-title").textContent = kind === "history" ? "History" : "Bookmarks";
  $("clear-history").classList.toggle("hidden", kind !== "history");
  let items;
  if (kind === "history") {
    try {
      items = (await api(`/api/history?limit=200&q=${encodeURIComponent(q)}`)).history;
    } catch (e) {
      if (seq === sideSeq) sideMessage("History could not be loaded just now. Close and open this panel to try again.");
      return;
    }
    if (seq !== sideSeq || side.kind !== kind) return;
  } else {
    items = state.bookmarks.filter((b) => !q || `${b.title} ${b.url}`.toLowerCase().includes(q));
  }
  if (!items.length) {
    sideMessage(typed ? `Nothing matches \u201c${typed}\u201d.`
      : kind === "history" ? "No history yet. Pages you visit show up here."
      : "No bookmarks yet. Press \u2606 in the toolbar to keep a page here.");
    return;
  }
  $("side-list").replaceChildren(...items.map((item) => {
    const row = siteButton(item, "row");
    if (side.kind === "bookmarks" && item.folder) {
      const folder = document.createElement("span");
      folder.className = "folder";
      folder.textContent = item.folder;
      row.appendChild(folder);
    }
    if (side.kind === "bookmarks") {
      const x = document.createElement("span");
      x.className = "x";
      x.textContent = "×";
      x.title = "Remove bookmark";
      x.addEventListener("click", async (e) => {
        e.stopPropagation();
        try {
          state.bookmarks = (await api(`/api/bookmarks?url=${encodeURIComponent(item.url)}`, { method: "DELETE" })).bookmarks;
        } catch (err) {
          note("Could not remove the bookmark: " + why(err));
          return;
        }
        renderSide();
        renderStart();
        renderToolbar();
      });
      row.appendChild(x);
    }
    return row;
  }));
}

/* ------------------------------------------------------------ menu and import */

function toggleMenu(on) {
  const open = on === undefined ? $("menu").classList.contains("hidden") : on;
  $("menu").classList.toggle("hidden", !open);
  cover("menu", open);
}

async function openImport() {
  toggleMenu(false);
  $("dialog").classList.remove("hidden");
  cover("dialog", true);
  $("imp-result").textContent = "";
  try {
    const found = await api("/api/firefox");
    $("import-where").textContent = found.profile ? `From ${found.profile}` : "No Firefox profile was found.";
    $("imp-go").disabled = !found.profile;
  } catch (e) {
    $("import-where").textContent = why(e);
  }
}

function closeImport() {
  $("dialog").classList.add("hidden");
  cover("dialog", false);
}

async function runImport() {
  $("imp-go").disabled = true;
  $("imp-result").textContent = "Importing…";
  const said = [];
  try {
    if ($("imp-bookmarks").checked || $("imp-history").checked) {
      const counts = await api("/api/firefox/import", { method: "POST",
        body: JSON.stringify({ bookmarks: $("imp-bookmarks").checked, history: $("imp-history").checked }) });
      if ($("imp-bookmarks").checked) said.push(`${counts.bookmarks} bookmarks`);
      if ($("imp-history").checked) said.push(`${counts.history} pages of history`);
    }
    if ($("imp-cookies").checked) {
      if (!inForge) {
        said.push("cookies need Forge open");
      } else {
        const { cookies } = await api("/api/firefox/cookies");
        const count = await new Promise((resolve) => {
          cookieWaiter = resolve;
          view("cookies", { cookies });
          setTimeout(() => { if (cookieWaiter) { cookieWaiter = null; resolve(null); } }, 15000);
        });
        said.push(count === null ? "cookies were sent but Forge did not confirm" : `${count} cookies`);
      }
    }
    const fresh = await api("/api/state");
    state.bookmarks = fresh.bookmarks;
    state.top = fresh.top;
    renderStart();
    renderToolbar();
    $("imp-result").textContent = `Imported ${said.join(", ")}.`;
  } catch (e) {
    $("imp-result").textContent = "Import failed: " + why(e);
  } finally {
    $("imp-go").disabled = false;
  }
}

function zoomBy(step) {
  const t = activeTab();
  if (!t) return;
  t.zoom = Math.max(0.3, Math.min(3, Math.round((t.zoom + step) * 10) / 10));
  view("zoom", { id: t.id, level: t.zoom });
  renderToolbar();
}

async function openFirefox(url) {
  try {
    await api("/api/open-firefox", { method: "POST", body: JSON.stringify({ url: url || "" }) });
    note("Opened in Firefox");
  } catch (e) {
    note("Could not open Firefox: " + why(e));
  }
}

/* ------------------------------------------------------------------ session */

let sessionTimer = null;
// Changed while the server was away or before the saved tabs came: saved once
// they are in, never over them.
let sessionDirty = false;
function saveSessionSoon() {
  clearTimeout(sessionTimer);
  sessionTimer = setTimeout(() => {
    if (offline || !state.loaded) { sessionDirty = true; return; }
    const tabs = state.tabs.map((t) => ({ url: t.url, title: t.title }));
    const active = Math.max(0, state.tabs.findIndex((t) => t.id === state.active));
    api("/api/session", { method: "POST", body: JSON.stringify({ tabs, active }) }).catch(() => {});
  }, 800);
}

/* ------------------------------------------ commands from the Claude panel */

function readTab(tab, timeout = 10000) {
  return new Promise((resolve) => {
    const request = `r${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
    const timer = setTimeout(() => { readWaiters.delete(request); resolve({ error: "The page did not answer" }); }, timeout);
    readWaiters.set(request, (page) => { clearTimeout(timer); resolve(page); });
    view("read", { id: tab.id, request });
  });
}

function settle(tab, timeout = 15000) {
  const started = Date.now();
  return new Promise((resolve) => {
    const check = () => {
      if ((!tab.loading && Date.now() - started > 400) || Date.now() - started > timeout) resolve();
      else setTimeout(check, 200);
    };
    setTimeout(check, 300);
  });
}

const tabInfo = (t) => ({ index: state.tabs.indexOf(t), id: t.id, url: t.url, title: t.title,
  active: t.id === state.active, loading: t.loading });

async function runCommand(c) {
  const pick = () => (c.tab === undefined || c.tab === null ? activeTab()
    : typeof c.tab === "number" ? state.tabs[c.tab] : tabById(c.tab));
  if (c.op === "tabs") return { ok: true, tabs: state.tabs.map(tabInfo) };
  if (c.op === "open" || c.op === "search") {
    const text = c.op === "search" ? c.query : c.url;
    if (!text) return { ok: false, error: "Nothing to open" };
    const tab = c.new_tab ? newTab() : activeTab() || newTab();
    await go(text, tab);
    if (c.new_tab === true || tab.id !== state.active) selectTab(tab.id);
    await settle(tab);
    return { ok: true, tab: tabInfo(tab) };
  }
  const tab = pick();
  if (!tab) return { ok: false, error: "No such tab" };
  if (c.op === "read") {
    if (isBlank(tab.url)) return { ok: true, page: { title: "New tab", url: "about:blank", text: "", links: [] } };
    if (!inForge) return { ok: false, error: "Pages can only be read inside Forge" };
    const page = await readTab(tab);
    const limit = Math.max(1000, Math.min(200000, Number(c.max_chars) || 40000));
    if (page.text && page.text.length > limit) { page.text = page.text.slice(0, limit); page.truncated = true; }
    return { ok: !page.error, page, tab: tabInfo(tab) };
  }
  if (c.op === "back" || c.op === "forward" || c.op === "reload") {
    view(c.op, { id: tab.id });
    await settle(tab, 8000);
    return { ok: true, tab: tabInfo(tab) };
  }
  if (c.op === "switch") { selectTab(tab.id); return { ok: true, tab: tabInfo(tab) }; }
  if (c.op === "close") { closeTab(tab.id); return { ok: true, tabs: state.tabs.map(tabInfo) }; }
  return { ok: false, error: `Unknown op ${c.op}` };
}

// The server not answering is shown as a calm strip above the page area (a
// page would cover anything drawn over it). Pages keep working; records and
// the Claude panel's commands wait, and everything picks up by itself.
let stateLoading = null;
function setOffline(on) {
  if (on !== offline) {
    offline = on;
    $("offline").classList.toggle("hidden", !on);
  }
  if (on) return;
  // Records the boot could not load are fetched again on the loop's pace, the
  // saved tabs with them; the tabs changed meanwhile are saved after that.
  if (state.loaded) saveDirty();
  else if (!stateLoading) {
    stateLoading = loadState(true).then(saveDirty, () => {}).finally(() => { stateLoading = null; });
  }
}
function saveDirty() {
  if (sessionDirty) { sessionDirty = false; saveSessionSoon(); }
}

// One loop for the life of the page. While the server is away it asks again
// after 3 s, then 6, 12, 24 and every 30 s, never in a burst, and without the
// 25 s hold, so the strip clears as soon as the server answers.
async function commandLoop() {
  let wait = 3000;
  for (;;) {
    let command;
    try {
      command = await api(`/api/agent/next?wait=${offline ? 0 : 25}`);
      setOffline(false);
      wait = 3000;
    } catch (e) {
      setOffline(true);
      await new Promise((r) => setTimeout(r, wait));
      wait = Math.min(30000, wait * 2);
      continue;
    }
    if (!command) continue;
    let result;
    try { result = await runCommand(command); } catch (e) { result = { ok: false, error: String(e.message || e) }; }
    try {
      await api(`/api/agent/result/${command.cid}`, { method: "POST", body: JSON.stringify(result) });
    } catch (e) { /* the caller has timed out or the server went away; the loop notices */ }
  }
}

/* ---------------------------------------------------------------- wiring */

$("new-tab").addEventListener("click", () => newTab());
// The strip's scrollbar is hidden: a mouse wheel scrolls it sideways.
$("tabs").addEventListener("wheel", (e) => {
  if (Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
  e.preventDefault();
  $("tabs").scrollLeft += e.deltaY;
}, { passive: false });
$("back").addEventListener("click", () => activeTab() && view("back", { id: state.active }));
$("forward").addEventListener("click", () => activeTab() && view("forward", { id: state.active }));
$("reload").addEventListener("click", () => activeTab() && view("reload", { id: state.active }));
$("address-form").addEventListener("submit", (e) => {
  e.preventDefault();
  // the page gets the keyboard, so arrows and space scroll it at once
  go($("address").value).then((t) => { if (!isBlank(t.url)) view("focus", { id: t.id }); });
  $("address").blur();
});
// Focus picks the whole address, so the first character typed replaces it.
// When the hub gets the keyboard back from a page, WebKit puts the old caret
// back some time after the focus event, and what was typed went onto the end
// of the old address; so the first character picks it all again. A click or a
// caret key first means the caret is placed on purpose.
let pickOnType = false;
function pickAddress() {
  $("address").select();
  pickOnType = true;
}
$("address").addEventListener("focus", pickAddress);
$("address").addEventListener("mousedown", () => { pickOnType = false; });
$("address").addEventListener("keydown", (e) => {
  if (pickOnType && e.key.length === 1 && !e.ctrlKey && !e.altKey && !e.metaKey) $("address").select();
  pickOnType = false;
});
$("start-form").addEventListener("submit", (e) => {
  e.preventDefault();
  go($("start-search").value);
  $("start-search").value = "";
});
$("star").addEventListener("click", toggleBookmark);
$("open-bookmarks").addEventListener("click", () => openSide("bookmarks"));
$("open-history").addEventListener("click", () => openSide("history"));
$("side-close").addEventListener("click", () => openSide(side.kind));
$("side-search").addEventListener("input", () => renderSide());
$("clear-history").addEventListener("click", async () => {
  cover("confirm", true);
  let sure = false;
  try { sure = await ForgeDialog.confirm("Clear all browsing history here? Firefox's history is not touched."); } finally { cover("confirm", false); }
  if (!sure) return;
  try { await api("/api/history", { method: "DELETE" }); } catch (e) { note("Could not clear the history: " + why(e)); return; }
  state.top = [];
  renderSide();
  renderStart();
});
$("firefox").addEventListener("click", () => {
  const t = activeTab();
  openFirefox(t && /^https?:/.test(t.url) ? t.url : "");
});
$("menu-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleMenu(); });
document.addEventListener("click", (e) => {
  if (!$("menu").classList.contains("hidden") && !$("menu").contains(e.target)) toggleMenu(false);
});
$("menu").addEventListener("click", (e) => {
  const b = e.target.closest("[data-menu]");
  if (!b) return;
  const what = b.dataset.menu;
  if (what === "import") openImport();
  if (what === "reopen") { toggleMenu(false); reopenTab(); }
  if (what === "firefox") { toggleMenu(false); openFirefox(""); }
  if (what === "zoom-in") zoomBy(0.1);
  if (what === "zoom-out") zoomBy(-0.1);
});
async function savePrefs(change) {
  try {
    state.prefs = await api("/api/prefs", { method: "POST", body: JSON.stringify(change) });
  } catch (e) {
    note("Could not save the setting: " + why(e));
  }
  $("engine").value = state.prefs.engine;
  $("restore-tabs").checked = !!state.prefs.restore_tabs;
}
$("engine").addEventListener("change", (e) => savePrefs({ engine: e.target.value }));
$("restore-tabs").addEventListener("change", (e) => savePrefs({ restore_tabs: e.target.checked }));
$("show-bar").addEventListener("change", (e) => {
  $("bookmark-bar").classList.toggle("hidden", !e.target.checked);
  try { localStorage.setItem("browser.bar", e.target.checked ? "1" : "0"); } catch (err) {}
});
$("imp-cancel").addEventListener("click", closeImport);
$("imp-go").addEventListener("click", runImport);

// The keyboard shortcuts, one row each, named as forge_views.key_combo names
// them (letters and F keys only: other keys are named differently there).
// Every page view is made with this list, so they work while a page has the
// keyboard too: `first` rows before the page sees them (a tab's own keys, as
// Chrome keeps them), the rest only when the page leaves them alone (a web
// terminal's Ctrl+L stays its own). `page` rows hand the keyboard back to the
// page after. Alt+Left/Right are Forge's own (the app before or after).
const SHORTCUTS = {
  "ctrl+l": { run: () => { $("address").focus(); pickAddress(); } },
  "ctrl+t": { run: () => { newTab(); $("address").focus(); }, first: true },
  "ctrl+shift+t": { run: () => reopenTab(), page: true, first: true },
  "ctrl+w": { run: () => state.active && closeTab(state.active), page: true, first: true },
  "ctrl+d": { run: () => toggleBookmark(), page: true },
  f5: { run: () => $("reload").click(), page: true },
  "ctrl+r": { run: () => $("reload").click(), page: true },
};
function pageKeys() {
  const rows = Object.entries(SHORTCUTS);
  return { keys: rows.filter(([, s]) => !s.first).map(([k]) => k),
    keys_first: rows.filter(([, s]) => s.first).map(([k]) => k) };
}
function comboOf(e) {
  return [e.ctrlKey && "ctrl", e.shiftKey && "shift", e.altKey && "alt", e.metaKey && "super", e.key.toLowerCase()]
    .filter(Boolean).join("+");
}

document.addEventListener("keydown", (e) => {
  const s = SHORTCUTS[comboOf(e)];
  if (s) { e.preventDefault(); s.run(); }
  else if (e.key === "Escape") { toggleMenu(false); if (!$("dialog").classList.contains("hidden")) closeImport(); }
});

// The records from the server, and with `restore` the saved tabs. After a boot
// with the server away, the boot's untouched blank tab gives way to the saved
// tabs, and tabs opened meanwhile stay beside them.
async function loadState(restore) {
  const body = await api("/api/state");
  state.loaded = true;
  state.prefs = body.prefs;
  state.bookmarks = body.bookmarks;
  state.top = body.top;
  state.engines = body.engines;
  state.search = body.search || {};
  state.homeDir = typeof body.home_dir === "string" ? body.home_dir : "";
  $("engine").replaceChildren(...body.engines.map((name) => {
    const o = document.createElement("option");
    o.value = name;
    o.textContent = name.charAt(0).toUpperCase() + name.slice(1);
    return o;
  }));
  $("engine").value = body.prefs.engine;
  $("restore-tabs").checked = body.prefs.restore_tabs;
  let bar = false;
  try { bar = localStorage.getItem("browser.bar") === "1"; } catch (e) {}
  $("show-bar").checked = bar;
  $("bookmark-bar").classList.toggle("hidden", !bar);
  renderStart();
  renderToolbar();
  if (side.kind) renderSide();
  if (!restore) return;
  const spare = state.tabs.length === 1 && isBlank(state.tabs[0].url) ? state.tabs[0].id : null;
  const kept = state.tabs.length && !spare;
  const open = new Set(state.tabs.map((t) => t.url));
  const saved = (body.prefs.restore_tabs ? body.session.tabs : []).filter((t) => !open.has(t.url));
  if (!saved.length) {
    if (!state.tabs.length) newTab();
    return;
  }
  saved.forEach((t) => newTab(t.url, { activate: false, title: t.title }));
  if (spare) closeTab(spare);
  if (!kept) selectTab(state.tabs[Math.max(0, Math.min(body.session.active, state.tabs.length - 1))].id);
}

async function boot() {
  $("standalone").classList.toggle("hidden", inForge);
  closeLeftoverViews();
  try {
    await loadState(true);
  } catch (e) {
    if (!inForge) note("Could not load: " + e.message);
    if (!state.tabs.length) newTab();
  }
  if (inForge) commandLoop();
}

boot();
