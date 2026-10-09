/* Terminal - xterm.js tabs attached to shells in ptyhost.py over WebSockets. */
"use strict";

const $ = (id) => document.getElementById(id);
const FONT = '"CaskaydiaCove Nerd Font Mono", "CaskaydiaCove NFM", "JetBrains Mono", "DejaVu Sans Mono", monospace';
const SHELLS = new Set(["bash", "zsh", "fish", "sh", "dash", "nu"]);

const S = {
  token: "",
  home: "",
  tabs: [],          // {el, root, focus}: root is the pane tree (see panesOf)
  tab: null,         // the tab in front
  active: null,      // its focused pane: {id, term, fit, search, ws, el, info, dead}
  fontSize: loadNum("term.font", 14),
};

function loadNum(key, def) {
  try { return Number(localStorage.getItem(key)) || def; } catch { return def; }
}
function save(key, v) { try { localStorage.setItem(key, String(v)); } catch { /* private */ } }

async function api(path, opts = {}) {
  // a backend that takes the connection but never answers fails after 15 s
  const init = { method: opts.method || "GET", headers: { "X-Forge": "1" }, signal: AbortSignal.timeout(15000) };
  if (opts.body !== undefined) {
    init.method = "POST";
    init.headers["Content-Type"] = "application/json";
    init.body = JSON.stringify(opts.body);
  }
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(await errText(res, `${res.status}`));
  return res.json();
}

/* ---------------------------------------------------------------- colours */

function cssVar(name, fallback) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

function theme() {
  const accent = cssVar("--accent", "#8fd18a");
  return {
    // Transparent, so the Forge background (wallpaper blur) shows through.
    background: "#00000000",
    foreground: cssVar("--text", "#e6e9ef"),
    cursor: accent,
    cursorAccent: "#000000",
    selectionBackground: accent + "55",
    black: "#1d2130", red: "#f07178", green: "#a5d98a", yellow: "#f2c66d",
    blue: "#7aa2f7", magenta: "#c792ea", cyan: "#7fd6e0", white: "#c8cedb",
    brightBlack: "#5c6370", brightRed: "#ff8b92", brightGreen: "#c3e88d",
    brightYellow: "#ffd98a", brightBlue: "#9ab8ff", brightMagenta: "#dcb0ff",
    brightCyan: "#a3eef5", brightWhite: "#ffffff",
  };
}

function applyTheme() {
  const t = theme();
  for (const pane of allPanes()) pane.term.options.theme = t;
}

/* ---------------------------------------------------------------- tabs and panes
   A tab holds a tree of panes, each its own shell, like a tiling terminal: a
   leaf is {pane}, a split is {dir, ratio, a, b} ("row" puts b to the right of
   a, "col" below it). S.tab is the tab in front and S.active its focused
   pane, which the keys, find and the menu act on. Every tab's layout is kept
   in localStorage by shell id, so a reload puts the panes back. */

function panesOf(node, out = []) {
  if (!node) return out;
  if (node.pane) out.push(node.pane);
  else { panesOf(node.a, out); panesOf(node.b, out); }
  return out;
}
function allPanes() { return S.tabs.flatMap((t) => panesOf(t.root)); }
function tabOf(pane) { return S.tabs.find((t) => panesOf(t.root).includes(pane)); }
function findLeaf(node, pane) {
  if (!node) return null;
  if (node.pane) return node.pane === pane ? node : null;
  return findLeaf(node.a, pane) || findLeaf(node.b, pane);
}
function parentOf(node, child) {
  if (!node || node.pane) return null;
  if (node.a === child || node.b === child) return node;
  return parentOf(node.a, child) || parentOf(node.b, child);
}
// Turn `node` into `next` in place, so its parent keeps pointing at it.
function become(node, next) {
  for (const k of Object.keys(node)) delete node[k];
  Object.assign(node, next);
}

