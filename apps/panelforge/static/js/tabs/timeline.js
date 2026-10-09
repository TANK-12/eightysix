"use strict";
/* Timeline editor: shot/dialogue/SFX/music tracks, drag to retime, a
   per-shot inspector (style, transition, camera keyframes on a preview
   canvas), and a play-through scrub of the selected range.

   Anything the automation guessed that gets touched here is stamped
   source:"user" (script lines, sfx, music) or edited:true (shots), per
   CONTRACTS, so a re-run of the automation never overwrites it.

   Two fields are used here that CONTRACTS.md does not list, and the two
   endpoints under them, which the backend now has:
     - script.json lines[].source ("auto"|"user") and .voice (per-line
       Kokoro override, null = use the speaker's own voice)
     - POST /api/chapters/{s}/{c}/lines/{id}/voice   (re-speak one line)
     - POST /api/chapters/{s}/{c}/shots/{id}/render  (re-render one shot)
     - POST /api/chapters/{s}/{c}/preview {kind:"range", from_panel, to_panel}
*/

(function () {
  const S = {
    series: null,
    chapter: null,
    timeline: null, // full timeline.json
    script: null, // full script.json
    sfxLib: [],
    musicLib: [],
    styles: [],
    transitions: [],
    px: 40, // pixels per second
    selected: null, // {kind:'shot'|'line'|'sfx'|'music', id}
    range: null, // {from, to} shot ids for play-through
    saveTimer: null,
    dirtyTimeline: false,
    dirtyScript: false,
  };

  function mount(el) {
    el.innerHTML = `
      <div class="strip-toolbar">
        <span class="ctx-picker">series <input type="text" id="tlSeries" style="width:130px"> chapter <input type="text" id="tlChapter" style="width:70px">
          <button class="btn" id="tlLoad">Load</button></span>
        <button class="btn" id="tlAutoTimeline">Auto camera/transitions</button>
        <span class="spacer" style="flex:1"></span>
        <label class="muted" style="font-size:11.5px">zoom <input type="range" id="tlZoom" min="15" max="120" step="5" style="width:100px"></label>
        <span id="tlSaveState" class="muted" style="font-size:11.5px"></span>
      </div>
      <div class="row" style="margin-bottom:8px">
        <button class="btn" id="tlAddSfx">+ SFX</button>
        <button class="btn" id="tlAddMusic">+ music</button>
        <button class="btn" id="tlClearRange">Clear range</button>
        <button class="btn btn-primary" id="tlPlayRange">▶ Preview selected range</button>
        <span class="muted" id="tlRangeLabel" style="font-size:11.5px"></span>
      </div>
      <div class="editor-layout">
        <div style="min-width:0">
          <div class="tl-ruler" id="tlRuler"></div>
          <div class="timeline" id="tlTracks">
            <div class="tl-track"><div class="tl-label">Shots</div><div class="tl-lane" id="laneShots"></div></div>
            <div class="tl-track"><div class="tl-label">Dialogue</div><div class="tl-lane" id="laneLines"></div></div>
            <div class="tl-track"><div class="tl-label">SFX</div><div class="tl-lane" id="laneSfx"></div></div>
            <div class="tl-track"><div class="tl-label">Music</div><div class="tl-lane" id="laneMusic"></div></div>
          </div>
          <div id="tlPeek" style="margin-top:12px"></div>
        </div>
        <div class="inspector card" id="tlInspector"><div class="placeholder">Select a shot, line, SFX or music block. Arrow keys nudge a selected line or sound by 0.1 s (Shift: 1 s).</div></div>
      </div>
    `;
    S.px = PF.getSettings().timeline_px_per_sec || 40;
    $("#tlZoom", el).value = S.px;
    $("#tlSeries", el).value = PF.state.series || "";
    $("#tlChapter", el).value = PF.state.chapter || "";
    $("#tlLoad", el).addEventListener("click", () => {
      PF.setContext($("#tlSeries", el).value.trim(), $("#tlChapter", el).value.trim());
    });
    $("#tlZoom", el).addEventListener("input", (e) => {
      S.px = parseFloat(e.target.value);
      PF.saveSettings({ timeline_px_per_sec: S.px });
      drawTracks(el);
    });
    $("#tlAutoTimeline", el).addEventListener("click", runAutoTimeline);
    $("#tlAddSfx", el).addEventListener("click", () => addSfx(el));
    $("#tlAddMusic", el).addEventListener("click", () => addMusic(el));
    $("#tlClearRange", el).addEventListener("click", () => {
      S.range = null;
      updateRangeLabel(el);
      drawTracks(el);
    });
    $("#tlPlayRange", el).addEventListener("click", () => playRange(el));

    document.addEventListener("pf:context", onContext);
    onContext();
    loadStylesAndTransitions();
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  const root = () => document.querySelector('[data-panel="timeline"]');

  // the transitions registry (GET /api/transitions), so a new transition
  // module shows up here with no edit; the old fixed list is the fallback
  function transitionKinds() {
    const reg = (S.transitions || []).filter((t) => t && t.kind);
    if (reg.length) return reg.map((t) => ({ kind: t.kind, label: t.label || t.kind }));
    return ["cut", "fade", "slide", "whip", "zoom-through", "match"].map((k) => ({ kind: k, label: k }));
  }

  async function loadStylesAndTransitions() {
    try {
      S.styles = ((await PF.getJson("/api/styles")).styles) || [];
    } catch (e) {
      S.styles = [];
    }
    try {
      S.transitions = ((await PF.getJson("/api/transitions")).transitions) || [];
    } catch (e) {
      S.transitions = [];
    }
  }

  function onContext() {
    S.series = PF.state.series;
    S.chapter = PF.state.chapter;
    const el = root();
    if (!el) return;
    $("#tlSeries", el).value = S.series || "";
    $("#tlChapter", el).value = S.chapter || "";
    if (!S.series || !S.chapter) {
      $("#tlTracks", el).innerHTML = `<div class="placeholder">No chapter selected. Pick one in the Library tab.</div>`;
      return;
    }
    loadAll(el);
  }

  async function loadAll(el) {
    const { series: s, chapter: c } = S;
    try {
      S.timeline = await PF.readWithFallback(`/api/chapters/${s}/${c}/timeline`, `/data/series/${s}/chapters/${c}/timeline.json`);
    } catch (e) {
      S.timeline = { settings: {}, shots: [], music: [] };
      $("#laneShots", el).innerHTML = "";
      PF.handleLoadError($("#tlTracks", el), e, "No timeline yet \u2014 press Auto camera/transitions to plan one.");
      return;
    }
    try {
      S.script = await PF.readWithFallback(`/api/chapters/${s}/${c}/script`, `/data/series/${s}/chapters/${c}/script.json`);
    } catch (e) {
      S.script = { lines: [], sfx: [], music: [] };
    }
    try {
      S.sfxLib = ((await PF.getJson("/api/sfx")).items) || (await PF.getJson("/api/sfx")) || [];
    } catch (e) {
      S.sfxLib = [];
    }
    try {
      S.musicLib = ((await PF.getJson("/api/music")).items) || [];
      try {
        S.policy = await PF.getJson("/api/sound");
      } catch (e) {
        S.policy = { echo: "scene", sfx: true, music: true };
      }
    } catch (e) {
      S.musicLib = [];
    }
    drawTracks(el);
  }

  /* ---------------------------------------------------------------------
     Layout helpers: shots carry absolute start/dur already. Dialogue lines
     and SFX are placed relative to the shot that contains their panel;
     music spans from one shot to another (see file header for the schema
     read). */
  function shotFor(panelId) {
    return (S.timeline.shots || []).find((sh) => sh.panel_id === panelId);
  }
  function lineById(id) {
    return (S.script.lines || []).find((l) => l.id === id);
  }
  function totalDur() {
    const shots = S.timeline.shots || [];
    if (!shots.length) return 30;
    const last = shots[shots.length - 1];
    return last.start + last.dur;
  }

  function drawTracks(el) {
    const shots = S.timeline.shots || [];
    const px = S.px;
    const dur = totalDur();
    const width = Math.max(600, Math.round(dur * px) + 200);

    // Ruler
    const ruler = $("#tlRuler", el);
    ruler.style.width = width + "px";
    let ticks = "";
    for (let t = 0; t < dur + 5; t += 5) {
      ticks += `<span style="position:absolute;left:${t * px}px;border-left:1px solid var(--border);padding-left:3px">${t}s</span>`;
    }
    ruler.innerHTML = ticks;

    drawShots(el, width, px);
    drawLines(el, width, px);
    drawSfx(el, width, px);
    drawMusic(el, width, px);
  }

  function laneSetWidth(lane, width) {
    lane.style.minWidth = width + "px";
  }

  function drawShots(el, width, px) {
    const lane = $("#laneShots", el);
    lane.innerHTML = "";
    laneSetWidth(lane, width);
    (S.timeline.shots || []).forEach((sh) => {
      const block = document.createElement("div");
      block.className = "tl-block shot" + (sh.edited ? " user-edited" : "") + (S.selected && S.selected.kind === "shot" && S.selected.id === sh.id ? " selected" : "");
      block.style.left = sh.start * px + "px";
      block.style.width = Math.max(6, sh.dur * px) + "px";
      block.style.backgroundImage = `url(/api/chapters/${S.series}/${S.chapter}/panels/${sh.panel_id}/image)`;
      block.title = `${sh.panel_id}  ${sh.start.toFixed(1)}s + ${sh.dur.toFixed(1)}s`;
      block.dataset.id = sh.id;
      if (S.range && (sh.id === S.range.from || sh.id === S.range.to)) block.style.outline = "2px dashed #fff";
      block.innerHTML = `<div class="rh e" style="right:-3px;top:0;bottom:0;width:8px;cursor:ew-resize;position:absolute"></div>`;
      wireShotDrag(block, sh);
      lane.appendChild(block);
    });
  }

  // A shot's start is not stored: the server lays shots end to end from
  // their durations on every save, so the only drag is the right-hand
  // handle (duration). A press that does not move is a click: select the
  // shot, or with Shift pick a range. The redraw after a drag replaces the
  // block, which used to swallow the browser's click, so a shot could not be
  // selected at all; selection now happens on pointerup instead.
  const CLICK_SLOP = 4; // pixels a press may wander and still be a click

  function wireShotDrag(block, sh) {
    block.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      if (e.target.classList.contains("rh")) dragResize(e, sh);
      else pressShot(e, sh);
    });
  }

  function pressShot(e, sh) {
    const x0 = e.clientX;
    function onUp(ev) {
      window.removeEventListener("pointerup", onUp);
      if (Math.abs(ev.clientX - x0) > CLICK_SLOP) return;
      if (ev.shiftKey && S.selected && S.selected.kind === "shot" && S.selected.id !== sh.id) {
        S.range = { from: S.selected.id, to: sh.id };
        updateRangeLabel(root());
        drawTracks(root());
        return;
      }
      select("shot", sh.id);
    }
    window.addEventListener("pointerup", onUp);
  }

  // lay shots end to end from their durations, as the server does on save
  function relayoutShots() {
    let t = 0;
    (S.timeline.shots || []).forEach((sh) => {
      sh.start = +t.toFixed(4);
      t += sh.dur;
    });
  }

  function dragResize(e, sh) {
    e.stopPropagation();
    const startX = e.clientX;
    const dur0 = sh.dur;
    let frame = 0;
    function onMove(ev) {
      const dt = (ev.clientX - startX) / S.px;
      sh.dur = Math.max(0.3, +(dur0 + dt).toFixed(2));
      relayoutShots();
      if (!frame)
        frame = requestAnimationFrame(() => {
          frame = 0;
          drawTracks(root());
        });
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (sh.dur !== dur0) {
        sh.edited = true;
        markTimelineDirty();
      }
      select("shot", sh.id);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function drawLines(el, width, px) {
    const lane = $("#laneLines", el);
    lane.innerHTML = "";
    laneSetWidth(lane, width);
    (S.timeline.shots || []).forEach((sh) => {
      (sh.lines || []).forEach((ref) => {
        const line = lineById(ref.line_id);
        if (!line) return;
        const abs = sh.start + (ref.at || 0);
        const dur = line.dur || 1.2;
        const block = document.createElement("div");
        block.className = "tl-block line" + (line.source === "user" ? " user-edited" : "") + (S.selected && S.selected.kind === "line" && S.selected.id === line.id ? " selected" : "");
        block.style.left = abs * px + "px";
        block.style.width = Math.max(6, dur * px) + "px";
        block.textContent = line.speaker || "?";
        block.title = (line.text || "") + (line.muted ? " (muted)" : "");
        if (line.muted) block.style.opacity = "0.35";
        block.addEventListener("pointerdown", (e) => dragRelative(e, block, ref, sh, "at", (v) => (ref.at = v)));
        block.addEventListener("click", () => select("line", line.id, { shot: sh, ref }));
        lane.appendChild(block);
      });
    });
  }

  function drawSfx(el, width, px) {
    const lane = $("#laneSfx", el);
    lane.innerHTML = "";
    laneSetWidth(lane, width);
    (S.script.sfx || []).forEach((x) => {
      const sh = shotFor(x.panel_id);
      if (!sh) return;
      const atNum = x.at === "panel-start" ? 0 : Number(x.at) || 0;
      const abs = sh.start + atNum;
      const block = document.createElement("div");
      block.className = "tl-block sfx" + (x.source === "user" ? " user-edited" : "") + (x.muted ? " " : "") + (S.selected && S.selected.kind === "sfx" && S.selected.id === x.id ? " selected" : "");
      const silentByPolicy = x.source !== "user" && !x.edited && S.policy && !S.policy.sfx;
      if (x.muted || silentByPolicy) block.style.opacity = "0.35";
      block.style.left = abs * px + "px";
      block.style.width = "26px";
      block.textContent = "♪".replace("♪", "🔊");
      block.title = x.sound + (silentByPolicy ? " -- auto, silent under the sound policy (Render tab); edit it to keep it" : "");
      block.addEventListener("pointerdown", (e) =>
        dragAbs(e, block, sh, atNum, (newAbs) => {
          x.at = +(newAbs - sh.start).toFixed(2);
          x.source = "user";
        })
      );
      block.addEventListener("click", () => select("sfx", x.id, { shot: sh }));
      lane.appendChild(block);
    });
  }

  function drawMusic(el, width, px) {
    const lane = $("#laneMusic", el);
    lane.innerHTML = "";
    laneSetWidth(lane, width);
    (S.script.music || []).forEach((m) => {
      const from = shotFor(m.from_panel);
      const to = shotFor(m.to_panel);
      if (!from || !to) return;
      const start = from.start;
      const end = to.start + to.dur;
      const block = document.createElement("div");
      block.className = "tl-block music" + (m.source === "user" ? " user-edited" : "") + (S.selected && S.selected.kind === "music" && S.selected.id === m.id ? " selected" : "");
      const silentByPolicy = m.source !== "user" && !m.edited && S.policy && !S.policy.music;
      if (silentByPolicy) block.style.opacity = "0.35";
      block.style.left = start * px + "px";
      block.style.width = Math.max(10, (end - start) * px) + "px";
      block.textContent = m.mood || m.track || "music";
      block.title = (m.track || m.mood || "music") + (silentByPolicy ? " -- auto, silent under the sound policy (Render tab); edit it to keep it" : "") + "\ndrag the ends to trim to a panel, the middle to move";
      block.addEventListener("pointerdown", (e) => dragMusic(e, block, m, start, end));
      block.addEventListener("click", () => select("music", m.id));
      lane.appendChild(block);
    });
  }

  // The shot under a point on the tracks, by time.
  function shotAtTime(t) {
    const shots = S.timeline.shots || [];
    let best = shots[0];
    for (const sh of shots) if (sh.start <= t) best = sh;
    return best;
  }

  // Music blocks snap to panels: drag the left end to change where the music
  // starts, the right end where it stops, the middle to move it whole.
  function dragMusic(e, block, m, start0, end0) {
    e.stopPropagation();
    const rect = block.getBoundingClientRect();
    const edge = 10;
    const grab = e.clientX - rect.left < edge ? "from" : rect.right - e.clientX < edge ? "to" : "move";
    const x0 = e.clientX;
    let moved = false;
    function onMove(ev) {
      const dt = (ev.clientX - x0) / S.px;
      if (Math.abs(dt) < 0.05) return;
      moved = true;
      let from = start0;
      let to = end0;
      if (grab === "from") from = Math.min(start0 + dt, end0 - 0.5);
      else if (grab === "to") to = Math.max(end0 + dt, start0 + 0.5);
      else { from = start0 + dt; to = end0 + dt; }
      const a = shotAtTime(Math.max(0, from));
      const b = shotAtTime(Math.max(0, to - 0.01));
      if (!a || !b) return;
      m.from_panel = a.panel_id;
      m.to_panel = (b.start >= a.start ? b : a).panel_id;
      const s = a.start;
      const bb = b.start >= a.start ? b : a;
      block.style.left = s * S.px + "px";
      block.style.width = Math.max(10, (bb.start + bb.dur - s) * S.px) + "px";
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (!moved) return;
      m.source = "user";
      markScriptDirty();
      drawTracks(root());
      if (S.selected && S.selected.kind === "music" && S.selected.id === m.id) renderInspector();
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function dragRelative(e, block, ref, sh, field, setter) {
    e.stopPropagation();
    const startX = e.clientX;
    const at0 = ref[field] || 0;
    function onMove(ev) {
      const dt = (ev.clientX - startX) / S.px;
      let v = Math.max(0, +(at0 + dt).toFixed(2));
      v = Math.min(v, Math.max(0, sh.dur - 0.05));
      block.style.left = (sh.start + v) * S.px + "px";
      setter(v);
    }
    function onUp(ev) {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (Math.abs(ev.clientX - startX) <= CLICK_SLOP) return;
      markTimelineDirty();
      const line = lineById(ref.line_id);
      if (line) line.source = "user";
      markScriptDirty();
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function dragAbs(e, block, sh, at0Abs, setter) {
    e.stopPropagation();
    const startX = e.clientX;
    const abs0 = sh.start + at0Abs;
    function onMove(ev) {
      const dt = (ev.clientX - startX) / S.px;
      const abs = Math.max(sh.start, abs0 + dt);
      block.style.left = abs * S.px + "px";
      setter(abs);
    }
    function onUp(ev) {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (Math.abs(ev.clientX - startX) > CLICK_SLOP) markScriptDirty();
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function updateRangeLabel(el) {
    $("#tlRangeLabel", el).textContent = S.range ? `range: ${S.range.from} → ${S.range.to} (shift-click a second shot to change it)` : "shift-click two shots to pick a range";
  }

  function select(kind, id, extra) {
    S.selected = { kind, id, extra };
    drawTracks(root());
    renderInspector();
  }

  // Arrow keys nudge the selected line or sound in time (0.1 s, Shift 1 s)
  // while the Timeline tab is showing and no text field has the focus.
  function nudgeSelected(dt) {
    const sel = S.selected;
    if (!sel || !sel.extra || !sel.extra.shot) return false;
    const sh = sel.extra.shot;
    const clampAt = (v) => Math.min(Math.max(0, +v.toFixed(2)), Math.max(0, sh.dur - 0.05));
    if (sel.kind === "line" && sel.extra.ref) {
      sel.extra.ref.at = clampAt((sel.extra.ref.at || 0) + dt);
      const line = lineById(sel.id);
      if (line) line.source = "user";
      markTimelineDirty();
      markScriptDirty();
    } else if (sel.kind === "sfx") {
      const x = (S.script.sfx || []).find((s) => s.id === sel.id);
      if (!x) return false;
      const cur = x.at === "panel-start" ? 0 : Number(x.at) || 0;
      x.at = clampAt(cur + dt);
      x.source = "user";
      markScriptDirty();
    } else return false;
    drawTracks(root());
    renderInspector();
    return true;
  }

  document.addEventListener("keydown", (e) => {
    if (!root() || root().classList.contains("hidden") || root().offsetParent === null) return;
    const t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    const step = (e.shiftKey ? 1.0 : 0.1) * (e.key === "ArrowLeft" ? -1 : 1);
    if (nudgeSelected(step)) e.preventDefault();
  });

  function renderInspector() {
    const el = root();
    const box = $("#tlInspector", el);
    if (!S.selected) {
      box.innerHTML = `<div class="placeholder">Select a shot, line, SFX or music block.</div>`;
      return;
    }
    if (S.selected.kind === "shot") renderShotInspector(box);
    else if (S.selected.kind === "line") renderLineInspector(box);
    else if (S.selected.kind === "sfx") renderSfxInspector(box);
    else if (S.selected.kind === "music") renderMusicInspector(box);
  }

  /* ---------------- Shot inspector: style, transition, camera keys ---- */
  function renderShotInspector(box) {
    const sh = (S.timeline.shots || []).find((x) => x.id === S.selected.id);
    if (!sh) return;
    sh.camera = sh.camera || { keys: [{ t: 0, cx: 0.5, cy: 0.5, zoom: 1, rot: 0 }], shake: 0, auto: true };
    box.innerHTML = `
      <h3>Shot ${PF.esc(sh.panel_id)}</h3>
      <div class="field"><label>Style</label><select id="shStyle">
        <option value="">chapter default</option>
        ${S.styles.filter((s) => typeof s === "string" || s.enabled !== false).map((s) => { const id = typeof s === "string" ? s : s.name || s.id; const label = (typeof s === "object" && s.label) || id; return `<option value="${PF.esc(id)}" ${sh.style === id ? "selected" : ""}>${PF.esc(label)}</option>`; }).join("")}
      </select></div>
      <div class="field"><label><input type="checkbox" id="shTransAuto" ${sh.transition_in && sh.transition_in.auto !== false ? "checked" : ""} style="width:auto"> Transition: auto</label></div>
      <div class="field"><label>Transition kind</label><select id="shTransKind" ${sh.transition_in && sh.transition_in.auto !== false ? "disabled" : ""}>
        ${transitionKinds().map((t) => `<option value="${PF.esc(t.kind)}" ${sh.transition_in && sh.transition_in.kind === t.kind ? "selected" : ""}>${PF.esc(t.label)}</option>`).join("")}
      </select></div>
      <div class="field"><label>Transition duration (s)</label><input type="number" id="shTransDur" step="0.1" min="0" value="${(sh.transition_in && sh.transition_in.dur) ?? 0.3}"></div>
      <div class="field"><label><input type="checkbox" id="shCamAuto" ${sh.camera.auto !== false ? "checked" : ""} style="width:auto"> Camera: auto</label></div>
      <h4 style="margin-bottom:4px">Camera keyframes</h4>
      <div class="camera-canvas-wrap">
        <div class="camera-canvas" id="camCanvas" style="width:200px;height:${Math.round((200 * (sh.panel_h || 1280)) / (sh.panel_w || 800))}px">
          <img src="/api/chapters/${S.series}/${S.chapter}/panels/${sh.panel_id}/image">
          <div class="cam-rect" id="camRect"></div>
        </div>
        <div style="flex:1;min-width:140px">
          <div class="key-list" id="camKeyList"></div>
          <button class="btn" id="camAddKey" style="margin-top:8px;font-size:11px">+ keyframe</button>
        </div>
      </div>
      <div class="row" style="margin-top:12px">
        <button class="btn btn-primary" id="shRerender">Re-render this shot</button>
      </div>
      <div id="shPeek" style="margin-top:10px"></div>
      <p class="muted" style="margin-top:8px">${sh.edited ? "edited by hand" : "from auto camera/transitions"}</p>
    `;
    $("#shStyle", box).addEventListener("change", (e) => {
      sh.style = e.target.value || null;
      sh.edited = true;
      markTimelineDirty();
    });
    $("#shTransAuto", box).addEventListener("change", (e) => {
      sh.transition_in = sh.transition_in || { kind: "cut", dur: 0.3 };
      sh.transition_in.auto = e.target.checked;
      sh.edited = true;
      markTimelineDirty();
      renderShotInspector(box);
    });
    $("#shTransKind", box).addEventListener("change", (e) => {
      sh.transition_in = sh.transition_in || {};
      sh.transition_in.kind = e.target.value;
      sh.transition_in.auto = false;
      sh.edited = true;
      markTimelineDirty();
    });
    $("#shTransDur", box).addEventListener("change", (e) => {
      sh.transition_in = sh.transition_in || {};
      sh.transition_in.dur = parseFloat(e.target.value);
      sh.edited = true;
      markTimelineDirty();
    });
    $("#shCamAuto", box).addEventListener("change", (e) => {
      sh.camera.auto = e.target.checked;
      sh.edited = true;
      markTimelineDirty();
    });
    $("#camAddKey", box).addEventListener("click", () => {
      sh.camera.keys.push({ t: (sh.camera.keys[sh.camera.keys.length - 1]?.t || 0) + 0.5, cx: 0.5, cy: 0.5, zoom: 1, rot: 0 });
      sh.camera.auto = false;
      sh.edited = true;
      markTimelineDirty();
      renderShotInspector(box);
    });
    $("#shRerender", box).addEventListener("click", () => rerenderShot(box, sh));
    renderKeyList(box, sh);
    wireCameraCanvas(box, sh);
  }

  function renderKeyList(box, sh) {
    const list = $("#camKeyList", box);
    list.innerHTML = sh.camera.keys
      .map(
        (k, i) => `
      <div class="k" data-i="${i}">
        <span>t</span><input type="number" class="kt" step="0.1" value="${k.t}">
        <span>zoom</span><input type="number" class="kz" step="0.05" value="${k.zoom}">
        <span>rot</span><input type="number" class="kr" step="1" value="${k.rot}">
        <button class="btn btn-danger kdel" style="padding:2px 6px;font-size:10px">×</button>
      </div>`
      )
      .join("");
    list.querySelectorAll(".k").forEach((row) => {
      const i = Number(row.dataset.i);
      row.querySelector(".kt").addEventListener("change", (e) => {
        sh.camera.keys[i].t = parseFloat(e.target.value);
        sh.edited = true;
        markTimelineDirty();
      });
      row.querySelector(".kz").addEventListener("change", (e) => {
        sh.camera.keys[i].zoom = parseFloat(e.target.value);
        sh.edited = true;
        markTimelineDirty();
        drawCamRect(box, sh, i);
      });
      row.querySelector(".kr").addEventListener("change", (e) => {
        sh.camera.keys[i].rot = parseFloat(e.target.value);
        sh.edited = true;
        markTimelineDirty();
      });
      row.querySelector(".kdel").addEventListener("click", () => {
        sh.camera.keys.splice(i, 1);
        sh.edited = true;
        markTimelineDirty();
        renderShotInspector(box);
      });
    });
  }

  let camActiveKey = 0;
  function wireCameraCanvas(box, sh) {
    camActiveKey = 0;
    drawCamRect(box, sh, camActiveKey);
    const canvas = $("#camCanvas", box);
    const rect = $("#camRect", box);
    rect.addEventListener("pointerdown", (e) => {
      e.stopPropagation();
      const cRect = canvas.getBoundingClientRect();
      function onMove(ev) {
        const cx = Math.min(1, Math.max(0, (ev.clientX - cRect.left) / cRect.width));
        const cy = Math.min(1, Math.max(0, (ev.clientY - cRect.top) / cRect.height));
        sh.camera.keys[camActiveKey].cx = +cx.toFixed(3);
        sh.camera.keys[camActiveKey].cy = +cy.toFixed(3);
        drawCamRect(box, sh, camActiveKey);
      }
      function onUp() {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        sh.camera.auto = false;
        sh.edited = true;
        markTimelineDirty();
      }
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
  }

  function drawCamRect(box, sh, i) {
    const k = sh.camera.keys[i] || sh.camera.keys[0];
    if (!k) return;
    const canvas = $("#camCanvas", box);
    const rect = $("#camRect", box);
    const w = canvas.clientWidth,
      h = canvas.clientHeight;
    const rw = w / Math.max(0.3, k.zoom || 1);
    const rh = h / Math.max(0.3, k.zoom || 1);
    rect.style.width = rw + "px";
    rect.style.height = rh + "px";
    rect.style.left = Math.min(w - rw, Math.max(0, k.cx * w - rw / 2)) + "px";
    rect.style.top = Math.min(h - rh, Math.max(0, k.cy * h - rh / 2)) + "px";
    rect.style.transform = `rotate(${k.rot || 0}deg)`;
  }

  async function rerenderShot(box, sh) {
    const peek = $("#shPeek", box);
    peek.innerHTML = `<div class="placeholder">Re-rendering this shot…</div>`;
    await saveNow();
    try {
      const result = await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/shots/${sh.id}/render`, {});
      const url = result && (result.video || result.url);
      peek.innerHTML = url
        ? `<video src="${PF.esc(url)}" controls autoplay loop style="max-width:260px;border-radius:8px"></video>`
        : `<div class="placeholder">Done, but no preview came back.</div>`;
    } catch (e) {
      if (e.status === 404) {
        peek.innerHTML = `<div class="placeholder">This shot could not be re-rendered; showing the panel quick look instead.</div>`;
        try {
          const result = await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/preview`, { kind: "panel", panel_id: sh.panel_id, style: sh.style || undefined });
          const url = result && result.video;
          if (url) peek.insertAdjacentHTML("beforeend", `<video src="${PF.esc(url)}" controls autoplay loop style="max-width:260px;border-radius:8px;margin-top:6px"></video>`);
        } catch (e2) {
          /* leave the explanatory note above */
        }
      } else {
        toast(`Re-render failed: ${e.message}`, "err");
      }
    }
  }

  /* ---------------- Line inspector -------------------------------------- */
  function renderLineInspector(box) {
    const line = lineById(S.selected.id);
    if (!line) return;
    line.emotion = line.emotion || { speed: 1, gain_db: 0, pause_after: 0.25, reverb: 0 };
    // why the line sounds the way it does: the rule cues, and what the local
    // model read (its speaker, expression, delivery and reason) -- everything
    // automatic is shown so it can be judged and changed here
    const whyHtml = (ln) => {
      const cues = (ln.emotion && ln.emotion.cues) || [];
      const m = ln.llm || {};
      const bits = [];
      if (ln.emotion && ln.emotion.expression && ln.emotion.expression !== "neutral")
        bits.push(`sounds ${PF.esc(ln.emotion.expression)}${ln.emotion.intensity ? " " + Math.round(ln.emotion.intensity * 100) + "%" : ""}`);
      if (cues.length) bits.push(`cues: ${PF.esc(cues.join(", "))}`);
      if (m.model) {
        const parts = [];
        if (m.speaker) parts.push(`speaker ${PF.esc(m.speaker)}${m.speaker_taken ? " (taken)" : ""}`);
        if (m.vision_speaker) parts.push(`seen in the picture: ${PF.esc(m.vision_speaker)}`);
        if (m.expression) parts.push(`${PF.esc(m.expression)}${m.expression_taken ? " (taken)" : ""}`);
        if (m.why) parts.push(`"${PF.esc(m.why)}"`);
        if (m.fix) parts.push(`text fix${m.fix_taken ? " taken" : ""}`);
        bits.push(`model read: ${parts.join(" · ")}`);
      }
      return bits.length ? `<div class="muted" style="font-size:11.5px;margin:-4px 0 8px">${bits.join("<br>")}</div>` : "";
    };
    const castOptions = (getCastCache() || [])
      .map((c) => `<option value="${PF.esc(c.id)}" ${line.speaker === c.id ? "selected" : ""}>${PF.esc(c.name || c.auto_name)}</option>`)
      .join("");
    box.innerHTML = `
      <h3>Dialogue line</h3>
      <div class="field"><label>Text</label><textarea id="lnText" rows="3">${PF.esc(line.text || "")}</textarea></div>
      <div class="field"><label>Speaker</label><select id="lnSpeaker">
        <option value="">— none —</option><option value="narrator" ${line.speaker === "narrator" ? "selected" : ""}>Narrator</option>${castOptions}
      </select></div>
      <div class="field"><label>Voice override (blank = speaker's own voice)</label><input type="text" id="lnVoice" value="${PF.esc(line.voice || "")}" placeholder="kokoro voice id"></div>
      ${whyHtml(line)}
      <div class="slider-row">speed <input type="range" id="lnSpeed" min="0.5" max="2" step="0.05" value="${line.emotion.speed}"><span class="val">${line.emotion.speed}</span></div>
      <div class="slider-row">gain <input type="range" id="lnGain" min="-12" max="12" step="1" value="${line.emotion.gain_db}"><span class="val">${line.emotion.gain_db}</span></div>
      <div class="slider-row">pause after <input type="range" id="lnPause" min="0" max="2" step="0.05" value="${line.emotion.pause_after}"><span class="val">${line.emotion.pause_after}</span></div>
      <div class="slider-row">reverb <input type="range" id="lnReverb" min="0" max="1" step="0.05" value="${line.emotion.reverb}"><span class="val">${line.emotion.reverb}</span></div>
      <div class="field"><label>Room (echo) -- auto rooms are silent under the sound policy; one chosen here always plays</label><select id="lnRoom">
        <option value="">none (dry)</option>${ROOMS.map((r) => `<option value="${r}" ${line.emotion.room === r ? "selected" : ""}>${r}</option>`).join("")}
      </select></div>
      <div class="field"><label><input type="checkbox" id="lnMute" ${line.muted ? "checked" : ""} style="width:auto"> Mute this line (stays in the timing, makes no sound)</label></div>
      <div class="row" style="margin-top:10px">
        <button class="btn btn-primary" id="lnRespeak">Re-speak this line</button>
        <button class="btn" id="lnPreview" ${line.audio ? "" : "disabled"}>▶ preview</button>
      </div>
      <audio id="lnPlayer" controls style="width:100%;margin-top:8px;${line.audio ? "" : "display:none"}" ${line.audio ? `src="/data/series/${S.series}/chapters/${S.chapter}/${line.audio}"` : ""}></audio>
      <p class="muted" style="margin-top:8px">${line.source === "user" ? "edited by hand" : "from auto script build"}</p>
    `;
    $("#lnText", box).addEventListener("input", (e) => {
      line.text = e.target.value;
      line.source = "user";
      markScriptDirty();
    });
    $("#lnSpeaker", box).addEventListener("change", (e) => {
      line.speaker = e.target.value || null;
      line.source = "user";
      markScriptDirty();
    });
    $("#lnVoice", box).addEventListener("change", (e) => {
      line.voice = e.target.value || null;
      line.source = "user";
      markScriptDirty();
    });
    box.querySelectorAll(".slider-row input[type=range]").forEach((inp) => {
      const key = { lnSpeed: "speed", lnGain: "gain_db", lnPause: "pause_after", lnReverb: "reverb" }[inp.id];
      inp.addEventListener("input", (e) => {
        inp.nextElementSibling.textContent = e.target.value;
        line.emotion[key] = parseFloat(e.target.value);
        line.emotion.source = "user"; // set by hand: the sound policy leaves it alone
        line.source = "user";
        markScriptDirty();
      });
    });
    $("#lnRoom", box).addEventListener("change", (e) => {
      if (e.target.value) {
        line.emotion.room = e.target.value;
        if (!line.emotion.reverb) line.emotion.reverb = 0.5;
        if (e.target.value === "comms") line.emotion.eq = "radio";
        else if (e.target.value === "void") line.emotion.eq = "void";
        else delete line.emotion.eq;
      } else {
        delete line.emotion.room;
        delete line.emotion.eq;
        line.emotion.reverb = 0;
      }
      line.emotion.source = "user";
      line.source = "user";
      $("#lnReverb", box).value = line.emotion.reverb;
      $("#lnReverb", box).nextElementSibling.textContent = line.emotion.reverb;
      markScriptDirty();
    });
    $("#lnMute", box).addEventListener("change", (e) => {
      line.muted = e.target.checked;
      line.source = "user";
      markScriptDirty();
      drawTracks(root());
    });
    $("#lnPreview", box).addEventListener("click", () => $("#lnPlayer", box).play());
    $("#lnRespeak", box).addEventListener("click", () => respeakLine(box, line));
  }

  async function respeakLine(box, line) {
    await saveNow();
    try {
      const result = await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/lines/${line.id}/voice`, {
        voice: line.voice || undefined,
      });
      if (result && result.audio) line.audio = result.audio;
      toast("Re-spoken");
      renderLineInspector(box);
    } catch (e) {
      if (e.status === 404) toast("That line could not be re-spoken: the chapter has no script yet.", "err");
      else toast(`Re-speak failed: ${e.message}`, "err");
    }
  }

  /* ---------------- SFX inspector ---------------------------------------- */
  function renderSfxInspector(box) {
    const x = (S.script.sfx || []).find((s) => s.id === S.selected.id);
    if (!x) return;
    const libOptions = S.sfxLib
      .map((s) => {
        const id = typeof s === "string" ? s : s.id || s.sound;
        return `<option value="${PF.esc(id)}" ${x.sound === id ? "selected" : ""}>${PF.esc(id)}</option>`;
      })
      .join("");
    box.innerHTML = `
      <h3>SFX</h3>
      <div class="field"><label>Sound</label><select id="sfxSound"><option value="${PF.esc(x.sound)}">${PF.esc(x.sound)} (current)</option>${libOptions}</select></div>
      <div class="field"><label>Retime (seconds into the panel)</label><input type="number" id="sfxAt" step="0.05" value="${x.at === "panel-start" ? 0 : x.at}"></div>
      <div class="slider-row">gain <input type="range" id="sfxGain" min="-24" max="12" step="1" value="${x.gain_db || 0}"><span class="val">${x.gain_db || 0}</span></div>
      <div class="field"><label><input type="checkbox" id="sfxMute" ${x.muted ? "checked" : ""} style="width:auto"> Mute</label></div>
      <div class="row" style="margin-top:8px">
        <button class="btn" id="sfxAudition">▶ audition</button>
        <button class="btn btn-danger" id="sfxDelete">Delete</button>
      </div>
      <audio id="sfxPlayer" controls style="width:100%;margin-top:8px;display:none"></audio>
      <p class="muted" style="margin-top:8px">${x.source === "user" ? "edited by hand" : "auto-placed"}</p>
    `;
    $("#sfxSound", box).addEventListener("change", (e) => {
      x.sound = e.target.value;
      x.source = "user";
      markScriptDirty();
    });
    $("#sfxAt", box).addEventListener("change", (e) => {
      x.at = parseFloat(e.target.value);
      x.source = "user";
      markScriptDirty();
      drawTracks(root());
    });
    $("#sfxGain", box).addEventListener("input", (e) => {
      e.target.nextElementSibling.textContent = e.target.value;
      x.gain_db = parseFloat(e.target.value);
      x.source = "user";
      markScriptDirty();
    });
    $("#sfxMute", box).addEventListener("change", (e) => {
      x.muted = e.target.checked;
      x.source = "user";
      markScriptDirty();
      drawTracks(root());
    });
    $("#sfxDelete", box).addEventListener("click", () => {
      S.script.sfx = S.script.sfx.filter((s) => s.id !== x.id);
      S.selected = null;
      markScriptDirty();
      drawTracks(root());
      renderInspector();
    });
    $("#sfxAudition", box).addEventListener("click", async () => {
      try {
        const res = await fetch("/api/sfx/audition", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ sound: x.sound }) });
        if (!res.ok) throw new PF.PfError("audition failed", res.status);
        const blob = await res.blob();
        const player = $("#sfxPlayer", box);
        player.src = URL.createObjectURL(blob);
        player.style.display = "block";
        player.play().catch(() => {});
      } catch (e) {
        toast(e.status === 404 ? "That sound is not available to audition." : `Audition failed: ${e.message}`, "err");
      }
    });
  }

  function addSfx(el) {
    if (!S.timeline || !S.timeline.shots || !S.timeline.shots.length) return toast("Load a chapter with shots first", "err");
    const sh = (S.selected && S.selected.kind === "shot" && (S.timeline.shots || []).find((s) => s.id === S.selected.id)) || S.timeline.shots[0];
    S.script.sfx = S.script.sfx || [];
    const id = "x" + String(Date.now()).slice(-6);
    S.script.sfx.push({ id, panel_id: sh.panel_id, source: "user", sound: (S.sfxLib[0] && (S.sfxLib[0].id || S.sfxLib[0])) || "synth:clank", at: 0, gain_db: 0 });
    (sh.sfx = sh.sfx || []).push(id);
    markScriptDirty();
    markTimelineDirty();
    drawTracks(el);
    select("sfx", id);
  }

  /* ---------------- Music inspector --------------------------------------- */
  const MOODS = ["calm", "tense", "action", "mystery", "sad", "happy"];
  const ROOMS = ["small-room", "hall", "outdoor", "vehicle", "comms", "void"];

  function renderMusicInspector(box) {
    const m = (S.script.music || []).find((s) => s.id === S.selected.id);
    if (!m) return;
    const shots = S.timeline.shots || [];
    const panelOptions = shots.map((sh) => `<option value="${PF.esc(sh.panel_id)}">${PF.esc(sh.panel_id)}</option>`).join("");
    const libOptions = S.musicLib
      .map((s) => {
        const id = typeof s === "string" ? s : s.id || s.track;
        return `<option value="${PF.esc(id)}" ${m.track === id ? "selected" : ""}>${PF.esc(id)}</option>`;
      })
      .join("");
    box.innerHTML = `
      <h3>Music</h3>
      <div class="field"><label>Track</label><select id="muTrack"><option value="${PF.esc(m.track || "")}">${PF.esc(m.track || "(none)")} (current)</option>${libOptions}</select></div>
      <div class="field"><label>Mood (used when no track is chosen)</label><select id="muMood">${MOODS.map((x) => `<option value="${x}" ${m.mood === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
      <div class="field"><label>From panel</label><select id="muFrom">${panelOptions}</select></div>
      <div class="field"><label>To panel</label><select id="muTo">${panelOptions}</select></div>
      <div class="slider-row">gain <input type="range" id="muGain" min="-24" max="6" step="1" value="${m.gain_db || -14}"><span class="val">${m.gain_db || -14}</span></div>
      <button class="btn btn-danger" id="muDelete" style="margin-top:8px">Delete</button>
      <p class="muted" style="margin-top:8px">${m.source === "user" ? "edited by hand: always plays" : S.policy && !S.policy.music ? "auto mood music: silent under the sound policy (Render tab) until you edit it" : "auto mood music"}</p>
    `;
    $("#muFrom", box).value = m.from_panel;
    $("#muTo", box).value = m.to_panel;
    $("#muTrack", box).addEventListener("change", (e) => { m.track = e.target.value; m.source = "user"; markScriptDirty(); });
    $("#muMood", box).addEventListener("change", (e) => { m.mood = e.target.value; m.source = "user"; markScriptDirty(); });
    $("#muFrom", box).addEventListener("change", (e) => { m.from_panel = e.target.value; m.source = "user"; markScriptDirty(); drawTracks(root()); });
    $("#muTo", box).addEventListener("change", (e) => { m.to_panel = e.target.value; m.source = "user"; markScriptDirty(); drawTracks(root()); });
    $("#muGain", box).addEventListener("input", (e) => { e.target.nextElementSibling.textContent = e.target.value; m.gain_db = parseFloat(e.target.value); m.source = "user"; markScriptDirty(); });
    $("#muDelete", box).addEventListener("click", () => {
      S.script.music = S.script.music.filter((s) => s.id !== m.id);
      S.timeline.music = (S.timeline.music || []).filter((id) => id !== m.id);
      S.selected = null;
      markScriptDirty();
      markTimelineDirty();
      drawTracks(root());
      renderInspector();
    });
  }

  function addMusic(el) {
    const shots = S.timeline.shots || [];
    if (!shots.length) return toast("Load a chapter with shots first", "err");
    S.script.music = S.script.music || [];
    const id = "m" + String(Date.now()).slice(-6);
    S.script.music.push({ id, from_panel: shots[0].panel_id, to_panel: shots[shots.length - 1].panel_id, mood: "calm", track: (S.musicLib[0] && (S.musicLib[0].id || S.musicLib[0])) || null, source: "user", gain_db: -14 });
    S.timeline.music = S.timeline.music || [];
    S.timeline.music.push(id);
    markScriptDirty();
    markTimelineDirty();
    drawTracks(el);
    select("music", id);
  }

  /* ---------------- Play-through of the selected range -------------------- */
  async function playRange(el) {
    const shots = S.timeline.shots || [];
    if (!shots.length) return;
    const from = S.range ? shots.find((s) => s.id === S.range.from) : shots[0];
    const to = S.range ? shots.find((s) => s.id === S.range.to) : shots[shots.length - 1];
    if (!from || !to) return;
    const startT = Math.min(from.start, to.start);
    const endT = Math.max(from.start + from.dur, to.start + to.dur);
    const peek = $("#tlPeek", el);
    peek.innerHTML = `<div class="muted" style="font-size:11.5px">Scrubbing ${startT.toFixed(1)}s – ${endT.toFixed(1)}s…</div>`;
    const ruler = $("#tlRuler", el);
    const scrub = PF.el(`<div class="tl-scrub"></div>`);
    ruler.appendChild(scrub);
    const t0 = performance.now();
    const durMs = (endT - startT) * 1000;
    function step(now) {
      const frac = Math.min(1, (now - t0) / durMs);
      scrub.style.left = (startT + frac * (endT - startT)) * S.px + "px";
      if (frac < 1) requestAnimationFrame(step);
      else scrub.remove();
    }
    requestAnimationFrame(step);
    // A representative clip alongside the scrub, since there's no combined
    // range-render endpoint yet (suggested: preview {kind:"range", ...}).
    try {
      const result = await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/preview`, { kind: "range", from_panel: from.panel_id, to_panel: to.panel_id });
      const url = result && (result.video || (result.videos && Object.values(result.videos)[0]));
      if (url) peek.insertAdjacentHTML("beforeend", `<video src="${PF.esc(url)}" controls autoplay style="max-width:340px;border-radius:8px;margin-top:6px"></video>`);
    } catch (e) {
      peek.insertAdjacentHTML(
        "beforeend",
        `<div class="muted" style="font-size:11px;margin-top:4px">A combined-range preview clip isn't wired up on the backend yet -- the scrub above still shows timing.</div>`
      );
    }
  }

  /* ---------------- Saving ------------------------------------------------ */
  function markTimelineDirty() {
    S.dirtyTimeline = true;
    scheduleSave();
  }
  function markScriptDirty() {
    S.dirtyScript = true;
    scheduleSave();
  }
  function scheduleSave() {
    const el = root();
    if (el) $("#tlSaveState", el).textContent = "unsaved changes…";
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(saveNow, 900);
  }
  async function saveNow() {
    const el = root();
    const stateEl = el && $("#tlSaveState", el);
    if (!S.series || !S.chapter) return;
    if (stateEl) stateEl.textContent = "saving…";
    try {
      if (S.dirtyTimeline) {
        await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/timeline`, S.timeline);
        S.dirtyTimeline = false;
      }
      if (S.dirtyScript) {
        await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/script`, S.script);
        S.dirtyScript = false;
      }
      if (stateEl) stateEl.textContent = "saved";
    } catch (e) {
      if (stateEl) stateEl.textContent = `save failed: ${e.message}`;
    }
  }

  async function runAutoTimeline() {
    if (!S.series || !S.chapter) return toast("Pick a chapter first", "err");
    try {
      await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/timeline/auto`, {});
      toast("Auto camera/transitions finished");
      loadAll(root());
    } catch (e) {
      toast(e.status === 404 ? "The render backend did not answer. Check /api/health." : `Failed: ${e.message}`, "err");
    }
  }

  function getCastCache() {
    return (window.PF._castCache && window.PF._castCache[S.series]) || [];
  }
  // Best-effort: the cast tab caches its list on window.PF._castCache so the
  // speaker dropdown here has names without a second round trip. Falls back
  // to a direct fetch if that cache is empty.
  document.addEventListener("pf:context", async () => {
    if (!S.series) return;
    try {
      const r = await PF.getJson(`/api/series/${S.series}/cast`);
      window.PF._castCache = window.PF._castCache || {};
      window.PF._castCache[S.series] = r.cast || [];
    } catch (e) {
      /* fine, speaker select just shows narrator/none */
    }
  });

  PF.registerTab("timeline", { label: "Timeline", mount });
})();
