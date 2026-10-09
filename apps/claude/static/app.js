/* The Claude panel page.
 *
 * Long-polls a conversation's events and draws them: the user's messages,
 * Claude's text as it streams, tool calls as cards with their results (Forge
 * Browser tools marked), and each turn's cost. Links in answers open in the
 * Forge Browser; attachments are uploaded as base64 and listed in the message.
 *
 * Accounts: the list under the conversations shows each Claude account
 * (profile), who is signed in, and how much of its 5-hour window is used.
 * Clicking one makes it the default account for new tabs; a conversation
 * already open stays on the account it was started with. Signing in relays
 * `claude auth login`: the address, the pasted code, the result.
 *
 * Tabs: the side list is the history, the tab bar is the live set. Each tab is
 * {id, profile}: one conversation, locked to the account it was created on.
 * Every conversation runs as its own Claude Code process, so a tab keeps
 * working while another is shown. Open tabs and unsent drafts are remembered
 * in localStorage.
 *
 * Commands: typing / or . at the start of a message opens the commands and
 * skills from /api/commands (Claude Code's own list plus the skills on disk,
 * each with its description), filtered on every keystroke; picking one
 * writes it as /name.
 *
 * Switching is instant: each conversation is drawn once into its own box and
 * kept (a "view"), so changing tabs swaps boxes instead of redrawing thousands
 * of events. Open tabs are drawn in the background at start, and a kept view
 * only catches up on events newer than the last one it drew.
 */

const $ = (id) => document.getElementById(id);
const { api, post, markdown, el, isImage, fileUrl, fileChip, shot, readBase64 } = ClaudeCommon;
const state = { options: null, chats: [], current: null, meta: null, seq: -1, busy: false,
  files: [], view: null, poll: 0, accounts: null, signin: null, sentAt: 0, seqAtSend: -1,
  tabs: [], drafts: {}, commands: [], menu: { items: [], index: 0 } };
const TABS_KEY = "forge.claude.tabs";

function status(text) { $("status").textContent = text || ""; }
ClaudeCommon.onStatus = status;

/* ---------------------------------------------------------------- drawing
   Markdown, event drawing and images in and out (A24) live in
   claude_common.js, shared with the Enjoy layout. */

function scrollDown(force) {
  const log = $("log");
  if (force || log.scrollHeight - log.scrollTop - log.clientHeight < 160) log.scrollTop = log.scrollHeight;
}

// Scroll only for the view on screen, and not per event while a history is
// drawn in bulk: each scroll forces a layout of the whole log.
function scrollFor(view, force) {
  if (view === state.view && !view.bulk) scrollDown(force);
}

// Drawing lives in claude_common.js, shared with the Enjoy layout; these hooks
// are what only this page does with it.
const drawHooks = {
  shown(view) { if (view === state.view) $("empty").classList.add("hidden"); },
  scroll: (view, force) => scrollFor(view, force),
  init(event) {
    if (state.meta) state.meta.model_seen = event.model;
    if (Array.isArray(event.slash_commands)) loadCommands();
  },
  browserTool: (card) => openBrowserFor(card),
};

function draw(event, view = state.view) {
  ClaudeCommon.draw(event, view, drawHooks);
}

/* ------------------------------------------------------------ conversations */

async function loadChats() {
  const [chats, folders] = await Promise.all([api("/api/conversations"), api("/api/folders")]);
  state.chats = chats.conversations;
  if (chats.focus) state.focus = chats.focus;
  state.folders = folders.folders;
  const names = new Set(state.folders.map((f) => f.name));
  const shown = state.chats.filter((c) => !c.archived);
  const archived = state.chats.filter((c) => c.archived);
  const inFolder = (name) => shown.filter((c) => (names.has(c.folder) ? c.folder : "") === name);
  const groups = state.folders.map((f) => folderGroup(f, inFolder(f.name)));
  const loose = el("div", "folder-body loose");
  loose.append(...inFolder("").map(chatItem));
  dropTarget(loose, "");
  $("chats").replaceChildren(...groups, loose, ...(archived.length ? [archiveGroup(archived)] : []));
  // An archived conversation's tab closes too, unless it is on screen or holds a draft.
  archived.forEach((c) => { if (c.id !== state.current && !state.drafts[c.id]) closeTab(c.id); });
  drawTabs();
  if (state.booted) followFocus();
}

// The Board's "Go to it" asked for a conversation: open its tab once.
function takeFocus() {
  const id = state.focus;
  state.focus = "";
  return id && state.chats.some((c) => c.id === id) ? id : "";
}

function followFocus() {
  const id = takeFocus();
  if (id) openTab(id);
}

function chatItem(c) {
  const item = el("div", "chat-item" + (c.id === state.current ? " on" : ""));
  item.dataset.id = c.id;
  item.draggable = true;
  item.addEventListener("dragstart", (e) => e.dataTransfer.setData("text/x-conversation", c.id));
  item.append(chatLabel(c));
  item.title = "Double-click to rename";
  item.addEventListener("dblclick", () => renameChat(c.id));
  if (c.busy) item.appendChild(el("span", "busy"));
  const move = el("button", "x mv", "📁");
  move.title = "Move to a folder";
  move.addEventListener("click", async (e) => {
    e.stopPropagation();
    const choices = state.folders.map((f) => f.name);
    const answer = await ForgeDialog.prompt(`Move to which folder? Leave empty for none.\n${choices.join(", ") || "(no folders yet; a new name makes one)"}`, c.folder || "");
    if (answer === null) return;
    fileInto(c.id, answer.trim());
  });
  const x = el("button", "x", "×");
  x.title = "Delete conversation";
  x.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!await ForgeDialog.confirm(`Delete "${c.title || "this conversation"}" and its attached files?`)) return;
    await api(`/api/conversations/${c.id}`, { method: "DELETE" });
    await loadChats();
    views.delete(c.id);
    closeTab(c.id);
  });
  if (c.archived) {
    const back = el("button", "x back", "↩");
    back.title = "Bring back out of Archived";
    back.addEventListener("click", async (e) => {
      e.stopPropagation();
      await post(`/api/conversations/${c.id}/settings`, { archived: false });
      await loadChats();
    });
    item.append(back);
  }
  item.append(move, x);
  item.addEventListener("click", () => openTab(c.id));
  return item;
}