function tabLabel(pane) {
  const info = pane?.info || {};
  if (info.program && !SHELLS.has(info.program)) return info.program;
  const cwd = info.cwd || "";
  if (!cwd) return "shell";
  if (cwd === S.home) return "~";
  return cwd.split("/").filter(Boolean).pop() || "/";
}

function renderTabs() {
  const box = $("tabs");
  box.replaceChildren();
  for (const tab of S.tabs) {
    const panes = panesOf(tab.root);
    const el = document.createElement("div");
    el.className = "tab";
    el.role = "tab";
    el.classList.toggle("active", tab === S.tab);
    el.classList.toggle("dead", panes.every((p) => p.dead));
    const info = tab.focus?.info || {};
    el.title = (info.cwd || "") + (info.program ? ` (${info.program})` : "");
    const label = document.createElement("span");
    label.className = "label";
    label.textContent = tabLabel(tab.focus);
    el.append(label);
    if (panes.length > 1) {
      const n = document.createElement("span");
      n.className = "panes";
      n.textContent = `▦${panes.length}`;
      n.title = `${panes.length} panes`;
      el.append(n);
    }
    const x = document.createElement("button");
    x.className = "x";
    x.textContent = "×";
    x.title = "Close tab";
    x.onclick = (e) => { e.stopPropagation(); closeTab(tab); };
    el.append(x);
    el.onclick = () => activate(tab);
    el.onauxclick = (e) => { if (e.button === 1) closeTab(tab); };
    box.append(el);
  }
  $("font-size").textContent = S.fontSize;
  box.querySelector(".tab.active")?.scrollIntoView({ block: "nearest", inline: "nearest" });
  saveLayout();
}

function saveLayout() {
  const ser = (n) => (n.pane ? { p: n.pane.id } : { d: n.dir, r: +n.ratio.toFixed(3), a: ser(n.a), b: ser(n.b) });
  save("term.layout", JSON.stringify(S.tabs.filter((t) => t.root).map((t) => ({ root: ser(t.root), focus: t.focus?.id }))));
  save("term.order", allPanes().map((p) => p.id).join(","));
}

function activate(tab, pane) {
  if (!tab) return;
  S.tab = tab;
  if (pane) tab.focus = pane;
  S.active = tab.focus;
  for (const t of S.tabs) t.el.hidden = t !== tab;
  markFocus(tab);
  renderTabs();
  requestAnimationFrame(() => { fitTab(tab); S.active?.term.focus(); });
  if (S.active) save("term.active", S.active.id);
  if (findOpen()) { for (const p of allPanes()) if (p !== S.active) p.search.clearDecorations(); runFind(1, true); }
}

// A click or the keyboard landing in a pane makes it the focused one.
function focusPane(pane) {
  const tab = tabOf(pane);
  if (!tab || (tab.focus === pane && S.active === pane)) return;
  tab.focus = pane;
  if (tab !== S.tab) return;
  S.active = pane;
  markFocus(tab);
  renderTabs();
  save("term.active", pane.id);
}

function markFocus(tab) {
  const panes = panesOf(tab.root);
  for (const p of panes) p.el.classList.toggle("focused", panes.length > 1 && p === tab.focus);
}

function fitTab(tab) {
  if (!tab || tab.el.hidden) return;
  for (const p of panesOf(tab.root)) {
    try { p.fit.fit(); } catch { /* not laid out yet */ }
  }
}

// The tree as nested flex boxes. Pane elements are moved, never rebuilt, so
// each xterm keeps its screen.
function layout(tab) {
  const build = (node) => {
    if (node.pane) return node.pane.el;
    const box = document.createElement("div");
    box.className = `split ${node.dir}`;
    const a = build(node.a);
    const b = build(node.b);
    a.style.flex = `${node.ratio} 1 0`;
    b.style.flex = `${1 - node.ratio} 1 0`;
    const bar = document.createElement("div");
    bar.className = "divider";
    bar.title = "Drag to resize";
    bar.addEventListener("pointerdown", (e) => dragDivider(e, tab, node, box, a, b));
    box.append(a, bar, b);
    return box;
  };
  const root = build(tab.root);
  root.style.flex = "1 1 0";
  // moving an element drops the keyboard; give it straight back, so keys
  // typed right after a split or a close are not lost
  const had = tab.el.contains(document.activeElement);
  tab.el.replaceChildren(root);
  if (had && tab.focus && tab === S.tab) tab.focus.term.focus();
  markFocus(tab);
  requestAnimationFrame(() => fitTab(tab));
}

