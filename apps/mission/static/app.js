/* Mission Control page. One poll (/api/overview?sig=...) feeds every view;
   an unchanged answer is two fields and re-renders nothing. Polling backs
   off while nothing changes and stops while the page is hidden. */
(function () {
  "use strict";
  const L = window.MissionLogic;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HEAD = { "Content-Type": "application/json", "X-Mission": "1" };

  /* Settings: each numeric one is a slider plus a number field. */
  const SETTINGS = [
    { key: "fast", label: "Fastest refresh (seconds)", min: 2, max: 30, step: 1, def: 4, hint: "How soon a change shows while things are happening." },
    { key: "slow", label: "Slowest refresh (seconds)", min: 10, max: 300, step: 5, def: 30, hint: "Refresh stretches up to this while nothing changes." },
    { key: "feed", label: "Feed lines per card", min: 0, max: 6, step: 1, def: 3, hint: "Recent actions shown under each session (Advanced shows all six)." },
    { key: "ended", label: "Archived sessions shown", min: 0, max: 30, step: 1, def: 8, hint: "Most recent archived sessions kept in the list: ended, or idle for half an hour." },
    { key: "helpers", label: "Helpers per card", min: 0, max: 12, step: 1, def: 3, hint: "Helper agents listed on a card before \"and N more\"." },
  ];
  const store = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem("mission." + k)); return v ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("mission." + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const S = Object.assign(Object.fromEntries(SETTINGS.map((s) => [s.key, s.def])), store.get("settings", {}));
  const ui = {
    view: store.get("view", "sessions"),
    filter: store.get("filter", "all").replace(/^ended$/, "archived"), // Ended became Archived
    place: store.get("place", ""),
    mode: store.get("mode", "simple"),
    zoom: store.get("zoom", 0), // map scale; 0 = fit the window
    search: "",
    selected: null, // {id, agent}
  };
  let seen = store.get("seen", {});
  let data = null;
  // The backend's last rows, and what calm order and gentle leaving
  // remember between polls (logic.js calmOrder / linger).
  let rawSessions = [];
  const calmMemo = { at: {} };
  const goneMemo = { last: {}, gone: {} };
  const LINGER_S = 180;
  let sig = "";
  let delay = S.fast;
  let timer = 0;
  let inflight = false;
  let failures = 0;
  let serverSkew = 0; // server now - local now, seconds
  const lastAction = new Map();

  /* ---------------------------------------------------------------- art */
  /* Each Crew Room sprite becomes one horizontal strip (all its frames side
     by side) plus a CSS @keyframes that steps through them with the sprite's
     own frame times. A live state (working, needs you) picks the moving
     variant (type, talk, busy); idle and ended show a still first frame, so
     nothing loops while nothing happens. CSS animations pause by themselves
     while the page is hidden (page-hidden, forge-idle) or calm. */
  let atlas = null;
  const strips = new Map(); // sprite id -> {url, w, h, n, anim, total} | null
  let animSheet = null;
  async function loadArt() {
    try {
      const lib = await window.ForgeArt.load("/api/art");
      const pal = lib.palettes.crewroom ? "crewroom" : Object.keys(lib.palettes)[0];
      atlas = window.ForgeArt.atlas(lib, pal);
    } catch (e) { atlas = null; }
  }
  function strip(id) {
    if (strips.has(id)) return strips.get(id);
    if (!atlas) return null; // not loaded yet: ask again later, cache nothing
    let out = null;
    try {
      const s = atlas && atlas.get(id);
      if (s && s.frames.length) {
        const n = s.frames.length, w = s.frames[0].width, h = s.frames[0].height;
        const c = document.createElement("canvas");
        c.width = w * n; c.height = h;
        const g = c.getContext("2d");
        s.frames.forEach((f, i) => g.drawImage(f, i * w, 0));
        const durs = (s.durations || []).slice(0, n);
        const total = durs.reduce((a, b) => a + b, 0);
        let anim = "";
        if (n > 1 && total > 0) {
          anim = "spr" + strips.size;
          let at = 0;
          const steps = durs.map((d, i) => { const k = `${(at / total * 100).toFixed(3)}%{transform:translateX(${(-i * 100 / n).toFixed(4)}%)}`; at += d; return k; });
          steps.push(`100%{transform:translateX(${(-(n - 1) * 100 / n).toFixed(4)}%)}`);
          if (!animSheet) { animSheet = document.createElement("style"); document.head.appendChild(animSheet); }
          animSheet.appendChild(document.createTextNode(`@keyframes ${anim}{${steps.join("")}}`));
        }
        out = { url: c.toDataURL(), w, h, n, anim, total, durs };
      }
    } catch (e) { out = null; }
    strips.set(id, out);
    return out;
  }
  const LIVE_VARIANT = { working: "_type", needs_you: "_talk" };
  function spriteOf(kind, key, type, state) {
    const base = L.spriteFor(kind, key, type);
    const want = kind === "model" ? (state === "working" ? "_busy" : "") : LIVE_VARIANT[state] || "";
    if (want) {
      const id = base.replace(/_idle$/, want);
      const st = strip(id);
      if (st) return { st, live: true };
    }
    return { st: strip(base), live: false };
  }
  // Typing reads fine a little slower than the Crew Room's own pace, and
  // every sprite steps on one shared beat (syncSprites), so the page repaints
  // a few times a second in total, not once per sprite.
  const SPRITE_PACE = 1.6;
  const animCss = (st, live) => (live && st.anim ? `animation-name:${st.anim};animation-duration:${Math.round(st.total * SPRITE_PACE)}ms;` : "");
  function syncSprites(root) {
    const now = performance.now();
    for (const el of root.querySelectorAll(".spr.live > i:not([data-s])")) {
      const period = parseFloat(el.style.animationDuration) || 0;
      if (period) el.style.animationDelay = `-${Math.round(now % period)}ms`;
      el.setAttribute("data-s", "1");
    }
  }
  function avatar(kind, key, type, label, cls = "", state = "") {
    // small avatars (helper rows, crew trees) stay still: their dot already
    // says working, and a dozen typing sprites per card cost more than they add
    const small = cls === "small";
    const { st, live } = spriteOf(kind, key, type, small ? "" : state);
    const wrap = small ? "av" + (kind === "helper" ? " h" : "") : "tile";
    if (!st) return `<span class="${wrap} blank">${esc((label || "?").slice(0, 1).toUpperCase())}</span>`;
    return `<span class="${wrap}"><span class="spr${live && st.anim ? " live" : ""}" style="aspect-ratio:${st.w}/${st.h}"><i style="width:${st.n * 100}%;background-image:url(${st.url});${animCss(st, live)}"></i></span></span>`;
  }
  const icon = (name) => `<svg class="ic" aria-hidden="true"><use href="#i-${name}"/></svg>`;
  const calm = () => document.body.classList.contains("calm");

  /* ------------------------------------------------------------- polling */
  // Shown: the browser says visible and, inside the hub, no other app is in
  // front (shared/forge_idle.js reads both).
  const shown = () => (window.ForgeIdle ? window.ForgeIdle.shown() : document.visibilityState !== "hidden");
  function schedule() {
    clearTimeout(timer);
    if (!shown()) return;
    timer = setTimeout(poll, delay * 1000);
  }
  let again = false; // asked for a fresh look while one was on its way
  async function poll() {
    if (inflight) { again = true; return; }
    if (!shown()) return;
    again = false;
    inflight = true;
    let changed = false;
    try {
      const ctl = new AbortController();
      const stop = setTimeout(() => ctl.abort(), 10000);
      let r;
      try {
        r = await fetch("/api/overview?sig=" + encodeURIComponent(sig), { cache: "no-store", signal: ctl.signal });
      } catch (e) {
        throw new Error(e.name === "AbortError" ? "the server took over 10 seconds" : e.message);
      } finally {
        clearTimeout(stop);
      }
      if (!r.ok) throw new Error(await errText(r, "Mission Control did not answer"));
      const got = await r.json();
      serverSkew = got.now - Date.now() / 1000;
      failures = 0;
      if (!got.same) {
        changed = true;
        sig = got.sig;
        rawSessions = got.sessions || [];
        data = got;
        settle();
        render();
      } else if (data && L.lingerDue(goneMemo, nowS(), openIds(), LINGER_S)) {
        settle();
        render();
      } else {
        refreshTimes();
      }
      $("live").className = "live" + (delay >= S.slow ? " slow" : "");
      $("live").title = changed ? "Live: just changed" : `Live: nothing new, next look in ${Math.round(L.nextDelay(delay, false, S.fast, S.slow))} s`;
      $("liveTxt").textContent = delay >= S.slow ? "live · resting" : "live";
    } catch (e) {
      failures++;
      $("live").className = "live off";
      $("live").title = "Offline: " + e.message;
      $("liveTxt").textContent = "offline, retrying";
      if (!data) $("grid").innerHTML = emptyHtml("off", "Can't reach Mission Control", "The server did not answer (" + e.message + "). It keeps trying; this page fills in as soon as it is back.");
      if (failures === 1) toast("Lost the Mission Control server; retrying", "err");
    } finally {
      inflight = false;
      // Out of focus (open on another screen, or behind a window) the
      // fastest refresh is 2.5 times slower: changes still show, less often.
      const floor = document.hasFocus() ? S.fast : Math.min(S.slow, S.fast * 2.5);
      delay = failures ? Math.min(S.slow, Math.max(floor, delay * 2)) : L.nextDelay(delay, changed, floor, S.slow);
      if (again) { again = false; delay = S.fast; clearTimeout(timer); poll(); }
      else schedule();
    }
  }
  function pollNow() { delay = S.fast; clearTimeout(timer); poll(); }
  window.addEventListener("focus", () => { if (delay > S.fast) pollNow(); });
  function onShown() {
    document.body.classList.toggle("page-hidden", !shown());
    if (!shown()) clearTimeout(timer);
    else pollNow();
  }
  document.addEventListener("visibilitychange", onShown);
  document.addEventListener("forge-visible", onShown);

  const nowS = () => Date.now() / 1000 + serverSkew;
  function refreshTimes() {
    for (const el of document.querySelectorAll("[data-at]")) el.textContent = L.ago(nowS() - Number(el.dataset.at));
  }

  /* -------------------------------------------------------------- render */
  // What the page lists: the backend's rows plus the ones that just left
  // (kept a while, marked ended, and kept while open), in calm order.
  function openIds() {
    const ids = new Set();
    if (ui.selected) ids.add(ui.selected.id);
    const cv = window.MissionConvos;
    if (cv && ui.view === "convos" && cv.selected) ids.add(cv.selected);
    return ids;
  }
  function settle() {
    const now = nowS();
    const rows = L.linger(rawSessions, goneMemo, now, openIds(), LINGER_S);
    for (const s of rows) s.section = L.section(s, now);
    data.sessions = L.calmOrder(rows, calmMemo, now);
  }
  function visibleSessions() {
    if (!data) return [];
    let ended = 0;
    const q = ui.search.trim().toLowerCase();
    return data.sessions.filter((s) => {
      if (!L.matches(s, ui.filter, seen, ui.place)) return false;
      if (q && ![L.displayName(s), s.label, s.name, s.title, s.place, s.cwd, s.action, s.model].some((v) => String(v || "").toLowerCase().includes(q))) return false;
      return !(s.section === "archived" && ui.filter !== "archived" && ++ended > S.ended);
    });
  }

  function markFirstSight() {
    let dirty = false;
    for (const s of data.sessions) if (seen[s.id] === undefined) { seen[s.id] = s.last_active || 0; dirty = true; }
    // forget sessions untouched for a week, so the store stays small; one
    // that drops out of a single poll keeps its unread state
    const ids = new Set(data.sessions.map((s) => s.id));
    const weekAgo = nowS() - 7 * 86400;
    for (const id of Object.keys(seen)) if (!ids.has(id) && seen[id] < weekAgo) { delete seen[id]; dirty = true; }
    if (dirty) store.set("seen", seen);
  }
  function markSeen(id) {
    const s = data && data.sessions.find((x) => x.id === id);
    if (!s) return;
    seen[id] = Math.max(s.last_active || 0, nowS());
    store.set("seen", seen);
  }

  function render() {
    if (!data) return;
    markFirstSight();
    if (ui.place && !data.sessions.some((s) => s.place === ui.place)) { ui.place = ""; store.set("place", ""); }
    renderTop();
    renderSide();
    renderNeeds();
    $("errors").innerHTML = Object.entries(data.errors || {}).map(([k, v]) => `<div>Could not read ${esc(k)}: ${esc(v)}</div>`).join("");
    if (ui.view === "sessions") renderGrid();
    if (ui.view === "map") renderMap();
    if (ui.view === "crews") renderCrews();
    if (ui.view === "relay") renderRelay();
    if (ui.view === "swarm" && window.MissionSwarm) window.MissionSwarm.draw();
    if (ui.view === "messages" && window.MissionMessages) window.MissionMessages.draw();
    if (ui.view === "convos" && window.MissionConvos) window.MissionConvos.draw();
    if (ui.selected) renderDrawer();
    for (const s of data.sessions) lastAction.set(s.id, s.action + "|" + s.group);
  }

  const shownCounts = {};
  function countUp(el, from, to) {
    if (from === to || calm() || from === undefined) { el.textContent = to; return; }
    const t0 = performance.now();
    const step = (t) => {
      const k = Math.min(1, (t - t0) / 420);
      el.textContent = Math.round(from + (to - from) * (1 - Math.pow(1 - k, 3)));
      if (k < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  }
  function renderTop() {
    const c = Object.assign({}, data.counts, L.counts(data.sessions, seen)); // same numbers as the sidebar
    const notes = data.needs_you.filter((n) => n.kind === "note").length;
    const stats = [
      ["needs_you", c.needs_you, c.needs_you === 1 ? "needs you" : "need you", 'data-filter="needs_you"'],
      ["working", c.working, "working", 'data-filter="working"'],
      ["idle", c.idle, "idle", 'data-filter="idle"'],
      ["helpers", c.helpers_working || 0, (c.helpers_working === 1 ? "helper" : "helpers") + " busy", 'data-view-go="map"'],
      ["notes", notes, notes === 1 ? "note for you" : "notes for you", 'data-view-go="crews"'],
    ].filter(([k, n]) => n || ["working", "idle"].includes(k));
    const shape = stats.map(([k, , l]) => k + l).join("|");
    const pulse = $("pulse");
    if (pulse.dataset.shape !== shape) {
      pulse.innerHTML = stats.map(([k, , l, act]) => `<button type="button" class="stat k-${k}" data-k="${k}" ${act} title="Show ${esc(l)}">${["needs_you", "working", "idle"].includes(k) ? `<i class="dot ${k}"></i>` : ""}<b></b><span>${esc(l)}</span></button>`).join("");
      pulse.dataset.shape = shape;
    }
    for (const [k, n] of stats) {
      const el = pulse.querySelector(`.stat[data-k="${k}"]`);
      el.classList.toggle("zero", !n);
      const prev = shownCounts[k];
      if (prev !== n) {
        countUp(el.querySelector("b"), prev, n);
        if (prev !== undefined && !calm()) { el.classList.remove("bump"); void el.offsetWidth; el.classList.add("bump"); }
        shownCounts[k] = n;
      } else if (!el.querySelector("b").textContent) el.querySelector("b").textContent = n;
    }
    const r = data.relay || {};
    if (!r.present) { $("relayStrip").innerHTML = ""; return; }
    const meters = Object.entries(r.meters || {}).filter(([, m]) => m.five !== null && m.five !== undefined);
    const html = `<span class="r-name">${icon("relay")}Relay</span>${r.paused ? '<span class="paused-pill">paused</span>' : ""}` +
      meters.map(([a, m]) => `<span class="acct-m" title="Account ${esc(a)}: ${Math.round(m.five)}% of the 5-hour window used">${esc(a)} ${meterBar(m.five)} ${Math.round(m.five)}%</span>`).join("") +
      `<span class="r-cnt">${(r.running || []).length} running · ${(r.counts || {}).queued || 0} queued</span>`;
    if ($("relayStrip").innerHTML !== html) $("relayStrip").innerHTML = html;
  }
  /* Relay writes "stale reading (5809 min old)"; say it in hours or days. */
  function humanMinutes(text) {
    return String(text).replace(/(\d+) min old/, (_, m) => {
      m = Number(m);
      return m >= 2880 ? Math.round(m / 1440) + " days old" : m >= 120 ? Math.round(m / 60) + " hours old" : m + " min old";
    });
  }
  function meterBar(p) {
    const v = Math.max(0, Math.min(100, Number(p) || 0));
    return `<span class="meter"><i class="${v >= 92 ? "bad" : v >= 70 ? "warn" : ""}" style="width:${v}%"></i></span>`;
  }

  function renderSide() {
    for (const b of document.querySelectorAll(".views button")) b.classList.toggle("on", b.dataset.view === ui.view);
    const c = L.counts(data.sessions, seen);
    const names = { all: "All", needs_you: "Needs you", working: "Working", unread: "Unread", idle: "Idle", archived: "Archived" };
    setHtml($("filters"), L.FILTERS.map((f) => `<button type="button" data-filter="${f}" class="${f} ${ui.filter === f ? "on" : ""}"><i class="dot ${f}"></i><span>${names[f]}</span><span class="n">${c[f] || ""}</span></button>`).join(""));
    const pl = L.places(data.sessions);
    setHtml($("places"), `<button type="button" data-place="" class="${ui.place ? "" : "on"}"><span>Every folder</span><span class="n"></span></button>` +
      pl.map((p) => `<button type="button" data-place="${esc(p.place)}" title="${esc(p.cwd)}" class="${ui.place === p.place ? "on" : ""}"><span>${esc(p.place === "~" ? "home folder (~)" : p.place)}</span><span class="n">${p.live}${p.total > p.live ? "/" + p.total : ""}</span></button>`).join(""));
    const crews = (data.crews || []).filter((x) => x.active);
    setHtml($("crewList"), crews.length ? crews.map((x) => {
      const open = x.tasks.filter((t) => t.status !== "done").length;
      return `<button type="button" data-crew="${esc(x.name)}"><span>${esc(x.name)}</span><span class="n">${open ? open + " open" : "done"}</span></button>`;
    }).join("") : `<div class="muted small" style="padding:4px 10px">No active crew</div>`);
  }

  /* Sessions waiting and blocked Relay tasks each get a row; notes for
     Emerson get rows only while there are few, else one summary row. */
  function renderNeeds() {
    const all = data.needs_you || [];
    const notes = all.filter((n) => n.kind === "note");
    let rows = notes.length > 2 ? all.filter((n) => n.kind !== "note") : all;
    const waiting = rows.filter((n) => n.kind === "session");
    if (waiting.length > 2) {
      const first = rows.indexOf(waiting[0]);
      rows = rows.filter((n) => n.kind !== "session");
      rows.splice(Math.min(first, rows.length), 0, { kind: "fold", label: `${waiting.length} sessions wait for you`, text: waiting.map((n) => n.label).join(", ") });
    }
    const crewsWithNotes = [...new Set(notes.map((n) => n.crew))];
    const summary = notes.length > 2
      ? `<div class="need"><span class="tag">${icon("bell")}notes</span><span class="who">${notes.length} notes for you</span><span class="what">on ${esc(crewsWithNotes.join(", "))}: ${esc(notes.slice(0, 3).map((n) => n.label).join(", "))}${notes.length > 3 ? " and more" : ""}</span><button type="button" class="btn btn-primary mini" data-crew="${esc(crewsWithNotes[0])}">Read them</button></div>`
      : "";
    setHtml($("needs"), rows.slice(0, 8).map((n) => {
      if (n.kind === "fold") return `<div class="need"><span class="tag">${icon("bell")}waiting</span><span class="who">${esc(n.label)}</span><span class="what" title="${esc(n.text)}">${esc(n.text)}</span><button type="button" class="btn btn-primary mini" data-filter="needs_you">Show them</button></div>`;
      const act = n.kind === "session"
        ? `<button type="button" class="btn btn-primary mini" data-open="${esc(n.session)}">Look</button>`
        : n.kind === "note"
          ? `<button type="button" class="btn btn-primary mini" data-reply="${esc(n.crew)}|${esc(n.note)}">Answer</button><button type="button" class="ghost mini" data-ack="${esc(n.crew)}|${esc(n.note)}">Seen</button>`
          : `<button type="button" class="btn mini" data-view-go="relay">Relay</button>`;
      const tag = n.kind === "session" ? "waiting" : n.kind === "note" ? "note · " + n.crew : "relay";
      return `<div class="need" data-k="${esc(n.kind)}"><span class="tag">${icon("bell")}${esc(tag)}</span><span class="who">${esc(n.label)}</span><span class="what" title="${esc(n.text)}">${esc(n.text)}</span>${act}</div>`;
    }).join("") + (rows.length > 8 ? `<div class="muted small">and ${rows.length - 8} more</div>` : "") + summary);
  }

  const GROUP_NAME = { needs_you: "Needs you", working: "Working", idle: "Idle", ended: "Ended", archived: "Archived" };
  function emptyHtml(art, title, text, extra = "") {
    const ic = { off: "off", none: "empty", filter: "search" }[art] || "empty";
    return `<div class="empty"><div class="e-art ${art === "off" ? "bad" : ""}">${icon(ic)}</div><h3>${esc(title)}</h3><p>${esc(text)}</p>${extra}</div>`;
  }

  /* Keyed update: an element whose HTML is unchanged stays in the page (no
     flash, hover and focus kept); changed ones are swapped in place; moved
     ones glide to their new spot (FLIP, transform only); new ones fade in. */
  const htmlOf = new WeakMap();
  function patchList(box, items, opts = {}) {
    const old = new Map();
    for (const el of box.children) if (el.dataset && el.dataset.key) old.set(el.dataset.key, el);
    const animate = opts.flip && !calm() && old.size > 0;
    const first = new Map();
    if (animate) for (const [k, el] of old) first.set(k, el.getBoundingClientRect());
    const tpl = document.createElement("template");
    const next = items.map((it) => {
      let el = old.get(it.key);
      if (el && htmlOf.get(el) === it.html) return el;
      tpl.innerHTML = it.html.trim();
      const fresh = tpl.content.firstElementChild;
      fresh.dataset.key = it.key;
      htmlOf.set(fresh, it.html);
      if (!el && old.size && !calm() && opts.enter) fresh.classList.add(opts.enter);
      return fresh;
    });
    const keep = new Set(next);
    for (const el of [...box.children]) if (!keep.has(el)) el.remove();
    next.forEach((el, i) => { if (box.children[i] !== el) box.insertBefore(el, box.children[i] || null); });
    if (!animate) return;
    const moved = [];
    for (const el of next) {
      const a = first.get(el.dataset.key);
      if (!a) continue;
      const b = el.getBoundingClientRect();
      const dx = a.left - b.left, dy = a.top - b.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) continue;
      el.style.transition = "none";
      el.style.transform = `translate(${dx}px, ${dy}px)`;
      moved.push(el);
    }
    if (!moved.length) return;
    void box.offsetWidth;
    requestAnimationFrame(() => {
      for (const el of moved) {
        el.style.transition = "transform 280ms cubic-bezier(0.2, 0.7, 0.2, 1)";
        el.style.transform = "";
        el.addEventListener("transitionend", () => { el.style.transition = ""; }, { once: true });
      }
    });
  }

  /* Columns: as many as the biggest group needs (at least two, so one
     session is not a 1300 px slab), never more than fit at about 380 px. */
  function gridCols(list) {
    const sizes = {};
    for (const s of list) sizes[s.section] = (sizes[s.section] || 0) + 1;
    const fit = Math.max(1, Math.floor(($("grid").clientWidth + 14) / 394));
    return Math.max(1, Math.min(fit, Math.max(2, ...Object.values(sizes))));
  }
  function renderGrid() {
    const grid = $("grid");
    const list = visibleSessions();
    if (!list.length) {
      const filtered = data.sessions.length;
      grid.innerHTML = filtered
        ? emptyHtml("filter", "Nothing matches", "No session fits this filter, folder or search.", '<button type="button" class="btn" data-clear="1">Show everything</button>')
        : emptyHtml("none", "No Claude sessions running", "Start one in a terminal or the Claude app and it shows up here within a few seconds.");
      return;
    }
    grid.style.setProperty("--cols", gridCols(list));
    const sizes = {};
    for (const s of list) sizes[s.section] = (sizes[s.section] || 0) + 1;
    const items = [];
    let group = "";
    for (const s of list) {
      if (s.section !== group) {
        group = s.section;
        items.push({ key: "g:" + group, html: `<div class="group-title"><span>${GROUP_NAME[group]}</span><span class="n">${sizes[group]}</span></div>` });
      }
      items.push({ key: "s:" + s.id, html: card(s) });
    }
    patchList(grid, items, { flip: true, enter: "enter" });
    syncSprites(grid);
    refreshTimes();
  }

  function card(s) {
    const unread = L.isUnread(s, seen);
    const prev = lastAction.get(s.id);
    const ping = prev !== undefined && prev !== s.action + "|" + s.group;
    const name = L.displayName(s);
    const tag = L.personaTag(s);
    const full = (s.relay && s.relay.title) || s.title || "";
    const fam = esc(s.family || "");
    const meta = [
      s.model ? `<span class="m-model ${fam}"><i class="fam ${fam}"></i>${esc(L.modelName(s.model))}</span>` : "",
      s.effort ? `<span>${esc(s.effort)}</span>` : "",
      `<span title="${esc(s.cwd)}">${esc(s.place || "?")}</span>`,
      ...(s.crews || []).map((c) => `<span class="m-crew" title="${esc(c.role)} in crew ${esc(c.crew)}">${esc(c.crew)}${c.commander ? " · lead" : ""}</span>`),
      s.relay ? `<span class="m-relay" title="Relay runs this as task ${esc(s.relay.task)}">Relay</span>` : "",
      s.background ? `<span class="adv">headless</span>` : "",
    ].join("");
    const simple = document.body.classList.contains("simple");
    const feed = (s.feed || []).slice(-(simple ? S.feed : 6)).reverse();
    const helpers = s.helpers || [];
    const pool = simple ? helpers.filter((h) => h.state === "working" || h.crew_member) : helpers;
    const shownH = pool.slice(0, S.helpers);
    const restH = pool.length - shownH.length;
    const ended = s.group === "ended";
    const primary = ended || s.claude_tab ? "claude" : "go";
    const btn = (kind, attr, label, ic, title = "") =>
      `<button type="button" class="${primary === kind ? "btn btn-primary" : "ghost quiet"}" ${attr} title="${esc(title || label)}">${icon(ic)}<span class="bl">${esc(label)}</span></button>`;
    const acts = [];
    const goB = !ended ? btn("go", `data-go="${esc(s.name)}"`, "Go to it", "go", "Bring up its terminal tab or its tab in the Claude app; a Relay session opens its chat here") : "";
    const claudeB = s.claude_tab || ended ? btn("claude", `data-claude="${esc(s.id)}"`, ended ? "Resume in Claude" : "Open in Claude", "open") : "";
    const msgB = !ended ? btn("msg", `data-msg="${esc(s.id)}"`, "Message", "msg", "A note on the forge board for this session") : "";
    if (primary === "claude") acts.push(claudeB, goB, msgB); else acts.push(goB, msgB, claudeB);
    return `<article class="s-card ${esc(s.group)} ${ui.selected && ui.selected.id === s.id ? "sel" : ""} ${ping ? "ping" : ""} ${s.gone ? "gone" : ""}" data-open="${esc(s.id)}" tabindex="0" aria-label="${esc(name)}, ${esc(GROUP_NAME[s.group])}. Open details">
      ${unread ? '<span class="unread-dot" title="Finished something since you last looked"></span>' : ""}
      <div class="s-head">
        ${avatar("session", s.name || s.id, "", name, "", s.group)}
        <div class="s-who">
          <div class="s-name"><span class="nm" title="${esc(name)}">${esc(name)}</span>${tag ? `<span class="handle" title="${esc(s.name ? "board name " + s.name : tag)}">${esc(tag)}</span>` : ""}</div>
          <div class="s-meta">${meta}</div>
        </div>
        <span class="state ${esc(s.group)}">${esc(GROUP_NAME[s.group])}</span>
      </div>
      ${full && !name.endsWith(full) ? `<div class="s-title" title="${esc(full)}">${esc(full)}</div>` : ""}
      <div class="s-now ${ping ? "fresh" : ""}">${icon("now")}<span title="${esc(s.action)}">${esc(s.action || "…")}</span></div>
      <div class="ctx" title="Context in use: ${(s.context || 0).toLocaleString()} of ${(s.window || 0).toLocaleString()} tokens">
        <span>${L.tokens(s.context)} context</span>${meterBar(L.pct(s.context, s.window))}<span>${Math.round(L.pct(s.context, s.window))}%</span>
      </div>
      ${feed.length ? `<ol class="feed">${feed.map((a) => `<li><time>${esc(clock(a.at))}</time><span title="${esc(a.text)}">${esc(a.text)}</span></li>`).join("")}</ol>` : ""}
      ${shownH.length ? `<div class="helpers">${shownH.map((h) => helperRow(s, h)).join("")}${restH > 0 ? `<span class="more">and ${restH} more</span>` : ""}</div>` : ""}
      <div class="adv small muted">pid ${esc(s.pid)} · ${s.turns || 0} turns · started <span data-at="${s.started}"></span></div>
      <div class="s-actions">${acts.join("")}<span class="grow"></span><span class="when" data-at="${s.last_active}"></span></div>
    </article>`;
  }
  function helperRow(s, h) {
    const who = L.helperName(h);
    const st = h.state === "working" ? "working" : "done";
    return `<div class="helper ${st}" data-open="${esc(s.id)}" data-agent="${esc(h.id)}" title="${esc(h.task)}${h.action ? " — " + esc(h.action) : ""}">
      <span class="dot ${st}"></span>
      ${avatar("helper", h.id, h.type, who, "small", h.state)}
      <span class="h-name">${esc(who)}</span>
      <span class="h-task">${esc(h.state === "working" ? h.action || h.task : h.task)}</span>
      ${h.model ? `<span class="tag-chip ${esc(h.family || "")} adv">${esc(L.modelName(h.model))}</span>` : ""}
      ${h.context ? `<span class="tag-chip adv">${L.tokens(h.context)}</span>` : ""}
      ${h.crew_status ? `<span class="task-state ${esc(h.crew_status)}">${esc(h.crew_status)}</span>` : ""}
    </div>`;
  }
  function clock(at) {
    if (!at) return "";
    const d = new Date(at);
    return isNaN(d) ? "" : d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
  }

  /* ----------------------------------------------------------------- map */
  /* Lanes of cards (task 73). The server says who sits in which lane (a crew
     with its commander first, Relay, a shared board, a session with its
     helpers, Jan); the page lays them out: every card is one column wide, a
     lane spans as many columns as it needs for about three rows, and lanes
     are packed into the columns like bricks, each into the lowest gap that
     takes it. Lanes sit at fixed spots worked out here, so nothing overlaps,
     the columns always fill the width (never a sideways scroll) and "fit"
     picks the biggest size whose map still fits the window's height. Cards
     are kept between polls; only their inside or class changes. */
  const ZOOMS = [1, 1.1, 1.2, 1.3, 1.45, 1.6, 1.8, 2];
  // "fit" tries 180% down to 100% in 5% steps; never below 100%: his eyes
  const FIT = Array.from({ length: 17 }, (_, i) => Math.round((1.8 - i * 0.05) * 100) / 100);
  const MAP = { col: 290, colMax: 460, gap: 14, laneGap: 16, rows: 3 }; // px at 100%
  const mapMem = { cards: new Map(), lanes: new Map(), drawn: false, shape: "", room: null, scale: 1 };
  const NODE_GLYPH = { run: "task" };
  const STATE_WORD = { working: "working", needs_you: "needs you", idle: "idle", ended: "ended", done: "done" };
  function sessionByRef(ref) { return data.sessions.find((s) => s.id === ref); }
  function mapZoom(how) {
    const cur = ui.zoom || mapMem.scale || 1;
    if (how === "fit") ui.zoom = 0;
    else if (how === "in") ui.zoom = ZOOMS.find((z) => z > cur + 0.01) || ZOOMS[ZOOMS.length - 1];
    else ui.zoom = [...ZOOMS].reverse().find((z) => z < cur - 0.01) || ZOOMS[0];
    store.set("zoom", ui.zoom);
    layoutMap(true);
  }
  function zoomLabel() {
    const el = $("zoomPct");
    if (!el) return;
    el.textContent = (ui.zoom ? "" : "fit · ") + Math.round(mapMem.scale * 100) + "%";
    const fit = document.querySelector('[data-zoom="fit"]');
    if (fit) fit.classList.toggle("on", !ui.zoom);
  }
  /* Board notes of the last hour, counted per card. */
  function notesByNode(g) {
    const nameTo = new Map();
    for (const n of g.nodes) {
      const s = n.ref && sessionByRef(n.ref);
      if (n.kind === "session" && s) { nameTo.set(s.name, n.id); if (s.label) nameTo.set(s.label, n.id); }
      if (n.kind === "helper" && s) {
        const h = (s.helpers || []).find((x) => x.id === n.helper);
        if (h && h.crew_member) nameTo.set(h.crew_member, n.id);
      }
    }
    const count = {};
    const hourAgo = nowS() - 3600;
    for (const c of data.crews || []) {
      for (const note of c.notes || []) {
        const id = note.t >= hourAgo && nameTo.get(note.from);
        if (id) count[id] = (count[id] || 0) + 1;
      }
    }
    return count;
  }
  function cardInner(n, lead, notes) {
    const s = n.kind === "session" ? sessionByRef(n.ref) : null;
    const key = n.kind === "helper" ? n.helper : s ? s.name : n.id;
    const label = s ? L.displayName(s) : n.label;
    const art = NODE_GLYPH[n.kind]
      ? `<span class="tile glyph">${icon(NODE_GLYPH[n.kind])}</span>`
      : avatar(n.kind === "helper" ? "helper" : n.kind === "model" ? "model" : "session", key, n.type, label, "", n.state);
    const role = lead ? "lead" : n.kind === "helper" ? n.type || "helper" : n.kind === "model" ? "model" : "";
    const badges = [
      n.relay_task && !s && n.label !== `task ${n.relay_task}` ? `<span class="b relay" title="Relay runs this as task ${esc(n.relay_task)}">task ${esc(n.relay_task)}</span>` : "",
      notes ? `<span class="b note" title="${notes} board note${notes === 1 ? "" : "s"} in the last hour">${notes} note${notes === 1 ? "" : "s"}</span>` : "",
      n.helpers_busy ? `<span class="b help">${n.helpers_busy} helper${n.helpers_busy === 1 ? "" : "s"} busy</span>` : "",
    ].join("");
    return `${n.family ? `<i class="fam ${esc(n.family)}"></i>` : ""}${art}
      <div class="mcb">
        <div class="mc-name">${esc(label)}</div>
        <div class="mc-state"><i class="dot ${esc(n.state)}"></i><span>${esc(STATE_WORD[n.state] || n.state)}</span>${role ? `<span class="role">${esc(role)}</span>` : ""}${badges}</div>
        <div class="mc-act">${esc(n.sub || "")}</div>
      </div>`;
  }
  function renderMap() {
    const g = data.graph;
    const root = $("map");
    if (!g.lanes.length) {
      setHtml(root, `<div class="map-empty"><b>Nobody is working right now</b><span>Sessions, crews, Relay and Jan show up here as they start.</span></div>`);
      root.style.height = "";
      mapMem.cards.clear(); mapMem.lanes.clear(); mapMem.drawn = false; mapMem.shape = "";
      return;
    }
    if (!root.querySelector(".lane")) { root.innerHTML = ""; root._html = ""; }
    const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
    const notes = notesByNode(g);
    const fx = mapMem.drawn && !calm();
    const keepLanes = new Set(), keepCards = new Set();
    for (const lane of g.lanes) {
      keepLanes.add(lane.id);
      let el = mapMem.lanes.get(lane.id);
      if (!el) {
        el = document.createElement("section");
        el.innerHTML = `<header class="lane-head"></header><div class="lane-grid"></div>`;
        mapMem.lanes.set(lane.id, el);
        if (fx) el.classList.add("spawn");
        if (laneWatch) laneWatch.observe(el);
      }
      root.appendChild(el); // keeps the server's order; an existing lane just moves
      el.className = `lane k-${esc(lane.kind)}${el.classList.contains("spawn") ? " spawn" : ""}`;
      const ids = (lane.lead ? [lane.lead] : []).concat(lane.ring);
      el._count = ids.length;
      const go = lane.kind === "relay" ? "relay" : lane.kind === "crew" || lane.kind === "board" ? "crews" : "";
      const title = lane.title === "~" ? "home folder" : lane.title;
      setHtml(el.firstChild, `${go ? `<button type="button" class="lane-title" data-view-go="${go}" title="Open ${go === "relay" ? "Relay" : "Crews"}">` : `<span class="lane-title">`}${esc(title || "session")}${go ? "</button>" : "</span>"}${lane.subtitle ? `<span class="lane-sub" title="${esc(lane.subtitle)}">${esc(lane.subtitle)}</span>` : ""}<span class="lane-n">${ids.length > 1 && lane.kind !== "relay" ? ids.length : ""}</span>`);
      const grid = el.lastChild;
      for (const id of ids) {
        const n = byId[id];
        if (!n) continue;
        keepCards.add(id);
        const lead = id === lane.lead;
        const html = cardInner(n, lead, notes[id] || 0);
        let c = mapMem.cards.get(id);
        const isNew = !c;
        if (isNew) {
          c = document.createElement("div");
          c.tabIndex = 0;
          c.dataset.node = id;
          mapMem.cards.set(id, c);
        }
        const prev = c._mc || {};
        const ping = !isNew && prev.sub !== undefined && (prev.sub !== n.sub || prev.state !== n.state);
        c.className = `mcard k-${esc(n.kind)} ${esc(n.state)}${lead ? " lead" : ""}${isNew && fx ? " spawn" : ""}${ping && fx ? " ping" : ""}`;
        c.title = n.label + (n.sub ? " — " + n.sub : "");
        if (prev.html !== html) c.innerHTML = html;
        c._mc = { html, sub: n.sub, state: n.state };
        grid.appendChild(c);
      }
    }
    for (const [id, el] of mapMem.lanes) if (!keepLanes.has(id)) { el.remove(); mapMem.lanes.delete(id); }
    for (const [id, el] of mapMem.cards) if (!keepCards.has(id)) { el.remove(); mapMem.cards.delete(id); }
    syncSprites(root);
    const shape = g.lanes.map((l) => l.id + ":" + ((l.lead ? 1 : 0) + l.ring.length)).join("|");
    layoutMap(shape !== mapMem.shape);
    mapMem.shape = shape;
    mapMem.drawn = true;
  }
  /* The map's room: its width, and the height left in the window under it. */
  function mapRoom() {
    const root = $("map"), main = root && root.closest(".mc-main");
    if (!root || !main || !root.clientWidth) return null;
    const legend = document.querySelector("#view-map .legend");
    const top = root.getBoundingClientRect().top - main.getBoundingClientRect().top + main.scrollTop;
    const h = main.clientHeight - top - (legend ? legend.offsetHeight + 14 : 0) - 28;
    return { w: root.clientWidth, h: Math.max(240, h) };
  }
  /* Place the lanes at scale z; returns the map's height. */
  function placeLanes(z, w) {
    const root = $("map");
    const lanes = [...root.querySelectorAll(":scope > .lane")];
    const G = Math.round(MAP.laneGap * z), col = MAP.col * z;
    const most = Math.max(1, Math.floor((w + G) / (col + G)));
    const want = lanes.map((el) => Math.min(most, Math.max(1, Math.ceil(el._count / MAP.rows))));
    // fewer lanes than columns: use only the columns needed, each not too wide, centred
    const n = Math.max(1, Math.min(most, want.reduce((a, b) => a + b, 0)));
    const span = want.map((k) => Math.min(k, n));
    const cw = Math.min((w - (n - 1) * G) / n, MAP.colMax * z * (n < most ? 1 : 10));
    const x0 = Math.max(0, (w - (n * cw + (n - 1) * G)) / 2);
    root.style.setProperty("--mz", z);
    lanes.forEach((el, i) => {
      el.style.width = `${span[i] * cw + (span[i] - 1) * G}px`;
      el.lastChild.style.gridTemplateColumns = `repeat(${span[i]}, minmax(0, 1fr))`;
    });
    const hs = lanes.map((el) => el.offsetHeight); // one reflow for all
    // Each lane goes into the lowest gap that takes it. Packed in the
    // server's order and widest-first; the shorter map wins (a small lane
    // first can strand a wide one under a hole).
    const pack = (order) => {
      const sky = new Array(n).fill(0), at = [];
      for (const i of order) {
        const k = span[i];
        let best = 0, bestTop = Infinity;
        for (let c = 0; c + k <= n; c++) {
          const t = Math.max(...sky.slice(c, c + k));
          if (t < bestTop - 0.5) { bestTop = t; best = c; }
        }
        at[i] = [best, bestTop];
        for (let c = best; c < best + k; c++) sky[c] = bestTop + hs[i] + G;
      }
      return { at, sky };
    };
    const asIs = lanes.map((_, i) => i);
    const wideFirst = [...asIs].sort((a, b) => span[b] - span[a] || a - b);
    let best = pack(asIs);
    const other = pack(wideFirst);
    if (Math.max(...other.sky) < Math.max(...best.sky) - 1) best = other;
    const sky = best.sky;
    // A lane with empty columns beside it for its whole height takes them
    // (no hole left beside it); its cards spread out, so it only gets
    // shorter, never taller, and still overlaps nothing.
    const box = lanes.map((_, i) => ({ c: best.at[i][0], k: span[i], top: best.at[i][1], bot: best.at[i][1] + hs[i] }));
    const free = (c, i) => box.every((b, j) => j === i || c < b.c || c >= b.c + b.k || b.bot + G <= box[i].top || box[i].bot + G <= b.top);
    box.forEach((b, i) => {
      while (b.c + b.k < n && free(b.c + b.k, i)) b.k++;
      while (b.c > 0 && free(b.c - 1, i)) { b.c--; b.k++; }
    });
    lanes.forEach((el, i) => {
      const { c, k, top } = box[i];
      el.style.width = `${k * cw + (k - 1) * G}px`;
      el.lastChild.style.gridTemplateColumns = `repeat(${Math.max(span[i], Math.min(k, el._count))}, minmax(0, 1fr))`;
      el.style.transform = `translate(${(x0 + c * (cw + G)).toFixed(1)}px, ${top.toFixed(1)}px)`;
    });
    mapMem.heights = lanes.map((el) => el.offsetHeight).join(",");
    const height = Math.max(0, Math.max(...sky) - G);
    root.style.height = `${Math.ceil(height)}px`;
    return height;
  }
  /* refit: try the fit sizes again (lanes changed, the room changed or the
     zoom was set); otherwise only re-place at the current size. */
  function layoutMap(refit) {
    const root = $("map");
    if (!data || ui.view !== "map" || !root.querySelector(".lane")) { zoomLabel(); return; }
    const room = mapRoom();
    if (!room) return;
    const old = mapMem.room;
    const moved = !old || Math.abs(room.w - old.w) > 4 || Math.abs(room.h - old.h) > 24;
    if (refit || moved || !root.classList.contains("placed")) {
      mapMem.room = room;
      let z = ui.zoom || FIT[FIT.length - 1];
      if (!ui.zoom) for (const k of FIT) { if (placeLanes(k, room.w) <= room.h) { z = k; break; } }
      mapMem.scale = z;
    }
    placeLanes(mapMem.scale, room.w);
    if (!root.classList.contains("placed")) requestAnimationFrame(() => root.classList.add("placed"));
    zoomLabel();
  }
  /* A lane can grow after it was placed (a sprite or font arrives late, a
     line wraps): place again, so it never runs into the next lane or out
     of the map. Same heights as placed = nothing to do, so no loop. */
  const laneWatch = window.ResizeObserver ? new ResizeObserver(() => {
    clearTimeout(laneWatch._t);
    laneWatch._t = setTimeout(() => {
      const lanes = [...$("map").querySelectorAll(":scope > .lane")];
      if (lanes.map((el) => el.offsetHeight).join(",") !== mapMem.heights) layoutMap(!ui.zoom);
    }, 120);
  }) : null;
  // the map's own box changes when the drawer opens or the sidebar folds
  if (window.ResizeObserver) {
    let t = 0;
    new ResizeObserver(() => {
      clearTimeout(t);
      // a new width (drawer, sidebar, scrollbar) re-places before the next
      // paint, so no lane ever spills out; height changes can wait
      const w = $("map").clientWidth;
      if (mapMem.room && Math.abs(w - mapMem.room.w) > 4) layoutMap(false);
      else t = setTimeout(() => layoutMap(false), 150);
    }).observe($("map"));
  }
  function setHtml(el, html) { if (el._html !== html) { el.innerHTML = html; el._html = html; } }
  const trim = (t, n) => { t = String(t || ""); return t.length > n ? t.slice(0, n - 1) + "…" : t; };

  /* --------------------------------------------------------------- crews */
  function renderCrews() {
    const crews = data.crews || [];
    const active = crews.filter((c) => c.active);
    const older = crews.filter((c) => !c.active);
    const sessionsByName = Object.fromEntries(data.sessions.map((s) => [s.name, s]));
    const block = (c) => {
      const tasksBy = {};
      for (const t of c.tasks) (tasksBy[t.owner || ""] = tasksBy[t.owner || ""] || []).push(t);
      const cmd = c.members.find((m) => m.name === c.commander);
      // A shared board (forge) remembers every session that ever joined;
      // show the ones seen lately, running now, or holding a task.
      const others = c.members.filter((m) => m.name !== c.commander);
      const hiddenMembers = c.members_hidden || 0;
      const memberLi = (m, cls) => {
        const s = sessionsByName[m.name] || data.sessions.find((x) => x.id === m.session);
        const tasks = tasksBy[m.name] || [];
        return `<li class="${cls}">
          ${avatar(cls === "cmd" ? "session" : "helper", m.name, cls === "cmd" ? "" : "crew-worker", m.persona || m.name, "small")}
          <div class="t-body"><div>${esc(m.persona || m.name)} <span class="muted small">${esc(m.name)} · ${esc(m.role)}${m.slot ? " · " + esc(m.slot) : ""}</span>
            ${s ? ` <span class="state ${esc(s.group)}">${esc(GROUP_NAME[s.group])}</span>` : ""}</div>
            ${tasks.map((t) => `<div class="t-task">#${esc(t.id)} ${esc(t.title)} <span class="task-state ${esc(t.status)}">${esc(t.status)}</span>${t.note ? `<div class="adv">${esc(t.note)}</div>` : ""}</div>`).join("")}
          </div>
          <button type="button" class="ghost mini quiet-note" data-note-to="${esc(c.name)}|${esc(m.name)}" title="A note on the ${esc(c.name)} board for ${esc(m.name)}">Note</button>
        </li>`;
      };
      const open = (tasksBy[""] || []);
      return `<div class="crew" id="crew-${esc(c.name)}">
        <h3>${esc(c.name)} <span class="muted small">${others.length + (cmd ? 1 : 0)} active members · ${c.tasks.filter((t) => t.status === "done").length}/${c.tasks.length} tasks done · <span data-at="${c.last}">${L.ago(nowS() - c.last)}</span></span></h3>
        <div class="goal">${esc(c.goal || "")}</div>
        <div class="crew-cols">
          <div>
            <ul class="tree">
              ${cmd ? memberLi(cmd, "cmd") : c.commander ? `<li class="cmd">${esc(c.commander)} <span class="muted small">commander (not joined)</span></li>` : ""}
              ${others.map((m) => memberLi(m, "member")).join("")}
              ${hiddenMembers ? `<li class="member muted small">and ${hiddenMembers} member${hiddenMembers === 1 ? "" : "s"} not seen in the last six hours</li>` : ""}
              ${open.map((t) => `<li class="member"><div class="t-body"><div class="t-task">#${esc(t.id)} ${esc(t.title)} <span class="task-state open">unassigned</span></div></div></li>`).join("")}
            </ul>
            ${c.claims.length ? `<div class="claims adv"><b>Claims</b><br>${c.claims.map((x) => `${esc(x.owner)}: ${esc(x.path)}`).join("<br>")}</div>` : ""}
            ${c.log.length ? `<div class="claims adv"><b>Log</b><br>${c.log.slice().reverse().map((x) => `<span data-at="${x.t}">${L.ago(nowS() - x.t)}</span> ${esc(x.text)}`).join("<br>")}</div>` : ""}
          </div>
          <div>
            <div class="notes">${c.notes.length ? c.notes.slice(0, 25).map((n) => noteHtml(c, n)).join("") : '<div class="muted small">No notes yet.</div>'}</div>
            <form class="composer" data-crew="${esc(c.name)}">
              <select name="to" aria-label="To"><option value="">Everyone in ${esc(c.name)}</option>${c.members.map((m) => `<option value="${esc(m.name)}">${esc(m.persona || m.name)} (${esc(m.name)})</option>`).join("")}</select>
              <input name="text" maxlength="4000" placeholder="A note on this board" aria-label="Note">
              <button class="btn btn-primary" type="submit">Post</button>
            </form>
          </div>
        </div>
      </div>`;
    };
    // A poll must never eat a half-typed note: carry each composer's text,
    // recipient, focus and caret across the re-render.
    const kept = {};
    for (const f of document.querySelectorAll("#crews form.composer")) {
      kept[f.dataset.crew] = { text: f.text.value, to: f.to.value, focus: document.activeElement === f.text, sel: [f.text.selectionStart, f.text.selectionEnd] };
    }
    const scroller = document.querySelector(".mc-main");
    const top = scroller.scrollTop;
    const notesTop = {};
    for (const n of document.querySelectorAll("#crews .crew")) { const b = n.querySelector(".notes"); if (b) notesTop[n.id] = b.scrollTop; }
    $("crews").innerHTML = (active.length ? active.map(block).join("") : '<div class="empty">No crew has been active in the last two days.</div>') +
      (older.length ? `<details class="older" ${ui.olderOpen ? "open" : ""}><summary>${older.length} older crew${older.length === 1 ? "" : "s"}</summary>${older.map(block).join("")}</details>` : "");
    const det = document.querySelector("#crews details.older");
    if (det) det.addEventListener("toggle", () => { ui.olderOpen = det.open; });
    for (const f of document.querySelectorAll("#crews form.composer")) {
      const k = kept[f.dataset.crew];
      if (!k) continue;
      f.text.value = k.text;
      f.to.value = k.to;
      if (k.focus) { f.text.focus(); try { f.text.setSelectionRange(k.sel[0], k.sel[1]); } catch (e) { /* not a text box */ } }
    }
    for (const n of document.querySelectorAll("#crews .crew")) { const b = n.querySelector(".notes"); if (b && notesTop[n.id]) b.scrollTop = notesTop[n.id]; }
    scroller.scrollTop = top;
  }
  function noteHtml(c, n) {
    const mine = n.from === "Emerson";
    return `<div class="note ${mine ? "mine" : ""} ${n.for_emerson ? "for-me" : ""}">
      <div class="n-head"><b>${esc(n.from_persona || n.from)}</b><span>to ${esc(n.to || "everyone")}</span>${n.re ? `<span>re #${esc(n.re)}</span>` : ""}<span>#${esc(n.id)}</span><span data-at="${n.t}">${L.ago(nowS() - n.t)}</span>${n.fyi ? "<span>fyi</span>" : ""}</div>
      <div class="n-text">${esc(n.text)}</div>
      ${!mine ? `<div class="n-acts"><button type="button" class="btn mini" data-reply="${esc(c.name)}|${esc(n.id)}">Answer</button>${n.for_emerson ? `<button type="button" class="btn mini" data-ack="${esc(c.name)}|${esc(n.id)}">Seen</button>` : ""}</div>` : ""}
    </div>`;
  }

  /* --------------------------------------------------------------- relay */
  function renderRelay() {
    const r = data.relay || {};
    if (!r.present) { $("relay").innerHTML = '<div class="empty">Relay has no data folder on this laptop yet.</div>'; return; }
    const acct = Object.entries(r.meters || {}).map(([a, m]) => `
      <div class="acct"><b>${esc(a)}</b>${m.five === null || m.five === undefined ? `<span class="muted">${esc(humanMinutes(m.error || "no reading"))}</span><span></span>` : `${meterBar(m.five)}<span>${Math.round(m.five)}%</span>`}
      <span class="muted small">week</span>${m.week === null || m.week === undefined ? "<span></span><span></span>" : `${meterBar(m.week)}<span>${Math.round(m.week)}%</span>`}</div>`).join("");
    const counts = Object.entries(r.counts || {}).map(([k, v]) => `<span class="chip">${esc(k)} <b>${esc(v)}</b></span>`).join(" ");
    const running = (r.running || []).map((x) => `<div class="r-row"><span class="num">#${esc(x.task)}</span><span class="ttl" title="${esc(x.last_text)}">${esc(x.last_action || x.kind)}</span><span class="st running">${esc(x.account)} · ${esc(x.effort)}</span>${x.session ? `<button type="button" class="btn mini" data-open="${esc(x.session)}">Look</button>` : ""}</div>`).join("") || '<div class="muted small">Nothing running.</div>';
    const tasks = (r.tasks || []).map((t) => `<div class="r-row"><span class="num">#${esc(t.id)}</span><span class="ttl" title="${esc(t.title)}">${esc(t.title)}</span><span class="st ${esc(t.status)}">${esc(t.status)}${t.account ? " · " + esc(t.account) : ""}</span></div>`).join("");
    $("relay").innerHTML = `<div class="relay-grid">
      <div class="r-panel"><h3>Boss ${r.paused ? '<span class="paused-pill">paused</span>' : ""}<span class="spacer"></span>
        <button type="button" class="btn mini" data-relay="${r.paused ? "resume" : "pause"}">${r.paused ? "Resume" : "Pause"}</button></h3>
        <div class="small ${r.boss_up ? "" : "muted"}">${r.boss_up ? "Boss process alive" : "The boss has not ticked lately"}${r.boss_seen ? ` · last tick <span data-at="${r.boss_seen}">${L.ago(nowS() - r.boss_seen)}</span>` : ""}</div>
        ${r.wait_reason && !(r.paused && /^paused\b/i.test(r.wait_reason)) ? `<div class="small muted" style="margin-top:4px">Waiting: ${esc(r.wait_reason)}</div>` : ""}
        <div style="margin-top:10px">${counts}</div>
      </div>
      <div class="r-panel"><h3>Accounts</h3>${acct || '<div class="muted small">No meter readings.</div>'}</div>
      <div class="r-panel"><h3>Running</h3>${running}</div>
      <div class="r-panel" style="grid-column: 1 / -1"><h3>Queue and recent tasks</h3>${tasks || '<div class="muted small">No tasks.</div>'}</div>
      <div class="r-panel adv"><h3>Goals</h3>${(r.goals || []).map((g) => `<div class="r-row"><span class="ttl">${esc(g.title || g.slug)}</span><span class="st">${esc(g.status)}</span></div>`).join("") || '<div class="muted small">No goals.</div>'}</div>
      <div class="r-panel adv"><h3>Events</h3>${(r.events || []).map((e) => `<div class="r-row"><span class="num" data-at="${e.at}">${L.ago(nowS() - e.at)}</span><span class="ttl" title="${esc(e.text)}">${esc(e.text)}</span></div>`).join("")}</div>
    </div>`;
  }

  /* -------------------------------------------------------------- drawer */
  // The action row (Open in Claude, Go to it, Message) sits on top as it
  // always has; under it two tabs: Chat, the whole conversation drawn by
  // chat.js with the Claude app's own renderer plus a reply box, and
  // Details, the facts and helpers.
  ui.dtab = store.get("dtab", "chat");
  function openDrawer(id, agent) {
    // In Conversations the chat is the view itself: the session is picked
    // there and the drawer shows only its details.
    if (ui.view === "convos" && window.MissionConvos) window.MissionConvos.select(id);
    ui.selected = { id, agent: agent || "" };
    markSeen(id);
    const dr = $("drawer");
    if (dr.hidden && !calm()) { dr.classList.remove("enter"); void dr.offsetWidth; dr.classList.add("enter"); }
    dr.hidden = false;
    renderDrawer();
    if (ui.view === "sessions") renderGrid();
    renderSide();
  }
  function closeDrawer() {
    ui.selected = null;
    if (window.MissionChat) window.MissionChat.hide();
    $("drawer").hidden = true;
    document.body.classList.remove("chat-open");
    if (data && ui.view === "sessions") renderGrid();
  }
  function setDtab(tab) {
    ui.dtab = tab === "details" ? "details" : "chat";
    store.set("dtab", ui.dtab);
    if (ui.selected) renderDrawer();
  }
  function renderDrawer() {
    const sel = ui.selected;
    const s = data && data.sessions.find((x) => x.id === sel.id);
    if (!s) {
      if (window.MissionChat) window.MissionChat.hide();
      $("dTitle").textContent = "Session gone";
      $("dBody").innerHTML = '<div class="muted">That session is no longer listed. It may have ended more than three days ago.</div>';
      $("dBody").dataset.key = "";
      return;
    }
    const h = sel.agent ? s.helpers.find((x) => x.id === sel.agent) : null;
    const name = L.displayName(s);
    const tag = L.personaTag(s);
    const dt = (h ? `${esc(L.helperName(h))} <span class="muted small">helper of ${esc(name)}</span>` : esc(name) + (tag ? ` <span class="muted small">${esc(tag)}</span>` : "")) + ` <span class="state ${esc(h ? (h.state === "working" ? "working" : "ended") : s.group)}">${esc(h ? (h.state === "working" ? "Working" : "Done") : GROUP_NAME[s.group])}</span>`;
    if ($("dTitle").innerHTML !== dt) $("dTitle").innerHTML = dt;
    const key = s.id + "|" + sel.agent;
    const kv = h
      ? [["task", h.task], ["type", h.type], ["model", L.modelName(h.model)], ["effort", h.effort], ["context", h.context ? L.tokens(h.context) : ""], ["crew", h.crew ? `${h.crew_member} in ${h.crew}` : ""], ["state", h.state]]
      : [["state", GROUP_NAME[s.group]], ["model", L.modelName(s.model)], ["effort", s.effort], ["folder", s.cwd], ["context", `${L.tokens(s.context)} of ${L.tokens(s.window)}`], ["board name", s.name], ["session", s.id], ["pid", s.pid]];
    const inConvos = ui.view === "convos";
    const chatOn = ui.dtab === "chat" && !inConvos;
    const top = `<div class="s-actions d-acts">
        ${h ? `<button type="button" class="ghost" data-open="${esc(s.id)}">Back to ${esc(name)}</button>` : ""}
        ${s.claude_tab || s.group === "ended" ? `<button type="button" class="btn btn-primary" data-claude="${esc(s.id)}">${icon("open")}${s.group === "ended" ? "Resume in Claude" : "Open in Claude"}</button>` : ""}
        ${s.group !== "ended" ? `<button type="button" class="${s.claude_tab ? "btn" : "btn btn-primary"}" data-go="${esc(s.name)}">${icon("go")}Go to it</button><button type="button" class="btn" data-msg="${esc(s.id)}">${icon("msg")}Message</button>` : ""}
        ${h && h.crew ? `<button type="button" class="btn" data-note-to="${esc(h.crew)}|${esc(h.crew_member)}">Note to ${esc(h.crew_member)}</button>` : ""}
      </div>
      ${s.gone ? '<p class="gone-note">This session is no longer listed: it ended or moved on. What it showed stays here until you close it.</p>' : ""}
      <div class="d-tabs" role="tablist"${inConvos ? " hidden" : ""}>
        <button type="button" role="tab" data-dtab="chat" aria-selected="${chatOn}" class="${chatOn ? "on" : ""}">Chat</button>
        <button type="button" role="tab" data-dtab="details" aria-selected="${!chatOn}" class="${chatOn ? "" : "on"}">Details${!h && s.helpers.length ? ` <span class="n">${s.helpers.length}</span>` : ""}</button>
      </div>`;
    const facts = `<dl class="kv">${kv.filter(([, v]) => v).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("")}</dl>
      ${!h && s.helpers.length ? `<h4>Helpers</h4><div class="helpers">${s.helpers.map((x) => helperRow(s, x)).join("")}</div>` : ""}`;
    const box = $("dBody");
    if (!$("dHead") || box.dataset.key !== key) {
      box.innerHTML = '<div id="dHead"></div><div id="dChat" class="d-pane d-chat"></div><div id="dFacts" class="d-pane d-facts"></div>';
      box.dataset.key = key;
    }
    setHtml($("dHead"), top);
    setHtml($("dFacts"), facts);
    $("dChat").hidden = !chatOn;
    $("dFacts").hidden = chatOn;
    box.classList.toggle("chat-on", chatOn);
    document.body.classList.toggle("chat-open", chatOn);
    // The chat keeps running while Details is shown, so going back to it
    // lands where the reader left off.
    if (chatOn && window.MissionChat) window.MissionChat.show($("dChat"), s, sel.agent);
  }

  /* ------------------------------------------------------------- actions */
  async function post(url, body) {
    const r = await fetch(url, { method: "POST", headers: HEAD, body: JSON.stringify(body || {}) });
    if (!r.ok) throw new Error(await errText(r, "That did not work"));
    return r.json();
  }
  async function guarded(btn, fn) {
    if (btn && btn.disabled) return;
    if (btn) btn.disabled = true;
    try { await fn(); } catch (e) { toast(e.message, "err"); } finally { if (btn) btn.disabled = false; }
  }
  function compose(title, hint, send) {
    $("composeTitle").textContent = title;
    $("composeHint").textContent = hint;
    $("composeText").value = "";
    const dlg = $("compose");
    dlg.onclose = async () => {
      const text = $("composeText").value.trim();
      if (dlg.returnValue !== "send" || !text) return;
      try { await send(text); toast("Sent", "ok"); pollNow(); } catch (e) {
        toast(e.message, "err");
        $("composeText").value = text; // keep the words; try again or cancel
        dlg.returnValue = "";
        dlg.showModal();
      }
    };
    dlg.returnValue = "";
    dlg.showModal();
    $("composeText").focus();
  }

  document.addEventListener("click", (ev) => {
    const t = ev.target.closest("button, [data-open], [data-node]");
    if (!t) return;
    const d = t.dataset;
    if (d.view) {
      if (d.chat && window.MissionConvos) window.MissionConvos.select(d.chat); // e.g. the WhatsApp chat
      return setView(d.view);
    }
    if (d.clear) { ui.filter = "all"; ui.place = ""; ui.search = ""; $("search").value = ""; store.set("filter", "all"); store.set("place", ""); render(); return; }
    if (d.viewGo) return setView(d.viewGo);
    if (d.filter !== undefined) { ui.filter = d.filter; store.set("filter", ui.filter); if (ui.view !== "sessions") setView("sessions"); else render(); return; }
    if (d.place !== undefined) { ui.place = d.place; store.set("place", ui.place); if (ui.view !== "sessions") setView("sessions"); else render(); return; }
    if (d.crew !== undefined && t.tagName === "BUTTON") { setView("crews"); const el = document.getElementById("crew-" + d.crew); if (el) el.scrollIntoView({ block: "start" }); return; }
    if (d.msg) {
      const s = data.sessions.find((x) => x.id === d.msg);
      return compose(`Message ${s ? L.displayName(s) : "session"}`, "A note on the forge board addressed to this session. Its notes hook hands it over at its next step, even mid-job.", (text) => post(`/api/sessions/${encodeURIComponent(d.msg)}/message`, { text }));
    }
    if (d.noteTo) {
      const [crew, to] = d.noteTo.split("|");
      return compose(`Note to ${to} (${crew})`, `Posted on the ${crew} crew board for ${to}. A helper running inside another session gets it only if its notes hook runs there.`, (text) => post(`/api/crews/${encodeURIComponent(crew)}/notes`, { text, to }));
    }
    if (d.reply) {
      const [crew, id] = d.reply.split("|");
      return compose(`Answer note #${id}`, `Your answer is posted on the ${crew} board as a reply to its author; the note stays open.`, async (text) => {
        const c = data.crews.find((x) => x.name === crew);
        const n = c && c.notes.find((x) => String(x.id) === id);
        await post(`/api/crews/${encodeURIComponent(crew)}/notes`, { text, to: n ? n.from : null, re: Number(id) });
      });
    }
    if (d.ack) {
      const [crew, id] = d.ack.split("|");
      return guarded(t, async () => { await post(`/api/crews/${encodeURIComponent(crew)}/notes/${encodeURIComponent(id)}/ack`, {}); toast("Marked seen", "ok"); pollNow(); });
    }
    if (d.go) return guarded(t, async () => {
      const g = L.goResult(await post(`/api/go/${encodeURIComponent(d.go)}`));
      const s = g.chat && data.sessions.find((x) => x.name === d.go);
      if (s && window.MissionConvos) { window.MissionConvos.select(s.id); setView("convos"); }
      toast(g.text, g.kind);
    });
    if (d.claude) {
      const s = data.sessions.find((x) => x.id === d.claude);
      if (!s) return;
      return guarded(t, async () => { const r = await post(`/api/sessions/${encodeURIComponent(s.id)}/open`, { state: s.group, cwd: s.cwd, name: s.label || s.name }); toast(r.shown ? "Opened in the Claude app" : "Opened; switch to the Claude app to see it", "ok"); });
    }
    if (d.relay) return guarded(t, async () => { const r = await post(`/api/relay/${d.relay}`); toast(r.message || "Done", "ok"); pollNow(); });
    if (d.open) return openDrawer(d.open, d.agent);
    if (d.zoom) return mapZoom(d.zoom);
    if (d.node) {
      const n = data.graph.nodes.find((x) => x.id === d.node);
      if (!n) return;
      if (n.kind === "relay" || n.kind === "run") return n.ref && n.kind === "run" && data.sessions.some((s) => s.id === n.ref) ? openDrawer(n.ref) : setView("relay");
      if (n.kind === "crew") return setView("crews");
      if (n.ref) return openDrawer(n.ref, n.helper);
    }
    if (d.dtab) return setDtab(d.dtab);
    if (t.id === "dClose") return closeDrawer();
    if (t.id === "noteAll" || t.id === "askAll" || d.askAll !== undefined) return compose("Note to everyone", "Posted on the forge board for every session; each one sees it at its next step. Their answers come back under Messages.", async (text) => { await post("/api/broadcast", { text, crew: "forge" }); if (window.MissionMessages) window.MissionMessages.refresh(); });
    if (t.id === "markRead") { for (const s of data.sessions) seen[s.id] = Math.max(s.last_active || 0, nowS()); store.set("seen", seen); render(); return; }
    if (t.id === "settingsBtn") return openSettings();
    if (t.dataset.mode) return setMode(t.dataset.mode);
  });
  document.addEventListener("keydown", (e) => {
    if (e.target.classList && e.target.classList.contains("s-card") && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); openDrawer(e.target.dataset.open); return; }
    if (e.target.closest && e.target.closest("[data-node]") && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); e.target.closest("[data-node]").dispatchEvent(new MouseEvent("click", { bubbles: true })); }
    if (e.key === "Escape" && ui.selected && !document.querySelector("dialog[open]")) closeDrawer();
    if (e.key === "F11") { e.preventDefault(); window.ForgeChrome && window.ForgeChrome.toggle(); }
  });
  // Click away (Emerson, 2026-10-08): a click outside the open details
  // drawer closes it, the same as Esc. A click on another session (card,
  // tile, map node, Open chat) switches the drawer to that one instead; a
  // click in a dialog, or a press that started in the drawer or moved
  // (picking text, panning) leaves it open. Keyboard clicks (detail 0) go
  // by where they land only.
  const press = { inside: false, x: 0, y: 0 };
  const within = (e, sel) => e.composedPath().some((n) => n instanceof Element && n.matches(sel));
  document.addEventListener("pointerdown", (e) => {
    press.inside = within(e, "#drawer, dialog");
    press.x = e.clientX;
    press.y = e.clientY;
  }, true);
  document.addEventListener("click", (e) => {
    if (!ui.selected || $("drawer").hidden) return;
    if (e.detail && (press.inside || Math.hypot(e.clientX - press.x, e.clientY - press.y) > 6)) return;
    if (within(e, "#drawer, dialog, #toast, [data-open], [data-node]")) return;
    closeDrawer();
  }, true);
  // A click on the dim backdrop round a dialog closes it too. The note
  // dialog stays while it holds words, so a stray click never loses them.
  for (const dlg of document.querySelectorAll("dialog")) {
    dlg.addEventListener("click", (e) => {
      if (e.target !== dlg || !e.detail) return;
      const r = dlg.getBoundingClientRect();
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) return;
      if (dlg.id === "compose" && $("composeText").value.trim()) return;
      dlg.close("cancel");
    });
  }
  document.addEventListener("submit", (ev) => {
    const f = ev.target.closest("form.composer");
    if (!f) return;
    ev.preventDefault();
    const text = f.text.value.trim();
    if (!text) return;
    const btn = f.querySelector("button");
    guarded(btn, async () => { await post(`/api/crews/${encodeURIComponent(f.dataset.crew)}/notes`, { text, to: f.to.value || null }); f.text.value = ""; toast("Posted", "ok"); pollNow(); });
  });
  let searchT = 0;
  $("search").addEventListener("input", (e) => { ui.search = e.target.value; clearTimeout(searchT); searchT = setTimeout(() => data && renderGrid(), 120); });
  $("relayStrip").addEventListener("click", () => setView("relay"));

  const VIEWS = ["sessions", "convos", "swarm", "map", "messages", "crews", "relay"];
  function setView(v) {
    if (!VIEWS.includes(v)) v = "sessions";
    if (ui.view === "convos" && v !== "convos" && window.MissionConvos) window.MissionConvos.left();
    ui.view = v;
    store.set("view", v);
    if (location.hash !== "#" + v) history.replaceState(null, "", "#" + v);
    for (const sec of document.querySelectorAll(".view")) {
      const on = sec.id === "view-" + v;
      sec.classList.toggle("on", on);
    }
    // Conversations is the chat alone: the top bar, nav and needs band step aside
    document.body.classList.toggle("focus-chat", v === "convos");
    render();
    if (v === "map") layoutMap(false);
    if (v === "messages" && window.MissionMessages) window.MissionMessages.shown();
    if (v === "convos" && window.MissionConvos) window.MissionConvos.shown();
  }
  function setMode(m) {
    ui.mode = m === "advanced" ? "advanced" : "simple";
    store.set("mode", ui.mode);
    document.body.classList.toggle("simple", ui.mode === "simple");
    document.body.classList.toggle("advanced", ui.mode === "advanced"); // shared forge.css hides .adv without it
    for (const b of document.querySelectorAll(".mode-switch button")) b.classList.toggle("on", b.dataset.mode === ui.mode);
    render();
  }

  function openSettings() {
    $("settingsFields").innerHTML = SETTINGS.map((s) => `<div class="set-row"><label for="r-${s.key}">${esc(s.label)}</label>
      <input type="range" id="r-${s.key}" data-key="${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" value="${S[s.key]}">
      <input type="number" id="n-${s.key}" data-key="${s.key}" min="${s.min}" max="${s.max}" step="${s.step}" value="${S[s.key]}">
      <div class="hint">${esc(s.hint)}</div></div>`).join("");
    $("settings").showModal();
  }
  $("settingsFields").addEventListener("input", (e) => {
    const k = e.target.dataset.key;
    const spec = SETTINGS.find((s) => s.key === k);
    if (!spec) return;
    let v = Number(e.target.value);
    if (!isFinite(v)) return;
    v = Math.max(spec.min, Math.min(spec.max, v));
    S[k] = v;
    if (S.slow < S.fast) S.slow = S.fast;
    $("r-" + k).value = v;
    if (e.target.type === "range") $("n-" + k).value = v;
    store.set("settings", S);
    delay = S.fast;
    render();
  });
  $("settingsReset").addEventListener("click", () => {
    for (const s of SETTINGS) S[s.key] = s.def;
    store.set("settings", S);
    render();
  });

  /* ---------------------------------------------------------------- boot */
  // Calm: the system asks for less motion. Loops and sparks stop; one-shot
  // fades stay off too (the stylesheet shortens them to nothing).
  const reduce = window.matchMedia ? window.matchMedia("(prefers-reduced-motion: reduce)") : null;
  const setCalm = () => { document.body.classList.toggle("calm", !!(reduce && reduce.matches)); };
  setCalm();
  if (reduce && reduce.addEventListener) reduce.addEventListener("change", setCalm);
  let resizeT = 0;
  window.addEventListener("resize", () => { clearTimeout(resizeT); resizeT = setTimeout(() => { if (data && ui.view === "sessions") renderGrid(); if (ui.view === "map") layoutMap(false); }, 150); });
  if (window.ForgeChrome) window.ForgeChrome.init({ button: "go-fullscreen", key: "f" });
  const fromHash = location.hash.slice(1);
  const params = new URLSearchParams(location.search);
  if (params.get("mode")) ui.mode = params.get("mode");
  setMode(ui.mode);
  setView(VIEWS.includes(fromHash) ? fromHash : ui.view);
  window.addEventListener("hashchange", () => { const v = location.hash.slice(1); if (v !== ui.view) setView(v); });
  loadArt().then(() => { if (data) render(); });
  const openFirst = params.get("open");
  if (openFirst) {
    const wait = setInterval(() => {
      if (!data) return;
      clearInterval(wait);
      const s = openFirst === "first" ? data.sessions[0] : data.sessions.find((x) => x.id === openFirst);
      if (s) openDrawer(s.id);
    }, 200);
  }
  // What chat.js, messages.js and swarm.js share with this page.
  window.MissionApp = {
    get data() { return data; },
    esc, avatar, icon, nowS, openDrawer, post, pollNow, guarded, meterBar, markSeen, setView,
    toast: (m, k) => toast(m, k),
  };
  poll();
})();