// Emerson (2026-09-27): conversations in no folder land here once quiet for
// the hours in Settings > Apps (runner.py _archive_quiet). A message, a folder
// or ↩ brings one back. Open or shut is kept for this page only.
function archiveGroup(chats) {
  const group = el("div", "folder archived" + (state.archiveOpen ? "" : " shut"));
  const head = el("div", "folder-head");
  const caret = el("span", "caret", state.archiveOpen ? "▾" : "▸");
  head.append(caret, el("span", "t", "Archived"), el("span", "count", String(chats.length)));
  head.title = "Quiet conversations in no folder. Click to open or close";
  head.addEventListener("click", () => {
    state.archiveOpen = !state.archiveOpen;
    group.classList.toggle("shut", !state.archiveOpen);
    caret.textContent = state.archiveOpen ? "▾" : "▸";
  });
  const body = el("div", "folder-body");
  body.append(...chats.map(chatItem));
  group.append(head, body);
  return group;
}

function folderGroup(f, chats) {
  const group = el("div", "folder" + (f.collapsed ? " shut" : ""));
  const head = el("div", "folder-head");
  head.append(el("span", "caret", f.collapsed ? "▸" : "▾"), el("span", "t", f.name), el("span", "count", String(chats.length)));
  head.title = "Click to open or close; drop a conversation here to file it";
  const rename = el("button", "x", "✎");
  rename.title = "Rename folder";
  rename.addEventListener("click", async (e) => {
    e.stopPropagation();
    const name = await ForgeDialog.prompt("New folder name", f.name);
    if (name === null || name.trim() === f.name) return;
    await folderPost("/api/folders/update", { name: f.name, new_name: name });
  });
  const x = el("button", "x", "×");
  x.title = "Delete folder (its conversations are kept)";
  x.addEventListener("click", async (e) => {
    e.stopPropagation();
    if (!await ForgeDialog.confirm(`Delete the folder "${f.name}"? Its ${chats.length} conversation(s) are kept, just out of the folder.`)) return;
    await folderPost("/api/folders/delete", { name: f.name });
  });
  head.append(rename, x);
  head.addEventListener("click", () => folderPost("/api/folders/update", { name: f.name, collapsed: !f.collapsed }));
  const body = el("div", "folder-body");
  body.append(...chats.map(chatItem));
  dropTarget(group, f.name);
  group.append(head, body);
  return group;
}

function dropTarget(node, folder) {
  node.addEventListener("dragover", (e) => {
    if (![...e.dataTransfer.types].includes("text/x-conversation")) return;
    e.preventDefault();
    e.stopPropagation();
    node.classList.add("drop");
  });
  node.addEventListener("dragleave", () => node.classList.remove("drop"));
  node.addEventListener("drop", (e) => {
    const id = e.dataTransfer.getData("text/x-conversation");
    node.classList.remove("drop");
    if (!id) return;
    e.preventDefault();
    e.stopPropagation();
    fileInto(id, folder);
  });
}

async function folderPost(path, body) {
  try { await post(path, body); }
  catch (e) { status(e.message); }
  await loadChats();
}

async function fileInto(id, folder) {
  try {
    if (folder && !state.folders.some((f) => f.name === folder)) await post("/api/folders", { name: folder });
    await post(`/api/conversations/${id}/settings`, { folder });
  } catch (e) { status(e.message); }
  await loadChats();
}

async function newFolder() {
  const name = await ForgeDialog.prompt("Folder name");
  if (!name || !name.trim()) return;
  await folderPost("/api/folders", { name });
}

async function newChat() {
  const previous = state.meta || {};
  const profile = state.accounts ? state.accounts.active : "";
  const meta = await post("/api/conversations", {
    cwd: previous.cwd || state.options.home, model: previous.model || "", effort: previous.effort || "",
    mode: previous.mode || state.options.default_mode, profile });
  // ultracode and the agent limits carry over like model and effort
  const carry = {};
  if (previous.ultracode) carry.ultracode = true;
  if (previous.limits && Object.keys(previous.limits).length) carry.limits = previous.limits;
  if (Object.keys(carry).length) {
    try { await post(`/api/conversations/${meta.id}/settings`, carry); } catch (e) { status(e.message); }
  }
  await loadChats();
  openTab(meta.id);
  $("input").focus();
}

/* --------------------------------------------------------------------- tabs */

function saveTabs() {
  localStorage.setItem(TABS_KEY, JSON.stringify({ tabs: state.tabs, current: state.current, drafts: state.drafts }));
}

function restoreTabs() {
  let saved = {};
  try { saved = JSON.parse(localStorage.getItem(TABS_KEY) || "{}"); } catch (e) { /* start clean */ }
  const drafts = saved.drafts || {};
  // archived ones stay closed, as in loadChats, unless on screen or holding a draft
  const known = new Set(state.chats
    .filter((c) => !c.archived || c.id === saved.current || drafts[c.id])
    .map((c) => c.id));
  state.tabs = (saved.tabs || []).filter((t) => t && known.has(t.id));
  state.drafts = drafts;
  return known.has(saved.current) && state.tabs.some((t) => t.id === saved.current) ? saved.current : "";
}

// A conversation's human name, then its topic in grey (names.py picks the name).
function chatLabel(c) {
  const label = el("span", "t");
  label.append(el("span", "who", c.name || "New"));
  if (c.title) label.append(el("span", "topic", c.title));
  return label;
}

async function renameChat(id) {
  const c = state.chats.find((x) => x.id === id) || {};
  const name = await ForgeDialog.prompt("Name this conversation", c.name || "");
  if (!name || !name.trim()) return;
  await post(`/api/conversations/${id}/settings`, { name });
  await loadChats();
}

function drawTabs() {
  const chats = new Map(state.chats.map((c) => [c.id, c]));
  const multi = new Set(state.tabs.map((t) => t.profile)).size > 1
    || (state.accounts && state.accounts.profiles.length > 1);
  const items = state.tabs.map((t) => {
    const c = chats.get(t.id) || {};
    const tab = el("div", "tab" + (t.id === state.current ? " on" : ""));
    tab.dataset.id = t.id;
    tab.title = `${c.name || "New"}: ${c.title || "new conversation"}\nAccount: ${t.profile} (fixed for this tab)\nDouble-click to rename`;
    if (c.busy) tab.appendChild(el("span", "busy"));
    tab.appendChild(chatLabel(c));
    tab.addEventListener("dblclick", () => renameChat(t.id));
    if (multi) tab.appendChild(el("span", "acct", t.profile));
    const x = el("button", "x", "×");
    x.title = "Close the tab (the conversation stays in the list)";
    x.addEventListener("click", (e) => { e.stopPropagation(); closeTab(t.id); });
    tab.appendChild(x);
    tab.addEventListener("click", () => openTab(t.id));
    tab.addEventListener("auxclick", (e) => { if (e.button === 1) closeTab(t.id); });
    return tab;
  });
  const add = el("button", "tab-new", "+");
  add.title = "New conversation in a new tab (Ctrl+T), on the default account";
  add.addEventListener("click", newChat);
  $("tabs").replaceChildren(...items, add);
}