function dragDivider(e, tab, node, box, a, b) {
  e.preventDefault();
  const bar = e.currentTarget;
  bar.classList.add("dragging");
  try { bar.setPointerCapture(e.pointerId); } catch { /* synthetic */ }
  const move = (ev) => {
    const r = box.getBoundingClientRect();
    const t = node.dir === "row" ? (ev.clientX - r.left) / r.width : (ev.clientY - r.top) / r.height;
    node.ratio = Math.max(0.1, Math.min(0.9, t));
    a.style.flex = `${node.ratio} 1 0`;
    b.style.flex = `${1 - node.ratio} 1 0`;
    fitTab(tab);
  };
  const up = () => {
    bar.classList.remove("dragging");
    for (const [n, f] of [["pointermove", move], ["pointerup", up], ["pointercancel", up]]) bar.removeEventListener(n, f);
    fitTab(tab);
    saveLayout();
    S.active?.term.focus();
  };
  bar.addEventListener("pointermove", move);
  bar.addEventListener("pointerup", up);
  bar.addEventListener("pointercancel", up);
}

function sendJson(pane, obj) {
  if (pane.ws?.readyState === WebSocket.OPEN) pane.ws.send(JSON.stringify(obj));
}

function makeTab() {
  const el = document.createElement("div");
  el.className = "screen";
  el.hidden = true;
  $("screens").append(el);
  const tab = { el, root: null, focus: null };
  S.tabs.push(tab);
  return tab;
}

function mountPane(info, tab) {
  const el = document.createElement("div");
  el.className = "pane";
  tab.el.append(el); // in the page so xterm can measure; layout() moves it
  const term = new Terminal({
    fontFamily: FONT,
    fontSize: S.fontSize,
    cursorBlink: true,
    allowTransparency: true,
    scrollback: 10000,
    theme: theme(),
    macOptionIsMeta: true,
    rightClickSelectsWord: false,
    allowProposedApi: true,  // the search add-on's match highlights use decorations
  });
  const fit = new FitAddon.FitAddon();
  term.loadAddon(fit);
  // Ctrl+click opens links in the default browser, like VS Code.
  term.loadAddon(new WebLinksAddon.WebLinksAddon((ev, uri) => {
    if (ev.ctrlKey || ev.metaKey) window.open(uri, "_blank", "noopener");
  }));
  const search = new SearchAddon.SearchAddon();
  term.loadAddon(search);
  term.open(el);
  const pane = { id: info.id, term, fit, search, el, ws: null, info, dead: !info.alive };
  search.onDidChangeResults(({ resultIndex, resultCount }) => { if (pane === S.active) showCount(resultIndex, resultCount); });
  term.attachCustomKeyEventHandler((e) => keyFilter(e, pane));
  term.onData((d) => {
    if (pane.dead) { if (d === "\r") closePane(pane); return; }
    // taken by another window: the next key brings the shell back here
    if (pane.taken) { pane.taken = false; connect(pane); return; }
    sendJson(pane, { t: "in", d });
  });
  term.onBinary((d) => sendJson(pane, { t: "in", d }));
  term.onResize(({ cols, rows }) => sendJson(pane, { t: "resize", cols, rows }));
  el.addEventListener("focusin", () => focusPane(pane));
  el.addEventListener("contextmenu", (e) => { e.preventDefault(); focusPane(pane); showMenu(e.clientX, e.clientY, pane); });
  connect(pane);
  return pane;
}

function mountTab(info) {
  const tab = makeTab();
  const pane = mountPane(info, tab);
  tab.root = { pane };
  tab.focus = pane;
  layout(tab);
  return tab;
}

