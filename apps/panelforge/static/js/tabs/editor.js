"use strict";
/* Chapter / panels editor: a vertical strip of pages with panel boxes and
   bubble overlays, drag/resize, split/merge, a bubble inspector with speaker
   suggestions, and detect/analyze jobs. Saves via PUT with edited:true. */

(function () {
  const S = {
    series: null,
    chapter: null,
    chapterMeta: null, // chapter.json
    pageOffsets: [], // [{idx, top, h, w, file}] in display px, cumulative
    scale: 1,
    panels: [],
    bubbles: [],
    speakerGuesses: {}, // bubble_id -> [{speaker, conf, why}]
    cast: [], // [{id,name}]
    selected: null, // {type:'panel'|'bubble', id}
    mergeSet: new Set(),
    mode: "select", // select | add-panel | split
    dirty: false,
    saveTimer: null,
  };
  const DISPLAY_W = 460;

  function mount(el) {
    el.innerHTML = `
      <div class="strip-toolbar">
        <span class="ctx-picker">series <input type="text" id="edSeries" style="width:120px"> chapter <input type="text" id="edChapter" style="width:80px">
          <button class="btn" id="edLoad">Load</button></span>
        <span class="spacer" style="flex:1"></span>
        <button class="btn" id="edDetect">Run detect</button>
        <button class="btn" id="edAnalyze">Run analyze</button>
        <button class="btn" id="edReadPage" title="The local model reads the page: who speaks, how, and fixes broken words. Needs script/build first; starts Jan if it is not running.">Read page with model</button>
        <span id="edSaveState" class="muted" style="font-size:11.5px"></span>
      </div>
      <div class="editor-layout">
        <div>
          <div class="row" style="margin-bottom:8px" id="edPanelTools">
            <button class="btn" id="edAddPanel">+ panel</button>
            <button class="btn" id="edSplit">Split</button>
            <button class="btn" id="edMerge">Merge selected</button>
            <button class="btn btn-danger" id="edDelete">Delete</button>
          </div>
          <div class="strip-wrap"><div id="edStage" class="strip-stage"></div></div>
        </div>
        <div>
          <div class="inspector card" id="edInspector">
            <div class="placeholder">Select a panel or a bubble on the strip.</div>
          </div>
          <details class="card" id="edWords" style="margin-top:10px">
            <summary style="cursor:pointer;font-weight:600">Series words</summary>
            <div class="muted" style="font-size:11.5px;margin:6px 0">Names and coined words the reader keeps whole. It learns them from the chapters; add ones it misses, ban ones it learned wrongly. Re-detect (or re-clean) to apply.</div>
            <div class="muted" style="font-size:11.5px" id="edWordsLearned"></div>
            <div class="field"><label>Always words</label><textarea id="edWordsAdd" rows="2" placeholder="Bellato, Corite, Ilay"></textarea></div>
            <div class="field"><label>Never words</label><textarea id="edWordsBan" rows="2" placeholder="yoou"></textarea></div>
            <button class="btn small" id="edWordsSave">Save words</button>
          </details>
        </div>
      </div>
    `;
    $("#edWords", el).addEventListener("toggle", () => $("#edWords", el).open && loadWords(el));
    $("#edWordsSave", el).addEventListener("click", () => saveWords(el));
    $("#edSeries", el).value = PF.state.series || "";
    $("#edChapter", el).value = PF.state.chapter || "";
    $("#edLoad", el).addEventListener("click", () => {
      PF.setContext($("#edSeries", el).value.trim(), $("#edChapter", el).value.trim());
    });
    $("#edDetect", el).addEventListener("click", runDetect);
    $("#edAnalyze", el).addEventListener("click", runAnalyze);
    $("#edReadPage", el).addEventListener("click", readPageWithModel);
    $("#edAddPanel", el).addEventListener("click", () => setMode("add-panel"));
    $("#edSplit", el).addEventListener("click", () => setMode("split"));
    $("#edMerge", el).addEventListener("click", mergeSelected);
    $("#edDelete", el).addEventListener("click", deleteSelected);

    document.addEventListener("pf:context", onContext);
    onContext();
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  const root = () => document.querySelector('[data-panel="editor"]');

  function setMode(m) {
    S.mode = m;
    toast(m === "select" ? "Select mode" : m === "add-panel" ? "Drag a rectangle to add a panel" : "Click a line inside a panel to split it");
  }

  function onContext() {
    S.series = PF.state.series;
    S.chapter = PF.state.chapter;
    const el = root();
    if (!el) return;
    $("#edSeries", el).value = S.series || "";
    $("#edChapter", el).value = S.chapter || "";
    if (!S.series || !S.chapter) {
      $("#edStage", el).innerHTML = `<div class="placeholder">No chapter selected yet. Pick one in the Library tab, or type series/chapter above.</div>`;
      return;
    }
    loadAll(el);
  }

  async function loadAll(el) {
    const stage = $("#edStage", el);
    stage.innerHTML = `<div class="placeholder">Loading…</div>`;
    const { series: s, chapter: c } = S;
    try {
      S.chapterMeta = await PF.getJson(`/data/series/${s}/chapters/${c}/chapter.json`);
    } catch (e) {
      PF.handleLoadError(stage, e, "no chapter.json yet — fetch or import this chapter in Library");
      return;
    }
    let strip = null;
    try {
      strip = await PF.getJson(`/data/series/${s}/chapters/${c}/strip.json`);
    } catch (e) {
      /* fine, we'll stack pages by their own heights */
    }
    computeOffsets(strip);

    try {
      const r = await PF.readWithFallback(`/api/chapters/${s}/${c}/panels`, `/data/series/${s}/chapters/${c}/panels.json`);
      S.panels = r.panels || [];
    } catch (e) {
      S.panels = [];
    }
    try {
      const r = await PF.readWithFallback(`/api/chapters/${s}/${c}/bubbles`, `/data/series/${s}/chapters/${c}/bubbles.json`);
      S.bubbles = r.bubbles || [];
    } catch (e) {
      S.bubbles = [];
    }
    try {
      const r = await PF.readWithFallback(`/api/chapters/${s}/${c}/scene`, `/data/series/${s}/chapters/${c}/scene.json`);
      S.speakerGuesses = (r.speakers || {});
    } catch (e) {
      S.speakerGuesses = {};
    }
    try {
      const r = await PF.readWithFallback(`/api/series/${s}/cast`, `/data/series/${s}/cast.json`);
      S.cast = r.cast || [];
    } catch (e) {
      S.cast = [];
    }

    renderStage(el);
    if (!S.panels.length) {
      stage.insertAdjacentHTML(
        "afterbegin",
        `<div class="placeholder">No panels yet. Run detect to cut this chapter into panels.</div>`
      );
    }
  }

  function computeOffsets(strip) {
    const pages = S.chapterMeta.pages || [];
    S.scale = DISPLAY_W / (pages[0] ? pages[0].w : 800);
    const bySeg = {};
    if (strip && strip.segments) strip.segments.forEach((seg) => (bySeg[seg.page_idx] = seg));
    let cum = 0;
    S.pageOffsets = pages.map((p) => {
      const seg = bySeg[p.idx];
      const top = seg ? seg.strip_y : cum;
      cum = top + p.h;
      return { idx: p.idx, top, h: p.h, w: p.w, file: p.file };
    });
  }

  function renderStage(el) {
    const stage = $("#edStage", el);
    const totalH = S.pageOffsets.length ? S.pageOffsets[S.pageOffsets.length - 1].top + S.pageOffsets[S.pageOffsets.length - 1].h : 0;
    stage.style.width = DISPLAY_W + "px";
    stage.style.height = Math.round(totalH * S.scale) + "px";
    const imgs = S.pageOffsets
      .map(
        (p) =>
          `<img class="page" style="position:absolute;top:${Math.round(p.top * S.scale)}px;left:0;width:${DISPLAY_W}px"
                src="/data/series/${S.series}/chapters/${S.chapter}/${p.file}" loading="lazy">`
      )
      .join("");
    stage.innerHTML = `${imgs}<div class="strip-overlay" id="edOverlay"></div>`;
    const overlay = $("#edOverlay", el);
    overlay.addEventListener("pointerdown", (e) => {
      if (e.target === overlay) onStageDown(e, overlay);
    });
    drawBoxes(el);
  }

  function drawBoxes(el) {
    const overlay = $("#edOverlay", el);
    Array.from(overlay.querySelectorAll(".box")).forEach((b) => b.remove());
    S.panels.forEach((p) => overlay.appendChild(makeBox(p, "panel")));
    S.bubbles.forEach((b) => overlay.appendChild(makeBox(b, "bubble")));
  }

  function toDisp(box) {
    const [x, y, w, h] = box;
    return { x: x * S.scale, y: y * S.scale, w: w * S.scale, h: h * S.scale };
  }
  function toStrip(d) {
    return [Math.round(d.x / S.scale), Math.round(d.y / S.scale), Math.round(d.w / S.scale), Math.round(d.h / S.scale)];
  }

  function makeBox(item, type) {
    const d = toDisp(item.box);
    const box = document.createElement("div");
    box.className = "box" + (type === "bubble" ? " bubble" : "");
    box.style.left = d.x + "px";
    box.style.top = d.y + "px";
    box.style.width = d.w + "px";
    box.style.height = d.h + "px";
    box.dataset.id = item.id;
    box.dataset.type = type;
    const label = type === "panel" ? `${item.order}. ${item.kind}` : `${item.kind}${item.speaker ? " · " + item.speaker : ""}`;
    box.innerHTML = `<span class="tag">${PF.esc(label)}</span>
      <div class="rh nw"></div><div class="rh ne"></div><div class="rh sw"></div><div class="rh se"></div>`;
    if (S.selected && S.selected.type === type && S.selected.id === item.id) box.classList.add("selected");
    box.addEventListener("pointerdown", (e) => onBoxDown(e, box, item, type));
    return box;
  }

  function itemsFor(type) {
    return type === "panel" ? S.panels : S.bubbles;
  }
  function findItem(type, id) {
    return itemsFor(type).find((x) => x.id === id);
  }

  function onBoxDown(e, box, item, type) {
    e.stopPropagation();
    if (S.mode === "split" && type === "panel") {
      const rect = box.getBoundingClientRect();
      const yFrac = (e.clientY - rect.top) / rect.height;
      splitPanel(item, yFrac);
      S.mode = "select";
      return;
    }
    if (e.ctrlKey || e.metaKey) {
      if (type === "panel") {
        if (S.mergeSet.has(item.id)) S.mergeSet.delete(item.id);
        else S.mergeSet.add(item.id);
        box.classList.toggle("selected");
      }
      return;
    }
    select(type, item.id);
    const handle = e.target.classList.contains("rh") ? Array.from(e.target.classList).find((c) => c !== "rh") : null;
    const startX = e.clientX,
      startY = e.clientY;
    const d0 = toDisp(item.box);
    const overlay = box.parentElement;
    const scaleRect = overlay.getBoundingClientRect();

    function onMove(ev) {
      const dx = ev.clientX - startX;
      const dy = ev.clientY - startY;
      let { x, y, w, h } = d0;
      if (!handle) {
        x = d0.x + dx;
        y = d0.y + dy;
      } else {
        if (handle.includes("n")) {
          y = d0.y + dy;
          h = d0.h - dy;
        }
        if (handle.includes("s")) h = d0.h + dy;
        if (handle.includes("w")) {
          x = d0.x + dx;
          w = d0.w - dx;
        }
        if (handle.includes("e")) w = d0.w + dx;
      }
      w = Math.max(8, w);
      h = Math.max(8, h);
      box.style.left = x + "px";
      box.style.top = y + "px";
      box.style.width = w + "px";
      box.style.height = h + "px";
      box._pending = { x, y, w, h };
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      if (box._pending) {
        item.box = toStrip(box._pending);
        item.edited = true;
        if (type === "panel") renumberPanels();
        markDirty();
        drawBoxes(root());
        select(type, item.id);
      }
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function onStageDown(e, overlay) {
    if (S.mode !== "add-panel") {
      select(null, null);
      return;
    }
    const rect = overlay.getBoundingClientRect();
    const startX = e.clientX - rect.left,
      startY = e.clientY - rect.top;
    const ghost = document.createElement("div");
    ghost.className = "box";
    ghost.style.left = startX + "px";
    ghost.style.top = startY + "px";
    ghost.style.width = "0px";
    ghost.style.height = "0px";
    overlay.appendChild(ghost);
    function onMove(ev) {
      const x = ev.clientX - rect.left,
        y = ev.clientY - rect.top;
      ghost.style.left = Math.min(startX, x) + "px";
      ghost.style.top = Math.min(startY, y) + "px";
      ghost.style.width = Math.abs(x - startX) + "px";
      ghost.style.height = Math.abs(y - startY) + "px";
    }
    function onUp() {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      const d = {
        x: parseFloat(ghost.style.left),
        y: parseFloat(ghost.style.top),
        w: parseFloat(ghost.style.width),
        h: parseFloat(ghost.style.height),
      };
      ghost.remove();
      if (d.w < 8 || d.h < 8) {
        S.mode = "select";
        return;
      }
      const id = "p" + String(Date.now()).slice(-6);
      S.panels.push({
        id,
        order: 0,
        box: toStrip(d),
        kind: "panel",
        shape: "rect",
        polygon: null,
        image: null,
        edited: true,
      });
      renumberPanels();
      markDirty();
      S.mode = "select";
      drawBoxes(root());
      select("panel", id);
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  }

  function splitPanel(item, yFrac) {
    const [x, y, w, h] = item.box;
    const splitY = Math.round(y + h * yFrac);
    if (splitY <= y + 4 || splitY >= y + h - 4) return;
    const top = { ...item, box: [x, y, w, splitY - y], id: item.id, edited: true };
    const bottom = { ...item, box: [x, splitY, w, y + h - splitY], id: "p" + String(Date.now()).slice(-6), edited: true };
    const i = S.panels.findIndex((p) => p.id === item.id);
    S.panels.splice(i, 1, top, bottom);
    renumberPanels();
    markDirty();
    drawBoxes(root());
  }

  function mergeSelected() {
    if (S.mergeSet.size < 2) return toast("Ctrl-click at least two panels to merge", "err");
    const ids = Array.from(S.mergeSet);
    const items = ids.map((id) => findItem("panel", id)).filter(Boolean);
    if (items.length < 2) return;
    const x0 = Math.min(...items.map((p) => p.box[0]));
    const y0 = Math.min(...items.map((p) => p.box[1]));
    const x1 = Math.max(...items.map((p) => p.box[0] + p.box[2]));
    const y1 = Math.max(...items.map((p) => p.box[1] + p.box[3]));
    const first = items[0];
    first.box = [x0, y0, x1 - x0, y1 - y0];
    first.edited = true;
    S.panels = S.panels.filter((p) => p === first || !ids.includes(p.id));
    S.mergeSet.clear();
    renumberPanels();
    markDirty();
    drawBoxes(root());
    select("panel", first.id);
    toast("Merged");
  }

  function deleteSelected() {
    if (!S.selected) return;
    const { type, id } = S.selected;
    if (type === "panel") S.panels = S.panels.filter((p) => p.id !== id);
    else S.bubbles = S.bubbles.filter((b) => b.id !== id);
    S.selected = null;
    if (type === "panel") renumberPanels();
    markDirty();
    drawBoxes(root());
    renderInspector();
  }

  function renumberPanels() {
    S.panels.sort((a, b) => a.box[1] - b.box[1]);
    S.panels.forEach((p, i) => (p.order = i + 1));
  }

  function select(type, id) {
    S.selected = type ? { type, id } : null;
    drawBoxes(root());
    renderInspector();
  }

  function renderInspector() {
    const el = root();
    const box = $("#edInspector", el);
    if (!S.selected) {
      box.innerHTML = `<div class="placeholder">Select a panel or a bubble on the strip.<br><span class="muted">Ctrl-click panels to pick several, then Merge.</span></div>`;
      return;
    }
    const item = findItem(S.selected.type, S.selected.id);
    if (!item) {
      box.innerHTML = `<div class="placeholder">Gone.</div>`;
      return;
    }
    if (S.selected.type === "panel") renderPanelInspector(box, item);
    else renderBubbleInspector(box, item);
  }

  function renderPanelInspector(box, item) {
    box.innerHTML = `
      <h3>Panel ${item.order}</h3>
      <div class="field">
        <label>Kind</label>
        <select id="insPanelKind">
          ${["panel", "splash", "caption-only", "transition"]
            .map((k) => `<option value="${k}" ${k === item.kind ? "selected" : ""}>${k}</option>`)
            .join("")}
        </select>
      </div>
      <div class="field">
        <label>Shape</label>
        <select id="insPanelShape">
          ${["rect", "slanted", "borderless"]
            .map((k) => `<option value="${k}" ${k === item.shape ? "selected" : ""}>${k}</option>`)
            .join("")}
        </select>
      </div>
      <p class="muted">${item.edited ? "edited by hand" : "from detect"}</p>
    `;
    $("#insPanelKind", box).addEventListener("change", (e) => {
      item.kind = e.target.value;
      item.edited = true;
      markDirty();
      drawBoxes(root());
    });
    $("#insPanelShape", box).addEventListener("change", (e) => {
      item.shape = e.target.value;
      item.edited = true;
      markDirty();
    });
  }

  function renderBubbleInspector(box, item) {
    const speakerOptions = [`<option value="">— none —</option>`, `<option value="narrator" ${item.speaker === "narrator" ? "selected" : ""}>Narrator</option>`]
      .concat(S.cast.map((c) => `<option value="${PF.esc(c.id)}" ${item.speaker === c.id ? "selected" : ""}>${PF.esc(c.name || c.auto_name)}</option>`))
      .join("");
    const guesses = S.speakerGuesses[item.id];
    box.innerHTML = `
      <h3>Bubble</h3>
      <div class="field">
        <label>Text</label>
        <textarea id="insBubbleText" rows="3">${PF.esc(item.text || "")}</textarea>
      </div>
      <div class="field">
        <label>Kind</label>
        <select id="insBubbleKind">
          ${["speech", "thought", "caption", "shout", "whisper", "sfx"]
            .map((k) => `<option value="${k}" ${k === item.kind ? "selected" : ""}>${k}</option>`)
            .join("")}
        </select>
      </div>
      <div class="field">
        <label>Speaker</label>
        <select id="insBubbleSpeaker">${speakerOptions}</select>
      </div>
      ${
        guesses
          ? `<div class="suggest-row">${(Array.isArray(guesses) ? guesses : [guesses])
              .map(
                (g) =>
                  `<button class="suggest-btn" data-speaker="${PF.esc(g.speaker)}" title="${PF.esc(g.why || "")}">
                     ${PF.esc(g.speaker)} (${Math.round((g.conf || 0) * 100)}%)</button>`
              )
              .join("")}</div>`
          : ""
      }
      <p class="muted">${item.edited ? "edited by hand" : `ocr ${Math.round((item.ocr_conf || 0) * 100)}%`}</p>
    `;
    $("#insBubbleText", box).addEventListener("input", (e) => {
      item.text = e.target.value;
      item.edited = true;
      markDirty();
    });
    $("#insBubbleKind", box).addEventListener("change", (e) => {
      item.kind = e.target.value;
      item.edited = true;
      markDirty();
      drawBoxes(root());
    });
    $("#insBubbleSpeaker", box).addEventListener("change", (e) => {
      item.speaker = e.target.value || null;
      item.speaker_conf = 1.0;
      item.edited = true;
      markDirty();
      drawBoxes(root());
    });
    box.querySelectorAll(".suggest-btn").forEach((btn) =>
      btn.addEventListener("click", () => {
        item.speaker = btn.dataset.speaker;
        item.speaker_conf = 1.0;
        item.edited = true;
        markDirty();
        drawBoxes(root());
        renderInspector();
      })
    );
  }

  function markDirty() {
    S.dirty = true;
    const el = root();
    if (el) $("#edSaveState", el).textContent = "unsaved changes…";
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(save, 900);
  }

  async function save() {
    if (!S.dirty || !S.series || !S.chapter) return;
    const el = root();
    const stateEl = el && $("#edSaveState", el);
    if (stateEl) stateEl.textContent = "saving…";
    try {
      await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/panels`, { panels: S.panels });
      await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/bubbles`, { bubbles: S.bubbles });
      S.dirty = false;
      if (stateEl) stateEl.textContent = "saved";
    } catch (e) {
      if (stateEl) stateEl.textContent = `save failed: ${e.message}`;
    }
  }

  async function runDetect() {
    if (!S.series || !S.chapter) return toast("Pick a chapter first", "err");
    const el = root();
    $("#edSaveState", el).textContent = "detecting…";
    try {
      await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/detect`, {}, {
        onProgress: (f) => ($("#edSaveState", el).textContent = `detecting… ${Math.round(f * 100)}%`),
      });
      toast("Detect finished");
      loadAll(el);
    } catch (e) {
      PF.handleLoadError($("#edStage", el), e, "No panels yet \u2014 run Detect on this chapter.");
    }
  }

  const splitWords = (text) => text.split(/[\s,;]+/).map((w) => w.trim()).filter(Boolean);

  async function loadWords(el) {
    if (!S.series) return;
    try {
      const r = await PF.getJson(`/api/series/${S.series}/words`);
      $("#edWordsLearned", el).textContent = r.learned.length
        ? `learned from the chapters: ${r.learned.join(", ")}`
        : "nothing learned yet (needs two chapters read)";
      $("#edWordsAdd", el).value = (r.words || []).join(", ");
      $("#edWordsBan", el).value = (r.banned || []).join(", ");
    } catch (e) {
      $("#edWordsLearned", el).textContent = `couldn't load the words: ${e.message}`;
    }
  }

  async function saveWords(el) {
    if (!S.series) return toast("Pick a series first", "err");
    try {
      await PF.putJson(`/api/series/${S.series}/words`, {
        words: splitWords($("#edWordsAdd", el).value),
        banned: splitWords($("#edWordsBan", el).value),
      });
      toast("Series words saved");
      loadWords(el);
    } catch (e) {
      toast(`Couldn't save the words: ${e.message}`, "err");
    }
  }

  async function readPageWithModel() {
    if (!S.series || !S.chapter) return toast("Pick a chapter first", "err");
    try {
      const took = await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/script/llm`, {});
      toast(
        `Model read the page: ${took.speaker || 0} speakers, ${took.expression || 0} expressions, ` +
          `${took.delivery || 0} deliveries, ${took.fix || 0} word fixes`
      );
    } catch (e) {
      toast(`Model pass failed: ${e.message}`, "err");
    }
  }

  async function runAnalyze() {
    if (!S.series || !S.chapter) return toast("Pick a chapter first", "err");
    const el = root();
    try {
      await PF.runJob(`/api/chapters/${S.series}/${S.chapter}/analyze`, {});
      toast("Analyze finished — speaker suggestions updated");
      loadAll(el);
    } catch (e) {
      toast(`Analyze not ready: ${e.message}`, "err");
    }
  }

  PF.registerTab("editor", { label: "Chapter", mount });
})();
