// 3D worlds: a player for world models that build the place as you move.
//
// How a world session works (src/worlds/, src/app.py):
//   POST /api/worlds/{model}/start  {prompt, start_image | start_image_url}
//   POST /api/worlds/sessions/{sid}/step  {actions: ["forward", ...]}  queues moves
//   GET  /api/worlds/sessions/{sid}?since=N  state + the frame names after N
//   GET  /api/worlds/sessions/{sid}/frames/{name}  one picture
//   POST /api/worlds/sessions/{sid}/stop, POST .../clip -> {url}
// Every reply to start/step/stop is the same poll payload:
//   {id, state: starting|working|waiting|stopped|done|failed, message,
//    frame_count, frames: [names], fps, queued_steps}   (docs/WORLDS.md)
// One press is one move; moves are sent one request at a time (presses made
// meanwhile go together in the next one) and queue on the server while it
// draws. Pictures play back at the world's own pace, and everything rests
// while AI Studio is hidden.
"use strict";
(function (AS) {
  const $ = AS.$, el = AS.el;
  const enc = encodeURIComponent;
  const FINAL = new Set(["stopped", "done", "failed"]);
  const WORLD_API = {
    // the move names: GET /api/worlds/actions, or the "actions" of GET /api/worlds
    labels: async () => {
      try { return await AS.get("/api/worlds/actions"); } catch (e) { return (await AS.get("/api/worlds")).actions; }
    },
    start: (modelId, body) => AS.post(`/api/worlds/${enc(modelId)}/start`, body, "The world didn't start"),
    step: (sid, actions) => AS.post(`/api/worlds/sessions/${enc(sid)}/step`, { actions }, "The world didn't take the move"),
    poll: (sid, since) => AS.get(`/api/worlds/sessions/${enc(sid)}?since=${since}`, "The world didn't answer"),
    stop: (sid) => AS.post(`/api/worlds/sessions/${enc(sid)}/stop`, undefined, "The world didn't stop"),
    clip: (sid) => AS.post(`/api/worlds/sessions/${enc(sid)}/clip`, undefined, "The video couldn't be made"),
    frame: (sid, name) => `/api/worlds/sessions/${enc(sid)}/frames/${enc(name)}`,
    stopUrl: (sid) => `/api/worlds/sessions/${enc(sid)}/stop`,
  };
  // keyboard -> move; the labels come from the server when it has them
  const KEYS = {
    w: "forward", s: "back", a: "left", d: "right", r: "rise", f: "sink",
    arrowleft: "turn_left", arrowright: "turn_right", arrowup: "look_up", arrowdown: "look_down",
  };
  const LABELS = {
    forward: "Walk forward", back: "Walk back", left: "Step left", right: "Step right",
    rise: "Go up", sink: "Go down", turn_left: "Turn left", turn_right: "Turn right",
    look_up: "Look up", look_down: "Look down", stay: "Stay and look",
  };
  const PAD = [
    ["Walk", [["forward", "k-up"], ["left", "k-left"], ["back", "k-down"], ["right", "k-right"]]],
    ["Turn and look", [["look_up", "k-up"], ["turn_left", "k-left"], ["look_down", "k-down"], ["turn_right", "k-right"]]],
    ["Up and down", [["rise", "k-up"], ["stay", "k-left"], ["sink", "k-down"]]],
  ];

  const form = $("worldForm"), view = $("worldView"), frameImg = $("worldFrame");
  const note = $("worldNote"), status = $("worldStatus");
  const startBtn = $("worldStart"), stopBtn = $("worldStop"), clipBtn = $("worldClip"), clipLink = $("worldClipLink");
  const errorEl = form.querySelector(".error");
  const picker = AS.picker($("worldPicker"));

  let s = null; // the running session
  let poller = null, player = null;
  const held = new Set(); // moves whose key or button is down
  let pending = []; // moves waiting to be sent
  let sending = false;

  // ---- the pad ----
  function paintPad() {
    $("worldPad").replaceChildren(...PAD.map(([title, keys]) => el("div", { className: "pad-group" + (keys.length === 3 ? " column" : "") },
      el("span", { className: "pad-label" }, title),
      el("div", { className: "pad-grid" }, keys.map(([act, cls]) => {
        const b = el("button", { type: "button", className: cls, dataset: { act }, title: LABELS[act] }, LABELS[act]);
        b.addEventListener("pointerdown", (e) => { e.preventDefault(); b.setPointerCapture(e.pointerId); press(act); });
        const up = () => release(act);
        b.addEventListener("pointerup", up);
        b.addEventListener("pointercancel", up);
        b.addEventListener("lostpointercapture", up);
        return b;
      })),
    )));
    paintHeld();
  }
  function paintHeld() {
    document.querySelectorAll("#worldPad button[data-act]").forEach((b) => {
      b.classList.toggle("held", held.has(b.dataset.act));
      b.disabled = !s || FINAL.has(s.state);
    });
  }
  paintPad();
  // labels from the server, once
  WORLD_API.labels().then((labels) => {
    if (labels && typeof labels === "object") { Object.assign(LABELS, labels); paintPad(); }
  }).catch(() => {});

  // ---- status line ----
  function paintStatus() {
    if (!s) { status.textContent = "Not running"; return; }
    const words = {
      starting: "Getting the world ready", working: "Drawing the next part", running: "Drawing the next part",
      waiting: "Ready for your next move", stopped: "Stopped", done: "Finished", failed: "Stopped",
    }[s.state] || s.state;
    const parts = [words];
    if (s.shown) parts.push(`${s.shown} pictures so far`);
    if (s.queued > 0 && !FINAL.has(s.state)) parts.push(`${s.queued} move${s.queued === 1 ? "" : "s"} being built`);
    status.textContent = parts.join(" · ");
    clipBtn.disabled = !s.seen;
  }

  // ---- taking a payload ----
  function take(p) {
    if (!s || !p) return;
    if (p.state) s.state = p.state;
    if (Number.isFinite(p.fps) && p.fps > 0) s.fps = p.fps;
    s.queued = Number(p.queued_steps) || 0;
    const since = Number.isFinite(p.since) ? p.since : s.seen;
    (p.frames || []).forEach((name, i) => {
      if (since + i < s.seen) return; // already have it
      s.queue.push(WORLD_API.frame(s.id, name));
      s.seen = since + i + 1;
    });
    if (p.message) note.textContent = p.message;
    else if (s.state === "working" && !s.queue.length) note.textContent = "Drawing the next part. Each move can take a few minutes on this laptop.";
    else if (s.state === "waiting") note.textContent = "";
    if (FINAL.has(s.state)) ended(p.message);
    paintStatus();
    paintHeld();
  }

  // ---- sending moves: one request at a time ----
  function press(act) {
    if (!s || FINAL.has(s.state)) return;
    if (!held.has(act)) { held.add(act); pending.push(act); }
    paintHeld();
    pump();
  }
  function release(act) {
    if (held.delete(act)) paintHeld();
  }
  async function pump() {
    if (sending || !s || FINAL.has(s.state) || !pending.length || !ForgeIdle.shown()) return;
    sending = true;
    const sid = s.id;
    const acts = pending.splice(0, 8);
    try {
      const p = await WORLD_API.step(sid, acts);
      if (s && s.id === sid) take(p);
    } catch (e) {
      if (s && s.id === sid) note.textContent = AS.failText(e);
    } finally {
      sending = false;
    }
    if (pending.length) pump();
  }

  // ---- polling for new pictures ----
  async function pollOnce() {
    if (!s) return;
    const sid = s.id;
    try {
      const p = await WORLD_API.poll(sid, s.seen);
      if (!s || s.id !== sid) return;
      take(p);
    } catch (e) {
      if (!s || s.id !== sid) return;
      if (e.status === 404) { ended("This world has closed."); return; }
      note.textContent = AS.failText(e) + " Trying again by itself...";
      return false; // wait longer before the next try
    }
  }

  // ---- playing the pictures at the world's pace ----
  function play(t) {
    if (!s) return false;
    const every = 1000 / Math.max(1, s.fps || 16);
    if (s.queue.length && t - s.lastShown >= every) {
      const url = s.queue.shift();
      frameImg.src = url;
      frameImg.hidden = false;
      s.shown += 1;
      s.lastShown = t;
      // warm the next few so playback does not stutter
      s.queue.slice(0, 3).forEach((u) => { const i = new Image(); i.src = u; });
      if (s.shown % 8 === 0) paintStatus();
    }
    return true;
  }

  function begin(p) {
    const id = p.id || p.session_id;
    if (!id) throw new Error("The world started without a session to talk to.");
    s = { id, state: "starting", fps: 16, seen: 0, queue: [], shown: 0, lastShown: 0, queued: 0 };
    take(p);
    startBtn.hidden = true;
    stopBtn.hidden = false;
    clipLink.hidden = true;
    form.parentElement.classList.add("live");
    AS.heavy.set("world", "A 3D world is running. Stop it first.", form);
    // every 1.5 s, as docs/WORLDS.md asks; a failing server waits longer
    poller = ForgeIdle.poll(pollOnce, 1500, { backoff: 2, maxMs: 15000 });
    player = ForgeIdle.loop(play);
    view.focus();
  }

  function ended(message) {
    if (poller) { poller.stop(); poller = null; }
    form.parentElement.classList.remove("live");
    AS.heavy.set("world", null);
    held.clear();
    pending = [];
    startBtn.hidden = false;
    startBtn.disabled = false;
    startBtn.textContent = "Start the world";
    stopBtn.hidden = true;
    note.textContent = message || "The world has stopped. Start it again to go somewhere new.";
    paintHeld();
    paintStatus();
    // the player keeps going until the last pictures have shown
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (startBtn.disabled || (s && !FINAL.has(s.state))) return;
    errorEl.textContent = "";
    const wait = AS.heavy.reason(form);
    if (wait) { errorEl.textContent = wait; return; }
    const model = AS.models.active("world");
    if (!model) {
      errorEl.textContent = AS.models.loaded
        ? "There is no 3D world model ready yet. Use the button at the top of this form to get or pick one."
        : "Still checking which models are on this laptop. Try again in a moment.";
      return;
    }
    const prompt = $("worldPrompt").value.trim();
    const v = picker.value;
    if (!prompt && !v) { errorEl.textContent = "Describe the place, or choose a picture to start from."; return; }
    if (player) { player.stop(); player = null; }
    s = null;
    startBtn.disabled = true;
    startBtn.textContent = "Starting...";
    note.textContent = "Starting the world. The first pictures can take a while.";
    try {
      begin(await WORLD_API.start(model.id, { prompt, ...AS.pictureFields(v) }));
    } catch (err) {
      s = null;
      errorEl.textContent = AS.failText(err);
      note.textContent = "Start a world and it is built here as you move.";
      startBtn.disabled = false;
      startBtn.textContent = "Start the world";
      AS.emit("heavy");
    }
    paintHeld();
    paintStatus();
  });

  stopBtn.addEventListener("click", async () => {
    if (!s || stopBtn.disabled) return;
    const sid = s.id;
    stopBtn.disabled = true;
    try { take(await WORLD_API.stop(sid)); } catch (e) { /* it may be gone already */ }
    stopBtn.disabled = false;
    if (s && s.id === sid && !FINAL.has(s.state)) { s.state = "stopped"; ended("Stopped."); }
  });

  clipBtn.addEventListener("click", async () => {
    if (!s || clipBtn.disabled) return;
    clipBtn.disabled = true;
    clipBtn.textContent = "Saving...";
    try {
      const out = await WORLD_API.clip(s.id);
      clipLink.href = out.url;
      clipLink.hidden = false;
      AS.toast("Saved the walk as a video.");
    } catch (e) {
      AS.toast(AS.failText(e));
    } finally {
      clipBtn.textContent = "Save as a video";
      clipBtn.disabled = !s || !s.seen;
    }
  });

  // closing AI Studio stops the world on the server too
  window.addEventListener("pagehide", () => {
    if (s && !FINAL.has(s.state) && navigator.sendBeacon) navigator.sendBeacon(WORLD_API.stopUrl(s.id));
  });

  // ---- keys ----
  const typing = (t) => t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable);
  document.addEventListener("keydown", (e) => {
    const act = KEYS[e.key.toLowerCase()];
    if (!act || !s || $("sec-worlds").hidden || typing(e.target) || e.ctrlKey || e.altKey || e.metaKey) return;
    if (document.querySelector(".overlay:not([hidden]), .forge-dialog-back")) return;
    e.preventDefault();
    press(act);
  });
  document.addEventListener("keyup", (e) => {
    const act = KEYS[e.key.toLowerCase()];
    if (act) release(act);
  });
  const letGo = () => { held.clear(); paintHeld(); };
  window.addEventListener("blur", letGo);
  document.addEventListener("visibilitychange", letGo);
  document.addEventListener("forge-visible", letGo);
  view.addEventListener("focus", () => view.classList.add("listening"));
  view.addEventListener("blur", () => view.classList.remove("listening"));

  // ---- drag on the view: a long enough drag is one turn or look ----
  let drag = null;
  view.addEventListener("pointerdown", (e) => {
    view.focus();
    drag = { x: e.clientX, y: e.clientY };
    view.setPointerCapture(e.pointerId);
    view.classList.add("dragging");
  });
  view.addEventListener("pointermove", (e) => {
    if (!drag || !s) return;
    const r = view.getBoundingClientRect();
    const dx = (e.clientX - drag.x) / Math.max(1, r.width), dy = (e.clientY - drag.y) / Math.max(1, r.height);
    if (Math.abs(dx) >= 0.12) { pending.push(dx > 0 ? "turn_left" : "turn_right"); drag.x = e.clientX; pump(); }
    if (Math.abs(dy) >= 0.15) { pending.push(dy > 0 ? "look_up" : "look_down"); drag.y = e.clientY; pump(); }
  });
  const endDrag = () => { drag = null; view.classList.remove("dragging"); };
  view.addEventListener("pointerup", endDrag);
  view.addEventListener("pointercancel", endDrag);

  $("worldFull").addEventListener("click", () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else if (view.requestFullscreen) view.requestFullscreen().then(() => view.focus()).catch(() => AS.toast("Whole screen isn't allowed here."));
  });

  AS.worlds = { api: WORLD_API, get session() { return s; } };
  paintStatus();
})(window.AS);
