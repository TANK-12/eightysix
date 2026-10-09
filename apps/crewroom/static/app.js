/* Crew Room renderer.
 *
 * Draws the room into a small buffer canvas at 1 room pixel = 1 canvas pixel,
 * then blits it to the visible canvas at an integer scale so the pixel art
 * stays crisp. Name tags, speech bubbles and the board's task list are DOM
 * elements laid over the canvas, which keeps text sharp at every scale.
 *
 * Rooms and sprites are data (see /api/rooms and /api/art/library); nothing
 * here knows what a particular room contains beyond the fields it reads.
 */
(function () {
  "use strict";

  const T = 16;
  const LOOKS = 8;
  const FAMILY_COLORS = { opus: "#a57bff", sonnet: "#ffbe55", haiku: "#69e0c8", fable: "#f79ac0" };
  const HELPER_KIND = { "crew-light": "light", "crew-worker": "worker", "crew-deep": "deep" };
  const JAN_GLOW = { a: "127,247,255", b: "247,154,192", c: "143,224,174" };
  const FRAME_MS = 33;
  const DEFAULTS = {
    room: "office",
    reducedMotion: window.matchMedia("(prefers-reduced-motion: reduce)").matches,
    tags: true,
    helperTags: false,
    bubbles: "all",
    poll: 2,
    scale: 0,
    palette: "crewroom",
    mode: "simple",
    demo: false,
    launchFolder: "",
    taskModel: "",
  };
  const TASK_COLORS = { running: "var(--good)", done: "var(--muted)", failed: "var(--bad)" };

  const S = loadSettings();
  if (/[?&]demo\b/.test(location.search)) S.demo = true;
  const roomParam = location.search.match(/[?&]room=([\w-]+)/);
  if (roomParam) S.room = roomParam[1];

  const $ = (id) => document.getElementById(id);
  const canvas = $("room");
  const ctx = canvas.getContext("2d");
  const buffer = document.createElement("canvas");
  const bctx = buffer.getContext("2d");
  const overlay = $("overlay");
  const boardEl = $("board");

  const state = {
    lib: null,
    atlas: null,
    rooms: [],
    room: null,
    solid: [],
    data: null,
    actors: new Map(),
    stations: new Map(),
    lounge: new Map(),
    janSpots: new Map(),
    claims: new Map(),
    selected: null,
    scale: 1,
    firstData: true,
    stars: [],
    motes: [],
    lastFrame: 0,
    nextChat: 0,
    poller: null,
    pollRestart: 0,
    roomSeq: 0,
    bound: false,
    boardKey: "",
    where: null,
    ended: null,
    convo: null,
    tasksKey: "",
  };

  // --- settings ----------------------------------------------------------------

  function loadSettings() {
    try {
      return Object.assign({}, DEFAULTS, JSON.parse(localStorage.getItem("crewroom.settings") || "{}"));
    } catch (err) {
      return Object.assign({}, DEFAULTS);
    }
  }

  function saveSettings() {
    try {
      localStorage.setItem("crewroom.settings", JSON.stringify(S));
    } catch (err) {
      /* private mode: settings last for this visit only */
    }
  }

  // --- helpers -----------------------------------------------------------------

  function hash(text) {
    let h = 2166136261;
    for (let i = 0; i < text.length; i++) {
      h ^= text.charCodeAt(i);
      h = Math.imul(h, 16777619);
    }
    return h >>> 0;
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
  }

  function tokens(n) {
    if (!n) return "0";
    return n >= 1000 ? (n / 1000).toFixed(n >= 100000 ? 0 : 1) + "k" : String(n);
  }

  function shortModel(info) {
    const fam = info.family || (info.model ? String(info.model).replace(/^claude-/, "") : "");
    return [fam, info.effort].filter(Boolean).join(" · ");
  }

  function showStatus(text) {
    const el = $("status");
    el.textContent = text || "";
    el.hidden = !text;
  }

  // --- rooms and walking ---------------------------------------------------------

  async function loadRoom(id) {
    const seq = ++state.roomSeq;
    const res = await fetch("/api/rooms/" + encodeURIComponent(id), { signal: AbortSignal.timeout(15000) });
    if (!res.ok) throw new Error("could not load the room " + id + " (" + res.status + ")");
    const room = await res.json();
    if (seq !== state.roomSeq) return; // a newer room was picked meanwhile
    room.tiles = room.tiles || [];
    room.h = room.h || room.tiles.length || 12;
    room.w = room.w || (room.tiles[0] || "").length || 20;
    room.legend = room.legend || {};
    room.props = room.props || [];
    room.stations = room.stations || [];
    room.lounge = room.lounge || [];
    room.jan = room.jan || { spots: [] };
    room.jan.spots = room.jan.spots || [];
    room.seat = room.seat || { dx: 1, dy: 0.7 };
    room.helper_offsets = room.helper_offsets || [[-1.1, 0.45], [1.1, 0.45], [-1.1, 1.25], [1.1, 1.25]];
    room.door = room.door || { x: room.w / 2, y: room.h - 0.1 };
    state.room = room;
    buffer.width = room.w * T;
    buffer.height = room.h * T;
    if (room.palette && state.lib.palettes[room.palette] && !S.paletteChosen) {
      state.atlas.rebake(room.palette);
    }
    buildSolid();
    state.stations.clear();
    state.lounge.clear();
    state.janSpots.clear();
    for (const a of state.actors.values()) {
      a.goal = null;
      a.path = [];
      a.visit = null;
      a.placeOnArrive = true;
    }
    initAmbient();
    state.boardKey = "";
    renderTabs();
    resize();
  }

  function buildSolid() {
    const r = state.room;
    const solid = [];
    for (let y = 0; y < r.h; y++) {
      const row = [];
      for (let x = 0; x < r.w; x++) {
        const leg = r.legend[(r.tiles[y] || "")[x]];
        row.push(!!(leg && leg.solid));
      }
      solid.push(row);
    }
    const block = (bx, by, bw, bh) => {
      for (let y = Math.floor(by); y < Math.ceil(by + bh); y++) {
        for (let x = Math.floor(bx); x < Math.ceil(bx + bw); x++) {
          if (solid[y] && x >= 0 && x < r.w) solid[y][x] = true;
        }
      }
    };
    const footprint = (p) => {
      if (p.block) return block(p.block[0], p.block[1], p.block[2], p.block[3]);
      const s = state.atlas.get(p.sprite);
      if (!s) return;
      const w = s.w / T;
      const h = s.h / T;
      block(p.x + 0.1, p.y + h * 0.55, w - 0.2, h * 0.45);
    };
    for (const p of r.props) if (p.solid || p.block) footprint(p);
    for (const st of r.stations) footprint(st);
    if (r.board && r.board.solid) footprint(r.board);
    if (r.jan.prop && r.jan.prop.solid) footprint(r.jan.prop);
    state.solid = solid;
  }

  function findPath(fx, fy, tx, ty) {
    const r = state.room;
    const cell = (v, max) => Math.max(0, Math.min(max - 1, Math.floor(v / T)));
    const sx = cell(fx, r.w);
    const sy = cell(fy, r.h);
    const gx = cell(tx, r.w);
    const gy = cell(ty, r.h);
    const key = (x, y) => y * r.w + x;
    const prev = new Map([[key(sx, sy), -1]]);
    const queue = [[sx, sy]];
    let found = false;
    for (let i = 0; i < queue.length; i++) {
      const [x, y] = queue[i];
      if (x === gx && y === gy) {
        found = true;
        break;
      }
      for (const [dx, dy] of [[0, -1], [1, 0], [0, 1], [-1, 0]]) {
        const nx = x + dx;
        const ny = y + dy;
        if (nx < 0 || ny < 0 || nx >= r.w || ny >= r.h) continue;
        const k = key(nx, ny);
        if (prev.has(k)) continue;
        if (state.solid[ny][nx] && !(nx === gx && ny === gy)) continue;
        prev.set(k, key(x, y));
        queue.push([nx, ny]);
      }
    }
    if (!found) return [{ x: tx, y: ty }];
    const cells = [];
    for (let k = key(gx, gy); k !== -1; k = prev.get(k)) cells.push(k);
    cells.reverse();
    const points = cells.slice(1, -1).map((k) => ({ x: ((k % r.w) + 0.5) * T, y: (Math.floor(k / r.w) + 0.5) * T }));
    points.push({ x: tx, y: ty });
    return points;
  }

  function assign(map, id, count) {
    if (map.has(id)) return map.get(id);
    const used = new Set(map.values());
    for (let i = 0; i < count; i++) {
      if (!used.has(i)) {
        map.set(id, i);
        return i;
      }
    }
    let overflow = -1;
    while (used.has(overflow)) overflow--;
    map.set(id, overflow);
    return overflow;
  }

  function seatPoint(index) {
    const r = state.room;
    if (index >= 0) {
      const st = r.stations[index];
      const seat = st.seat || { x: st.x + r.seat.dx, y: st.y + r.seat.dy };
      return { x: seat.x * T, y: seat.y * T };
    }
    return overflowPoint(index);
  }

  function overflowPoint(index) {
    const r = state.room;
    const n = -index - 1;
    return { x: (1.5 + (n % 9) * 2) * T, y: (r.h - 0.6 - Math.floor(n / 9) * 0.8) * T };
  }

  // --- data -> actors ------------------------------------------------------------

  function newActor(id, kind) {
    const r = state.room;
    const a = {
      id,
      kind,
      x: r.door.x * T,
      y: r.door.y * T,
      path: [],
      dir: "down",
      alpha: state.firstData ? 1 : 0,
      leaving: false,
      info: {},
      look: 1,
      goal: null,
      visit: null,
      chatUntil: 0,
      bubbleAt: 0,
      phase: hash(id) % 5000,
      placeOnArrive: state.firstData,
      moving: false,
      box: null,
      tagEl: null,
      bubbleEl: null,
      tagKey: "",
    };
    state.actors.set(id, a);
    return a;
  }

  function lookFor(id, name) {
    const used = new Set();
    for (const a of state.actors.values()) if (a.kind === "session" && a.id !== id) used.add(a.look);
    let n = hash(name) % LOOKS;
    for (let i = 0; i < LOOKS && used.has(n + 1); i++) n = (n + 1) % LOOKS;
    return n + 1;
  }

  function sync(raw) {
    const data = S.demo && window.CrewRoomDemo ? window.CrewRoomDemo.apply(raw, Date.now()) : raw;
    state.data = data;
    const now = performance.now();
    const seen = new Set();

    for (const s of data.sessions || []) {
      const id = "s:" + s.id;
      seen.add(id);
      let a = state.actors.get(id);
      if (!a) {
        a = newActor(id, "session");
        a.look = lookFor(id, s.name);
      }
      if (a.info.action !== s.action) a.bubbleAt = now;
      a.info = s;
      if (a.leaving) a.leaving = false;
    }
    for (const h of data.helpers || []) {
      const id = "h:" + h.id;
      seen.add(id);
      const known = state.actors.get(id);
      const a = known || newActor(id, "helper");
      a.hair = "abc"[hash(h.id) % 3];
      a.helperKind = HELPER_KIND[h.type] || "other";
      // No bubble on first sight: a room full of helpers arriving at once
      // would otherwise open with a wall of overlapping bubbles.
      if (known && (a.info.action !== h.action || a.info.state !== h.state)) a.bubbleAt = now;
      a.info = h;
    }
    for (const m of (data.jan && data.jan.models) || []) {
      const id = "j:" + m.id;
      seen.add(id);
      const a = state.actors.get(id) || newActor(id, "jan");
      a.variant = "abc"[hash(m.name) % 3];
      a.info = m;
    }
    for (const a of state.actors.values()) {
      if (!seen.has(a.id) && !a.leaving) {
        a.leaving = true;
        a.goal = null;
      }
    }

    state.claims = new Map();
    for (const crew of data.crews || []) {
      for (const c of crew.claims || []) {
        if (!state.claims.has(c.owner)) state.claims.set(c.owner, []);
        state.claims.get(c.owner).push(c.path);
      }
    }
    state.firstData = false;
    renderCounts();
    renderBoard(true);
    if (state.selected) renderDetails();
  }

  function helperSiblings(parentId) {
    const list = [];
    for (const a of state.actors.values()) {
      if (a.kind === "helper" && !a.leaving && "s:" + a.info.parent === parentId) list.push(a.id);
    }
    return list.sort();
  }

  function goalFor(a, now) {
    const r = state.room;
    const door = { x: r.door.x * T, y: r.door.y * T, pose: "idle" };
    if (a.leaving) return door;

    if (a.kind === "session") {
      const station = assign(state.stations, a.id, r.stations.length);
      if (a.visit && a.visit.until > now) return { x: a.visit.x, y: a.visit.y, pose: "talk" };
      a.visit = null;
      if (a.info.busy) {
        state.lounge.delete(a.id);
        return Object.assign(seatPoint(station), { pose: "type" });
      }
      const spot = assign(state.lounge, a.id, r.lounge.length);
      if (spot >= 0) {
        const sp = r.lounge[spot];
        return { x: sp.x * T, y: sp.y * T, pose: a.chatUntil > now && sp.pose !== "relax" ? "talk" : sp.pose || "idle" };
      }
      return Object.assign(overflowPoint(spot), { pose: "idle" });
    }

    if (a.kind === "helper") {
      const parent = state.actors.get("s:" + a.info.parent);
      if (!parent || parent.leaving) return door;
      const siblings = helperSiblings(parent.id);
      const index = Math.max(0, siblings.indexOf(a.id));
      if (a.info.state === "done") {
        const base = parent.goal || parent;
        const side = base.x > (r.w * T) / 2 ? -1 : 1;
        return { x: base.x + side * (0.95 + index * 0.7) * T, y: base.y + 2, pose: "talk" };
      }
      const seat = seatPoint(assign(state.stations, parent.id, r.stations.length));
      const offsets = r.helper_offsets;
      const off = offsets[index % offsets.length];
      const ring = Math.floor(index / offsets.length);
      return { x: seat.x + off[0] * T * (1 + ring * 0.6), y: seat.y + (off[1] + ring * 0.5) * T, pose: "type" };
    }

    const spots = r.jan.spots.length ? r.jan.spots : [{ x: r.w - 1.5, y: r.h - 1 }];
    const i = assign(state.janSpots, a.id, spots.length);
    const n = i >= 0 ? i : -i - 1;
    const sp = spots[n % spots.length];
    return { x: (sp.x - (i >= 0 ? 0 : 0.9 * (Math.floor(n / spots.length) + 1))) * T, y: sp.y * T, pose: "float" };
  }

  function release(a) {
    state.actors.delete(a.id);
    if (a.kind === "session") {
      state.stations.delete(a.id);
      state.lounge.delete(a.id);
    }
    state.janSpots.delete(a.id);
    if (a.tagEl) a.tagEl.remove();
    if (a.bubbleEl) a.bubbleEl.remove();
    if (state.selected === a.id) {
      // An ended session keeps its panel: conversation, and how to resume it.
      if (a.kind === "session" && !a.info.sample) {
        state.ended = a.info;
        loadWhere();
        renderDetails();
      } else closeDetails();
    }
  }

  function step(a, dt, now) {
    const goal = goalFor(a, now);
    if (!a.goal || Math.abs(goal.x - a.goal.x) > 0.5 || Math.abs(goal.y - a.goal.y) > 0.5) {
      a.goal = goal;
      if (S.reducedMotion || a.placeOnArrive) {
        a.x = goal.x;
        a.y = goal.y;
        a.path = [];
      } else {
        a.path = a.kind === "jan" ? [{ x: goal.x, y: goal.y }] : findPath(a.x, a.y, goal.x, goal.y);
      }
    } else {
      a.goal.pose = goal.pose;
    }
    a.placeOnArrive = false;

    const speed = a.kind === "helper" ? 40 : a.kind === "jan" ? 24 : 34;
    let budget = speed * dt;
    a.moving = false;
    while (a.path.length && budget > 0) {
      const p = a.path[0];
      const dx = p.x - a.x;
      const dy = p.y - a.y;
      const d = Math.hypot(dx, dy);
      if (d > 0.01) {
        a.dir = Math.abs(dx) > Math.abs(dy) ? (dx > 0 ? "right" : "left") : dy > 0 ? "down" : "up";
        a.moving = true;
      }
      if (d <= budget) {
        a.x = p.x;
        a.y = p.y;
        a.path.shift();
        budget -= d;
      } else {
        a.x += (dx / d) * budget;
        a.y += (dy / d) * budget;
        budget = 0;
      }
    }

    if (a.leaving && !a.path.length) {
      a.alpha -= dt * (S.reducedMotion ? 10 : 2);
      if (a.alpha <= 0) release(a);
    } else if (a.alpha < 1) {
      a.alpha = Math.min(1, a.alpha + dt * 2);
    }
  }

  function maybeChat(now) {
    if (now < state.nextChat) return;
    state.nextChat = now + 9000 + Math.random() * 9000;
    const idle = [];
    for (const a of state.actors.values()) {
      if (a.kind === "session" && !a.leaving && !a.info.busy && !a.visit && a.goal && !a.moving) idle.push(a);
    }
    if (idle.length < 2) return;
    const i = Math.floor(Math.random() * idle.length);
    const visitor = idle[i];
    const host = idle[(i + 1 + Math.floor(Math.random() * (idle.length - 1))) % idle.length];
    const side = host.goal.x > (state.room.w * T) / 2 ? -1 : 1;
    const until = now + 7000;
    visitor.visit = { x: host.goal.x + side * 0.95 * T, y: host.goal.y + 1, until };
    host.chatUntil = until;
  }

  // --- drawing -------------------------------------------------------------------

  function spriteFor(a) {
    if (a.kind === "jan") return "jan_" + a.variant + "_" + ((a.info.cpu || 0) >= 25 ? "busy" : "idle");
    const pose = a.goal ? a.goal.pose : "idle";
    if (a.kind === "helper") {
      const base = "helper_" + a.helperKind + "_" + a.hair + "_";
      if (a.moving) return base + (a.dir === "up" ? "walk_up" : "walk");
      return base + (pose === "talk" || pose === "type" ? pose : "idle");
    }
    const base = "person" + a.look + "_";
    if (a.moving) return base + "walk_" + a.dir;
    return base + (pose === "type" || pose === "relax" || pose === "talk" ? pose : "idle");
  }

  function shadow(x, y, rx) {
    bctx.fillStyle = "rgba(20, 12, 30, 0.28)";
    bctx.beginPath();
    bctx.ellipse(x, y - 1, rx, 2, 0, 0, Math.PI * 2);
    bctx.fill();
  }

  function drawActor(a, t, now) {
    const id = spriteFor(a);
    const s = state.atlas.get(id);
    if (!s) return;
    bctx.globalAlpha = Math.max(0, Math.min(1, a.alpha));
    const x = Math.round(a.x - s.w / 2);
    let y = Math.round(a.y - s.h);
    if (a.kind === "jan") {
      const share = Math.min(1, (a.info.cpu || 0) / 100);
      const bob = S.reducedMotion ? 0 : Math.sin((now + a.phase) / (620 - 420 * share)) * (1.5 + 2 * share);
      shadow(a.x, a.y, 5);
      y = Math.round(a.y - s.h - 5 + bob);
      const cx = a.x;
      const cy = y + 8;
      const radius = 9 + 12 * share;
      const glow = bctx.createRadialGradient(cx, cy, 1, cx, cy, radius);
      const rgb = JAN_GLOW[a.variant] || JAN_GLOW.a;
      glow.addColorStop(0, "rgba(" + rgb + "," + (0.25 + 0.5 * share).toFixed(2) + ")");
      glow.addColorStop(1, "rgba(" + rgb + ",0)");
      bctx.fillStyle = glow;
      bctx.fillRect(cx - radius, cy - radius, radius * 2, radius * 2);
    } else if (!(a.goal && a.goal.pose === "type" && !a.moving && a.kind === "session")) {
      shadow(a.x, a.y, a.kind === "helper" ? 4 : 5);
    }
    state.atlas.draw(bctx, id, x, y, t + a.phase);
    bctx.globalAlpha = 1;
    a.box = { x, y, w: s.w, h: s.h };
  }

  function stationOwner(index) {
    for (const [id, i] of state.stations) if (i === index) return state.actors.get(id);
    return null;
  }

  function draw(now, dt) {
    const r = state.room;
    const A = state.atlas;
    const t = S.reducedMotion ? 0 : now;
    bctx.fillStyle = r.background || "#1b1726";
    bctx.fillRect(0, 0, buffer.width, buffer.height);

    for (let y = 0; y < r.h; y++) {
      const row = r.tiles[y] || "";
      for (let x = 0; x < r.w; x++) {
        const leg = r.legend[row[x]];
        if (leg && leg.sprite) A.draw(bctx, leg.sprite, x * T, y * T, t + x * 90);
      }
    }
    drawAmbientBack(dt);

    const items = [];
    const addSprite = (p, extra) => {
      const s = A.get(p.sprite);
      if (!s) return;
      const z = p.layer === "back" ? -100000 + p.y : p.layer === "front" ? 100000 : p.y * T + s.h;
      items.push({
        z,
        draw: () => {
          A.draw(bctx, p.sprite, p.x * T, p.y * T, t + (p.phase || 0));
          if (extra) extra();
        },
      });
    };
    for (const p of r.props) addSprite(p);
    if (r.board) addSprite(r.board);
    if (r.jan.prop) addSprite(r.jan.prop);
    r.stations.forEach((st, index) => {
      addSprite(st, () => {
        const owner = stationOwner(index);
        const files = owner ? state.claims.get(owner.info.name) || [] : [];
        for (let k = 0; k < Math.min(2, files.length); k++) {
          A.draw(bctx, "item_file", st.x * T + 1 + k * 7, st.y * T + 1, 0);
        }
      });
    });
    for (const a of state.actors.values()) items.push({ z: a.y, draw: () => drawActor(a, t, now) });
    items.sort((p, q) => p.z - q.z);
    for (const item of items) item.draw();
    drawAmbientFront(now);

    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(buffer, 0, 0, canvas.width, canvas.height);
  }

  function initAmbient() {
    state.stars = [];
    state.motes = [];
    const amb = state.room.ambient;
    if (!amb) return;
    const [, , w, h] = amb.rect || [0, 0, buffer.width, buffer.height];
    if (amb.type === "stars") {
      for (let i = 0; i < 70; i++) state.stars.push({ x: Math.random() * w, y: Math.random() * h, z: 1 + (i % 3) });
    } else if (amb.type === "motes") {
      for (let i = 0; i < 16; i++) state.motes.push({ x: Math.random() * w, y: Math.random() * h, p: Math.random() * 6.28 });
    }
  }

  function drawAmbientBack(dt) {
    const amb = state.room.ambient;
    if (!amb || amb.type !== "stars") return;
    const [x, y, w, h] = amb.rect;
    bctx.fillStyle = "#0b0e22";
    bctx.fillRect(x, y, w, h);
    const colors = ["", "#6b6485", "#a9a3c2", "#fbf7ff"];
    for (const s of state.stars) {
      if (!S.reducedMotion) {
        s.x -= dt * 5 * s.z * s.z;
        if (s.x < 0) {
          s.x += w;
          s.y = Math.random() * h;
        }
      }
      bctx.fillStyle = colors[s.z];
      bctx.fillRect(x + Math.round(s.x), y + Math.round(s.y), s.z === 3 && !S.reducedMotion ? 2 : 1, 1);
    }
  }

  function drawAmbientFront(now) {
    const amb = state.room.ambient;
    if (!amb || amb.type !== "motes") return;
    const [x, y, w, h] = amb.rect;
    for (const m of state.motes) {
      const k = S.reducedMotion ? 0 : now / 1000;
      const mx = x + ((m.x + k * 3) % w);
      const my = y + ((m.y - k * 2 + h * 10) % h) + Math.sin(k + m.p) * 3;
      bctx.fillStyle = "rgba(255, 224, 102, " + (0.25 + 0.25 * Math.sin(k * 1.7 + m.p)).toFixed(2) + ")";
      bctx.fillRect(Math.round(mx), Math.round(my), 1, 1);
    }
  }

  // --- overlay: tags, bubbles, board ----------------------------------------------

  function bubbleText(a, now) {
    if (S.bubbles === "off" || a.leaving) return "";
    if (a.kind === "jan") return (a.info.cpu || 0) >= 50 ? "thinking hard" : "";
    if (a.kind === "helper") {
      if (a.info.state === "done") return "reporting back";
      return now - a.bubbleAt < 5000 ? a.info.action : "";
    }
    if (a.visit || a.chatUntil > now) return a.visit ? "hey, how's it going?" : "chatting";
    if (!a.info.busy) return "";
    if (S.bubbles === "changes" && now - a.bubbleAt > 6000) return "";
    return a.info.action || "";
  }

  // The human name (Hotaru) the Claude app and the Board use, else ejb-a9.
  function nameOf(i) {
    return i.label || i.name;
  }

  // A crew task owner is a board name like ejb-a9; show its session's name.
  function ownerName(owner) {
    const s = ((state.data && state.data.sessions) || []).find((x) => x.name === owner);
    return s ? nameOf(s) : owner;
  }

  function tagHtml(a) {
    const i = a.info;
    if (a.kind === "jan") {
      const cpu = i.cpu == null ? "…" : Math.round(i.cpu) + "%";
      return '<span>' + esc(i.short || i.name) + '</span><span class="chip" style="--c:#7ff7ff">' + cpu + "</span>";
    }
    if (a.kind === "helper") {
      return '<span class="chip" style="--c:' + (FAMILY_COLORS[i.family] || "#a9a3c2") + '">' + esc(i.type.replace(/^crew-/, "")) + "</span>";
    }
    const color = FAMILY_COLORS[i.family] || "#a9a3c2";
    const bg = i.background ? '<span class="chip" style="--c:#8fe0ae">background</span>' : "";
    return "<b>" + esc(nameOf(i)) + '</b><span class="chip" style="--c:' + color + '">' + esc(shortModel(i) || "…") + "</span>" + bg;
  }

  function layoutOverlay(now) {
    const k = state.scale;
    for (const a of state.actors.values()) {
      if (!a.box) continue;
      if (!a.tagEl) {
        a.tagEl = document.createElement("div");
        a.tagEl.className = "tag" + (a.kind === "helper" ? " helper" : "");
        a.tagEl.dataset.id = a.id;
        a.bubbleEl = document.createElement("div");
        a.bubbleEl.className = "bubble" + (a.kind === "session" ? "" : " small");
        overlay.append(a.tagEl, a.bubbleEl);
      }
      const wantTag = a.kind === "helper" ? S.helperTags : S.tags;
      a.tagEl.hidden = !wantTag;
      if (wantTag) {
        // Seated neighbours are one sprite apart, so their tags shrink to the
        // name and alternate rows instead of piling on top of each other.
        const seated = !a.moving && a.goal && a.goal.pose === "relax";
        const spot = seated ? state.lounge.get(a.id) || 0 : 0;
        const key = JSON.stringify([a.info.name, a.info.label, a.info.family, a.info.effort, a.info.cpu, a.info.type, seated]);
        if (key !== a.tagKey) {
          a.tagEl.innerHTML = tagHtml(a);
          a.tagEl.title = a.kind === "session" ? nameOf(a.info) + (a.info.label ? " (" + a.info.name + ")" : "") + " · " + shortModel(a.info) : "";
          a.tagEl.classList.toggle("compact", seated);
          a.tagEl.style.maxWidth = seated ? Math.round(1.9 * T * k) + "px" : "";
          a.tagKey = key;
        }
        a.tagEl.classList.toggle("selected", state.selected === a.id);
        a.tagEl.style.opacity = a.alpha.toFixed(2);
        const drop = seated && spot % 2 ? 15 : 0;
        a.tagEl.style.transform = "translate(" + Math.round(a.x * k) + "px," + (Math.round((a.y + 1) * k) + drop) + "px) translateX(-50%)";
      }
      const text = bubbleText(a, now);
      a.bubbleEl.hidden = !text;
      if (text) {
        if (a.bubbleEl.textContent !== text) a.bubbleEl.textContent = text;
        a.bubbleEl.style.opacity = a.alpha.toFixed(2);
        const top = a.kind === "session" ? a.box.y + 2 : a.box.y;
        a.bubbleEl.style.transform = "translate(" + Math.round(a.x * k) + "px," + Math.round(top * k - 6) + "px) translate(-50%,-100%)";
      }
    }
  }

  function renderBoard(force) {
    const r = state.room;
    if (!r || !r.board || !state.data) {
      boardEl.hidden = true;
      return;
    }
    const s = state.atlas.get(r.board.sprite);
    const [ix, iy, iw, ih] = r.board.text || [4, 4, s ? s.w - 8 : 56, s ? s.h - 8 : 28];
    const k = state.scale;
    boardEl.hidden = false;
    boardEl.style.left = Math.round((r.board.x * T + ix) * k) + "px";
    boardEl.style.top = Math.round((r.board.y * T + iy) * k) + "px";
    boardEl.style.width = Math.round(iw * k) + "px";
    boardEl.style.height = Math.round(ih * k) + "px";
    boardEl.style.fontSize = Math.max(8, Math.round(k * 3.4)) + "px";
    boardEl.style.setProperty("--ink", r.board.ink || "#2a2140");

    const crews = (state.data.crews || []).filter((c) => (c.tasks || []).length);
    let html;
    if (crews.length) {
      html = crews
        .map((c) => {
          const tasks = c.tasks.slice(0, 6).map((t) => '<li><span class="st ' + esc(t.status) + '">' + (t.status === "done" ? "✓" : t.status === "open" ? "○" : "▸") + "</span><span>" + esc(t.title) + (t.owner ? " · " + esc(ownerName(t.owner)) : "") + "</span></li>");
          return "<h3>" + esc(c.goal || "crew " + c.name) + "</h3><ul>" + tasks.join("") + "</ul>";
        })
        .join("");
    } else {
      const busy = (state.data.sessions || []).filter((x) => x.busy);
      html = "<h3>" + (busy.length ? "At work" : "Nobody busy") + "</h3><ul>" + busy.slice(0, 5).map((x) => "<li><span class=\"st taken\">▸</span><span>" + esc(nameOf(x)) + "</span></li>").join("") + "</ul>";
    }
    if (force || html !== state.boardKey) {
      boardEl.innerHTML = html;
      state.boardKey = html;
    }
  }

  function renderCounts() {
    const d = state.data || {};
    const sessions = (d.sessions || []).length;
    const busy = (d.sessions || []).filter((s) => s.busy).length;
    const helpers = (d.helpers || []).length;
    const models = ((d.jan || {}).models || []).length;
    const jan = (d.jan || {}).running ? models + " Jan model" + (models === 1 ? "" : "s") : "Jan not running";
    const errors = Object.keys(d.errors || {});
    $("counts").textContent =
      sessions + " session" + (sessions === 1 ? "" : "s") + " (" + busy + " busy) · " + helpers + " helper" + (helpers === 1 ? "" : "s") + " · " + jan + (d.sample ? " · sample crew on" : "") + (errors.length ? " · could not read " + errors.join(", ") : "");
  }

  // --- details panel -------------------------------------------------------------

  function openDetails(id) {
    const changed = state.selected !== id;
    state.selected = id;
    $("settings").hidden = true;
    closeLaunch();
    $("details").hidden = false;
    if (changed) {
      state.ended = null;
      state.where = null;
      resetConvo();
      if (selectedSessionId()) loadWhere();
      renderWhere();
    }
    renderDetails();
  }

  function closeDetails() {
    state.selected = null;
    state.ended = null;
    $("details").hidden = true;
    $("details").classList.remove("wide");
  }

  function selectedSessionId() {
    return state.selected && state.selected.startsWith("s:") ? state.selected.slice(2) : null;
  }

  function pill(text, color) {
    return '<span class="pill" style="--c:' + (color || "var(--text)") + '">' + esc(text) + "</span>";
  }

  function localTime(value) {
    if (!value) return "";
    const d = new Date(typeof value === "number" ? value * 1000 : value);
    return isNaN(d) ? "" : d.toLocaleString();
  }

  function bytesText(n) {
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(n < 10240 ? 1 : 0) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }

  function kv(rows) {
    return '<dl class="kv">' + rows.filter((r) => r[1] !== "" && r[1] != null).map((r) => "<dt>" + esc(r[0]) + "</dt><dd>" + r[1] + "</dd>").join("") + "</dl>";
  }

  function actionsList(actions) {
    if (!actions || !actions.length) return '<p class="muted small">No actions in the recent part of the transcript.</p>';
    return '<ul class="list">' + actions.slice().reverse().map((x) => "<li>" + esc(x.text) + "</li>").join("") + "</ul>";
  }

  function tokenRows(tk) {
    if (!tk || !tk.turns) return [["Tokens", '<span class="muted">no replies in the recent transcript</span>']];
    return [
      ["Average context", esc(tokens(tk.avg_context))],
      ["Latest context", esc(tokens(tk.last_context))],
      ["Average output", esc(tokens(tk.avg_output))],
      ["Replies counted", esc(tk.turns) + ' <span class="muted small">(last 64 KB)</span>'],
    ];
  }

  function renderDetails() {
    const a = state.actors.get(state.selected);
    const sessionId = selectedSessionId();
    $("details-extra").hidden = !sessionId || !!(a && a.info.sample);
    if (!a) return sessionId ? renderEnded(sessionId) : closeDetails();
    const i = a.info;
    let title;
    let html = "";

    if (a.kind === "session") {
      title = nameOf(i);
      const color = FAMILY_COLORS[i.family];
      html += kv([
        ["Status", pill(i.busy ? "busy" : "idle", i.busy ? "var(--good)" : "var(--muted)")],
        ["Model", i.model ? pill(i.model, color) : '<span class="muted">not seen yet</span>'],
        ["Effort", i.effort ? esc(i.effort) : '<span class="muted">not recorded</span>'],
        ["Doing", esc(i.action)],
        ["Folder", esc(i.cwd)],
        ["Kind", esc(i.background ? "background (headless)" : i.kind)],
      ].concat(tokenRows(i.tokens)));
      const helpers = [...state.actors.values()].filter((h) => h.kind === "helper" && h.info.parent === i.id);
      if (helpers.length) {
        html += "<h4>Helpers</h4><ul class=\"list\">" + helpers.map((h) => '<li><button class="link" data-open="' + esc(h.id) + '">' + esc(h.info.type) + "</button> " + esc(h.info.task) + " · " + esc(h.info.state) + "</li>").join("") + "</ul>";
      }
      const tasks = [];
      for (const c of (state.data && state.data.crews) || []) for (const t of c.tasks || []) if (t.owner === i.name) tasks.push(t);
      if (tasks.length) html += "<h4>Crew tasks</h4><ul class=\"list\">" + tasks.map((t) => "<li>" + esc(t.title) + " · " + esc(t.status) + "</li>").join("") + "</ul>";
      const files = state.claims.get(i.name) || [];
      if (files.length) html += "<h4>Claimed files</h4><ul class=\"list\">" + files.map((f) => "<li>" + esc(f) + "</li>").join("") + "</ul>";
      html += "<h4>Recent actions</h4>" + actionsList(i.actions);
    } else if (a.kind === "helper") {
      title = i.type + " helper";
      html += kv([
        ["Task", esc(i.task)],
        ["State", pill(i.state, i.state === "working" ? "var(--good)" : "var(--muted)")],
        ["Commander", '<button class="link" data-open="s:' + esc(i.parent) + '">' + esc(i.parent_name) + "</button>"],
        ["Model", i.model ? pill(i.model, FAMILY_COLORS[i.family]) : ""],
        ["Effort", i.effort ? esc(i.effort) : '<span class="muted">not recorded</span>'],
        ["Doing", esc(i.action)],
        ["Last write", esc(i.idle_seconds) + " s ago"],
      ].concat(tokenRows(i.tokens)));
      html += "<h4>Recent actions</h4>" + actionsList(i.actions);
    } else {
      title = i.short || i.name;
      html += kv([
        ["Model", esc(i.name)],
        ["Process", esc(i.pid)],
        ["CPU", i.cpu == null ? '<span class="muted">measuring…</span>' : esc(i.cpu) + "% of one core"],
        ["Share", i.share == null ? "" : esc(i.share) + "% of all cores"],
        ["Memory", i.rss_mb == null ? "" : esc(i.rss_mb) + " MB"],
      ]);
      html += '<p class="muted small">Read from process information only. The Crew Room never talks to Jan.</p>';
    }
    if (i.sample) html += '<p class="muted small">This is sample data from the "Add a sample crew" setting.</p>';
    $("details-title").textContent = title;
    $("details-body").innerHTML = html;
  }

  // A session with no character: it ended, or it was opened from the task list
  // before reaching the room.
  function renderEnded(sessionId) {
    const i = state.ended || {};
    const w = state.where || {};
    $("details-title").textContent = i.label || i.name || w.name || "Session " + sessionId.slice(0, 8);
    let status = '<span class="muted">looking…</span>';
    if (w.alive) status = pill("running", "var(--good)");
    else if (state.where) status = pill("ended", "var(--muted)");
    let html = kv([
      ["Status", status],
      ["Model", i.model ? pill(i.model, FAMILY_COLORS[i.family]) : ""],
    ]);
    if (w.alive) html += '<p class="muted small">It has not reached the room yet.</p>';
    $("details-body").innerHTML = html;
  }

  // --- where it runs ---------------------------------------------------------------

  async function loadWhere() {
    const id = selectedSessionId();
    if (!id) return;
    let data;
    try {
      const res = await fetch("/api/sessions/" + encodeURIComponent(id) + "/where", { cache: "no-store" });
      if (res.ok) data = await res.json();
      else data = { error: res.status === 404 ? "Nothing is recorded about this session yet." : "Could not read where it runs (" + res.status + ")." };
    } catch (err) {
      data = { error: "Could not read where it runs: " + err.message };
    }
    if (selectedSessionId() !== id) return;
    state.where = data;
    renderWhere();
    if (!state.actors.has(state.selected)) renderDetails();
  }

  function renderWhere() {
    const w = state.where;
    const el = $("where-body");
    if (!w || w.error) {
      el.innerHTML = '<p class="muted small">' + esc(w ? w.error : "Looking…") + "</p>";
      return;
    }
    let terminal = "";
    if (w.tty) terminal = "<code>" + esc(w.tty) + "</code>" + (w.terminal ? " in " + esc(w.terminal) : "");
    else if (w.background) terminal = '<span class="muted">none, it runs in the background</span>' + (w.terminal ? " · " + esc(w.terminal) : "");
    else if (!w.alive) terminal = '<span class="muted">none, it has ended</span>';
    else terminal = esc(w.terminal || "");
    let html = kv([
      ["Folder", w.folder ? "<code>" + esc(w.folder) + "</code>" : ""],
      ["Terminal", terminal],
      ["Name", w.name ? esc(w.name) : ""],
      ["Started", esc(localTime(w.started_at))],
      ["Process", w.pid ? esc(w.pid) : ""],
      ["Task", w.task ? esc(w.task.prompt) : ""],
    ]);
    if (w.alive && w.tty) html += '<p class="muted small">GNOME cannot bring one terminal tab forward from another app, so look for the tab with this name or folder.</p>';
    if (w.resume) {
      html += '<div class="set-row">Open it again<div class="copy-row"><input id="resume-cmd" type="text" readonly value="' + esc(w.resume) + '"><button class="btn" type="button" data-copy="resume-cmd">Copy</button></div></div>';
    }
    el.innerHTML = html;
  }

  async function copyField(input, button) {
    input.select();
    let ok;
    try {
      await navigator.clipboard.writeText(input.value);
      ok = true;
    } catch (err) {
      ok = document.execCommand("copy");
    }
    button.textContent = ok ? "Copied" : "Select and copy";
    setTimeout(() => (button.textContent = "Copy"), 1500);
  }

  // --- conversation ------------------------------------------------------------------

  function resetConvo() {
    state.convo = { open: false, items: [], before: null, more: false, loading: false };
    $("convo").hidden = true;
    $("convo-list").innerHTML = "";
    $("convo-note").textContent = "";
    $("toggle-convo").textContent = "Read the conversation";
    $("details").classList.remove("wide");
  }

  function toggleConvo() {
    const c = state.convo;
    c.open = !c.open;
    $("convo").hidden = !c.open;
    $("details").classList.toggle("wide", c.open);
    $("toggle-convo").textContent = c.open ? "Hide the conversation" : "Read the conversation";
    if (c.open && !c.items.length) loadConvo(false);
  }

  // Pages come from the end of the transcript backwards; a page can hold only
  // hidden entries, so keep reading a few more until something shows.
  async function loadConvo(older) {
    const id = selectedSessionId();
    const c = state.convo;
    if (!id || c.loading) return;
    c.loading = true;
    $("convo-note").textContent = "Loading…";
    try {
      let items = [];
      let before = older ? c.before : null;
      let page;
      for (let tries = 0; tries < 8; tries++) {
        const q = before != null ? "?before=" + before : "";
        const res = await fetch("/api/sessions/" + encodeURIComponent(id) + "/conversation" + q, { cache: "no-store" });
        if (!res.ok) throw new Error(res.status === 404 ? "no transcript found for this session" : "the server answered " + res.status);
        page = await res.json();
        items = page.items.concat(items);
        before = page.before;
        if (items.length || !page.more) break;
      }
      if (selectedSessionId() !== id || state.convo !== c) return;
      const panel = $("details");
      const fromBottom = panel.scrollHeight - panel.scrollTop;
      c.items = older ? items.concat(c.items) : items;
      c.before = page.before;
      c.more = page.more;
      renderConvo();
      panel.scrollTop = older ? panel.scrollHeight - fromBottom : panel.scrollHeight;
      $("convo-note").textContent = "Transcript " + bytesText(page.size) + (c.more ? " · newest " + bytesText(page.size - c.before) + " shown" : " · all shown");
    } catch (err) {
      $("convo-note").textContent = "Could not read the conversation: " + err.message;
    } finally {
      c.loading = false;
    }
  }

  function convoItem(x, tools) {
    const at = x.at ? ' title="' + esc(localTime(x.at)) + '"' : "";
    if (x.kind === "prompt" || x.kind === "reply") {
      const who = x.kind === "prompt" ? "Prompt" : "Claude";
      return '<li class="c-' + x.kind + '"' + at + '><div class="who">' + who + '</div><div class="txt">' + esc(x.text) + (x.truncated ? '<span class="muted"> … (shortened)</span>' : "") + "</div></li>";
    }
    if (x.kind === "tool") return '<li class="c-tool"' + at + ">" + esc(x.text) + (x.detail ? " <code>" + esc(x.detail) + "</code>" : "") + "</li>";
    if (x.kind === "result") {
      const of = tools.get(x.tool_use_id);
      let label = "result" + (of ? " of " + esc(of) : "") + " · " + bytesText(x.bytes);
      if (x.images) label += " · " + x.images + " image" + (x.images === 1 ? "" : "s");
      if (x.error) label += ' · <span class="bad">error</span>';
      if (x.text == null) return '<li class="c-result">' + label + " · too large to show</li>";
      if (!x.text) return '<li class="c-result">' + label + "</li>";
      return '<li class="c-result"><details><summary>' + label + "</summary><pre>" + esc(x.text) + "</pre></details></li>";
    }
    if (x.kind === "image") return '<li class="c-result"' + at + ">image · " + bytesText(x.bytes) + "</li>";
    return '<li class="c-result">a very large entry · ' + bytesText(x.bytes) + ", not shown</li>";
  }

  function renderConvo() {
    const c = state.convo;
    const tools = new Map();
    for (const x of c.items) if (x.kind === "tool") tools.set(x.id, x.text);
    $("convo-list").innerHTML = c.items.length ? c.items.map((x) => convoItem(x, tools)).join("") : '<li class="c-result">Nothing to show yet.</li>';
    $("convo-older").hidden = !c.more;
  }

  // --- starting sessions ---------------------------------------------------------------

  async function openLaunch() {
    $("settings").hidden = true;
    $("open-settings").setAttribute("aria-expanded", "false");
    closeDetails();
    $("launch").hidden = false;
    $("open-launch").setAttribute("aria-expanded", "true");
    loadTasks();
    try {
      const res = await fetch("/api/launch/options", { cache: "no-store" });
      if (!res.ok) throw new Error("the server answered " + res.status);
      fillLaunch(await res.json());
    } catch (err) {
      launchMessage("Could not read the folders and models: " + err.message, true);
    }
  }

  function closeLaunch() {
    $("launch").hidden = true;
    $("open-launch").setAttribute("aria-expanded", "false");
  }

  function fillLaunch(opts) {
    const home = opts.home || "";
    const nice = (f) => (home && f.startsWith(home) ? "~" + f.slice(home.length) : f);
    const group = (label, list) => (list.length ? '<optgroup label="' + esc(label) + '">' + list.map((o) => '<option value="' + esc(o.folder) + '">' + esc(o.label) + "</option>").join("") + "</optgroup>" : "");
    $("launch-pick").innerHTML =
      '<option value="">Pick a folder…</option>' +
      group("Recent session folders", opts.recent.map((f) => ({ folder: f, label: nice(f) }))) +
      group("Forge apps", opts.apps.map((a) => ({ folder: a.folder, label: a.label + " · " + nice(a.folder) })));
    const folder = $("launch-folder");
    if (!folder.value) folder.value = S.launchFolder || opts.recent[0] || home;
    const model = $("task-model");
    model.innerHTML = opts.models.map((m) => '<option value="' + esc(m.id) + '">' + esc(m.label) + "</option>").join("");
    model.value = opts.models.some((m) => m.id === S.taskModel) ? S.taskModel : "";
    $("terminal-name").textContent = opts.terminal || "a terminal (none supported was found)";
    $("launch-terminal").disabled = !opts.terminal || !opts.claude;
    $("launch-task").disabled = !opts.claude;
    if (!opts.claude) launchMessage("Claude Code (the claude command) was not found.", true);
  }

  function launchMessage(text, bad) {
    const el = $("launch-msg");
    el.textContent = text || "";
    el.classList.toggle("bad", !!bad);
  }

  async function postJson(url, body) {
    const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : "the server answered " + res.status);
    return data;
  }

  function rememberLaunch() {
    S.launchFolder = $("launch-folder").value.trim();
    S.taskModel = $("task-model").value;
    saveSettings();
  }

  async function launchTerminal() {
    const button = $("launch-terminal");
    if (button.disabled) return; // a double click opens one terminal, not two
    rememberLaunch();
    button.disabled = true;
    launchMessage("Opening a terminal…");
    try {
      const r = await postJson("/api/launch/terminal", { folder: S.launchFolder });
      launchMessage("Opened " + r.terminal + " in " + r.folder + ". Its character walks in once claude starts.");
    } catch (err) {
      launchMessage(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  // files and pictures for the task: paste, drop or Attach (Relay task 118);
  // the prompt names their paths and the session opens them
  const taskFiles = [];
  function drawTaskFiles() {
    $("task-files").replaceChildren(...taskFiles.map((f, i) => {
      const chip = document.createElement("span");
      chip.className = "task-file";
      chip.textContent = f.name;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.title = "Remove";
      x.addEventListener("click", () => { taskFiles.splice(i, 1); drawTaskFiles(); });
      chip.append(x);
      return chip;
    }));
  }
  let attach = null;
  function wireAttach() {
    if (!window.ForgeAttach) return;
    attach = ForgeAttach.wire({
      box: $("task-prompt"),
      picker: $("task-file"),
      upload: async (file) => postJson("/api/attach", { name: file.name || "pasted.png", data: await ForgeAttach.readBase64(file) }),
      pasteDesktop: () => postJson("/api/attach/paste-image", {}),
      onAdd: (saved) => { taskFiles.push(saved); drawTaskFiles(); },
      onError: (msg) => launchMessage(msg, true),
    });
  }

  async function launchTask() {
    const button = $("launch-task");
    if (button.disabled) return;
    if (attach && attach.busy()) { launchMessage("A file is still uploading; send again in a moment", true); return; }
    // a file that lands while the task starts stays for the next one
    const sent = taskFiles.slice();
    rememberLaunch();
    button.disabled = true;
    launchMessage("Starting…");
    try {
      await postJson("/api/launch/task", { prompt: $("task-prompt").value, folder: S.launchFolder, model: S.taskModel, files: sent.map((f) => f.path) });
      $("task-prompt").value = "";
      taskFiles.splice(0, taskFiles.length, ...taskFiles.filter((f) => !sent.includes(f)));
      drawTaskFiles();
      launchMessage("Started. It shows up in the room while it runs.");
      loadTasks();
    } catch (err) {
      launchMessage(err.message, true);
    } finally {
      button.disabled = false;
    }
  }

  async function loadTasks() {
    try {
      const res = await fetch("/api/tasks", { cache: "no-store" });
      if (!res.ok) throw new Error("the server answered " + res.status);
      renderTasks((await res.json()).tasks || []);
    } catch (err) {
      $("task-list").innerHTML = '<li class="muted">Could not read the tasks: ' + esc(err.message) + "</li>";
      state.tasksKey = "";
    }
  }

  function renderTasks(tasks) {
    let html = '<li class="muted small">None yet.</li>';
    if (tasks.length) {
      html = tasks
        .map((t) => {
          const prompt = t.prompt.length > 90 ? t.prompt.slice(0, 89) + "…" : t.prompt;
          const bits = [t.model || "default model", t.folder ? t.folder.split("/").pop() || t.folder : "", localTime(t.started_at)].filter(Boolean).map(esc).join(" · ");
          let out = "";
          if (t.result) out = '<div class="small">' + esc(t.result) + "</div>";
          else if (t.error) out = '<div class="small bad">' + esc(t.error) + "</div>";
          return "<li>" + pill(t.status, TASK_COLORS[t.status]) + ' <button class="link" type="button" data-session="' + esc(t.id) + '">' + esc(prompt) + '</button><div class="muted small">' + bits + "</div>" + out + "</li>";
        })
        .join("");
    }
    if (html !== state.tasksKey) {
      $("task-list").innerHTML = html;
      state.tasksKey = html;
    }
  }

  // --- UI wiring -----------------------------------------------------------------

  function renderTabs() {
    const tabs = $("tabs");
    tabs.innerHTML = "";
    const select = $("set-room");
    select.innerHTML = "";
    for (const room of state.rooms) {
      const b = document.createElement("button");
      b.type = "button";
      b.textContent = room.label;
      b.classList.toggle("on", state.room && room.id === state.room.id);
      b.addEventListener("click", () => switchRoom(room.id));
      tabs.append(b);
      const o = document.createElement("option");
      o.value = room.id;
      o.textContent = room.label;
      select.append(o);
    }
    if (state.room) select.value = state.room.id;
  }

  async function switchRoom(id) {
    S.room = id;
    saveSettings();
    try {
      await loadRoom(id);
    } catch (err) {
      showStatus(err.message);
    }
  }

  function resize() {
    const r = state.room;
    if (!r) return;
    const stage = $("stage");
    const w = r.w * T;
    const h = r.h * T;
    const fit = Math.max(1, Math.floor(Math.min((stage.clientWidth - 16) / w, (stage.clientHeight - 16) / h)));
    const k = S.scale > 0 ? S.scale : fit;
    state.scale = k;
    const dpr = window.devicePixelRatio || 1;
    canvas.style.width = w * k + "px";
    canvas.style.height = h * k + "px";
    canvas.width = Math.round(w * k * dpr);
    canvas.height = Math.round(h * k * dpr);
    $("frame").style.width = w * k + "px";
    $("frame").style.height = h * k + "px";
    renderBoard(true);
  }

  function pairInputs(rangeId, numberId, key, after) {
    const range = $(rangeId);
    const number = $(numberId);
    range.value = number.value = S[key];
    const set = (v) => {
      const n = Math.max(Number(range.min), Math.min(Number(range.max), Math.round(Number(v) || 0)));
      S[key] = n;
      range.value = number.value = n;
      saveSettings();
      if (after) after();
    };
    range.addEventListener("input", () => set(range.value));
    number.addEventListener("change", () => set(number.value));
  }

  function showMode(mode) {
    S.mode = mode;
    saveSettings();
    for (const b of document.querySelectorAll(".mode-tabs button")) b.classList.toggle("on", b.dataset.mode === mode);
    for (const g of document.querySelectorAll(".set-group")) g.hidden = !(g.dataset.group === "simple" || mode === "advanced");
  }

  function bindUI() {
    $("open-settings").addEventListener("click", () => {
      const panel = $("settings");
      panel.hidden = !panel.hidden;
      $("open-settings").setAttribute("aria-expanded", String(!panel.hidden));
      if (!panel.hidden) {
        $("details").hidden = true;
        closeLaunch();
      }
    });
    resetConvo();
    $("open-launch").addEventListener("click", () => ($("launch").hidden ? openLaunch() : closeLaunch()));
    $("close-launch").addEventListener("click", closeLaunch);
    $("launch-pick").addEventListener("change", (e) => {
      if (e.target.value) $("launch-folder").value = e.target.value;
    });
    $("launch-terminal").addEventListener("click", launchTerminal);
    $("launch-task").addEventListener("click", launchTask);
    wireAttach();
    $("task-list").addEventListener("click", (e) => {
      const b = e.target.closest("[data-session]");
      if (b) openDetails("s:" + b.dataset.session);
    });
    $("toggle-convo").addEventListener("click", toggleConvo);
    $("convo-older").addEventListener("click", () => loadConvo(true));
    $("convo-newest").addEventListener("click", () => loadConvo(false));
    $("where-body").addEventListener("click", (e) => {
      const b = e.target.closest("[data-copy]");
      if (b) copyField($(b.dataset.copy), b);
    });
    $("close-settings").addEventListener("click", () => {
      $("settings").hidden = true;
      $("open-settings").setAttribute("aria-expanded", "false");
    });
    $("close-details").addEventListener("click", closeDetails);
    for (const b of document.querySelectorAll(".mode-tabs button")) b.addEventListener("click", () => showMode(b.dataset.mode));
    showMode(S.mode);

    $("set-room").addEventListener("change", (e) => switchRoom(e.target.value));
    const check = (id, key, after) => {
      const input = $(id);
      input.checked = !!S[key];
      input.addEventListener("change", () => {
        S[key] = input.checked;
        saveSettings();
        if (after) after();
      });
    };
    check("set-reduced", "reducedMotion");
    check("set-tags", "tags");
    check("set-helper-tags", "helperTags");
    // dragging the slider restarts the poll once, when it settles
    const repoll = () => {
      clearTimeout(state.pollRestart);
      state.pollRestart = setTimeout(() => startPoll(true), 300);
    };
    check("set-demo", "demo", repoll);
    pairInputs("set-poll", "set-poll-n", "poll", repoll);
    pairInputs("set-scale", "set-scale-n", "scale", resize);

    const bubbles = $("set-bubbles");
    bubbles.value = S.bubbles;
    bubbles.addEventListener("change", () => {
      S.bubbles = bubbles.value;
      saveSettings();
    });
    const palette = $("set-palette");
    for (const id of Object.keys(state.lib.palettes)) {
      const o = document.createElement("option");
      o.value = id;
      o.textContent = state.lib.palettes[id].label || id;
      palette.append(o);
    }
    palette.value = state.atlas.paletteId;
    palette.addEventListener("change", () => {
      S.palette = palette.value;
      S.paletteChosen = true;
      saveSettings();
      state.atlas.rebake(palette.value);
    });
    $("rooms-path").textContent = (state.lib.root || "~/ForgeArtData") + "/packs/crewroom/rooms/";

    canvas.addEventListener("click", (e) => {
      const rect = canvas.getBoundingClientRect();
      const px = (e.clientX - rect.left) / state.scale;
      const py = (e.clientY - rect.top) / state.scale;
      const hits = [...state.actors.values()].filter((a) => a.box && px >= a.box.x && px < a.box.x + a.box.w && py >= a.box.y && py < a.box.y + a.box.h);
      hits.sort((p, q) => q.y - p.y);
      if (hits.length) openDetails(hits[0].id);
      else closeDetails();
    });
    overlay.addEventListener("click", (e) => {
      const tag = e.target.closest(".tag");
      if (tag) openDetails(tag.dataset.id);
    });
    $("details-body").addEventListener("click", (e) => {
      const link = e.target.closest("[data-open]");
      if (link && state.actors.has(link.dataset.open)) openDetails(link.dataset.open);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") {
        closeDetails();
        closeLaunch();
        $("settings").hidden = true;
      }
    });
    window.addEventListener("resize", resize);
  }

  /* The room poll (shared/forge_idle.js) rests out of sight (hidden window,
     or another app in front in Forge) and runs at once when shown again.
     While the backend does not answer it slows down, doubling up to 30 s,
     and picks up by itself when the backend is back. */
  async function pollOnce() {
    const ctl = new AbortController();
    const timer = setTimeout(() => ctl.abort(), 15000);
    try {
      const res = await fetch("/api/room", { cache: "no-store", signal: ctl.signal });
      if (!res.ok) throw new Error("the room data answered " + res.status);
      sync(await res.json());
      showStatus("");
      if (!$("launch").hidden) loadTasks();
    } catch (err) {
      const down = err instanceof TypeError || err.name === "AbortError";
      showStatus(down ? "Lost the Crew Room backend, retrying by itself…" : "Could not read the room data: " + err.message);
      return false;
    } finally {
      clearTimeout(timer);
    }
  }

  function startPoll(now) {
    if (state.poller) state.poller.stop();
    state.poller = ForgeIdle.poll(pollOnce, Math.max(1, S.poll) * 1000, { backoff: 2, maxMs: 30000 });
    if (now) state.poller.now();
  }

  // Resolves once the room can be seen (boot retries wait for that).
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
      check();
    });
  }

  // ForgeIdle.loop calls this each frame while the room can be seen.
  function frame(now) {
    if (!state.room || !state.data) return;
    const elapsed = now - state.lastFrame;
    if (elapsed < FRAME_MS) return;
    const dt = Math.min(0.1, elapsed / 1000);
    state.lastFrame = now;
    maybeChat(now);
    for (const a of [...state.actors.values()]) step(a, dt, now);
    draw(now, dt);
    layoutOverlay(now);
  }

  async function boot(wait) {
    showStatus("Setting up the room…");
    try {
      state.lib = await window.ForgeArt.load("/api/art/library");
      const palettes = Object.keys(state.lib.palettes);
      if (!palettes.length) throw new Error("the crewroom palette is missing from the art library");
      state.atlas = window.ForgeArt.atlas(state.lib, state.lib.palettes[S.palette] ? S.palette : palettes[0]);
      const listed = await (await fetch("/api/rooms", { signal: AbortSignal.timeout(15000) })).json();
      state.rooms = listed.rooms || [];
      if (!state.rooms.length) throw new Error("no rooms found in the art library");
      if (!state.rooms.some((r) => r.id === S.room)) S.room = state.rooms[0].id;
      await loadRoom(S.room);
      if (!state.bound) {
        bindUI();
        state.bound = true;
      }
      await pollOnce();
      startPoll(false);
      // Links can open a panel directly: ?panel=settings, ?panel=launch or
      // ?select=<actor id> (s:<sessionId>, h:<agentId>, j:<model id>), with
      // &conversation to open a session's conversation too. A session id works
      // after the session has ended.
      const params = new URLSearchParams(location.search);
      if (params.get("panel") === "settings") $("open-settings").click();
      if (params.get("panel") === "launch") openLaunch();
      if (params.get("mode") === "advanced" || params.get("mode") === "simple") showMode(params.get("mode"));
      const select = params.get("select");
      if (select && (state.actors.has(select) || select.startsWith("s:"))) {
        openDetails(select);
        if (params.has("conversation") && selectedSessionId()) toggleConvo();
      }
      ForgeIdle.loop(frame);
    } catch (err) {
      // the backend may be starting or gone for a moment: try again, slower
      // each time (1.5 s doubling to 30 s), and not while out of sight
      const ms = wait || 1500;
      const why = err instanceof TypeError ? "Can't reach the Crew Room backend" : err.message;
      showStatus(why + ", trying again in " + Math.round(ms / 1000) + " s…");
      await new Promise((go) => setTimeout(go, ms));
      await whenShown();
      boot(Math.min(ms * 2, 30000));
    }
  }

  boot();
})();
