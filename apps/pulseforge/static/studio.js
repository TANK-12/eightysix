/*
 * The AMV studio: the edit, drawn.
 *
 * Everything else in PulseForge is a form. This is the one place that shows the
 * video as a shape in time -- where the song's sections are, where every cut
 * falls, which clip fills it, what fires on the beat -- because those are
 * decisions you judge by looking, not by reading numbers out of a list.
 *
 * The important property is that planning is not rendering. The plan comes back
 * in milliseconds once the clips have been looked at once, so changing the style
 * or dragging the intensity redraws the whole edit immediately. You decide what
 * you want before spending an encode on it.
 *
 * Everything drawn here is the *actual* plan the renderer will execute -- the
 * same `amvplan.plan()` result, not a preview of it -- so what you see is what
 * gets made.
 */
(function (global) {
  "use strict";

  const el = (t, c, h) => Controls.el(t, c, h);
  const S = {
    plan: null,
    styles: [],
    style: "classic",
    schema: [],
    params: {},
    sel: -1,
    view: { t0: 0, t1: 1 },
    drag: null,
    hover: null,
    busy: false,
  };
  global.StudioState = S;

  async function jget(u) {
    const r = await fetch(u);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function jpost(u, body) {
    const r = await fetch(u, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : null,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  const say = (m) => {
    const n = document.getElementById("stStatus");
    if (n) n.textContent = m;
  };

  /* The page declares `PROJECT` with `let`, and a top-level `let` does not
   * become a property of `window` -- only `function` declarations do. So
   * `window.PROJECT` is permanently undefined while the binding itself is
   * perfectly visible to any script that reads it by name, which is why the
   * studio kept insisting no project was open while one plainly was. */
  const proj = () => (typeof PROJECT !== "undefined" ? PROJECT : null);

  // --- colours -------------------------------------------------------------
  const SECTION_COLOURS = {
    intro: "#2b3a56",
    outro: "#2b3a56",
    verse: "#3b4a2f",
    chorus: "#6b3550",
    build: "#5a4520",
    breakdown: "#33334a",
    bridge: "#33334a",
  };
  const FX_COLOURS = { camera: "#5ad2a0", colour: "#ffd166", glitch: "#ff6b8a" };

  /* A clip's colour is derived from its name, so the same clip is the same
   * colour every time you replan and you can see at a glance how the footage is
   * spread across the video. */
  function clipHue(path) {
    let h = 0;
    for (let i = 0; i < path.length; i++) h = (h * 31 + path.charCodeAt(i)) % 360;
    return h;
  }

  // --- the timeline --------------------------------------------------------
  function canvas() {
    return document.getElementById("stCanvas");
  }

  function fitCanvas(c) {
    const dpr = global.devicePixelRatio || 1;
    const w = c.clientWidth,
      h = c.clientHeight;
    if (c.width !== Math.round(w * dpr) || c.height !== Math.round(h * dpr)) {
      c.width = Math.round(w * dpr);
      c.height = Math.round(h * dpr);
    }
    const ctx = c.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  // [y, height] for each band of the timeline, top to bottom.
  const ROWS = {
    section: [4, 22],
    music: [30, 62],
    shots: [98, 96],
    trans: [198, 12],
    fx: [214, 18],
    ruler: [238, 18],
  };

  function draw() {
    const c = canvas();
    if (!c) return;
    const { ctx, w, h } = fitCanvas(c);
    ctx.clearRect(0, 0, w, h);
    ctx.fillStyle = "#0c0c11";
    ctx.fillRect(0, 0, w, h);

    const P = S.plan;
    if (!P || !P.shots || !P.shots.length) {
      ctx.fillStyle = "#6a6a78";
      ctx.font = "13px system-ui, sans-serif";
      ctx.fillText("No plan yet — pick a clips folder and press “Plan the edit”.", 14, 30);
      return;
    }
    const { t0, t1 } = S.view;
    const span = Math.max(0.05, t1 - t0);
    const X = (t) => ((t - t0) / span) * w;

    // sections
    const [sy, sh] = ROWS.section;
    for (const sec of P.sections || []) {
      const x = X(sec.start),
        x2 = X(sec.end);
      if (x2 < 0 || x > w) continue;
      ctx.fillStyle = SECTION_COLOURS[sec.kind] || "#2a2a36";
      ctx.fillRect(x, sy, Math.max(1, x2 - x), sh);
      if (x2 - x > 46) {
        ctx.fillStyle = "#e6e6f0";
        ctx.font = "11px system-ui, sans-serif";
        ctx.fillText(sec.kind, x + 5, sy + 15);
      }
    }

    // the music: bar lines, then drops
    const [my, mh] = ROWS.music;
    ctx.fillStyle = "#14141c";
    ctx.fillRect(0, my, w, mh);
    const bars = P.downbeats || [];
    const barPx = bars.length > 1 ? X(bars[1]) - X(bars[0]) : 999;
    if (barPx > 3) {
      ctx.strokeStyle = "#2c2c3c";
      ctx.lineWidth = 1;
      ctx.beginPath();
      for (const b of bars) {
        const x = Math.round(X(b)) + 0.5;
        if (x < 0 || x > w) continue;
        ctx.moveTo(x, my);
        ctx.lineTo(x, my + mh);
      }
      ctx.stroke();
    }
    // novelty: how much the song changes, per beat
    const nov = P.novelty || [];
    const beats = P.beats || [];
    if (nov.length && nov.length === beats.length) {
      ctx.strokeStyle = "#4b6fa8";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      let started = false;
      for (let i = 0; i < nov.length; i++) {
        const x = X(beats[i]);
        if (x < -20 || x > w + 20) continue;
        const y = my + mh - 3 - nov[i] * (mh - 6);
        started ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
        started = true;
      }
      ctx.stroke();
    }
    for (const d of P.drops || []) {
      const x = X(d);
      if (x < 0 || x > w) continue;
      ctx.fillStyle = "#ff5470";
      ctx.fillRect(x - 1, my, 2, mh);
      ctx.font = "10px system-ui, sans-serif";
      ctx.fillText("drop", x + 4, my + 11);
    }

    // shots
    const [shy, shh] = ROWS.shots;
    P.shots.forEach((s, i) => {
      const x = X(s.at),
        x2 = X(s.at + s.dur);
      if (x2 < 0 || x > w) return;
      const hue = clipHue(s.path);
      const sel = i === S.sel;
      ctx.fillStyle = `hsl(${hue} 45% ${sel ? 42 : 26}%)`;
      ctx.fillRect(x, shy, Math.max(1, x2 - x - 1), shh);
      if (sel) {
        ctx.strokeStyle = "#d16bff";
        ctx.lineWidth = 2;
        ctx.strokeRect(x + 1, shy + 1, Math.max(1, x2 - x - 3), shh - 2);
      }
      if (x2 - x > 54) {
        ctx.fillStyle = "#dfe0ea";
        ctx.font = "10px ui-monospace, monospace";
        const name = s.path.split("/").pop().replace(/\.[^.]+$/, "");
        ctx.fillText(name.slice(0, Math.floor((x2 - x) / 6)), x + 4, shy + 13);
        if (x2 - x > 96) {
          ctx.fillStyle = "#9a9ab0";
          ctx.fillText(s.look.slice(0, Math.floor((x2 - x) / 6)), x + 4, shy + 27);
          ctx.fillText(`${s.dur.toFixed(2)}s`, x + 4, shy + 41);
        }
      }
    });

    // transitions
    const [ty, th] = ROWS.trans;
    P.shots.forEach((s, i) => {
      if (!i || s.transition === "cut") return;
      const x = X(s.at);
      if (x < -6 || x > w + 6) return;
      ctx.fillStyle = "#ffd166";
      ctx.beginPath();
      ctx.moveTo(x, ty);
      ctx.lineTo(x + 5, ty + th / 2);
      ctx.lineTo(x, ty + th);
      ctx.lineTo(x - 5, ty + th / 2);
      ctx.closePath();
      ctx.fill();
    });

    // beat effects
    const [fy, fh] = ROWS.fx;
    ctx.fillStyle = "#14141c";
    ctx.fillRect(0, fy, w, fh);
    for (const s of P.shots) {
      for (const f of s.fx || []) {
        const fam = (S.fxFamily && S.fxFamily[f.id]) || "camera";
        ctx.fillStyle = FX_COLOURS[fam] || "#5ad2a0";
        const evs = (f.events && f.events.length ? f.events : [0]).slice(0, 40);
        for (const e of evs) {
          const x = X(s.at + e);
          if (x < 0 || x > w) continue;
          ctx.fillRect(x, fy + 3, 1.5, fh - 6);
        }
      }
    }

    // ruler
    const [ry] = ROWS.ruler;
    ctx.fillStyle = "#8a8a9c";
    ctx.font = "10px ui-monospace, monospace";
    const stepChoices = [0.5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
    const step = stepChoices.find((s) => (s / span) * w > 58) || 600;
    for (let t = Math.ceil(t0 / step) * step; t < t1; t += step) {
      const x = X(t);
      ctx.fillRect(x, ry, 1, 5);
      const mm = Math.floor(t / 60),
        ss = Math.floor(t % 60);
      ctx.fillText(`${mm}:${String(ss).padStart(2, "0")}`, x + 3, ry + 14);
    }

    if (S.hover != null) {
      const x = X(S.hover);
      ctx.strokeStyle = "#ffffff55";
      ctx.beginPath();
      ctx.moveTo(x + 0.5, 0);
      ctx.lineTo(x + 0.5, ROWS.ruler[0]);
      ctx.stroke();
    }
  }

  function shotAt(t) {
    if (!S.plan) return -1;
    for (let i = 0; i < S.plan.shots.length; i++) {
      const s = S.plan.shots[i];
      if (t >= s.at && t < s.at + s.dur) return i;
    }
    return -1;
  }

  function wireCanvas() {
    const c = canvas();
    if (!c || c.dataset.wired) return;
    c.dataset.wired = "1";
    const tAt = (ev) => {
      const r = c.getBoundingClientRect();
      const f = (ev.clientX - r.left) / r.width;
      return S.view.t0 + f * (S.view.t1 - S.view.t0);
    };
    c.addEventListener("wheel", (ev) => {
      if (!S.plan) return;
      ev.preventDefault();
      const at = tAt(ev);
      const k = ev.deltaY > 0 ? 1.22 : 1 / 1.22;
      let a = at - (at - S.view.t0) * k,
        b = at + (S.view.t1 - at) * k;
      const total = S.plan.duration || 1;
      if (b - a > total) {
        a = 0;
        b = total;
      }
      a = Math.max(0, a);
      b = Math.min(total, Math.max(a + 0.25, b));
      S.view = { t0: a, t1: b };
      draw();
    }, { passive: false });
    c.addEventListener("mousedown", (ev) => {
      S.drag = { x: ev.clientX, t0: S.view.t0, t1: S.view.t1, moved: false };
    });
    global.addEventListener("mousemove", (ev) => {
      if (S.drag) {
        const r = c.getBoundingClientRect();
        const dt = ((ev.clientX - S.drag.x) / r.width) * (S.drag.t1 - S.drag.t0);
        if (Math.abs(ev.clientX - S.drag.x) > 3) S.drag.moved = true;
        const total = (S.plan && S.plan.duration) || 1;
        let a = S.drag.t0 - dt,
          b = S.drag.t1 - dt;
        if (a < 0) { b -= a; a = 0; }
        if (b > total) { a -= b - total; b = total; }
        S.view = { t0: Math.max(0, a), t1: b };
        draw();
      } else if (S.plan) {
        const r = c.getBoundingClientRect();
        if (ev.clientX >= r.left && ev.clientX <= r.right && ev.clientY >= r.top && ev.clientY <= r.bottom) {
          S.hover = tAt(ev);
          draw();
        }
      }
    });
    global.addEventListener("mouseup", (ev) => {
      if (S.drag && !S.drag.moved && S.plan) {
        const i = shotAt(tAt(ev));
        if (i >= 0) {
          S.sel = i;
          showShot();
        }
      }
      S.drag = null;
    });
    global.addEventListener("resize", draw);
  }

  // --- the inspector -------------------------------------------------------
  function showShot() {
    const box = document.getElementById("stShot");
    if (!box) return;
    const s = S.plan && S.plan.shots[S.sel];
    if (!s) {
      box.className = "st-shot muted";
      box.textContent = "Click a shot on the timeline.";
      return;
    }
    box.className = "st-shot";
    const name = s.path.split("/").pop();
    const fx = (s.fx || [])
      .map((f) => `<span class="st-fx">${f.id}${f.events && f.events.length ? " ×" + f.events.length : ""}</span>`)
      .join("");
    const short = s.short_by > 0.02
      ? `<div style="color:#ffb066">holds the last frame for ${s.short_by.toFixed(2)}s — this clip is shorter than the shot</div>`
      : "";
    box.innerHTML = `
      <div><b>#${S.sel + 1}</b> &nbsp;${fmt(s.at)} → ${fmt(s.at + s.dur)} &nbsp;<span class="muted">(${s.dur.toFixed(2)}s)</span></div>
      <div style="margin-top:6px">${name}</div>
      <div class="muted">from ${s.start.toFixed(2)}s in the clip${s.speed !== 1 ? `, at ${(1 / s.speed).toFixed(2)}× slow motion` : ""}</div>
      <div style="margin-top:8px">${s.look}</div>
      <div class="muted">section: ${s.section} &nbsp;·&nbsp; business ${s.action.toFixed(2)} vs wanted ${s.target_action.toFixed(2)}</div>
      <div class="muted">movement carries across the cut: ${(s.continuity * 100).toFixed(0)}%</div>
      <div style="margin-top:6px">in: <b>${s.transition}</b>${s.transition_ms ? ` (${s.transition_ms}ms)` : ""}</div>
      ${fx ? `<div style="margin-top:6px">${fx}</div>` : ""}
      ${short}`;
  }
  const fmt = (t) => `${Math.floor(t / 60)}:${String(Math.floor(t % 60)).padStart(2, "0")}.${String(Math.floor((t % 1) * 100)).padStart(2, "0")}`;

  function showStats() {
    const box = document.getElementById("stStats");
    if (!box) return;
    box.innerHTML = "";
    const P = S.plan;
    if (!P) return;
    const s = P.summary || {};
    const cells = [
      [s.shots, "shots"],
      [`${s.bpm ?? "?"}`, "BPM"],
      [`${s.mean_shot ?? "?"}s`, "mean shot"],
      [`${s.shortest ?? "?"}–${s.longest ?? "?"}s`, "range"],
      [s.sections, "sections"],
      [`${s.clips_used}/${s.clips_available}`, "clips used"],
      [s.repeats_back_to_back, "repeats in a row"],
      [`${Math.round((s.mean_continuity || 0) * 100)}%`, "movement matched"],
      [s.shots_short_of_footage || 0, "short of footage"],
      [s.solver, "chosen by"],
    ];
    for (const [v, label] of cells) {
      const d = el("div", "st-stat");
      d.appendChild(el("b", null, String(v)));
      d.appendChild(el("span", null, label));
      box.appendChild(d);
    }
  }

  function showClips() {
    const box = document.getElementById("stClips");
    const count = document.getElementById("stClipCount");
    if (!box) return;
    const clips = (S.plan && S.plan.clips) || [];
    if (count) count.textContent = clips.length ? `(${clips.length})` : "";
    if (!clips.length) {
      box.className = "muted";
      box.textContent = "Nothing looked at yet.";
      return;
    }
    box.className = "";
    box.innerHTML = "";
    const used = {};
    for (const s of S.plan.shots || []) used[s.path] = (used[s.path] || 0) + 1;
    for (const c of clips) {
      const row = el("div", "st-clip");
      row.style.borderLeft = `3px solid hsl(${clipHue(c.path)} 45% 45%)`;
      row.appendChild(el("span", null, c.name));
      row.appendChild(
        el("small", null, `${(c.duration || 0).toFixed(1)}s · ${used[c.path] || 0} shots`)
      );
      box.appendChild(row);
    }
  }

  // --- styles and parameters ----------------------------------------------
  function showStyles() {
    const box = document.getElementById("stStyles");
    if (!box) return;
    box.innerHTML = "";
    for (const st of S.styles) {
      const d = el("div", "st-style" + (st.id === S.style ? " sel" : ""));
      d.appendChild(el("b", null, st.label));
      d.appendChild(el("span", null, st.description));
      d.onclick = () => {
        S.style = st.id;
        S.params.style = st.id;
        showStyles();
        plan();
      };
      box.appendChild(d);
    }
  }

  function showParams() {
    const box = document.getElementById("stStyleParams");
    if (!box || !S.schema.length) return;
    box.innerHTML = "";
    /* Built from the AMV scene's own parameter schema, so a control added to
     * `scenes/amv.py` appears here with a slider and a number box and no
     * change to this file. */
    const schema = S.schema.filter((p) => p.key !== "style");
    box.appendChild(
      Controls.buildForm(schema, S.params, (k, v, live) => {
        S.params[k] = v;
        if (!live) plan();
      })
    );
  }

  // --- actions -------------------------------------------------------------
  async function plan() {
    if (!proj()) return say("open a project first — the Projects tab lists them.");
    if (S.busy) return;
    S.busy = true;
    say("planning…");
    try {
      const body = Object.assign({ style: S.style }, S.params);
      delete body._assets;
      const p = await jpost(`/api/projects/${encodeURIComponent(PROJECT.slug)}/edit-plan`, body);
      const music = await jget(`/api/projects/${encodeURIComponent(PROJECT.slug)}/music-map`);
      p.novelty = music.novelty || [];
      p.beats = music.beats || [];
      S.plan = p;
      // Frame the whole video whenever the song's length changes -- including
      // the first plan, where the view is still the one-second placeholder it
      // starts as. Keeping the view otherwise means changing style or
      // intensity redraws in place instead of throwing away where you were
      // looking, which is the point of replanning being instant.
      if (S.viewFor !== p.duration) {
        S.view = { t0: 0, t1: p.duration || 1 };
        S.viewFor = p.duration;
      }
      S.sel = -1;
      draw();
      showStats();
      showClips();
      showShot();
      const s = p.summary || {};
      say(`${s.shots} shots at ${s.bpm} BPM across ${s.sections} sections — ${s.clips_used} of ${s.clips_available} clips used.`);
    } catch (e) {
      say("could not plan: " + String(e.message || e).slice(0, 220));
    } finally {
      S.busy = false;
    }
  }

  async function open() {
    wireCanvas();
    if (!S.styles.length) {
      try {
        const [st, sc, fx] = await Promise.all([
          jget("/api/edit-styles"),
          jget("/api/scenes"),
          jget("/api/beat-effects"),
        ]);
        S.styles = st.styles || [];
        S.style = st.default || "classic";
        // /api/scenes answers with a bare list while the newer registry
        // endpoints wrap theirs in an object; accept either rather than
        // silently ending up with no parameter form, which is what happened.
        const sceneList = Array.isArray(sc) ? sc : sc.scenes || [];
        const amv = sceneList.find((x) => x.id === "amv");
        S.schema = (amv && amv.params) || [];
        S.params = {};
        for (const p of S.schema) S.params[p.key] = p.default;
        S.fxFamily = {};
        for (const f of (Array.isArray(fx) ? fx : fx.effects) || []) S.fxFamily[f.id] = f.family;
      } catch (e) {
        say("could not load the studio: " + e);
        return;
      }
    }
    if (proj()) {
      const saved = proj().data.params || {};
      if (proj().data.scene === "amv") {
        for (const k of Object.keys(S.params)) if (saved[k] != null) S.params[k] = saved[k];
        if (saved.style) S.style = saved.style;
      }
      // The clips folder is stored as an absolute path in the asset list.
      const folder = (proj().data.assets || []).find((a) => String(a).includes("/"));
      const inp = document.getElementById("stFolder");
      if (inp && !inp.value && folder) inp.value = folder;
    }
    showStyles();
    showParams();
    draw();
    const panel = document.querySelector('[data-panel="studio"]');
    if (panel) panel.dataset.ready = "1";
  }

  function mount() {
    const on = (id, fn) => {
      const n = document.getElementById(id);
      if (n) n.onclick = fn;
    };
    on("stSetFolder", async () => {
      const v = (document.getElementById("stFolder") || {}).value || "";
      if (!proj()) return say("open a project first");
      try {
        await jpost(`/api/projects/${encodeURIComponent(PROJECT.slug)}/clips-folder`, { path: v });
        say("folder set — press “Look at the clips”.");
      } catch (e) {
        say("could not set the folder: " + e);
      }
    });
    on("stAnalyse", async () => {
      if (!proj()) return say("open a project first");
      try {
        const j = await jpost(`/api/projects/${encodeURIComponent(PROJECT.slug)}/analyse-clips`);
        say("looking at the clips…");
        // `runJob` is the page's one job watcher: it streams the log into the
        // shared log box and re-plans when the analysis finishes.
        if (typeof runJob === 'function') runJob(j.job_id, { onDone: () => plan() });
        else say("started — check the Output tab for progress");
      } catch (e) {
        say("could not start: " + String(e.message || e).slice(0, 200));
      }
    });
    on("stPlan", plan);
    on("stRender", async () => {
      if (!proj()) return say("open a project first");
      const params = Object.assign({}, S.params, { style: S.style });
      await fetch(`/api/projects/${encodeURIComponent(PROJECT.slug)}/`.replace(/\/$/, ""), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scene: "amv", params }),
      });
      PROJECT.data.scene = "amv";
      PROJECT.data.params = params;
      if ((typeof startRender === 'function' ? startRender : null)) (typeof startRender === 'function' ? startRender : null)();
      else say("rendering is on the Output tab");
    });
  }

  global.Studio = { open, mount, plan, draw, state: S };
  global.openStudio = () => open();
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mount);
  } else {
    mount();
  }
})(window);
