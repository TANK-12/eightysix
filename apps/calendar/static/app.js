/* Calendar page: month (dots per source), week and day timelines, search,
 * source filters, adding and editing events and reminders, feeder switches,
 * and a Jan summary of a day. Data: web_app.py's /api routes. */

const $ = (id) => document.getElementById(id);
const H = { "Content-Type": "application/json", "X-Forge": "1" };
const DOWN = "The Calendar backend is not answering. It keeps trying by itself.";
async function api(path, opts = {}) {
  let r;
  try {
    r = await fetch(path, { ...opts, headers: { ...H, ...(opts.headers || {}) } });
  } catch (e) {
    offline();
    throw new Error(DOWN);
  }
  if (reconnect) online();
  if (!r.ok) {
    let d = r.statusText;
    try { d = (await r.json()).detail || d; } catch (e) {}
    throw new Error(d);
  }
  return r.json();
}
const send = (path, method, body) => api(path, { method, body: JSON.stringify(body || {}) });

const SOURCES = {
  emerson: ["You", "#f2c14e"], claude: ["Claude Code", "#e0916b"], jan: ["Jan", "#6ea8fe"],
  nyarch: ["Nyarch", "#c38bff"], apps: ["Apps", "#7cc4a8"], forge: ["Forge", "#59d499"],
  hyprland: ["Hyprland", "#4cc9f0"], script: ["Scripts", "#f2637d"],
};
const KIND_LABEL = { said: "Said", app_open: "Opened", app_close: "Closed", session: "Session", task: "Task",
  note: "Note", reminder: "Reminder", milestone: "Milestone" };
const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
const VIEWS = ["month", "week", "day"];
const S = { view: "month", at: startOfDay(new Date()), hidden: new Set(), query: "", editing: null, feeders: null, kinds: [],
  summaries: new Map(), summing: new Set() };

function load(key, fallback) { try { return JSON.parse(localStorage.getItem("cal." + key)) ?? fallback; } catch (e) { return fallback; } }
function keep(key, value) { try { localStorage.setItem("cal." + key, JSON.stringify(value)); } catch (e) {} }

function startOfDay(d) { const x = new Date(d); x.setHours(0, 0, 0, 0); return x; }
function addDays(d, n) { const x = new Date(d); x.setDate(x.getDate() + n); return x; }
function mondayOf(d) { const x = startOfDay(d); return addDays(x, -((x.getDay() + 6) % 7)); }
const secs = (d) => d.getTime() / 1000;
const ymd = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
const hm = (ts) => new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hourCycle: "h23" });
const base = (src) => src.split(":")[0];
const colour = (src) => (SOURCES[base(src)] || ["", "#8b93a3"])[1];

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function visibleSources() { return Object.keys(SOURCES).filter((s) => !S.hidden.has(s)); }

async function fetchEvents(start, end, extra = {}) {
  const p = new URLSearchParams({ start: secs(start), end: secs(end), sources: visibleSources().join(","), ...extra });
  return (await api("/api/events?" + p)).events;
}

/* ------------------------------------------------------------ rows */

function eventRow(e) {
  const r = el("div", `ev${e.source === "emerson" ? " mine" : ""}${e.done ? " done" : ""}`);
  r.append(el("span", "t", hm(e.ts)));
  const dot = el("span", "dot");
  dot.style.background = colour(e.source);
  r.append(dot);
  const icon = e.kind === "reminder" ? "⏰ " : e.kind === "milestone" ? "⭐ " : "";
  r.append(el("span", "title", icon + e.title));
  r.append(el("span", "src", `${(SOURCES[base(e.source)] || [e.source])[0]} · ${KIND_LABEL[e.kind] || e.kind}`));
  r.title = e.body || e.title;
  r.addEventListener("click", () => openForm(e));
  return r;
}

/* ------------------------------------------------------------ views */