function keepDraft() {
  if (!state.current) return;
  const text = $("input").value;
  if (text.trim()) state.drafts[state.current] = text;
  else delete state.drafts[state.current];
}

function openTab(id) {
  if (!state.tabs.some((t) => t.id === id)) {
    const c = state.chats.find((x) => x.id === id) || {};
    state.tabs.push({ id, profile: c.profile || "default" });
  }
  if (state.current && state.current !== id) keepDraft();
  if (state.current !== id) {
    $("input").value = state.drafts[id] || "";
    delete state.drafts[id];
    autosize();
    closeMenu();
    openChat(id);
  }
  saveTabs();
  drawTabs();
}

function closeTab(id) {
  const at = state.tabs.findIndex((t) => t.id === id);
  if (at < 0) return;
  state.tabs.splice(at, 1);
  delete state.drafts[id];
  // a closed tab ends its claude process, so no idle session lingers
  post(`/api/conversations/${id}/close`).catch(() => {});
  if (state.current === id) {
    state.current = null;
    const next = state.tabs[Math.min(at, state.tabs.length - 1)];
    $("input").value = "";
    autosize();
    if (next) { openTab(next.id); return; }
    saveTabs();
    newChat();
    return;
  }
  saveTabs();
  drawTabs();
}

function stepTab(by) {
  if (state.tabs.length < 2) return;
  const at = state.tabs.findIndex((t) => t.id === state.current);
  openTab(state.tabs[(at + by + state.tabs.length) % state.tabs.length].id);
}

async function refreshTabs() {
  try {
    const body = await api("/api/conversations");
    state.chats = body.conversations;
    if (body.focus) state.focus = body.focus;
  } catch (e) { return; }
  drawTabs();
  followFocus();
}

/* ---------------------------------------------------------------- commands */

async function loadCommands() {
  try {
    const body = await api("/api/commands");
    if (body.commands.length) state.commands = body.commands;
  } catch (e) { /* the list fills in from the next init event */ }
}

function menuMatches(text) {
  const m = /^[\/.]([\w:-]*)$/.exec(text);
  if (!m) return [];
  const q = m[1].toLowerCase();
  const name = (c) => c.name.toLowerCase();
  const starts = state.commands.filter((c) => name(c).startsWith(q) || name(c).split(":").pop().startsWith(q));
  const inside = state.commands.filter((c) => !starts.includes(c) && name(c).includes(q));
  const described = q ? state.commands.filter((c) => !starts.includes(c) && !inside.includes(c)
    && c.description.toLowerCase().includes(q)) : [];
  return [...starts, ...inside, ...described].slice(0, 60);
}

function closeMenu() {
  state.menu.items = [];
  $("cmd-menu").classList.add("hidden");
}

function drawMenu() {
  const items = menuMatches($("input").value);
  if (!items.length) { closeMenu(); return; }
  const key = (list) => list.map((c) => c.name).join();
  if (key(items) !== key(state.menu.items)) state.menu.index = 0;
  state.menu.items = items;
  $("cmd-menu").replaceChildren(...items.map((c, i) => {
    const row = el("div", "cmd" + (i === state.menu.index ? " on" : ""));
    row.append(el("span", "n", "/" + c.name), el("span", "d", c.description));
    row.title = c.description;
    row.setAttribute("role", "option");
    row.addEventListener("mousedown", (e) => { e.preventDefault(); pickCommand(i); });
    return row;
  }));
  $("cmd-menu").classList.remove("hidden");
  const on = $("cmd-menu").children[state.menu.index];
  if (on) on.scrollIntoView({ block: "nearest" });
}

function pickCommand(i) {
  const c = state.menu.items[i];
  if (!c) return;
  // typed in rather than set, so Ctrl+Z can take the pick back
  $("input").focus();
  $("input").select();
  if (!document.execCommand("insertText", false, `/${c.name} `)) $("input").value = `/${c.name} `;
  closeMenu();
  autosize();
  $("input").focus();
}

function menuKey(e) {
  if (!state.menu.items.length) return false;
  const n = state.menu.items.length;
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    state.menu.index = (state.menu.index + (e.key === "ArrowDown" ? 1 : -1) + n) % n;
    drawMenu();
  } else if (e.key === "Tab" || (e.key === "Enter" && !e.shiftKey)) {
    pickCommand(state.menu.index);
  } else if (e.key === "Escape") {
    closeMenu();
  } else {
    return false;
  }
  e.preventDefault();
  return true;
}

/* ------------------------------------------------------------------ views */

const views = new Map(); // conversation id -> its drawn view, least recent first
const KEEP_VIEWS = 4; // views kept for conversations with no open tab

function viewFor(id) {
  let view = views.get(id);
  if (!view) {
    view = ClaudeCommon.newView(id);
    views.set(id, view);
  }
  return view;
}

// Draw everything after the view's last event, in one go, off screen or on.
async function catchUp(view) {
  const body = await api(`/api/conversations/${view.id}/events?after=${view.seq}&boot=${view.boot || ""}`);
  if (body.reset) resetView(view);
  view.boot = body.boot;
  view.bulk = true;
  try { body.events.forEach((e) => draw(e, view)); } finally { view.bulk = false; }
  if (body.events.length) view.seq = body.events[body.events.length - 1].seq;
  view.meta = body.meta;
  view.busy = body.busy;
  return body;
}

// The backend restarted since this view was drawn: its event numbers start
// again, so the view is emptied and drawn afresh from the full history.
function resetView(view) {
  const old = view.box;
  Object.assign(view, ClaudeCommon.newView(view.id), { scroll: view.scroll });
  if (old.parentNode) old.replaceWith(view.box);
}

// The first full draw of a view; shared, so a tab opened while the background
// warm-up is drawing it waits for that instead of drawing it twice.
function fill(view) {
  if (!view.filling) view.filling = catchUp(view).catch((e) => { view.filling = null; throw e; });
  return view.filling;
}

