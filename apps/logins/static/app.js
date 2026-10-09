/* Logins: one tab per account in shared/accounts.json.
 *
 * Each tab's page is a native WebKit view (forge_views.py) created with
 * session = the account id, so it has its own cookie store. "Bring login in"
 * fetches the account's Firefox cookies from the backend and hands them to
 * forge.py for that session only, then reloads the page. */

const $ = (id) => document.getElementById(id);
const HEADERS = { "X-Forge": "1" };
const inForge = window.parent !== window;
const state = { accounts: [], active: null, views: {} };

// `offline` marks a backend that did not answer at all (starting, restarting).
async function api(path, options = {}) {
  let r;
  try { r = await fetch(path, { ...options, headers: { ...HEADERS, ...(options.headers || {}) } }); }
  catch (e) { throw Object.assign(new Error("The Logins backend is not answering."), { offline: true }); }
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

function view(op, extra = {}) {
  if (inForge) window.parent.postMessage({ forge: "view", op, ...extra }, "*");
}

function status(text) { $("status").textContent = text || ""; }

function viewportRect() {
  const r = $("viewport").getBoundingClientRect();
  const z = parseFloat(getComputedStyle(document.documentElement).zoom) || 1;
  return [r.left * z, r.top * z, r.width * z, r.height * z];
}

function sendRects() {
  const rect = viewportRect();
  Object.values(state.views).forEach((v) => view("rect", { id: v.id, rect }));
}
new ResizeObserver(sendRects).observe($("viewport"));
addEventListener("resize", sendRects);

const account = (id) => state.accounts.find((a) => a.id === id);

function drawTabs() {
  $("tabs").replaceChildren(...state.accounts.map((a) => {
    const tab = document.createElement("button");
    tab.type = "button";
    tab.className = "tab" + (a.id === state.active ? " active" : "") + (state.views[a.id] ? " in" : "");
    tab.setAttribute("aria-pressed", String(a.id === state.active));
    tab.title = `${a.url}\nSigns in through its own Firefox window`;
    const dot = document.createElement("span");
    dot.className = "dot";
    const name = document.createElement("span");
    name.className = "n";
    name.textContent = a.label;
    tab.append(dot, name);
    tab.addEventListener("click", () => select(a.id));
    return tab;
  }));
}

function select(id) {
  const a = account(id);
  if (!a) return;
  state.active = id;
  try { localStorage.setItem("logins.active", id); } catch (e) {}
  if (!state.views[id] && inForge) {
    const viewId = `login-${id}`;
    state.views[id] = { id: viewId, url: a.url, title: "" };
    view("create", { id: viewId, url: a.url, rect: viewportRect(), session: id });
  }
  Object.entries(state.views).forEach(([aid, v]) => view(aid === id ? "show" : "hide", { id: v.id }));
  $("empty").classList.toggle("hidden", inForge);
  if (!inForge) $("empty-text").textContent = "Open this app inside Forge to see the pages; here it can only sign in through Firefox.";
  drawTabs();
  drawWhere();
  syncBring();
  const tab = $("tabs").children[state.accounts.indexOf(a)];
  if (tab) tab.scrollIntoView({ block: "nearest", inline: "nearest" });
}

// The tab strip hides its scrollbar, so a plain mouse wheel scrolls it sideways.
$("tabs").addEventListener("wheel", (e) => {
  const t = e.currentTarget;
  if (t.scrollWidth <= t.clientWidth || Math.abs(e.deltaY) <= Math.abs(e.deltaX)) return;
  t.scrollLeft += e.deltaY;
  e.preventDefault();
}, { passive: false });

function drawWhere() {
  const a = account(state.active);
  const v = a && state.views[a.id];
  $("where").textContent = a ? `${a.label} · ${(v && v.url) || a.url}` : "";
}

function activeView() { return state.active && state.views[state.active]; }

$("back").addEventListener("click", () => activeView() && view("back", { id: activeView().id }));
$("forward").addEventListener("click", () => activeView() && view("forward", { id: activeView().id }));
$("reload").addEventListener("click", () => activeView() && view("reload", { id: activeView().id }));

// Each button is locked while its request runs, so a double click opens one
// Firefox window and sends the cookies once.
$("signin").addEventListener("click", async () => {
  const b = $("signin");
  if (!state.active || b.disabled) return;
  b.disabled = true;
  try { status((await api(`/api/accounts/${encodeURIComponent(state.active)}/signin`, { method: "POST" })).message + " When you are signed in there, press Bring login in."); }
  catch (e) { status(e.message); }
  finally { b.disabled = false; }
});

// Bring login in stays locked, for that account only, until forge.py says
// the cookies are in, or for 20 s at most (a Forge too old to answer, or a
// lost message).
const waits = new Map();  // account id -> its 20 s timer (0 while reading)
function syncBring() { $("bring").disabled = waits.has(state.active); }
function bringDone(id) {
  clearTimeout(waits.get(id));
  waits.delete(id);
  syncBring();
}

$("bring").addEventListener("click", async () => {
  const id = state.active, b = $("bring");
  if (!id || b.disabled || waits.has(id)) return;
  if (!inForge) { status("Bring login in works inside Forge."); return; }
  waits.set(id, 0);
  syncBring();
  try {
    const { cookies } = await api(`/api/accounts/${encodeURIComponent(id)}/cookies`);
    if (!cookies.length) { status("Firefox has no sign-in for this account yet. Press Sign in in Firefox first."); bringDone(id); return; }
    view("cookies", { cookies, session: id });
    status(`Sending ${cookies.length} cookies…`);
    waits.set(id, setTimeout(() => {
      if (!waits.has(id)) return;
      bringDone(id);
      const a = account(id);
      status(`Forge did not confirm the login arrived${a ? " for " + a.label : ""}. Press Bring login in to try again.`);
    }, 20000));
  } catch (e) { status(e.message); bringDone(id); }
});

addEventListener("message", (e) => {
  if (e.source !== window.parent) return;
  const m = e.data || {};
  if (m.forge === "view-layout") sendRects();
  if (m.forge !== "view-event" || !m.event) return;
  const ev = m.event;
  if (ev.event === "cookies" && ev.session && waits.has(ev.session)) {
    bringDone(ev.session);
    const v = state.views[ev.session], a = account(ev.session);
    status(`${ev.count} cookies brought in for ${a ? a.label : ev.session}; reloading.`);
    if (v && a) view("navigate", { id: v.id, url: a.url });
    return;
  }
  const entry = Object.entries(state.views).find(([, v]) => v.id === ev.id);
  if (entry && ev.event === "state") {
    Object.assign(entry[1], { url: ev.url || entry[1].url, title: ev.title || "" });
    drawWhere();
  }
});

/* The first load. If the backend is not up yet, or accounts.json has a
   mistake, the start card says so and it tries again by itself (2 s, growing
   to 30 s, resting while Logins is hidden). */
let starter = null;
function startCard(title, text, retry) {
  $("empty").classList.remove("hidden");
  $("empty-title").textContent = title;
  $("empty-text").textContent = text;
  $("empty-retry").hidden = !retry;
  $("empty").classList.toggle("problem", !!retry);
}

async function start() {
  try { state.accounts = (await api("/api/accounts")).accounts; }
  catch (e) {
    startCard(e.offline ? "Logins is not reachable yet" : "accounts.json needs a look",
      (e.offline ? "Its backend is not answering, probably still starting." : e.message.replace(/([^.!?…])$/, "$1.")) + " Trying again by itself…", true);
    if (!starter && window.ForgeIdle) starter = ForgeIdle.poll(start, 2000, { backoff: 2, maxMs: 30000 });
    return false;
  }
  if (starter) starter.stop();
  starter = null;
  $("empty").classList.remove("problem");
  $("empty-title").textContent = "Logins";
  $("empty-retry").hidden = true;
  if (!state.accounts.length) {
    startCard("No accounts yet", "Add one to Forge/shared/accounts.json and open Logins again.", false);
    drawTabs();
    return true;
  }
  let first = null;
  try { first = localStorage.getItem("logins.active"); } catch (e) {}
  drawTabs();
  select(account(first) ? first : state.accounts[0].id);
  return true;
}

$("empty-retry").addEventListener("click", () => starter && starter.now());
start();