async function drawMonth() {
  const first = new Date(S.at.getFullYear(), S.at.getMonth(), 1);
  const start = mondayOf(first);
  const end = addDays(start, 42);
  $("title").textContent = first.toLocaleDateString([], { month: "long", year: "numeric" });
  const offset = -new Date().getTimezoneOffset() * 60;
  const [counts, mine] = await Promise.all([
    api(`/api/days?start=${secs(start)}&end=${secs(end)}&offset=${offset}`),
    fetchEvents(start, end, { sources: "emerson,script" }),
  ]);
  const grid = el("div", "month");
  DOW.forEach((d) => grid.appendChild(el("div", "dow", d)));
  const today = ymd(new Date());
  for (let i = 0; i < 42; i++) {
    const day = addDays(start, i);
    const key = ymd(day);
    const cell = el("div", "cell" + (day.getMonth() !== first.getMonth() ? " other" : "") + (key === today ? " today" : ""));
    cell.appendChild(el("span", "n", day.getDate()));
    const dots = el("div", "dots");
    Object.entries(counts.days[key] || {}).forEach(([src, n]) => {
      if (S.hidden.has(src)) return;
      const d = el("span", "dot");
      d.style.background = colour(src);
      d.title = `${(SOURCES[src] || [src])[0]}: ${n}`;
      dots.append(d, document.createTextNode(n + " "));
    });
    cell.appendChild(dots);
    mine.filter((e) => ymd(new Date(e.ts * 1000)) === key && !S.hidden.has(base(e.source))).slice(0, 3).forEach((e) => {
      cell.appendChild(el("div", "mine", (e.kind === "reminder" ? "⏰ " : "") + e.title));
    });
    cell.addEventListener("click", () => { S.at = day; setView("day"); });
    grid.appendChild(cell);
  }
  return grid;
}

async function drawWeek() {
  const start = mondayOf(S.at);
  const end = addDays(start, 7);
  $("title").textContent = `Week of ${start.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}`;
  const events = await fetchEvents(start, end);
  const grid = el("div", "week");
  const today = ymd(new Date());
  for (let i = 0; i < 7; i++) {
    const day = addDays(start, i);
    const col = el("div", "wcol" + (ymd(day) === today ? " today" : ""));
    const h = el("h5", "", day.toLocaleDateString([], { weekday: "short", day: "numeric" }));
    h.addEventListener("click", () => { S.at = day; setView("day"); });
    col.appendChild(h);
    const mine = events.filter((e) => ymd(new Date(e.ts * 1000)) === ymd(day));
    mine.slice(0, 60).forEach((e) => col.appendChild(eventRow(e)));
    if (mine.length > 60) col.appendChild(el("div", "muted small", `+${mine.length - 60} more: open the day`));
    grid.appendChild(col);
  }
  return grid;
}

async function drawDay(quiet) {
  const start = startOfDay(S.at);
  const end = addDays(start, 1);
  $("title").textContent = start.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const events = await fetchEvents(start, end);
  // the minute tick redraws the day only when something new was logged
  const sig = secs(start) + JSON.stringify(events);
  if (quiet && $("body").firstElementChild?.dataset.sig === sig) return null;
  const key = secs(start);
  const box = el("div");
  box.dataset.sig = sig;
  const head = el("div", "day-head");
  head.append(el("span", "muted small", `${events.length} things logged`));
  const sum = el("button", "btn", "✨ Sum up this day with Jan");
  sum.title = "Uses the Calendar's own Jan model: it loads on demand and is released when idle.";
  sum.disabled = S.summing.has(key);
  sum.addEventListener("click", () => summarise(start, end));
  head.append(sum);
  box.appendChild(head);
  // a summary already asked for stays when the day is drawn again
  const out = el("div", "summary" + (S.summaries.has(key) ? "" : " hidden"), S.summaries.get(key) || "");
  out.dataset.day = key;
  box.appendChild(out);
  if (!events.length) box.appendChild(el("div", "empty", "Nothing logged on this day (with the sources shown)."));
  const list = el("div", "list");
  let hour = -1;
  events.forEach((e) => {
    const h = new Date(e.ts * 1000).getHours();
    if (h !== hour) { hour = h; list.appendChild(el("div", "hour", `${String(h).padStart(2, "0")}:00`)); }
    list.appendChild(eventRow(e));
  });
  box.appendChild(list);
  return box;
}