function connect(pane) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/${pane.id}?t=${encodeURIComponent(S.token)}`);
  ws.binaryType = "arraybuffer";
  pane.ws = ws;
  let reset = true;
  ws.onopen = () => {
    pane.retry = 0;
    pane.lost = false;
    const { cols, rows } = pane.term;
    sendJson(pane, { t: "resize", cols, rows });
  };
  ws.onmessage = (ev) => {
    if (typeof ev.data === "string") {
      const msg = JSON.parse(ev.data);
      if (msg.t === "exit") markDead(pane, msg.code);
      return;
    }
    // The first frame after (re)connecting is the kept scrollback: start clean.
    if (reset) { pane.term.reset(); reset = false; }
    pane.term.write(new Uint8Array(ev.data));
  };
  ws.onclose = (ev) => {
    if (pane.closing || pane.dead || pane.ws !== ws) return;
    if (ev.code === 4404) { markDead(pane, null); return; }
    if (ev.code === 4409) {
      pane.taken = true;
      note(pane, "this shell is open in another window; press a key to bring it here");
      return;
    }
    // Backend restarting (4403: it has a new token) or down: retry, slower
    // each time (1.5 s doubling to 30 s), and not while out of sight.
    if (!pane.lost && ev.code !== 4403) note(pane, "lost the Terminal backend; reconnecting");
    pane.lost = true;
    pane.retry = Math.min(pane.retry ? pane.retry * 2 : 1500, 30000);
    clearTimeout(pane.retryTimer);
    pane.retryTimer = setTimeout(() => reconnect(pane, ev.code === 4403), pane.retry);
  };
}

async function reconnect(pane, freshToken) {
  pane.retryTimer = 0;
  if (pane.closing || pane.dead || !allPanes().includes(pane)) return;
  if (!ForgeIdle.shown()) { await whenShown(); if (pane.retryTimer) return; }
  if (freshToken) {
    try { S.token = (await api("/api/session")).token; } catch { /* still down: the socket fails and we come back */ }
  }
  if (!pane.closing && !pane.dead && allPanes().includes(pane) && pane.ws?.readyState === WebSocket.CLOSED) connect(pane);
}

// Retry lost panes at once (the info poll just reached the backend again).
function reconnectNow() {
  for (const pane of allPanes()) {
    if (pane.lost && pane.retryTimer) { clearTimeout(pane.retryTimer); reconnect(pane, true); }
  }
}

function whenShown() {
  return new Promise((done) => {
    const check = () => {
      if (!ForgeIdle.shown()) return;
      document.removeEventListener("visibilitychange", check);
      document.removeEventListener("forge-visible", check);
      done();
    };
    document.addEventListener("visibilitychange", check);
    document.addEventListener("forge-visible", check);
  });
}

// A dim one-line notice in the pane; the next replay from the shell wipes it.
function note(pane, text) {
  pane.term.write(`\r\n\x1b[2m[${text}]\x1b[0m\r\n`);
}

function markDead(pane, code) {
  if (pane.dead) return;
  pane.dead = true;
  const how = code === null ? "is gone" : `exited${code ? ` with code ${code}` : ""}`;
  const what = panesOf(tabOf(pane)?.root).length > 1 ? "pane" : "tab";
  pane.term.write(`\r\n\x1b[2m[the shell ${how}; press Enter to close this ${what}]\x1b[0m\r\n`);
  renderTabs();
}

async function openShell(cwd) {
  const cur = S.active?.term;
  return api("/api/terms", {
    body: { cwd: cwd || S.active?.info?.cwd || null, cols: cur?.cols || 100, rows: cur?.rows || 30 },
  });
}

async function newTab(cwd) {
  try { activate(mountTab(await openShell(cwd))); } catch (e) { toast(e.message, "err"); }
}

// Split the focused pane: "row" puts the new shell to its right, "col" below.
async function split(dir) {
  const tab = S.tab;
  const from = S.active;
  if (!tab || !from) return;
  try {
    const pane = mountPane(await openShell(from.info?.cwd), tab);
    become(findLeaf(tab.root, from), { dir, ratio: 0.5, a: { pane: from }, b: { pane } });
    layout(tab);
    activate(tab, pane);
  } catch (e) { toast(e.message, "err"); }
}

// The nearest pane on that side of the focused one.
function moveFocus(dx, dy) {
  const tab = S.tab;
  const from = S.active;
  if (!tab || !from) return;
  const r = from.el.getBoundingClientRect();
  const cx = r.left + r.width / 2;
  const cy = r.top + r.height / 2;
  let best = null;
  let bestD = Infinity;
  for (const p of panesOf(tab.root)) {
    if (p === from) continue;
    const q = p.el.getBoundingClientRect();
    const ahead = dx > 0 ? q.left >= r.right - 2 : dx < 0 ? q.right <= r.left + 2 : dy > 0 ? q.top >= r.bottom - 2 : q.bottom <= r.top + 2;
    if (!ahead) continue;
    const d = Math.hypot(q.left + q.width / 2 - cx, q.top + q.height / 2 - cy);
    if (d < bestD) { bestD = d; best = p; }
  }
  if (best) activate(tab, best);
}

async function dropShell(pane) {
  pane.closing = true;
  if (!pane.dead) {
    try { await api(`/api/terms/${pane.id}`, { method: "DELETE" }); } catch { /* already gone */ }
  }
  pane.ws?.close();
  pane.term.dispose();
  pane.el.remove();
}

// Close one pane; its neighbour takes the space. The last pane closes the tab.
async function closePane(pane) {
  const tab = tabOf(pane);
  if (!tab) return;
  if (panesOf(tab.root).length === 1) return closeTab(tab);
  const leaf = findLeaf(tab.root, pane);
  const parent = parentOf(tab.root, leaf);
  become(parent, parent.a === leaf ? parent.b : parent.a);
  if (tab.focus === pane) tab.focus = panesOf(parent)[0];
  layout(tab);
  if (tab === S.tab) activate(tab);
  else renderTabs();
  await dropShell(pane);
  // the closed pane had the keyboard; hand it to the one now in focus
  if (tab === S.tab && S.active && !S.active.el.contains(document.activeElement)) S.active.term.focus();
}

async function closeTab(tab) {
  const i = S.tabs.indexOf(tab);
  if (i < 0) return;
  await Promise.all(panesOf(tab.root).map(dropShell));
  tab.el.remove();
  S.tabs.splice(S.tabs.indexOf(tab), 1);
  if (!S.tabs.length) { S.tab = S.active = null; await newTab(S.home); return; }
  if (S.tab === tab) activate(S.tabs[Math.min(i, S.tabs.length - 1)]);
  else renderTabs();
}

function cycle(delta) {
  if (S.tabs.length < 2) return;
  const i = S.tabs.indexOf(S.tab);
  activate(S.tabs[(i + delta + S.tabs.length) % S.tabs.length]);
}

// Rebuild the saved layouts from the shells still running; a pane whose
// shell is gone is left out and its neighbour takes the space.
function restoreLayouts(alive) {
  const byId = Object.fromEntries(alive.map((t) => [t.id, t]));
  const used = new Set();
  let saved = [];
  try { saved = JSON.parse(localStorage.getItem("term.layout") || "[]"); } catch { /* ignore */ }
  const rebuild = (n, tab) => {
    if (!n || typeof n !== "object") return null;
    if (n.p) {
      if (!byId[n.p] || used.has(n.p)) return null;
      used.add(n.p);
      return { pane: mountPane(byId[n.p], tab) };
    }
    const a = rebuild(n.a, tab);
    const b = rebuild(n.b, tab);
    if (a && b) return { dir: n.d === "col" ? "col" : "row", ratio: Math.max(0.1, Math.min(0.9, Number(n.r) || 0.5)), a, b };
    return a || b;
  };
  for (const s of Array.isArray(saved) ? saved : []) {
    const tab = makeTab();
    tab.root = rebuild(s && s.root, tab);
    if (!tab.root) { tab.el.remove(); S.tabs.pop(); continue; }
    tab.focus = panesOf(tab.root).find((p) => p.id === s.focus) || panesOf(tab.root)[0];
    layout(tab);
  }
  return used;
}

/* ---------------------------------------------------------------- font size */

function setFont(n) {
  S.fontSize = Math.max(8, Math.min(32, n));
  save("term.font", S.fontSize);
  for (const pane of allPanes()) pane.term.options.fontSize = S.fontSize;
  fitTab(S.tab);
  renderTabs();
}

/* ---------------------------------------------------------------- clipboard */

async function copySel(tab) {
  const text = tab.term.getSelection();
  if (!text) return;
  try { await navigator.clipboard.writeText(text); toast("Copied"); }
  catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
  tab.term.focus();
}

async function pasteText(tab) {
  try {
    const text = await navigator.clipboard.readText();
    if (text) tab.term.paste(text);
  } catch { toast("Press Ctrl+Shift+V to paste here"); }
  tab.term.focus();
}

/* ---------------------------------------------------------------- keys */

// Return false to stop xterm handling the key. Plain Ctrl+V is left alone on
// purpose: programs like Claude Code read it themselves to paste images.
function keyFilter(e, pane) {
  if (e.type !== "keydown") return true;
  const ctrl = e.ctrlKey || e.metaKey;
  const k = e.key.toLowerCase();
  if (ctrl && e.shiftKey && k === "c") { copySel(pane); return false; }
  if (ctrl && e.shiftKey && k === "v") return false;  // the browser's own paste event reaches xterm
  if (ctrl && e.shiftKey && k === "t") { e.preventDefault(); newTab(); return false; }
  if (ctrl && e.shiftKey && k === "w") { e.preventDefault(); closePane(pane); return false; }
  if (ctrl && e.shiftKey && k === "d") { e.preventDefault(); split("row"); return false; }
  if (ctrl && e.shiftKey && k === "e") { e.preventDefault(); split("col"); return false; }
  const arrow = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[e.key];
  if (ctrl && e.shiftKey && arrow) { e.preventDefault(); moveFocus(...arrow); return false; }
  if (ctrl && e.shiftKey && k === "f") { e.preventDefault(); openFind(); return false; }
  if (ctrl && e.key === "PageDown") { e.preventDefault(); cycle(1); return false; }
  if (ctrl && e.key === "PageUp") { e.preventDefault(); cycle(-1); return false; }
  if (ctrl && !e.shiftKey && (e.key === "=" || e.key === "+")) { e.preventDefault(); setFont(S.fontSize + 1); return false; }
  if (ctrl && !e.shiftKey && e.key === "-") { e.preventDefault(); setFont(S.fontSize - 1); return false; }
  return true;
}

/* ---------------------------------------------------------------- find */

const FIND = { caseSensitive: false, wholeWord: false, regex: false };

function hex6(v, fallback) { return /^#[0-9a-f]{6}$/i.test(v) ? v : fallback; }

// Mix two #rrggbb colours; the add-on only takes opaque #rrggbb.
function mix(a, b, t) {
  const n = (h, i) => parseInt(h.slice(i, i + 2), 16);
  return "#" + [1, 3, 5].map((i) => Math.round(n(a, i) * (1 - t) + n(b, i) * t).toString(16).padStart(2, "0")).join("");
}

function findOptions(incremental) {
  const accent = hex6(cssVar("--accent", ""), "#8fd18a");
  const bg = hex6(cssVar("--bg", ""), "#11131a");
  return {
    ...FIND,
    incremental,
    decorations: {
      matchBackground: mix(bg, accent, 0.35),
      matchOverviewRuler: accent,
      activeMatchBackground: "#f2c66d",
      activeMatchBorder: "#ffd98a",
      activeMatchColorOverviewRuler: "#f2c66d",
    },
  };
}

function findOpen() { return !$("find").classList.contains("hidden"); }

function openFind() {
  const q = $("find-q");
  const sel = S.active?.term.getSelection() || "";
  if (sel && !sel.includes("\n")) q.value = sel;
  $("find").classList.remove("hidden");
  q.focus();
  q.select();
  runFind(1, true);
}

function closeFind() {
  $("find").classList.add("hidden");
  for (const p of allPanes()) p.search.clearDecorations();
  S.active?.term.clearSelection();
  S.active?.term.focus();
}

function runFind(dir, incremental = false) {
  const tab = S.active;
  const q = $("find-q").value;
  if (!tab) return;
  if (!q) { tab.search.clearDecorations(); tab.term.clearSelection(); showCount(-1, 0, true); return; }
  let found = false;
  try {
    found = dir < 0 ? tab.search.findPrevious(q, findOptions(false)) : tab.search.findNext(q, findOptions(incremental));
  } catch { /* half-typed regular expression */ }
  $("find-q").classList.toggle("miss", !found);
  if (!found) showCount(-1, 0);
}

function showCount(index, count, empty = false) {
  let text = "";
  if (!empty) {
    if (count === 0) text = "No matches";
    else if (count < 0) text = "1000+ matches";
    else text = index >= 0 ? `${index + 1} of ${count}` : `${count} matches`;
  }
  $("find-count").textContent = text;
}

function wireFind() {
  const q = $("find-q");
  q.addEventListener("input", () => runFind(1, true));
  q.addEventListener("keydown", (e) => {
    if (e.key === "Enter") { e.preventDefault(); runFind(e.shiftKey ? -1 : 1); }
    else if (e.key === "Escape") { e.preventDefault(); closeFind(); }
    else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "f") { e.preventDefault(); q.select(); }
  });
  for (const [id, key] of [["find-case", "caseSensitive"], ["find-word", "wholeWord"], ["find-regex", "regex"]]) {
    $(id).onclick = () => {
      FIND[key] = !FIND[key];
      $(id).setAttribute("aria-pressed", String(FIND[key]));
      q.focus();
      runFind(1, true);
    };
  }
  $("find-prev").onclick = () => runFind(-1);
  $("find-next").onclick = () => runFind(1);
  $("find-close").onclick = closeFind;
}

/* ---------------------------------------------------------------- menu */

function showMenu(x, y, tab) {
  const m = $("menu");
  m.replaceChildren();
  const entries = [
    { label: "Copy", key: "Ctrl+Shift+C", disabled: !tab.term.hasSelection(), run: () => copySel(tab) },
    { label: "Paste", key: "Ctrl+Shift+V", run: () => pasteText(tab) },
    { label: "Select all", run: () => tab.term.selectAll() },
    { label: "Find…", key: "Ctrl+Shift+F", run: () => openFind() },
    "-",
    { label: "Split right", key: "Ctrl+Shift+D", run: () => split("row") },
    { label: "Split down", key: "Ctrl+Shift+E", run: () => split("col") },
    { label: "Close pane", key: "Ctrl+Shift+W", run: () => closePane(tab) },
    "-",
    { label: "New tab", key: "Ctrl+Shift+T", run: () => newTab() },
    { label: "Close tab", run: () => closeTab(tabOf(tab)) },
    { label: "Clear screen", run: () => tab.term.clear() },
    "-",
    { label: "Bigger text", key: "Ctrl+=", run: () => setFont(S.fontSize + 1) },
    { label: "Smaller text", key: "Ctrl+-", run: () => setFont(S.fontSize - 1) },
    { label: "Normal text size", run: () => setFont(14) },
  ];
  for (const e of entries) {
    if (e === "-") { m.append(document.createElement("hr")); continue; }
    const b = document.createElement("button");
    const l = document.createElement("span"); l.textContent = e.label; b.append(l);
    if (e.key) { const k = document.createElement("kbd"); k.textContent = e.key; b.append(k); }
    b.disabled = !!e.disabled;
    b.onclick = () => { hideMenu(); e.run(); };
    m.append(b);
  }
  m.classList.remove("hidden");
  const r = m.getBoundingClientRect();
  m.style.left = `${Math.min(x, innerWidth - r.width - 6)}px`;
  m.style.top = `${Math.min(y, innerHeight - r.height - 6)}px`;
}
function hideMenu() { $("menu").classList.add("hidden"); }

/* ---------------------------------------------------------------- boot */

// Returns false when the backend did not answer, so the poll backs off.
async function refreshInfo() {
  if (window.ForgeVisible && !window.ForgeVisible.on) return;
  try {
    const list = await api("/api/terms");
    const byId = Object.fromEntries(list.map((t) => [t.id, t]));
    let changed = false;
    for (const pane of allPanes()) {
      const info = byId[pane.id];
      if (!info) continue;
      if (tabLabel({ info }) !== tabLabel(pane)) changed = true;
      pane.info = info;
    }
    if (changed) renderTabs();
    reconnectNow();
  } catch { return false; /* backend restarting */ }
}

function hashCwd() {
  return new URLSearchParams(location.hash.slice(1)).get("cwd");
}

async function boot() {
  $("new-tab").onclick = () => newTab();
  $("split-right").onclick = () => split("row");
  $("split-down").onclick = () => split("col");
  $("font-up").onclick = () => setFont(S.fontSize + 1);
  $("font-down").onclick = () => setFont(S.fontSize - 1);
  wireFind();
  $("font-size").textContent = S.fontSize;
  // many tabs overflow sideways: let the mouse wheel scroll them
  $("tabs").addEventListener("wheel", (e) => {
    if (e.deltaY && !e.deltaX) { $("tabs").scrollLeft += e.deltaY; e.preventDefault(); }
  }, { passive: false });
  document.addEventListener("mousedown", (e) => { if (!e.target.closest("#menu")) hideMenu(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") hideMenu(); });
  new ResizeObserver(() => fitTab(S.tab)).observe($("screens"));
  // The hub restyles <html> when the theme changes; follow it.
  new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ["style", "class"] });
  addEventListener("hashchange", () => { const c = hashCwd(); if (c) newTab(c); });
  if (document.fonts?.ready) await document.fonts.ready;

  // The backend may still be starting (or down): say so calmly and retry,
  // 1.5 s doubling to 30 s, paused while out of sight; "Try now" skips the wait.
  for (let wait = 1500; ; wait = Math.min(wait * 2, 30000)) {
    try {
      const s = await api("/api/session");
      S.token = s.token;
      S.home = s.home;
      break;
    } catch (e) {
      $("down-why").textContent = e instanceof TypeError ? "It is not answering." : e.message;
      $("down").classList.remove("hidden");
      await new Promise((go) => { const t = setTimeout(go, wait); $("down-retry").onclick = () => { clearTimeout(t); go(); }; });
      if (!ForgeIdle.shown()) await whenShown();
    }
  }
  $("down").classList.add("hidden");

  // Reattach to shells that are still running (a reload keeps them): the saved
  // tabs and splits first, then any other shell in its own tab, in the old order.
  const list = await api("/api/terms").catch(() => []);
  let order = [];
  try { order = (localStorage.getItem("term.order") || "").split(","); } catch { /* ignore */ }
  list.sort((a, b) => (order.indexOf(a.id) + 1 || 1e9) - (order.indexOf(b.id) + 1 || 1e9));
  const alive = list.filter((t) => t.alive);
  const used = restoreLayouts(alive);
  for (const info of alive) if (!used.has(info.id)) mountTab(info);
  let lastActive = "";
  try { lastActive = localStorage.getItem("term.active") || ""; } catch { /* ignore */ }
  const cwd = hashCwd();
  const last = allPanes().find((p) => p.id === lastActive);
  if (cwd) await newTab(cwd);
  else if (last) activate(tabOf(last), last);
  else if (S.tabs.length) activate(S.tabs[0]);
  else await newTab(S.home);
  ForgeIdle.poll(refreshInfo, 2000, { backoff: 2, maxMs: 30000 });
}

boot();