function show(view) {
  state.view = view;
  state.seq = view.seq;
  $("log").replaceChildren($("empty"), view.box);
  $("empty").classList.toggle("hidden", view.box.childElementCount > 0);
  if (view.scroll === null) scrollDown(true);
  else $("log").scrollTop = view.scroll;
  if (view.persona) Stage.event(view.persona, false);
  if (view.meta) applyMeta(view.meta, view.busy);
  views.delete(view.id); // most recent last
  views.set(view.id, view);
  const open = new Set(state.tabs.map((t) => t.id));
  const spare = [...views.keys()].filter((id) => !open.has(id) && id !== view.id);
  spare.slice(0, Math.max(0, spare.length - KEEP_VIEWS)).forEach((id) => views.delete(id));
}

async function openChat(id) {
  const log = $("log");
  if (state.view) {
    state.view.seq = state.seq;
    state.view.scroll = log.scrollHeight - log.scrollTop - log.clientHeight < 160 ? null : log.scrollTop;
  }
  state.current = id;
  state.files = [];
  drawChips();
  document.querySelectorAll(".chat-item").forEach((n) => n.classList.toggle("on", n.dataset.id === id));
  const poll = ++state.poll;
  const view = viewFor(id);
  try {
    if (!view.filling) status("Opening…");
    await fill(view);
  } catch (e) {
    if (poll === state.poll) status("Could not open the conversation: " + e.message);
    return;
  }
  if (poll !== state.poll) return;
  show(view); // the previous conversation stays on screen until this moment
  try {
    const fresh = await catchUp(view);
    if (poll !== state.poll) return;
    state.seq = view.seq;
    applyMeta(fresh.meta, fresh.busy);
    if (fresh.events.length) scrollDown(view.scroll === null);
  } catch (e) { /* follow() retries */ }
  follow(poll);
}

// Draw the open tabs in the background, one at a time, so the first switch to
// each is instant too.
async function warmTabs() {
  for (const t of state.tabs) {
    try { await fill(viewFor(t.id)); } catch (e) { /* drawn when opened instead */ }
  }
}