// The answer is kept per day, so a redraw while Jan works (or after) shows it.
async function summarise(start, end) {
  const key = secs(start);
  if (S.summing.has(key)) return;
  S.summing.add(key);
  const show = (text) => {
    S.summaries.set(key, text);
    const out = document.querySelector(`.summary[data-day="${key}"]`);
    if (out) { out.textContent = text; out.classList.remove("hidden"); }
    const button = out && out.parentElement.querySelector(".day-head .btn");
    if (button) button.disabled = S.summing.has(key);
  };
  show("Asking Jan… (the model loads if it is not already)");
  let text;
  try {
    text = (await send("/api/summary", "POST", { start: secs(start), end: secs(end) })).summary;
  } catch (e) {
    text = "Could not sum up: " + e.message;
  }
  S.summing.delete(key);
  show(text);
}

async function drawSearch() {
  $("title").textContent = `Search: ${S.query}`;
  const p = new URLSearchParams({ q: S.query, sources: visibleSources().join(","), limit: 500 });
  const events = (await api("/api/events?" + p)).events.reverse();
  if (!events.length) return el("div", "empty", "Nothing matches.");
  const list = el("div", "list");
  let day = "";
  events.forEach((e) => {
    const d = new Date(e.ts * 1000).toLocaleDateString([], { weekday: "short", day: "numeric", month: "short", year: "numeric" });
    if (d !== day) { day = d; list.appendChild(el("div", "hour", d)); }
    list.appendChild(eventRow(e));
  });
  return list;
}

// Clicks can start a draw before the last one answered: only the newest one
// is put on screen, so a slow older answer never replaces a newer view.
// quiet: the minute tick, which keeps what is shown when nothing changed or
// the backend did not answer.
let drawSeq = 0;
async function draw(quiet) {
  const seq = ++drawSeq;
  const body = $("body");
  document.querySelectorAll("#views button").forEach((b) => b.classList.toggle("on", !S.query && b.dataset.view === S.view));
  if (!quiet) body.classList.add("busy");
  try {
    const node = S.query ? await drawSearch() : S.view === "month" ? await drawMonth()
      : S.view === "week" ? await drawWeek() : await drawDay(quiet);
    if (seq === drawSeq && node) body.replaceChildren(node);
  } catch (e) {
    if (seq === drawSeq && !quiet) body.replaceChildren(problem(e.message));
  } finally {
    if (seq === drawSeq) body.classList.remove("busy");
  }
}

// An error in the main pane: one calm sentence and a Try now button.
function problem(text) {
  const box = el("div", "empty", text === DOWN ? DOWN : "Could not load: " + text);
  const again = el("button", "btn retry", "Try now");
  again.type = "button";
  again.addEventListener("click", () => { again.disabled = true; retry(); });
  box.append(el("br"), again);
  return box;
}

function setView(v) { S.view = VIEWS.includes(v) ? v : "month"; S.query = ""; $("search").value = ""; keep("view", S.view); draw(); }

function step(n) {
  if (S.view === "month") S.at = new Date(S.at.getFullYear(), S.at.getMonth() + n, 1);
  else S.at = addDays(S.at, S.view === "week" ? 7 * n : n);
  draw();
}

/* ------------------------------------------------------------ side panel */

