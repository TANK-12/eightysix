/*
 * The Scenery editor -- where a background becomes a living shot.
 *
 * A shot is a background image, a set of marked regions each running a motion
 * effect, some stacked transparent images, and some emitters throwing particles
 * across the frame. This file is the workbench for building one: paint or
 * outline the parts that should move, pick what they do, and watch it.
 *
 * Two speeds of feedback, deliberately:
 *   - moving any control re-renders ONE real frame on the server (~200ms), so
 *     what you are tuning against is the actual renderer, never a lookalike;
 *   - "Preview loop" renders the whole loop and plays it round and round, which
 *     is the only way to judge whether the loop is clean.
 *
 * Nothing here hardcodes an effect, an emitter, a transition or a preset --
 * they all arrive from the backend registries and build their own controls via
 * controls.js. Adding one server-side makes it appear here with no UI change.
 */
(function (global) {
  "use strict";

  const MASK_W = 1024; // working resolution for painted regions
  const el = (t, c, h) => Controls.el(t, c, h);

  const S = {
    slug: null,
    data: null,
    shots: [],
    shotIndex: 0,
    layerIndex: -1,
    effects: [],
    emitters: [],
    transitions: [],
    presets: [],
    assets: [],
    masks: {},          // brush filename -> offscreen canvas
    tool: "brush",
    brushSize: 70,
    wandTolerance: 0.12,
    wandContiguous: true,
    poly: [],           // in-progress polygon, normalised
    showRegions: true,
    t: 0,
    stillUrl: null,
    stillBusy: false,
    stillAgain: false,
    undo: [],            // brush-stroke undo (mask pixels)
    past: [],            // whole-editor undo (the shot list)
    future: [],
    midDrag: false,
    dirtyMasks: new Set(),
  };
  global.SceneryState = S;

  /* ---- undo/redo over the whole shot list --------------------------------
   * The brush has always had its own undo over mask pixels. This is the other
   * half: deleting a region, swapping an effect or dragging a slider are all
   * recoverable, because the shot list is small JSON and cloning it is cheap.
   * A slider drag remembers once, on the first live event, rather than once per
   * pixel of travel. */
  const HISTORY_LIMIT = 60;

  function remember() {
    S.past.push(JSON.stringify(S.shots));
    if (S.past.length > HISTORY_LIMIT) S.past.shift();
    S.future = [];
    updateHistoryButtons();
  }

  async function stepHistory(from, to) {
    if (!from.length) return;
    to.push(JSON.stringify(S.shots));
    S.shots = JSON.parse(from.pop());
    S.shotIndex = Math.min(S.shotIndex, Math.max(0, S.shots.length - 1));
    await saveShots();
    await selectShot(S.shotIndex);
    renderShots();
    updateHistoryButtons();
  }

  const undoEdit = () => stepHistory(S.past, S.future);
  const redoEdit = () => stepHistory(S.future, S.past);

  function updateHistoryButtons() {
    const u = document.getElementById("scUndoEdit");
    const r = document.getElementById("scRedoEdit");
    if (u) u.disabled = !S.past.length;
    if (r) r.disabled = !S.future.length;
  }

  const shot = () => S.shots[S.shotIndex] || null;
  const layer = () => {
    const sh = shot();
    return sh && S.layerIndex >= 0 ? (sh.layers || [])[S.layerIndex] : null;
  };

  // ------------------------------------------------------------------ io ---
  async function jget(u) {
    const r = await fetch(u);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function jpost(u, body) {
    const r = await fetch(u, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }

  async function loadRegistries() {
    const [effects, emitters, transitions, presets, mod, scenes] = await Promise.all([
      jget("/api/motion-effects"),
      jget("/api/emitters"),
      jget("/api/transitions"),
      jget("/api/presets"),
      jget("/api/modulation-sources"),
      jget("/api/scenes"),
    ]);
    Object.assign(S, { effects, emitters, transitions, presets });
    // the camera and look controls are generated from the scene's own schema,
    // so a parameter added server-side turns up here with no UI change
    S.livingParams = (scenes.find((x) => x.id === "living") || {}).params || [];
    Controls.setModulationSources(mod.sources, mod.shapes);
  }

  async function reloadPresets() {
    S.presets = await jget("/api/presets");
    renderInspector();
  }

  async function saveShots() {
    await fetch(`/api/projects/${encodeURIComponent(S.slug)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ shots: S.shots }),
    });
    refreshTimeline();
  }

  // --------------------------------------------------------------- masks ---
  function maskCanvas(name, w, h) {
    let c = S.masks[name];
    if (!c) {
      c = document.createElement("canvas");
      c.width = w || MASK_W;
      c.height = h || Math.round(MASK_W * 9 / 16);
      const g = c.getContext("2d");
      g.fillStyle = "#000";
      g.fillRect(0, 0, c.width, c.height);
      S.masks[name] = c;
    }
    return c;
  }

  function loadMask(name) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => {
        const c = document.createElement("canvas");
        c.width = img.naturalWidth;
        c.height = img.naturalHeight;
        c.getContext("2d").drawImage(img, 0, 0);
        S.masks[name] = c;
        resolve(c);
      };
      img.onerror = () => resolve(null);
      img.src =
        `/api/projects/${encodeURIComponent(S.slug)}/mask-file` +
        `?name=${encodeURIComponent(name)}&_=${Date.now()}`;
    });
  }

  async function flushMasks() {
    for (const name of Array.from(S.dirtyMasks)) {
      const c = S.masks[name];
      if (!c) continue;
      const blob = await new Promise((res) => c.toBlob(res, "image/png"));
      const fd = new FormData();
      fd.append("file", blob, name);
      await fetch(
        `/api/projects/${encodeURIComponent(S.slug)}/mask?name=${encodeURIComponent(name)}`,
        { method: "POST", body: fd }
      );
      S.dirtyMasks.delete(name);
    }
  }

  /** Any region kind rendered into a canvas, so drawing code has one path. */
  function regionToCanvas(region, w, h) {
    const c = document.createElement("canvas");
    c.width = w;
    c.height = h;
    const g = c.getContext("2d");
    if (!region) return c;
    if (region.kind === "brush" && S.masks[region.brush]) {
      g.drawImage(S.masks[region.brush], 0, 0, w, h);
    } else if (region.kind === "polygon") {
      const shapes = region.shapes || (region.points ? [region.points] : []);
      g.fillStyle = "#fff";
      for (const pts of shapes) {
        if (pts.length < 3) continue;
        g.beginPath();
        pts.forEach(([x, y], i) =>
          i ? g.lineTo(x * w, y * h) : g.moveTo(x * w, y * h)
        );
        g.closePath();
        g.fill();
      }
    } else if (region.kind === "all") {
      g.fillStyle = "#fff";
      g.fillRect(0, 0, w, h);
    }
    return c;
  }

  // -------------------------------------------------------------- canvas ---
  let cv, ctx, bgImage = null;

  function fitCanvas() {
    const box = document.getElementById("scCanvasWrap");
    if (!box || !cv) return;
    const w = Math.max(320, box.clientWidth);
    const ratio = bgImage ? bgImage.naturalHeight / bgImage.naturalWidth : 9 / 16;
    cv.width = w;
    cv.height = Math.round(w * ratio);
    paint();
  }

  const LAYER_TINTS = [
    [110, 170, 255], [80, 235, 190], [255, 205, 90],
    [255, 130, 150], [190, 150, 255], [140, 255, 130],
  ];

  function paint() {
    if (!ctx) return;
    const w = cv.width, h = cv.height;
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0b0d13";
    ctx.fillRect(0, 0, w, h);

    if (bgImage) ctx.drawImage(bgImage, 0, 0, w, h);
    else {
      ctx.fillStyle = "#5a6070";
      ctx.font = "14px system-ui";
      ctx.fillText("Add a background image to this shot", 20, 30);
    }

    const sh = shot();
    if (!sh || !S.showRegions) return;

    (sh.layers || []).forEach((lay, i) => {
      const sel = i === S.layerIndex;
      const rc = regionToCanvas(lay.region, w, h);
      const src = rc.getContext("2d").getImageData(0, 0, w, h);
      const out = ctx.createImageData(w, h);
      const [r, g, b] = LAYER_TINTS[i % LAYER_TINTS.length];
      const strength = sel ? 0.5 : 0.2;
      for (let p = 0; p < src.data.length; p += 4) {
        const a = src.data[p] / 255;
        if (a <= 0.01) continue;
        out.data[p] = r;
        out.data[p + 1] = g;
        out.data[p + 2] = b;
        out.data[p + 3] = a * 255 * strength;
      }
      const tmp = document.createElement("canvas");
      tmp.width = w; tmp.height = h;
      tmp.getContext("2d").putImageData(out, 0, 0);
      ctx.drawImage(tmp, 0, 0);
    });

    if (S.poly.length) {
      ctx.strokeStyle = "#ffd166";
      ctx.fillStyle = "rgba(255,209,102,.18)";
      ctx.lineWidth = 2;
      ctx.beginPath();
      S.poly.forEach(([x, y], i) =>
        i ? ctx.lineTo(x * w, y * h) : ctx.moveTo(x * w, y * h)
      );
      if (S.poly.length > 2) ctx.fill();
      ctx.stroke();
      for (const [x, y] of S.poly) {
        ctx.fillStyle = "#ffd166";
        ctx.beginPath();
        ctx.arc(x * w, y * h, 4, 0, 7);
        ctx.fill();
      }
    }
  }

  // -------------------------------------------------------------- brush ----
  let painting = false;

  function pushUndo() {
    const lay = layer();
    if (!lay || lay.region?.kind !== "brush") return;
    const c = S.masks[lay.region.brush];
    if (!c) return;
    const snap = document.createElement("canvas");
    snap.width = c.width; snap.height = c.height;
    snap.getContext("2d").drawImage(c, 0, 0);
    S.undo.push({ name: lay.region.brush, canvas: snap });
    if (S.undo.length > 25) S.undo.shift();
  }

  function strokeAt(ev) {
    const lay = layer();
    if (!lay || lay.region?.kind !== "brush") return;
    const c = maskCanvas(lay.region.brush);
    const g = c.getContext("2d");
    const r = cv.getBoundingClientRect();
    const nx = (ev.clientX - r.left) / r.width;
    const ny = (ev.clientY - r.top) / r.height;
    const rad = (S.brushSize / 2) * (c.width / cv.width) * (cv.width / r.width);

    const grad = g.createRadialGradient(
      nx * c.width, ny * c.height, rad * 0.35,
      nx * c.width, ny * c.height, rad
    );
    const on = S.tool !== "erase";
    grad.addColorStop(0, on ? "rgba(255,255,255,1)" : "rgba(0,0,0,1)");
    grad.addColorStop(1, on ? "rgba(255,255,255,0)" : "rgba(0,0,0,0)");
    g.globalCompositeOperation = on ? "lighter" : "destination-out";
    if (!on) {
      // destination-out needs the alpha to carry the erase, then repaint black
      g.fillStyle = grad;
      g.beginPath();
      g.arc(nx * c.width, ny * c.height, rad, 0, 7);
      g.fill();
      g.globalCompositeOperation = "destination-over";
      g.fillStyle = "#000";
      g.fillRect(0, 0, c.width, c.height);
    } else {
      g.fillStyle = grad;
      g.beginPath();
      g.arc(nx * c.width, ny * c.height, rad, 0, 7);
      g.fill();
    }
    g.globalCompositeOperation = "source-over";
    S.dirtyMasks.add(lay.region.brush);
    paint();
  }

  async function wandAt(ev) {
    const sh = shot();
    if (!sh || !sh.image) return toast("this shot has no background image", "err");
    remember();
    const r = cv.getBoundingClientRect();
    const nx = (ev.clientX - r.left) / r.width;
    const ny = (ev.clientY - r.top) / r.height;
    try {
      const res = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/wand`, {
        image: sh.image, x: nx, y: ny,
        tolerance: S.wandTolerance, contiguous: S.wandContiguous,
      });
      await loadMask(res.region.brush);
      let lay = layer();
      if (!lay) {
        sh.layers = sh.layers || [];
        lay = { name: `region-${sh.layers.length + 1}`, effect: "water", params: {}, depth: 0.1 };
        sh.layers.push(lay);
        S.layerIndex = sh.layers.length - 1;
      }
      lay.region = res.region;
      toast(`selected ${Math.round(res.coverage * 100)}% of the picture`);
      saveShots(); renderInspector(); paint(); requestStill(0);
    } catch (e) {
      toast(String(e).replace(/^Error:\s*/, ""), "err");
    }
  }

  function canvasClick(ev) {
    if (S.tool === "wand") return wandAt(ev);
    if (S.tool !== "polygon") return;
    const r = cv.getBoundingClientRect();
    S.poly.push([(ev.clientX - r.left) / r.width, (ev.clientY - r.top) / r.height]);
    paint();
  }

  function closePolygon() {
    const lay = layer();
    if (!lay || S.poly.length < 3) return;
    lay.region = { kind: "polygon", points: S.poly.slice(), feather: lay.region?.feather ?? 0.03 };
    S.poly = [];
    saveShots();
    paint();
    requestStill();
    renderInspector();
  }

  // --------------------------------------------------------------- still ---
  let stillTimer = null;
  function requestStill(delay) {
    clearTimeout(stillTimer);
    stillTimer = setTimeout(doStill, delay === undefined ? 200 : delay);
  }

  async function doStill() {
    const sh = shot();
    if (!sh || !S.slug) return;
    if (S.stillBusy) { S.stillAgain = true; return; }
    S.stillBusy = true;
    try {
      await flushMasks();
      const r = await fetch(`/api/projects/${encodeURIComponent(S.slug)}/still`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shot: sh, t: S.t, width: 900 }),
      });
      if (r.ok) {
        const blob = await r.blob();
        if (S.stillUrl) URL.revokeObjectURL(S.stillUrl);
        S.stillUrl = URL.createObjectURL(blob);
        await setBackground(S.stillUrl);
      }
    } catch (e) {
      /* the still is a convenience; a failure must not break the editor */
    } finally {
      S.stillBusy = false;
      if (S.stillAgain) { S.stillAgain = false; doStill(); }
    }
  }

  function setBackground(url) {
    return new Promise((resolve) => {
      const img = new Image();
      img.onload = () => { bgImage = img; fitCanvas(); resolve(); };
      img.onerror = () => resolve();
      img.src = url;
    });
  }

  // ------------------------------------------------------------ inspector --
  function renderInspector() {
    const box = document.getElementById("scInspector");
    if (!box) return;
    box.innerHTML = "";
    const sh = shot();
    if (!sh) {
      box.appendChild(el("p", "muted", "Add a shot to get started."));
      return;
    }

    // the order you actually work in: what it is, then how it looks, then the
    // parts that move, then the fine grade
    box.appendChild(backgroundCard(sh));
    box.appendChild(presetCard(sh));
    box.appendChild(describeCard(sh));
    box.appendChild(layersCard(sh));
    box.appendChild(imagesCard(sh));
    box.appendChild(emittersCard(sh));
    box.appendChild(motionCard(sh));
  }

  // Sections are collapsible and remember what you left open. A shot can carry
  // a dozen controls per layer, and an inspector that is one endless column is
  // unusable however good the individual controls are.
  const openSections = new Set(["Background", "Moving regions"]);

  function card(title, action, onAction, count) {
    const c = el("details", "sc-card");
    c.open = openSections.has(title);
    c.addEventListener("toggle", () =>
      c.open ? openSections.add(title) : openSections.delete(title)
    );
    const sum = el("summary", null, `<span>${title}</span>`);
    if (count) sum.appendChild(el("span", "sc-count", count));
    if (action) {
      const b = el("button", "btn btn-sm", action);
      b.onclick = (e) => { e.preventDefault(); e.stopPropagation(); c.open = true; onAction(); };
      sum.appendChild(b);
    }
    c.appendChild(sum);
    const body = el("div", "sc-body");
    c.appendChild(body);
    c.body = body;
    // everything below appends to the body, not the <details> itself
    c.appendChild = body.appendChild.bind(body);
    return c;
  }

  /* Describe a look in words and let the local model pick from the registries.
   * It is only ever choosing from lists the app supplies, and anything it names
   * that does not exist is dropped server-side before it reaches here. */
  function describeCard(sh) {
    const c = card("Describe a look");
    c.appendChild(el("p", "muted sc-desc",
      "Type what you want and the local model picks from the effects, sprites " +
      "and presets that exist. Needs Jan running."));
    const row = el("div", "sc-head");
    const input = el("input");
    input.type = "text";
    input.placeholder = "a rainy neon street at night";
    input.style.flex = "1";
    const go = el("button", "btn btn-sm", "Ask");
    row.appendChild(input);
    row.appendChild(go);
    c.appendChild(row);
    const note = el("div", "muted sc-desc");
    c.appendChild(note);
    const ask = async () => {
      if (!input.value.trim()) return;
      go.disabled = true; note.textContent = "thinking…";
      remember();
      try {
        const res = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/describe-look`, {
          description: input.value, shot_index: S.shotIndex,
        });
        S.shots[S.shotIndex] = res.shot;
        note.innerHTML = (res.why ? `<b>${res.why}</b><br>` : "") +
          (res.dropped && res.dropped.length
            ? `ignored: ${res.dropped.join(", ")}` : "applied");
        renderInspector(); requestStill(0);
      } catch (e) {
        note.textContent = String(e).replace(/^Error:\s*/, "").slice(0, 200);
      }
      go.disabled = false;
    };
    go.onclick = ask;
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
    return c;
  }

  async function refreshSnapshots() {
    const box = document.getElementById("scSnapshots");
    if (!box || !S.slug) return;
    const list = await jget(`/api/projects/${encodeURIComponent(S.slug)}/snapshots`);
    box.innerHTML = list.length ? "" : '<span class="muted">No snapshots yet.</span>';
    for (const snap of list) {
      const row = el("span", "sc-snap");
      const label = document.createElement("b");
      label.textContent = snap.label;  // typed by the user: text, never markup
      row.append(label, " ", el("i", "", `${snap.shots} shot(s)`));
      const go = el("button", "btn btn-sm", "restore");
      go.onclick = async () => {
        if (!await ForgeDialog.confirm(`Go back to "${snap.label}"? Your current shots are replaced.`)) return;
        remember();
        const res = await jpost(
          `/api/projects/${encodeURIComponent(S.slug)}/snapshots/${encodeURIComponent(snap.id)}/restore`);
        S.shots = res.shots;
        S.masks = {};
        await selectShot(0);
        renderShots();
        toast(`back to "${snap.label}"`);
      };
      const del = el("button", "sc-x", "×");
      del.onclick = async () => {
        await fetch(`/api/projects/${encodeURIComponent(S.slug)}/snapshots/${encodeURIComponent(snap.id)}`,
                    { method: "DELETE" });
        refreshSnapshots();
      };
      row.appendChild(go);
      row.appendChild(del);
      box.appendChild(row);
    }
  }

  function presetCard(sh) {
    const c = card("Preset", "save this shot", async () => {
      const name = await ForgeDialog.prompt("Name this look — it will appear alongside the built-in presets:");
      if (!name) return;
      try {
        await jpost(`/api/projects/${encodeURIComponent(S.slug)}/save-preset`, {
          name, shot: sh,
        });
        toast(`saved "${name}"`);
        reloadPresets();
      } catch (e) { toast(String(e), "err"); }
    });
    const row = el("div", "sc-presets");
    for (const p of S.presets) {
      const b = el("button", "sc-preset" + (sh.preset === p.id ? " on" : "") + (p.user ? " mine" : ""));
      b.innerHTML = `<strong>${p.label}</strong><span>${p.description}</span>`;
      if (p.user) {
        const del = el("button", "sc-x", "×");
        del.title = "Delete this saved look";
        del.onclick = async (e) => {
          e.stopPropagation();
          if (!await ForgeDialog.confirm(`Delete the saved look "${p.label}"?`)) return;
          await fetch(`/api/presets/${encodeURIComponent(p.id)}`, { method: "DELETE" });
          reloadPresets();
        };
        b.appendChild(del);
      }
      b.onclick = async () => {
        b.disabled = true;
        remember();
        try {
          const res = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/apply-preset`, {
            preset: p.id, shot_index: S.shotIndex, auto: true,
          });
          S.shots[S.shotIndex] = res.shot;
          for (const lay of res.shot.layers || []) {
            if (lay.region?.kind === "brush") await loadMask(lay.region.brush);
          }
          toast(
            res.regions_found.length
              ? `${p.label} — found ${res.regions_found.join(", ")}`
              : `${p.label} applied`
          );
          S.layerIndex = (res.shot.layers || []).length ? 0 : -1;
          renderInspector();
          requestStill(0);
        } catch (e) { toast(String(e), "err"); }
        b.disabled = false;
      };
      row.appendChild(b);
    }
    c.appendChild(row);
    return c;
  }

  function backgroundCard(sh) {
    const c = card("Background");
    const images = S.assets.filter((a) =>
      /\.(png|jpe?g|webp|bmp|mp4|mov|mkv|webm|m4v|gif)$/i.test(a)
    );
    const isVideo = (n) => /\.(mp4|mov|mkv|webm|m4v|gif)$/i.test(n || "");
    const sel = el("select");
    sel.appendChild(el("option", null, "— none —"));
    for (const a of images) {
      const o = el("option", null, a);
      o.value = a;
      if (a === sh.image) o.selected = true;
      sel.appendChild(o);
    }
    sel.onchange = () => {
      sh.image = sel.value === "— none —" ? "" : sel.value;
      saveShots(); requestStill(0);
    };
    const f = el("div", "ctl");
    f.appendChild(el("label", null, "Image"));
    f.appendChild(sel);
    const grid = el("div", "ctl-grid");
    grid.appendChild(f);
    grid.appendChild(
      Controls.buildField(
        { key: "blur", label: "Background blur", type: "range", default: 0, min: 0, max: 1, step: 0.01 },
        sh.blur, (v, live) => { sh.blur = v; onEdit(live); }
      )
    );
    grid.appendChild(
      Controls.buildField(
        { key: "loop_seconds", label: "Loop length", type: "range", default: 12, min: 3, max: 60, step: 0.5, unit: "s",
          help: "How much unique motion is rendered before it repeats." },
        sh.loop_seconds, (v, live) => { sh.loop_seconds = v; onEdit(live); }
      )
    );
    grid.appendChild(
      Controls.buildField(
        { key: "mode", label: "Motion", type: "select", default: "loop", options: ["loop", "live"],
          help: "loop = a short seamless bed repeated (fast). live = every frame rendered so it reacts to the song (slow)." },
        sh.mode, (v) => { sh.mode = v; onEdit(false); }
      )
    );
    grid.appendChild(
      Controls.buildField(
        { key: "kind", label: "This shot is", type: "select", default: "scene",
          options: ["scene", "card"],
          help: "A card is a title over a plain background — an intro or an end card." },
        sh.kind, (v) => { sh.kind = v; onEdit(false); renderInspector(); }
      )
    );
    c.appendChild(grid);

    if (isVideo(sh.image)) {
      c.appendChild(el("p", "muted sc-desc",
        "A clip. It is decoded a frame at a time, and the stretch just past the loop " +
        "is dissolved into the start so it can repeat without a jump."));
      c.appendChild(Controls.buildForm(
        [
          { key: "video_start", label: "Start at", type: "range", default: 0, min: 0, max: 600, step: 0.5, unit: "s" },
          { key: "video_blend", label: "Blend the ends", type: "range", default: 0.5, min: 0, max: 2, step: 0.05, unit: "s",
            help: "How much of the clip is used to hide the loop point." },
        ],
        sh, (k, v, live) => { sh[k] = v; onEdit(live); }
      ));
    }

    if (sh.kind === "card") {
      c.appendChild(Controls.buildForm(
        [
          { key: "card_title", label: "Card title", type: "text", default: "" },
          { key: "card_subtitle", label: "Card second line", type: "text", default: "" },
          { key: "hold", label: "Hold for", type: "range", default: 6, min: 1, max: 60, step: 0.5, unit: "s" },
        ],
        sh, (k, v, live) => { sh[k] = v; onEdit(live); }
      ));
      c.appendChild(el("p", "muted sc-desc",
        "Leave the image empty and set the two grade colours below for a plain " +
        "coloured card. The title is drawn over the finished video."));
    }

    const auto = el("button", "btn btn-sm", "Find the moving parts");
    auto.onclick = async () => {
      if (!sh.image) return toast("pick a background image first", "err");
      remember();
      auto.disabled = true; auto.textContent = "looking…";
      try {
        const res = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/auto-regions`, { image: sh.image });
        sh.layers = sh.layers || [];
        for (const r of res.regions) {
          await loadMask(r.region.brush);
          sh.layers.push({ name: r.name, effect: r.effect, params: r.params, region: r.region, depth: 0.1 });
        }
        S.layerIndex = sh.layers.length - 1;
        toast(res.regions.length ? `found ${res.regions.map((r) => r.name).join(", ")}` : "nothing obvious found");
        saveShots(); renderInspector(); requestStill(0);
      } catch (e) { toast(String(e), "err"); }
      auto.disabled = false; auto.textContent = "Find the moving parts";
    };
    c.appendChild(auto);
    return c;
  }

  function layersCard(sh) {
    const c = card("Moving regions", "+ region", () => {
      remember();
      sh.layers = sh.layers || [];
      const name = `region-${sh.layers.length + 1}`;
      const brush = `${S.slug}-s${S.shotIndex}-${name}-${Date.now().toString(36)}.png`;
      maskCanvas(brush, MASK_W, Math.round(MASK_W * (cv ? cv.height / cv.width : 0.5625)));
      S.dirtyMasks.add(brush);
      sh.layers.push({
        name, effect: "water", params: {}, depth: 0.1,
        region: { kind: "brush", brush, feather: 0.0 },
      });
      S.layerIndex = sh.layers.length - 1;
      S.tool = "brush";
      saveShots(); renderInspector(); renderTools(); paint();
    }, `${(sh.layers || []).length}`);

    const list = el("div", "sc-list");
    (sh.layers || []).forEach((lay, i) => {
      const row = el("div", "sc-row" + (i === S.layerIndex ? " on" : ""));
      const tint = LAYER_TINTS[i % LAYER_TINTS.length];
      row.innerHTML =
        `<i class="sc-swatch" style="background:rgb(${tint.join(",")})"></i>` +
        `<span class="sc-name">${lay.name || lay.effect}</span>` +
        `<span class="muted">${(S.effects.find((e) => e.id === lay.effect) || {}).label || lay.effect}</span>`;
      row.onclick = () => { S.layerIndex = i; renderInspector(); paint(); };
      if (S.shots.length > 1) {
        const cp = el("button", "sc-copy", "copy to…");
        cp.title = "Copy this region to another shot";
        cp.onclick = (e) => {
          e.stopPropagation();
          copyToShot("layer", lay);
        };
        row.appendChild(cp);
      }
      const del = el("button", "sc-x", "×");
      del.onclick = (e) => {
        e.stopPropagation();
        remember();
        sh.layers.splice(i, 1);
        S.layerIndex = Math.min(S.layerIndex, sh.layers.length - 1);
        saveShots(); renderInspector(); paint(); requestStill(0);
      };
      row.appendChild(del);
      list.appendChild(row);
    });
    if (!(sh.layers || []).length) {
      list.appendChild(el("p", "muted",
        "No regions yet. Use <b>Find the moving parts</b> above, or add one and paint it."));
    }
    c.appendChild(list);

    const lay = layer();
    if (lay) {
      const sel = el("select", "sc-effect");
      for (const fam of ["geometry", "light", "custom"]) {
        const group = el("optgroup");
        group.label = { geometry: "Moves the picture", light: "Changes the light", custom: "Your own art" }[fam];
        for (const e of S.effects.filter((x) => x.family === fam)) {
          const o = el("option", null, e.label);
          o.value = e.id;
          if (e.id === lay.effect) o.selected = true;
          group.appendChild(o);
        }
        sel.appendChild(group);
      }
      sel.onchange = () => { lay.effect = sel.value; lay.params = {}; saveShots(); renderInspector(); requestStill(0); };
      c.appendChild(sel);

      const meta = S.effects.find((e) => e.id === lay.effect);
      if (meta) {
        c.appendChild(el("p", "muted sc-desc", meta.description));
        c.appendChild(Controls.buildForm(meta.params, lay.params, (k, v, live) => {
          lay.params = lay.params || {};
          lay.params[k] = v;
          onEdit(live);
        }));
      }
      c.appendChild(Controls.buildForm(
        [
          { key: "depth", label: "Depth (parallax)", type: "range", default: 0.1, min: 0, max: 1, step: 0.01,
            help: "How far this region drifts against the picture behind it. Small values only — for real separation, stack a transparent PNG instead." },
          { key: "feather", label: "Edge softness", type: "range", default: 0.03, min: 0, max: 0.25, step: 0.005 },
        ],
        { depth: lay.depth, feather: lay.region?.feather },
        (k, v, live) => {
          if (k === "depth") lay.depth = v;
          else { lay.region = lay.region || {}; lay.region.feather = v; }
          onEdit(live);
        }
      ));
    }
    return c;
  }

  /* Copying a region between shots shares its mask PNG deliberately: two shots
   * running the same effect over the same painted area is usually the point,
   * and duplicating a shot (which does copy the masks) covers the other case. */
  async function copyToShot(kind, item) {
    const others = S.shots.map((s, i) => i).filter((i) => i !== S.shotIndex);
    const which = await ForgeDialog.prompt(
      `Copy to which shot? (${others.map((i) => i + 1).join(", ")})`,
      String(others[0] + 1)
    );
    const target = parseInt(which, 10) - 1;
    if (!(target >= 0 && target < S.shots.length) || target === S.shotIndex) return;
    const dst = S.shots[target];
    const copy = JSON.parse(JSON.stringify(item));
    if (kind === "layer") (dst.layers = dst.layers || []).push(copy);
    else (dst.emitters = dst.emitters || []).push(copy);
    saveShots();
    toast(`copied to shot ${target + 1}`);
  }

  function imagesCard(sh) {
    const c = card("Stacked images", "+ image", () => {
      remember();
      sh.images = sh.images || [];
      sh.images.push({ src: "", depth: 0.8, x: 0.5, y: 0.5, scale: 1, opacity: 1, fit: "cover", blend: "over" });
      saveShots(); renderInspector();
    }, `${(sh.images || []).length}`);
    c.appendChild(el("p", "muted sc-desc",
      "Transparent PNGs laid over the background. These give real parallax — a cut-out moves against the picture with nothing showing through."));
    const images = S.assets.filter((a) => /\.(png|webp)$/i.test(a));
    (sh.images || []).forEach((im, i) => {
      const wrap = el("div", "sc-sub");
      const sel = el("select");
      sel.appendChild(el("option", null, "— pick a PNG —"));
      for (const a of images) {
        const o = el("option", null, a);
        o.value = a;
        if (a === im.src) o.selected = true;
        sel.appendChild(o);
      }
      sel.onchange = () => { im.src = sel.value.startsWith("—") ? "" : sel.value; onEdit(false); };
      const head = el("div", "sc-head");
      head.appendChild(sel);
      const del = el("button", "sc-x", "×");
      del.onclick = () => { remember(); sh.images.splice(i, 1); saveShots(); renderInspector(); requestStill(0); };
      head.appendChild(del);
      wrap.appendChild(head);

      const effOpts = ["", ...S.effects.map((e) => e.id)];
      wrap.appendChild(Controls.buildForm(
        [
          { key: "depth", label: "Depth", type: "range", default: 0.8, min: 0, max: 1, step: 0.01 },
          { key: "scale", label: "Scale", type: "range", default: 1, min: 0.1, max: 3, step: 0.01 },
          { key: "x", label: "Across", type: "range", default: 0.5, min: -0.5, max: 1.5, step: 0.01 },
          { key: "y", label: "Down", type: "range", default: 0.5, min: -0.5, max: 1.5, step: 0.01 },
          { key: "opacity", label: "Opacity", type: "range", default: 1, min: 0, max: 1, step: 0.01 },
          { key: "blur", label: "Blur", type: "range", default: 0, min: 0, max: 1, step: 0.01 },
          { key: "fit", label: "Fit", type: "select", default: "cover", options: ["cover", "contain", "stretch", "none"] },
          { key: "effect", label: "Motion on this layer", type: "select", default: "", options: effOpts,
            help: "Uses the PNG's own transparency as the region — nothing to paint." },
        ],
        im,
        (k, v, live) => { im[k] = v; if (k === "effect") im.params = {}; onEdit(live); }
      ));
      if (im.effect) {
        const meta = S.effects.find((e) => e.id === im.effect);
        if (meta) wrap.appendChild(Controls.buildForm(meta.params, im.params, (k, v, live) => {
          im.params = im.params || {}; im.params[k] = v; onEdit(live);
        }));
      }
      c.appendChild(wrap);
    });
    return c;
  }

  function emittersCard(sh) {
    const c = card("Sprites & particles", "+ sprites", () => {
      remember();
      sh.emitters = sh.emitters || [];
      sh.emitters.push({ id: "particles", params: {}, depth: 0.6 });
      saveShots(); renderInspector(); requestStill(0);
    }, `${(sh.emitters || []).length}`);
    (sh.emitters || []).forEach((em, i) => {
      const wrap = el("div", "sc-sub");
      const head = el("div", "sc-head");
      const sel = el("select");
      for (const fam of ["particles", "creatures", "custom"]) {
        const group = el("optgroup");
        group.label = { particles: "Particles", creatures: "Creatures", custom: "Your own art" }[fam];
        for (const e of S.emitters.filter((x) => x.family === fam)) {
          const o = el("option", null, e.label);
          o.value = e.id;
          if (e.id === em.id) o.selected = true;
          group.appendChild(o);
        }
        sel.appendChild(group);
      }
      sel.onchange = () => { em.id = sel.value; em.params = {}; saveShots(); renderInspector(); requestStill(0); };
      head.appendChild(sel);
      if (S.shots.length > 1) {
        const cp = el("button", "sc-copy", "copy to…");
        cp.onclick = () => copyToShot("emitter", em);
        head.appendChild(cp);
      }
      const del = el("button", "sc-x", "×");
      del.onclick = () => { remember(); sh.emitters.splice(i, 1); saveShots(); renderInspector(); requestStill(0); };
      head.appendChild(del);
      wrap.appendChild(head);

      const meta = S.emitters.find((e) => e.id === em.id);
      if (meta) {
        wrap.appendChild(el("p", "muted sc-desc", meta.description));
        wrap.appendChild(Controls.buildForm(meta.params, em.params, (k, v, live) => {
          em.params = em.params || {}; em.params[k] = v; onEdit(live);
        }));
      }
      const regionOpts = ["(anywhere)", ...(sh.layers || []).map((l) => l.name)];
      wrap.appendChild(Controls.buildForm(
        [
          { key: "depth", label: "Depth", type: "range", default: 0.6, min: 0, max: 1, step: 0.01,
            help: "Lower sits further back — behind a stacked image with a higher depth." },
          { key: "_region", label: "Keep inside region", type: "select", default: "(anywhere)", options: regionOpts,
            help: "Fish in the pond, stars in the sky." },
        ],
        { depth: em.depth, _region: (sh.layers || []).find((l) => l.region === em.region)?.name || "(anywhere)" },
        (k, v, live) => {
          if (k === "depth") em.depth = v;
          else {
            const found = (sh.layers || []).find((l) => l.name === v);
            em.region = found ? found.region : null;
          }
          onEdit(live);
        }
      ));
      c.appendChild(wrap);
    });
    if (!(sh.emitters || []).length) {
      c.appendChild(el("p", "muted", "Nothing drifting through yet."));
    }
    return c;
  }

  /* The look panel used to be one flat grid of about twenty sliders with the
   * camera, the grade, the film effects and the depth of field all mixed
   * together. It is now split by the `group` each parameter declares in
   * `scenes/living.py`, so the panel still generates itself and a parameter
   * added later lands in the right section by saying where it belongs. */
  const LOOK_GROUPS = [
    ["camera", "Camera", "How the frame drifts and pushes."],
    ["grade", "Colour", "The overall look: a film grade, then the fine controls."],
    ["analogue", "Analogue", "Scanlines, colour fringing, letterbox, light leak."],
    ["depth", "Depth", "What is sharp, and how the distance fades."],
    ["particles", "Particles", "Embers, snow, sparks on the beat, dust or petals over the picture."],
  ];
  const GROUP_TARGET = { camera: "camera" };  // everything else lives in `look`

  function motionCard(sh) {
    const c = card("Camera & look");
    sh.camera = sh.camera || {};
    sh.look = sh.look || {};
    const schema = S.livingParams || [];
    let first = true;
    for (const [group, title, blurb] of LOOK_GROUPS) {
      const specs = schema.filter((sp) => sp.group === group);
      if (!specs.length) continue;
      if (!first) c.appendChild(el("div", "sc-rule"));
      first = false;
      c.appendChild(el("div", "sc-group", `${title} <span>${blurb}</span>`));
      const target = GROUP_TARGET[group] === "camera" ? sh.camera : sh.look;
      c.appendChild(Controls.buildForm(specs, target, (k, v, live) => {
        target[k] = v;
        onEdit(live);
      }));
    }
    return c;
  }

  let saveTimer = null;
  function onEdit(live) {
    // one history entry per drag, taken on the first live event
    if (!live || !S.midDrag) remember();
    S.midDrag = !!live;
    requestStill(live ? 260 : 60);
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveShots, 600);
  }

  // ---------------------------------------------------------- shot strip ---
  function renderShots() {
    const strip = document.getElementById("scShots");
    if (!strip) return;
    strip.innerHTML = "";
    S.shots.forEach((sh, i) => {
      if (i > 0) {
        const t = el("select", "sc-trans");
        for (const tr of S.transitions) {
          const o = el("option", null, tr.label);
          o.value = tr.id;
          if (tr.id === sh.transition) o.selected = true;
          t.appendChild(o);
        }
        t.onchange = () => { sh.transition = t.value; saveShots(); };
        strip.appendChild(t);
      }
      const b = el("button", "sc-shot" + (i === S.shotIndex ? " on" : ""));
      const label = sh.kind === "card" ? "title card" : sh.image || "no image";
      b.innerHTML = `<span>${i + 1}</span><em>${label}</em>`;
      b.onclick = () => selectShot(i);
      b.draggable = true;
      b.dataset.index = String(i);
      b.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/plain", String(i));
        b.classList.add("dragging");
      });
      b.addEventListener("dragend", () => b.classList.remove("dragging"));
      b.addEventListener("dragover", (e) => { e.preventDefault(); b.classList.add("dropinto"); });
      b.addEventListener("dragleave", () => b.classList.remove("dropinto"));
      b.addEventListener("drop", async (e) => {
        e.preventDefault();
        b.classList.remove("dropinto");
        const from = parseInt(e.dataTransfer.getData("text/plain"), 10);
        if (!(from >= 0) || from === i) return;
        remember();
        const [moved] = S.shots.splice(from, 1);
        S.shots.splice(i, 0, moved);
        await saveShots();
        await selectShot(i);
        renderShots();
      });
      const del = el("button", "sc-x", "×");
      del.onclick = (e) => {
        e.stopPropagation();
        remember();
        S.shots.splice(i, 1);
        S.shotIndex = Math.max(0, Math.min(S.shotIndex, S.shots.length - 1));
        saveShots(); renderShots(); renderInspector(); requestStill(0);
      };
      b.appendChild(del);
      strip.appendChild(b);
    });
    if (S.shots.length) {
      const dup = el("button", "sc-shot sc-add", "⧉ duplicate");
      dup.title = "Copy this shot, painted regions and all";
      dup.onclick = async () => {
        try {
          const res = await jpost(
            `/api/projects/${encodeURIComponent(S.slug)}/duplicate-shot`,
            { shot_index: S.shotIndex }
          );
          S.shots = res.shots;
          await selectShot(res.index);
          renderShots();
          toast("shot duplicated");
        } catch (e) { toast(String(e), "err"); }
      };
      strip.appendChild(dup);
    }
    const slideshow = el("button", "sc-shot sc-add", "▦ one per image");
    slideshow.title = "Turn every attached image into its own shot";
    slideshow.onclick = async () => {
      const imgs = S.assets.filter((a) => /\.(png|jpe?g|webp|bmp)$/i.test(a));
      if (!imgs.length) return toast("attach some images first", "err");
      const hold = parseFloat(await ForgeDialog.prompt(`Make a shot from each of ${imgs.length} images. Hold each for how many seconds?`, "20"));
      if (!isFinite(hold)) return;
      try {
        const res = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/shots-from-images`, {
          images: imgs, hold, transition: "dissolve", transition_s: 1.5,
        });
        S.shots = res.shots;
        await selectShot(Math.max(0, S.shots.length - res.added));
        renderShots();
        toast(`${res.added} shots added`);
      } catch (e) { toast(String(e), "err"); }
    };
    strip.appendChild(slideshow);
    const add = el("button", "sc-shot sc-add", "+ shot");
    add.onclick = () => {
      remember();
      const prev = shot();
      S.shots.push({
        image: prev?.image || "", layers: [], images: [], emitters: [],
        camera: {}, look: {}, hold: "song", transition: "dissolve", transition_s: 1.5,
      });
      S.shotIndex = S.shots.length - 1;
      saveShots(); renderShots(); renderInspector(); requestStill(0);
    };
    strip.appendChild(add);
  }

  async function selectShot(i) {
    S.shotIndex = i;
    S.layerIndex = (shot()?.layers || []).length ? 0 : -1;
    S.poly = [];
    for (const lay of shot()?.layers || []) {
      if (lay.region?.kind === "brush" && !S.masks[lay.region.brush]) await loadMask(lay.region.brush);
    }
    renderShots(); renderInspector(); requestStill(0);
  }

  // ------------------------------------------------------------- preview ---
  async function previewLoop() {
    const btn = document.getElementById("scPreviewBtn");
    const sh = shot();
    if (!sh) return;
    btn.disabled = true;
    btn.textContent = "rendering…";
    try {
      await flushMasks();
      const { job_id } = await jpost(`/api/projects/${encodeURIComponent(S.slug)}/shot-preview`, {
        shot: sh, width: 854,
      });
      const done = await waitForJob(job_id, (f) => {
        btn.textContent = `rendering… ${Math.round(f * 100)}%`;
      });
      const v = document.getElementById("scPreviewVid");
      v.src = `/api/projects/${encodeURIComponent(S.slug)}/render-file?name=${encodeURIComponent(done.result.file)}&_=${Date.now()}`;
      v.hidden = false;
      v.loop = true;
      v.play().catch(() => {});
      document.getElementById("scPreviewNote").textContent =
        "Looping. If you can see where it repeats, that is the seam to fix.";
    } catch (e) {
      toast(String(e), "err");
    }
    btn.disabled = false;
    btn.textContent = "▸ Preview loop";
  }

  function waitForJob(id, onProgress) {
    return new Promise((resolve, reject) => {
      const tick = async () => {
        try {
          const j = await jget(`/api/jobs/${id}`);
          if (onProgress && typeof j.progress === "number") onProgress(j.progress);
          if (j.status === "done") return resolve(j);
          if (j.status === "error") return reject(new Error(j.error || "render failed"));
          if (j.status === "canceled") return reject(new Error("canceled"));
          setTimeout(tick, 600);
        } catch (e) { reject(e); }
      };
      tick();
    });
  }

  // ------------------------------------------------------------ timeline ---
  async function refreshTimeline() {
    const box = document.getElementById("scTimeline");
    if (!box || !S.slug) return;
    try {
      const t = await jget(`/api/projects/${encodeURIComponent(S.slug)}/timeline`);
      if (!t.duration) { box.innerHTML = '<span class="muted">Add songs on the Compose tab.</span>'; return; }
      const mins = Math.floor(t.duration / 60), secs = Math.round(t.duration % 60);
      box.innerHTML = "";
      const bar = el("div", "sc-tl");
      for (const s of t.shots) {
        const seg = el("div", "sc-tlseg", `${s.image || "—"}`);
        seg.style.flexGrow = String(Math.max(0.02, s.duration));
        seg.title = `shot ${s.index + 1} · ${s.duration.toFixed(0)}s · ${s.transition}`;
        bar.appendChild(seg);
      }
      box.appendChild(bar);
      const rep = (t.passes || 1) > 1 ? ` · the mix repeats ${t.passes}×` : "";
      box.appendChild(el("div", "muted",
        `${t.songs.length} play(s) · ${t.shots.length} shot placement(s) · ` +
        `${mins}m ${secs}s${rep} · only ${t.beds} loop bed(s) actually get rendered`));
    } catch (e) { /* timeline is informational */ }
  }

  // ---------------------------------------------------------------- tools --
  function renderTools() {
    for (const t of ["brush", "erase", "polygon", "wand"]) {
      const b = document.getElementById("scTool_" + t);
      if (b) b.classList.toggle("on", S.tool === t);
    }
    const close = document.getElementById("scClosePoly");
    if (close) close.hidden = S.tool !== "polygon";
    const wand = document.getElementById("scWandOpts");
    if (wand) wand.hidden = S.tool !== "wand";
    const brush = document.getElementById("scBrushOpts");
    if (brush) brush.hidden = S.tool === "wand" || S.tool === "polygon";
  }

  function toast(msg, kind) {
    if (global.toast) return global.toast(msg, kind);
    console.log(msg);
  }

  // ----------------------------------------------------------------- init --
  async function open(project) {
    S.slug = project.slug;
    S.data = project.data;
    S.shots = project.data.shots || [];
    S.assets = project.data.assets || [];
    if (!S.effects.length) await loadRegistries();
    if (!S.shots.length) {
      const firstImage = S.assets.find((a) => /\.(png|jpe?g|webp|bmp)$/i.test(a)) || "";
      S.shots = [{
        image: firstImage, layers: [], images: [], emitters: [],
        camera: {}, look: {}, hold: "song", transition: "dissolve", transition_s: 1.5,
      }];
    }
    S.shotIndex = 0;
    S.masks = {};
    await selectShot(0);
    renderShots();
    refreshTimeline();
    refreshSnapshots();
    const take = document.getElementById("scTakeSnapshot");
    if (take) take.onclick = async () => {
      const label = await ForgeDialog.prompt("Name this snapshot — you can come back to it later:",
                           new Date().toLocaleTimeString());
      if (!label) return;
      await jpost(`/api/projects/${encodeURIComponent(S.slug)}/snapshots`, { label });
      refreshSnapshots();
      toast("snapshot taken");
    };
  }

  function mount() {
    cv = document.getElementById("scCanvas");
    if (!cv) return;
    ctx = cv.getContext("2d");

    cv.addEventListener("pointerdown", (e) => {
      if (S.tool === "polygon" || S.tool === "wand") return canvasClick(e);
      painting = true;
      pushUndo();
      cv.setPointerCapture(e.pointerId);
      strokeAt(e);
    });
    cv.addEventListener("pointermove", (e) => { if (painting) strokeAt(e); });
    const stop = () => {
      if (!painting) return;
      painting = false;
      saveShots();
      requestStill(120);
    };
    cv.addEventListener("pointerup", stop);
    cv.addEventListener("pointercancel", stop);

    for (const t of ["brush", "erase", "polygon", "wand"]) {
      const b = document.getElementById("scTool_" + t);
      if (b) b.onclick = () => { S.tool = t; S.poly = []; renderTools(); paint(); };
    }
    const wt = document.getElementById("scWandTol");
    if (wt) wt.oninput = () => {
      S.wandTolerance = +wt.value / 100;
      document.getElementById("scWandTolLabel").textContent = wt.value + "%";
    };
    const wc = document.getElementById("scWandContig");
    if (wc) wc.onchange = () => { S.wandContiguous = wc.checked; };
    const bs = document.getElementById("scBrushSize");
    if (bs) bs.oninput = () => { S.brushSize = +bs.value; };
    const undoBtn = document.getElementById("scUndo");
    if (undoBtn) undoBtn.onclick = () => {
      const u = S.undo.pop();
      if (!u) return;
      const c = S.masks[u.name];
      const g = c.getContext("2d");
      g.clearRect(0, 0, c.width, c.height);
      g.drawImage(u.canvas, 0, 0);
      S.dirtyMasks.add(u.name);
      paint(); requestStill(0);
    };
    const close = document.getElementById("scClosePoly");
    if (close) close.onclick = closePolygon;
    const showBtn = document.getElementById("scShowRegions");
    if (showBtn) showBtn.onchange = () => { S.showRegions = showBtn.checked; paint(); };
    const scrub = document.getElementById("scScrub");
    if (scrub) scrub.oninput = () => {
      const sh = shot();
      S.t = (+scrub.value / 100) * (sh?.loop_seconds || 12);
      document.getElementById("scScrubLabel").textContent = S.t.toFixed(1) + "s";
      requestStill(120);
    };
    const pv = document.getElementById("scPreviewBtn");
    if (pv) pv.onclick = previewLoop;
    window.addEventListener("resize", fitCanvas);

    /* Shortcuts. Only while the Scenery tab is showing, and never while you are
     * typing into a field -- otherwise "b" in a track title switches tools. */
    window.addEventListener("keydown", (e) => {
      const panel = document.querySelector('.panel[data-panel="scenery"]');
      if (!panel || !panel.classList.contains("active")) return;
      const t = e.target;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT")) return;
      const key = e.key.toLowerCase();
      if ((e.metaKey || e.ctrlKey) && key === "z") {
        e.preventDefault();
        return e.shiftKey ? redoEdit() : undoEdit();
      }
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      const tools = { b: "brush", e: "erase", p: "polygon", w: "wand" };
      if (tools[key]) {
        S.tool = tools[key]; S.poly = []; renderTools(); paint();
      } else if (key === "[" || key === "]") {
        S.brushSize = Math.max(8, Math.min(220, S.brushSize + (key === "]" ? 10 : -10)));
        const bs = document.getElementById("scBrushSize");
        if (bs) bs.value = S.brushSize;
      } else if (key === "arrowleft" && S.shotIndex > 0) {
        selectShot(S.shotIndex - 1).then(renderShots);
      } else if (key === "arrowright" && S.shotIndex < S.shots.length - 1) {
        selectShot(S.shotIndex + 1).then(renderShots);
      } else if (key === " ") {
        e.preventDefault();
        previewLoop();
      } else if (key === "r") {
        requestStill(0);
      } else {
        return;
      }
      e.preventDefault();
    });

    const ue = document.getElementById("scUndoEdit");
    if (ue) ue.onclick = undoEdit;
    const re = document.getElementById("scRedoEdit");
    if (re) re.onclick = redoEdit;
    updateHistoryButtons();
    renderTools();
  }

  /** Open the editor on a particular shot -- how "Fine-tune this →" lands. */
  async function gotoShot(index) {
    if (!S.shots.length) return;
    await selectShot(Math.max(0, Math.min(index, S.shots.length - 1)));
    renderShots();
  }

  global.Scenery = { open, mount, paint, refreshTimeline, gotoShot, state: S };
})(window);