async function follow(poll) {
  while (poll === state.poll && state.current) {
    try {
      const body = await api(`/api/conversations/${state.current}/events?after=${state.seq}&wait=25&boot=${state.view.boot || ""}`);
      if (poll !== state.poll) return;
      if (body.reset) {
        // drawn afresh from the full history; nothing in it is new, so the
        // avatar and voice stay quiet
        resetView(state.view);
        state.view.bulk = true;
        try { body.events.forEach((e) => draw(e)); } finally { state.view.bulk = false; }
        scrollDown(true);
      } else {
        body.events.forEach((e) => draw(e));
        body.events.forEach((e) => Stage.event(e, true));
        body.events.forEach(voiceReply);
      }
      state.view.boot = body.boot;
      if (body.events.length) state.seq = body.events[body.events.length - 1].seq;
      Object.assign(state.view, { seq: state.seq, meta: body.meta, busy: body.busy });
      const wasBusy = state.busy;
      applyMeta(body.meta, body.busy);
      if (wasBusy !== body.busy) { loadChats(); if (!body.busy) loadAccounts(); }
    } catch (e) {
      status("Lost the connection to the Claude backend; retrying…");
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

function applyMeta(meta, busy) {
  state.meta = meta;
  state.busy = busy;
  if (document.activeElement !== $("title")) $("title").value = meta.title || "";
  if (document.activeElement !== $("cwd")) $("cwd").value = meta.cwd || "";
  $("model").value = meta.model || "";
  $("effort").value = meta.effort || "";
  if (state.run) state.run.apply(meta);
  $("mode").value = meta.mode;
  $("conv-account").replaceChildren("on ", el("b", "", meta.profile || "default"));
  $("send").title = busy ? "Claude Code adds it to the turn it is working on" : "";
  $("stop").classList.toggle("hidden", !busy);
  // Claude Code's figure is what the tokens would cost at API list prices; on a
  // Max or Pro plan nothing is billed per token, so it says so, not "spent".
  const cost = meta.cost_usd ? `This conversation at API list prices: $${Number(meta.cost_usd).toFixed(2)} (not billed: your plan covers it)` : "";
  const slow = busy && state.sentAt && state.seq === state.seqAtSend && Date.now() - state.sentAt > 20000;
  status(busy ? (slow ? "Claude Code is still starting; its first start can take a while…" : "Claude is working… anything you send now joins this turn.") : cost);
  if (!busy) state.sentAt = 0;
}

/* ---------------------------------------------------------------- accounts */

function usageTitle(usage) {
  if (!usage) return "No usage seen yet; it shows after the first answer on this account";
  const when = (t) => (t ? new Date(t * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" }) : "?");
  const pct = (w) => (w && w.used != null ? `${Math.round(w.used * 100)}% used` : "unknown");
  const five = usage.five_hour, week = usage.seven_day;
  return `5-hour window: ${pct(five)}${five ? `, resets ${when(five.resets_at)}` : ""}`
    + (week ? `\n7-day window: ${pct(week)}, resets ${when(week.resets_at)}` : "")
    + (usage.status && usage.status !== "allowed" ? `\nLast answer: ${usage.status}` : "")
    + (usage.seen ? `\nUpdated ${agoText(usage.seen)}${usage.source === "live" ? " (checked with the account; includes terminal sessions)" : " (from this panel's last answer)"}` : "")
    + (usage.check && usage.check.error ? `\nLast check ${agoText(usage.check.at)}: ${usage.check.error}` : "");
}

// The reading under each account, always visible: how full, and how old.
function usageLine(usage) {
  const five = usage && usage.five_hour;
  if (!five || five.used == null) return usage && usage.check ? "usage: checking…" : "";
  const busy = usage.check && usage.check.error && usage.check.at > (usage.seen || 0);
  return `5h ${Math.round(five.used * 100)}% · ${agoText(usage.seen)}${busy ? " · check busy" : ""}`;
}

function agoText(t) {
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  return s < 60 ? "just now" : s < 3600 ? `${Math.floor(s / 60)} min ago` : `${(s / 3600).toFixed(1)} h ago`;
}

function drawAccounts() {
  const data = state.accounts;
  if (!data) return;
  $("account-list").replaceChildren(...data.profiles.map((p) => {
    const row = el("div", "account" + (p.active ? " on" : "") + (p.logged_in ? " signed" : ""));
    row.title = (p.logged_in ? `Signed in as ${p.email}${p.plan ? ` (${p.plan})` : ""}` : "Not signed in")
      + `\n${p.config_dir}\n` + usageTitle(p.usage) + (p.active ? "\nDefault: new tabs use it" : "\nClick to make it the default for new tabs");
    row.appendChild(el("span", "dot"));
    const who = el("span", "who");
    who.append(el("span", "n", p.name), el("span", "e", p.logged_in ? p.email : (p.error || "not signed in")));
    if (p.same_as) {
      row.classList.add("same");
      who.appendChild(el("span", "same", `same account as ${p.same_as}: sign in with your other subscription to split the meters`));
      row.title += `\nThis is the same Claude account as "${p.same_as}", so both show one usage meter.`;
    }
    const line = usageLine(p.usage);
    if (line) who.appendChild(el("span", "u", line));
    row.appendChild(who);
    const used = p.usage && p.usage.five_hour && p.usage.five_hour.used != null ? p.usage.five_hour.used : null;
    if (used !== null) {
      const meter = el("span", "meter" + (used >= 1 ? " full" : used >= 0.7 ? " warm" : ""));
      const bar = el("i");
      bar.style.width = `${Math.min(100, Math.round(used * 100))}%`;
      meter.appendChild(bar);
      row.appendChild(meter);
    }
    if (!p.logged_in || (p.login && p.login.state !== "done")) {
      const go = el("button", "act in", p.login && p.login.state === "waiting" ? "signing in…" : "sign in");
      go.title = "Sign this account in";
      go.addEventListener("click", (e) => { e.stopPropagation(); startSignin(p.name); });
      row.appendChild(go);
    }
    if (!p.default) {
      const x = el("button", "act x", "×");
      x.title = "Remove this account and its sign-in";
      x.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!await ForgeDialog.confirm(`Remove the account "${p.name}"? Its sign-in and its own session files go with it. Conversations on it move to the default account.`)) return;
        try { state.accounts = await api(`/api/profiles/${p.name}`, { method: "DELETE" }); drawAccounts(); }
        catch (err) { status(err.message); }
      });
      row.appendChild(x);
    }
    row.addEventListener("click", () => switchAccount(p.name));
    return row;
  }));
  // A sign-in still running in the backend (say, after a page reload) comes back up.
  const live = data.profiles.find((p) => p.login && ["starting", "waiting", "checking"].includes(p.login.state));
  if (live && !state.signin) {
    state.signin = live.name;
    showSignin(live.login);
    watchSignin(live.name);
  }
}

async function loadWebAccounts() {
  let data;
  try { data = await api("/api/web-accounts"); }
  catch (e) { status("Could not list the web logins: " + e.message); return; }
  $("web-account-list").replaceChildren(...data.accounts.map((a) => {
    const row = el("div", "account web" + (a.open ? " signed" : ""));
    row.title = `${a.url}\nOpens in the Logins app, where each account keeps its own sign-in`;
    row.appendChild(el("span", "dot"));
    const who = el("span", "who");
    who.append(el("span", "n", a.label), el("span", "e", a.open ? "open" : "closed"));
    row.appendChild(who);
    const go = el("button", "act in", "open");
    go.title = `Open ${a.label} in the Logins app`;
    const open = async (e) => {
      e.stopPropagation();
      if (window.parent !== window) {
        window.parent.postMessage({ forge: "open", role: "logins" }, "*");
        return;
      }
      try { status((await post(`/api/web-accounts/${a.id}/open`)).message); }
      catch (err) { status(err.message); }
      setTimeout(loadWebAccounts, 4000);
    };
    go.addEventListener("click", open);
    row.addEventListener("click", open);
    row.appendChild(go);
    return row;
  }));
}

async function loadAccounts(refresh) {
  try {
    state.accounts = await api(`/api/profiles${refresh ? "?refresh=1" : ""}`);
    drawAccounts();
  } catch (e) {
    status("Could not list the accounts: " + e.message);
  }
}

async function switchAccount(name) {
  const p = (state.accounts || { profiles: [] }).profiles.find((x) => x.name === name);
  if (!p) return;
  if (!p.logged_in) { startSignin(name); return; }
  if (p.active) return;
  try {
    state.accounts = await post(`/api/profiles/${name}/activate`);
    drawAccounts();
    status(`New tabs now use "${name}". Open tabs stay on their own account.`);
  } catch (e) {
    status(e.message);
  }
}

async function addAccount() {
  const name = await ForgeDialog.prompt("A short name for the second account (letters, digits, - or _), for example: work", "");
  if (name === null) return;
  try {
    state.accounts = await post("/api/profiles", { name: name.trim() });
    drawAccounts();
    startSignin(name.trim().toLowerCase());
  } catch (e) {
    status(e.message);
  }
}

function showSignin(snapshot) {
  const box = $("signin");
  box.classList.remove("hidden");
  $("signin-title").textContent = `Signing in "${snapshot.profile}"`;
  $("signin-url").textContent = snapshot.url || "waiting for the address…";
  $("signin-url").href = snapshot.url || "#";
  const states = { starting: "Starting Claude Code…", waiting: "Waiting for you to sign in, or for the code.",
    checking: "Checking the code…", done: "Signed in.", failed: `Sign-in failed: ${snapshot.error}`, cancelled: "Cancelled." };
  $("signin-state").textContent = states[snapshot.state] || snapshot.state;
  $("signin-state").className = "small" + (snapshot.state === "failed" ? " bad" : "");
}

function hideSignin() {
  state.signin = null;
  $("signin").classList.add("hidden");
  $("signin-code").value = "";
}

async function startSignin(name) {
  try {
    showSignin({ profile: name, state: "starting", url: "" });
    const snapshot = await post(`/api/profiles/${name}/login`);
    state.signin = name;
    showSignin(snapshot);
    $("signin-code").focus();
    watchSignin(name);
  } catch (e) {
    showSignin({ profile: name, state: "failed", url: "", error: e.message });
  }
}

// The default browser may finish the sign-in on its own (the CLI listens for
// the callback), so the state is polled while the box is open.
async function watchSignin(name) {
  while (state.signin === name) {
    await new Promise((r) => setTimeout(r, 2000));
    if (state.signin !== name) return;
    try {
      const snapshot = await api(`/api/profiles/${name}/login`);
      if (snapshot.state === "done") { await signedIn(name); return; }
      if (snapshot.state === "failed" || snapshot.state === "cancelled") { showSignin(snapshot); state.signin = null; return; }
      showSignin(snapshot);
    } catch (e) { /* keep polling */ }
  }
}

async function signedIn(name) {
  hideSignin();
  await loadAccounts(true);
  const p = state.accounts.profiles.find((x) => x.name === name);
  status(p && p.logged_in ? `Signed in "${name}" as ${p.email}.` : `Sign-in finished, but "${name}" still reports not signed in.`);
}

async function submitCode() {
  const name = state.signin;
  const code = $("signin-code").value.trim();
  if (!name || !code) return;
  try {
    const snapshot = await post(`/api/profiles/${name}/login/code`, { code });
    if (snapshot.state === "done") await signedIn(name);
    else { showSignin(snapshot); if (snapshot.state === "failed") state.signin = null; }
  } catch (e) {
    showSignin({ profile: name, state: "failed", url: $("signin-url").textContent, error: e.message });
    state.signin = null;
  }
}

async function cancelSignin() {
  const name = state.signin;
  hideSignin();
  if (name) { try { await post(`/api/profiles/${name}/login/cancel`); } catch (e) { /* already over */ } }
  loadAccounts();
}

async function saveSetting(key, value) {
  return saveSettings({ [key]: value });
}

async function saveSettings(changes) {
  if (!state.current) return;
  const key = Object.keys(changes)[0];
  try {
    applyMeta(await post(`/api/conversations/${state.current}/settings`, changes), state.busy);
    if (key !== "title") status("Applies from your next message.");
    else loadChats();
  } catch (e) {
    status(e.message);
  }
}

/* ---------------------------------------------------------------- sending */

let voiceText = "";
function voiceReply(ev) {
  if (!window.ForgeVoice) return;
  if (ev.type === "assistant") {
    const text = ((ev.message || {}).content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
    if (text) voiceText = text; // the last text of the turn is what gets spoken
  } else if (ev.type === "result") {
    const text = voiceText.trim();
    voiceText = "";
    const bad = ev.is_error || (ev.subtype && ev.subtype !== "success");
    // the avatar speaks for itself when its own speaker is on
    if (bad || !text || !ForgeVoice.speakReplies("claude") || Stage.speaks()) return;
    ForgeVoice.speak(text, { app: "claude" }).catch((e) => status("Voice: " + e.message));
  }
}

async function send() {
  const text = $("input").value;
  const id = state.current;
  // one send at a time: a double click or a held Enter must not send twice
  if (state.sending || !id || (!text.trim() && !state.files.length)) return;
  state.sending = true;
  $("send").disabled = true;
  const files = state.files;
  $("input").value = "";
  state.files = [];
  drawChips();
  autosize();
  try {
    await post(`/api/conversations/${id}/send`, { text, files: files.map((f) => f.name) });
    state.sentAt = Date.now();
    state.seqAtSend = state.seq;
    applyMeta(state.meta, true);
    setTimeout(loadChats, 400);
  } catch (e) {
    // put it back so nothing typed is lost (unless a new message was started)
    if (state.current === id && !$("input").value) {
      $("input").value = text;
      state.files = files;
      drawChips();
      autosize();
    }
    status("Not sent: " + e.message);
  } finally {
    state.sending = false;
    $("send").disabled = false;
  }
}

function drawChips() {
  $("chips").replaceChildren(...state.files.map((f, i) => {
    const chip = fileChip(state.current, f.name);
    const x = el("button", "", "×");
    x.title = "Remove";
    x.addEventListener("click", () => { state.files.splice(i, 1); drawChips(); });
    chip.appendChild(x);
    return chip;
  }));
}

async function attach(fileList) {
  if (!state.current) return;
  for (const file of fileList) {
    status(`Attaching ${file.name}…`);
    try {
      const saved = await post(`/api/conversations/${state.current}/files`,
        { name: file.name || "pasted.png", data: await readBase64(file) });
      state.files.push(saved);
      drawChips();
      status("");
    } catch (e) {
      status(`Could not attach ${file.name}: ${e.message}`);
    }
  }
}

async function pasteFromDesktop() {
  if (!state.current) return;
  try {
    state.files.push(await post(`/api/conversations/${state.current}/paste-image`, {}));
    drawChips();
    status("");
  } catch (e) { /* no image on the clipboard: an ordinary empty paste */ }
}

async function attachPage() {
  if (!state.current) return;
  status("Reading the page open in the Browser…");
  try {
    const saved = await post(`/api/conversations/${state.current}/attach-page`, {});
    state.files.push(saved);
    drawChips();
    status(`Attached ${saved.url}`);
  } catch (e) {
    status(e.message);
  }
}

// Claude reaching for the Forge Browser while it is closed: ask the hub to open
// it (browser_mcp waits up to 25 s for it). Only for a call still waiting after
// a moment, so replaying an old conversation opens nothing.
function openBrowserFor(card) {
  if (state.browserUp) return;
  setTimeout(() => {
    if (state.browserUp || !card.classList.contains("pending")) return;
    state.browserUp = true;
    window.parent.postMessage({ forge: "open", role: "browser" }, "*");
    status("Opening the Forge Browser for Claude…");
  }, 400);
}

// A link in an answer opens as a new tab in the Forge Browser, and the hub
// brings the Browser to the front.
async function openLink(url) {
  try {
    window.parent.postMessage({ forge: "open", role: "browser" }, "*");
    const answer = await post("/api/open-link", { url });
    if (!answer.ok) status(answer.error || "The Browser did not open it");
  } catch (e) {
    status(e.message);
  }
}

function autosize() {
  const t = $("input");
  t.style.height = "auto";
  t.style.height = `${Math.min(220, t.scrollHeight)}px`;
}

/* ---------------------------------------------------------------- wiring */

$("new-chat").addEventListener("click", newChat);
$("new-folder").addEventListener("click", newFolder);
$("to-enjoy").addEventListener("click", () => {
  try { localStorage.setItem("claude.layout", "enjoy"); } catch (e) { /* private mode */ }
  location.href = "enjoy.html";
});
$("send").addEventListener("click", send);
// Voice (shared/forge_voice.js): dictation into the composer, and each
// finished reply spoken through the Forge voice service when the toggle is on.
if (window.ForgeVoice) {
  $("send").before(ForgeVoice.micButton($("input"), { app: "claude" }));
  $("send").before(ForgeVoice.speakRepliesToggle("claude"));
}
$("stop").addEventListener("click", async () => {
  if (state.current) await post(`/api/conversations/${state.current}/stop`);
});
$("input").addEventListener("keydown", (e) => {
  if (e.isComposing || menuKey(e)) return;
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
});
$("input").addEventListener("input", () => { autosize(); drawMenu(); });
$("input").addEventListener("blur", closeMenu);
document.addEventListener("keydown", (e) => {
  if (!e.ctrlKey || e.altKey) return;
  if (e.key === "Tab") stepTab(e.shiftKey ? -1 : 1);
  else if (e.key.toLowerCase() === "t" && !e.shiftKey) newChat();
  else if (e.key.toLowerCase() === "w" && !e.shiftKey && state.current) closeTab(state.current);
  else if (e.key === "PageDown" || e.key === "PageUp") stepTab(e.key === "PageDown" ? 1 : -1);
  else return;
  e.preventDefault();
});
window.addEventListener("beforeunload", () => { keepDraft(); saveTabs(); });
$("input").addEventListener("paste", (e) => {
  const dt = e.clipboardData;
  const images = dt ? [...dt.files] : [];
  if (!images.length && dt) {
    [...dt.items].forEach((item) => { const f = item.kind === "file" && item.getAsFile(); if (f) images.push(f); });
  }
  if (images.length) { e.preventDefault(); attach(images); return; }
  // WebKitGTK does not always hand a copied screenshot to the page, so when a
  // paste brings no text the backend reads the desktop clipboard itself. A
  // text paste goes ahead untouched.
  const types = dt ? [...dt.types] : [];
  if (types.includes("text/plain")) return;
  if (types.some((t) => t.startsWith("image/"))) e.preventDefault();
  pasteFromDesktop();
});
$("attach").addEventListener("click", () => $("file").click());
$("file").addEventListener("change", (e) => { attach([...e.target.files]); e.target.value = ""; });
$("attach-page").addEventListener("click", attachPage);
["dragenter", "dragover"].forEach((type) => document.addEventListener(type, (e) => {
  e.preventDefault();
  $("composer").classList.add("drop");
}));
["dragleave", "drop"].forEach((type) => document.addEventListener(type, (e) => {
  e.preventDefault();
  if (type === "drop" || !e.relatedTarget) $("composer").classList.remove("drop");
  if (type === "drop" && e.dataTransfer && e.dataTransfer.files.length) attach([...e.dataTransfer.files]);
}));
$("log").addEventListener("click", (e) => {
  const link = e.target.closest("a[data-url]");
  if (link) { e.preventDefault(); openLink(link.dataset.url); }
});
$("title").addEventListener("change", (e) => saveSetting("title", e.target.value));
$("cwd").addEventListener("change", (e) => saveSetting("cwd", e.target.value));
$("model").addEventListener("change", (e) => saveSetting("model", e.target.value));
$("effort").addEventListener("change", (e) => saveSetting("effort", e.target.value));
$("mode").addEventListener("change", (e) => saveSetting("mode", e.target.value));
$("add-account").addEventListener("click", addAccount);
$("signin-submit").addEventListener("click", submitCode);
$("signin-code").addEventListener("keydown", (e) => { if (e.key === "Enter") submitCode(); });
$("signin-cancel").addEventListener("click", cancelSignin);
$("signin-open").addEventListener("click", () => { const url = $("signin-url").href; if (url.startsWith("https://")) openLink(url); });
$("signin-copy").addEventListener("click", async () => {
  try { await navigator.clipboard.writeText($("signin-url").textContent); status("Address copied."); }
  catch (e) { status("Could not copy; select the address and copy it by hand."); }
});

function showVersion(text) {
  const version = String(text || "").split("\n")[0];
  $("version").textContent = /^[\w .()-]{1,60}$/.test(version) ? version : "";
}

async function boot() {
  // the list does not need the options: fetch both at once
  const chatsEarly = loadChats().catch(() => {});
  try {
    state.options = await api("/api/options");
  } catch (e) {
    status("Could not reach the Claude backend: " + e.message);
    return;
  }
  const o = state.options;
  showVersion(o.version);
  // the backend works the version out on a thread; read it once it is known
  if (o.claude && !o.version) setTimeout(() => api("/api/options").then((x) => showVersion(x.version)).catch(() => {}), 4000);
  $("model").replaceChildren(...Object.entries(o.models).map(([value, label]) => {
    const opt = el("option", "", label);
    opt.value = value;
    return opt;
  }));
  // A backend from before the effort setting sends no efforts: hide the picker.
  $("effort").closest("label").classList.toggle("hidden", !o.efforts);
  $("effort").replaceChildren(...Object.entries(o.efforts || {}).map(([value, label]) => {
    const opt = el("option", "", label);
    opt.value = value;
    return opt;
  }));
  state.run = RunControls.create(o, saveSettings);
  $("run-host").replaceChildren(state.run.root);
  $("mode").replaceChildren(...Object.entries(o.modes).map(([value, label]) => {
    const opt = el("option", "", label);
    opt.value = value;
    return opt;
  }));
  const problems = [];
  if (!o.claude) problems.push("Claude Code is not installed: the claude command was not found.");
  state.browserUp = !!o.browser;
  $("notice").textContent = problems.join(" ");
  $("notice").classList.toggle("hidden", !problems.length);
  Stage.boot();
  await loadAccounts();
  // Opening the app starts a fresh check of every account; read it once it lands.
  setTimeout(() => loadAccounts(), 5000);
  // The bars follow the account, and terminal sessions use it too: re-read
  // every minute (the backend checks the account at most every two).
  setInterval(() => { if (ForgeIdle.shown()) loadAccounts(); }, 60000);
  loadWebAccounts();
  await chatsEarly;
  loadCommands();
  const restored = restoreTabs();
  const current = takeFocus() || restored;
  if (current) openTab(current);
  else if (state.tabs.length) openTab(state.tabs[0].id);
  else if (state.chats.length) openTab((state.chats.find((c) => !c.archived) || state.chats[0]).id);
  else newChat();
  warmTabs();
  state.booted = true;
  splitters();
  // only while the page can be seen; coming back into view refreshes at once
  ForgeIdle.poll(refreshTabs, 4000);
  // Forge showing this app (after a Board jump) should not wait for the timer.
  document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") refreshTabs(); });
}

/* --- everyone: every Claude session on the laptop ---------------------------- */
const EV_LABEL = { working: "Working now", idle: "Idle, waiting for a message", cold: "Ended (cold, not working)" };

function toggleEveryone(on) {
  state.everyoneOn = on;
  $("everyone").classList.toggle("hidden", !on);
  $("chats").classList.toggle("hidden", on);
  $("to-everyone").classList.toggle("on", on);
  try { localStorage.setItem("forge.claude.everyone", on ? "1" : ""); } catch (e) { /* private mode */ }
  if (on) loadEveryone();
}

async function loadEveryone() {
  if (!state.everyoneOn || state.everyoneTyping) return;
  let rows;
  try { rows = (await api("/api/everyone")).sessions; } catch (e) { return; }
  const nodes = [];
  let group = "";
  for (const r of rows) {
    if (r.state !== group) { group = r.state; nodes.push(el("div", "ev-group", EV_LABEL[group])); }
    nodes.push(everyoneItem(r));
  }
  if (!rows.length) nodes.push(el("div", "ev-empty muted small", "No Claude sessions in the last three days."));
  $("everyone").replaceChildren(...nodes);
}

function everyoneItem(r) {
  const box = el("div", "ev " + r.state);
  const top = el("div", "top");
  const title = r.relay
    ? ForgeSessionTitle.displayName({ id: r.session_id, name: r.name, relay: r.relay })
    : r.conversation ? r.conversation.title || "Forge tab" : r.name || r.session_id.slice(0, 8);
  top.append(el("span", "dot"), el("span", "n", title));
  const when = r.state === "cold" ? "ended " : "active ";
  const sub = el("div", "sub", `${r.name}${r.conversation ? " · Forge tab" : ""} · ${r.cwd.replace(/^\/home\/[^/]+/, "~")} · ${when}${agoText(r.updated)}`);
  sub.title = `${r.cwd}\nsession ${r.session_id}\npid ${r.pid} · Claude Code ${r.version}`;
  const acts = el("div", "acts");
  const openBtn = el("button", "btn", r.conversation ? "open tab" : r.state === "cold" ? "resume here" : "");
  if (openBtn.textContent) {
    openBtn.onclick = async () => {
      try {
        const got = await post(`/api/everyone/${r.session_id}/open`, { state: r.state, cwd: r.cwd, name: r.name });
        toggleEveryone(false);
        await loadChats();
        openTab(got.id);
      } catch (e) { status("Could not open it: " + e.message); }
    };
    acts.append(openBtn);
  }
  if (r.state !== "cold") {
    const say = el("button", "btn", "message");
    say.onclick = () => askSession(box, r);
    acts.append(say);
  }
  box.append(top, sub, acts);
  if (r.helpers.length) {
    const kids = el("div", "kids");
    r.helpers.slice(0, 8).forEach((h) => {
      const k = el("div", "kid " + h.state);
      k.append(el("span", "dot"), el("span", "t", `${h.description}${h.model ? " (" + h.model + ")" : ""}`), el("span", "", h.state === "working" ? "working" : agoText(h.updated)));
      k.title = `helper agent ${h.id} · ${h.type}. Helpers report to their session; message the session to reach them.`;
      kids.append(k);
    });
    if (r.helpers.length > 8) kids.append(el("div", "kid", `+ ${r.helpers.length - 8} older helpers`));
    box.append(kids);
  }
  return box;
}

function askSession(box, r) {
  if (box.querySelector(".say")) return;
  const form = el("form", "say");
  const input = el("input");
  input.placeholder = `Message ${r.name}; it answers at its next step`;
  form.append(input, el("button", "btn btn-primary", "send"));
  state.everyoneTyping = true;
  const done = () => { state.everyoneTyping = false; form.remove(); };
  input.addEventListener("keydown", (e) => { if (e.key === "Escape") done(); });
  form.onsubmit = async (e) => {
    e.preventDefault();
    if (!input.value.trim()) return;
    try {
      const got = await post(`/api/everyone/${r.session_id}/message`, { text: input.value });
      status(`Sent to ${got.to} on the crew board (note ${got.id}); it sees it at its next step.`);
      done();
      loadEveryone();
    } catch (err) { status("Not sent: " + err.message); }
  };
  box.append(form);
  input.focus();
}

/* --- draggable dividers, remembered per pane ---------------------------------- */
window.splitters = splitters;
function splitters() {
  document.querySelectorAll(".split").forEach((bar) => {
    const pane = $(bar.dataset.pane);
    // data-side "top" is a bar above its pane that drags the pane's height
    const tall = bar.dataset.side === "top";
    const key = "forge.claude." + (tall ? "height." : "width.") + bar.dataset.pane;
    const size = (px) => {
      if (tall) pane.style.height = pane.style.maxHeight = px;
      else pane.style.width = px;
    };
    const saved = Number(localStorage.getItem(key));
    if (saved) size(saved + "px");
    bar.addEventListener("pointerdown", (e) => {
      e.preventDefault();
      bar.setPointerCapture(e.pointerId);
      bar.classList.add("drag");
      document.body.classList.add("dragging", tall ? "dragging-y" : "dragging-x");
      const x0 = e.clientX;
      const y0 = e.clientY;
      const box0 = pane.getBoundingClientRect();
      const move = (ev) => {
        if (tall) {
          size(Math.max(30, Math.min(window.innerHeight * 0.8, box0.height + y0 - ev.clientY)) + "px");
          return;
        }
        const d = bar.dataset.side === "left" ? ev.clientX - x0 : x0 - ev.clientX;
        size(Math.max(170, Math.min(window.innerWidth * 0.6, box0.width + d)) + "px");
      };
      const up = () => {
        bar.removeEventListener("pointermove", move);
        bar.classList.remove("drag");
        document.body.classList.remove("dragging", "dragging-y", "dragging-x");
        const box = pane.getBoundingClientRect();
        localStorage.setItem(key, String(Math.round(tall ? box.height : box.width)));
      };
      bar.addEventListener("pointermove", move);
      bar.addEventListener("pointerup", up, { once: true });
    });
    bar.addEventListener("dblclick", () => { size(""); localStorage.removeItem(key); });
  });
  const fold = (on) => {
    $("accounts").classList.toggle("folded", on);
    $("fold-accounts").textContent = (on ? "▸" : "▾") + " Account";
    localStorage.setItem("forge.claude.accountsFolded", on ? "1" : "");
  };
  $("fold-accounts").onclick = () => fold(!$("accounts").classList.contains("folded"));
  fold(!!localStorage.getItem("forge.claude.accountsFolded"));
  // web logins start folded, so the conversation list keeps the room; opened
  // once, they stay open
  const foldWeb = (on) => {
    $("web-account-list").classList.toggle("hidden", on);
    $("fold-web").textContent = (on ? "▸" : "▾") + " Web logins";
    localStorage.setItem("forge.claude.webLoginsOpen", on ? "" : "1");
  };
  $("fold-web").onclick = () => foldWeb(!$("web-account-list").classList.contains("hidden"));
  foldWeb(!localStorage.getItem("forge.claude.webLoginsOpen"));
  $("to-everyone").onclick = () => toggleEveryone(!state.everyoneOn);
  if (localStorage.getItem("forge.claude.everyone")) toggleEveryone(true);
  setInterval(() => { if (ForgeIdle.shown()) loadEveryone(); }, 5000);
}

boot();