function drawFilters() {
  const box = $("filters");
  box.replaceChildren();
  Object.entries(SOURCES).forEach(([key, [label, c]]) => {
    const l = el("label");
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = !S.hidden.has(key);
    cb.addEventListener("change", () => { cb.checked ? S.hidden.delete(key) : S.hidden.add(key); keep("hidden", [...S.hidden]); draw(); });
    const dot = el("span", "dot");
    dot.style.background = c;
    l.append(cb, dot, document.createTextNode(label));
    box.appendChild(l);
  });
}

function ago(t) {
  const s = Math.round(Date.now() / 1000 - t);
  return s < 60 ? `${Math.max(0, s)}s ago` : s < 3600 ? `${Math.round(s / 60)} min ago`
    : s < 172800 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} days ago`;
}

function drawFeeders() {
  const box = $("feeders");
  box.replaceChildren();
  S.feeders.feeders.forEach((f) => {
    const l = el("label");
    l.title = f.description;
    const cb = el("input");
    cb.type = "checkbox";
    cb.checked = f.enabled;
    cb.addEventListener("change", () => saveSettings({ enabled: { [f.name]: cb.checked } }));
    l.append(cb, document.createTextNode(f.label));
    if (f.last) {
      const last = el("span", "last" + (f.last.error ? " err" : ""), f.last.error ? "error" : `+${f.last.added} · ${ago(f.last.at)}`);
      if (f.last.error) last.title = f.last.error;
      l.appendChild(last);
    }
    box.appendChild(l);
  });
  $("paused").checked = S.feeders.settings.paused;
  $("keep").value = S.feeders.settings.keep_days;
}

async function loadFeeders() {
  S.feeders = await api("/api/feeders");
  S.kinds = S.feeders.kinds;
  drawFeeders();
}

// On failure the switches go back to what is really saved.
async function saveSettings(changes) {
  try { S.feeders = { ...S.feeders, ...(await send("/api/feeders/settings", "POST", changes)) }; drawFeeders(); }
  catch (e) { if (S.feeders) drawFeeders(); ForgeDialog.alert(e.message); }
}

/* ------------------------------------------------------------ add / edit */

function localInput(ts) {
  const d = new Date(ts * 1000);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 16);
}

function openForm(e) {
  S.editing = e || null;
  const kinds = $("f-kind");
  if (!kinds.options.length) S.kinds.forEach((k) => { const o = el("option", "", KIND_LABEL[k] || k); o.value = k; kinds.appendChild(o); });
  const now = S.view === "day" && !e ? secs(S.at) + (new Date().getHours() * 3600) : Date.now() / 1000;
  $("form-title").textContent = e ? `${(SOURCES[base(e.source)] || [e.source])[0]} · ${KIND_LABEL[e.kind] || e.kind}` : "New event";
  $("f-title").value = e ? e.title : "";
  $("f-kind").value = e ? e.kind : "note";
  $("f-when").value = localInput(e ? e.ts : now);
  $("f-end").value = e && e.end_ts ? localInput(e.end_ts) : "";
  $("f-body").value = e ? e.body : "";
  $("f-tags").value = e ? e.tags.join(", ") : "";
  $("f-delete").classList.toggle("hidden", !e);
  $("dialog").classList.remove("hidden");
  $("f-title").focus();
}

function closeForm() { $("dialog").classList.add("hidden"); S.editing = null; }

// Enter twice or a double click on Save must not log the event twice.
let saving = false;
$("form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  if (saving) return;
  const body = {
    title: $("f-title").value, kind: $("f-kind").value,
    ts: new Date($("f-when").value).getTime() / 1000,
    end_ts: $("f-end").value ? new Date($("f-end").value).getTime() / 1000 : null,
    body: $("f-body").value, tags: $("f-tags").value,
  };
  const save = $("form").querySelector('button[type="submit"]');
  saving = true;
  save.disabled = true;
  try {
    if (S.editing) await send(`/api/events/${S.editing.id}`, "PATCH", { ...body, done: body.kind === "reminder" && body.ts > Date.now() / 1000 ? false : S.editing.done });
    else await send("/api/events", "POST", { ...body, source: "emerson" });
    closeForm();
    draw();
  } catch (e) { ForgeDialog.alert(e.message); }
  finally { saving = false; save.disabled = false; }
});
$("f-cancel").addEventListener("click", closeForm);
$("dialog").addEventListener("click", (e) => { if (e.target === $("dialog")) closeForm(); });
$("f-delete").addEventListener("click", async () => {
  const del = $("f-delete");
  if (del.disabled || !S.editing || !await ForgeDialog.confirm(`Delete "${S.editing.title}"?`)) return;
  del.disabled = true;
  try {
    await send(`/api/events/${S.editing.id}`, "DELETE");
    closeForm();
    draw();
  } catch (e) { ForgeDialog.alert(e.message); }
  finally { del.disabled = false; }
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeForm(); });

/* ------------------------------------------------------------ wiring */

$("add").addEventListener("click", () => openForm());
$("prev").addEventListener("click", () => step(-1));
$("next").addEventListener("click", () => step(1));
$("today").addEventListener("click", () => { S.at = startOfDay(new Date()); draw(); });
document.querySelectorAll("#views button").forEach((b) => b.addEventListener("click", () => setView(b.dataset.view)));
let typing = 0;
$("search").addEventListener("input", () => {
  clearTimeout(typing);
  typing = setTimeout(() => { S.query = $("search").value.trim(); draw(); }, 300);
});
$("paused").addEventListener("change", () => saveSettings({ paused: $("paused").checked }));
// an emptied, negative or unreadable box goes back to the saved number instead of
// quietly saving 0 (which means keep forever)
$("keep").addEventListener("change", () => {
  const v = $("keep").value.trim();
  if (v === "" || !Number.isFinite(+v) || +v < 0) { if (S.feeders) $("keep").value = S.feeders.settings.keep_days; return; }
  saveSettings({ keep_days: Math.round(+v) });
});

/* ------------------------------------------------------------ live updates */

// Every minute while on screen: the feeder list, and the day view when it
// shows something new. While the backend is down (any request failed to
// connect) that poll stops and a reconnect poll knocks after 5 s, then waits
// twice as long each time up to a minute, so a dead backend is not hammered;
// the first answer brings the minute poll back and redraws.
let live = null, reconnect = null;

async function tick() {
  try { await loadFeeders(); } catch (e) { return false; }
  if (S.view === "day" && !S.query) await draw(true);
}

function goLive() { if (!live) live = ForgeIdle.poll(tick, 60000, { backoff: 2, maxMs: 300000 }); }

function offline() {
  $("conn").classList.remove("hidden");
  if (live) { live.stop(); live = null; }
  if (reconnect) return;
  reconnect = ForgeIdle.poll(async () => {
    try { await loadFeeders(); } catch (e) { return false; }
    await draw();
  }, 5000, { backoff: 2, maxMs: 60000 });
}

function online() {
  if (reconnect) { reconnect.stop(); reconnect = null; }
  $("conn").classList.add("hidden");
  goLive();
}

async function retry() {
  try { await loadFeeders(); } catch (e) { /* api() keeps the reconnect poll going */ }
  await draw();
}

(async function boot() {
  const view = load("view", "month");
  S.view = VIEWS.includes(view) ? view : "month";
  S.hidden = new Set(load("hidden", []));
  const hash = new URLSearchParams(location.hash.slice(1));
  if (VIEWS.includes(hash.get("view"))) S.view = hash.get("view");
  const at = startOfDay(new Date(hash.get("date") + "T00:00"));
  if (hash.get("date") && !isNaN(at)) S.at = at;
  drawFilters();
  try { await loadFeeders(); } catch (e) {
    $("body").replaceChildren(problem(e.message));
    offline();
    return;
  }
  await draw();
  goLive();
})();
