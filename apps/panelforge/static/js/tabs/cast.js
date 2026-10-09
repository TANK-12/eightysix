"use strict";
/* Cast and voices tab: character cards (rename, merge, split), extras,
   backgrounds and props, and a voice picker per character/narrator.
   Nothing is preselected here: a voice is chosen by hand, or by the model
   looking at the character's pictures when "Cast voices with the model" is
   pressed -- and that never touches a voice chosen by hand. */

(function () {
  const S = {
    series: null,
    cast: [],
    narrator: { voice: null },
    voices: [],
    mergeSet: new Set(),
    firstLines: {}, // cast_id|"narrator" -> text
    apps: [], // every appearance of the working chapter (crops with ledger keys)
    bench: null, // cast id whose crops are open, or "unsorted"
    checked: new Set(), // ledger keys ticked in the crop bench
    chapter: null, // chapter whose lines are listed
    script: null, // that chapter's script.json (lines carry speaker + audio)
    linesFilter: "", // search text for the lines list
    linesUnsure: false, // only lines the model was unsure about
    linesWho: "", // only one speaker's lines ("" = everyone)
    saveTimer: null,
    openLine: null, // line id whose editor (text, voice, expression) is open
    dirty: new Set(), // line ids changed here and not spoken since
  };

  function mount(el) {
    el.innerHTML = `
      <div class="row" style="margin-bottom:12px;align-items:center">
        <span class="ctx-picker">series <input type="text" id="castSeries" style="width:160px">
          <button class="btn" id="castLoad">Load</button></span>
        <span class="spacer" style="flex:1"></span>
        <button class="btn" id="castVoicesAuto" title="The model looks at each character's pictures and gives everyone without a hand-chosen voice a distinct, fitting voice">Cast voices with the model</button>
        <button class="btn" id="castUnsorted" title="Crops the grouping did not place: assign them by hand">Unsorted crops</button>
        <button class="btn" id="castMerge">Merge selected</button>
      </div>
      <div class="card">
        <h3 style="margin-top:0">Narrator</h3>
        <div id="narratorCard"></div>
      </div>
      <div class="card">
        <h3 style="margin-top:0">Named cast</h3>
        <div id="castGrid"><div class="placeholder">Pick a series and load.</div></div>
        <div id="cropBench"></div>
      </div>
      <div class="card">
        <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap">
          <h3 style="margin:0">Lines</h3>
          <span class="ctx-picker">chapter <input type="text" id="linesChapter" style="width:70px"></span>
          <input type="search" id="linesFilter" placeholder="find words…" style="width:160px">
          <select id="linesWho" title="Only the lines of one speaker" style="width:auto"><option value="">everyone</option></select>
          <label style="display:flex;align-items:center;gap:4px;width:auto"><input type="checkbox" id="linesUnsure" style="width:auto"> only unsure</label>
          <span class="spacer" style="flex:1"></span>
          <button class="btn" id="linesSpeak" title="Speaks again every line whose speaker, voice or words you changed here" disabled>Speak changed lines</button>
          <button class="btn" id="linesRender" title="Renders the scroll-reader film of this chapter with the Render tab's settings; the shots follow the new voices">Render scroll film</button>
          <button class="btn" id="linesLoad">Load lines</button>
        </div>
        <div class="sub" style="margin:4px 0 8px">Click a face to change who says a line. Your choice is kept when the script is rebuilt; "Re-speak" makes the sound again with that voice.</div>
        <div id="linesList"><div class="placeholder">Pick a chapter and load its lines.</div></div>
        <audio id="linesHear" style="display:none"></audio>
      </div>
      <div class="card"><h3 style="margin-top:0">Extras</h3><div id="extrasGrid"></div></div>
      <div class="card"><h3 style="margin-top:0">Backgrounds</h3><div id="bgGrid"></div></div>
      <div class="card"><h3 style="margin-top:0">Props</h3><div id="propsGrid"></div></div>
    `;
    $("#castSeries", el).value = PF.state.series || "";
    $("#castLoad", el).addEventListener("click", () => {
      S.series = $("#castSeries", el).value.trim();
      loadAll(el);
    });
    $("#castMerge", el).addEventListener("click", mergeSelected);
    $("#castVoicesAuto", el).addEventListener("click", () => castVoicesAuto(el));
    $("#castUnsorted", el).addEventListener("click", () => openBench("unsorted"));
    $("#linesChapter", el).value = PF.state.chapter || "";
    $("#linesLoad", el).addEventListener("click", () => loadLines(el));
    $("#linesFilter", el).addEventListener("input", (e) => {
      S.linesFilter = e.target.value.trim().toLowerCase();
      renderLines(el);
    });
    $("#linesWho", el).addEventListener("change", (e) => {
      S.linesWho = e.target.value;
      renderLines(el);
    });
    $("#linesUnsure", el).addEventListener("change", (e) => {
      S.linesUnsure = e.target.checked;
      renderLines(el);
    });
    $("#linesList", el).addEventListener("click", (e) => onLinesClick(el, e));
    $("#linesList", el).addEventListener("change", (e) => onLineEditorChange(el, e));
    $("#linesSpeak", el).addEventListener("click", () => speakChanged(el));
    $("#linesRender", el).addEventListener("click", () => renderScroll(el));
    renderNarratorPlaceholder(el);
    document.addEventListener("pf:context", () => {
      if (!S.series) {
        $("#castSeries", el).value = PF.state.series || "";
        S.series = PF.state.series;
        if (S.series) loadAll(el);
      }
    });
    loadVoices(el);
    if (PF.state.series) {
      S.series = PF.state.series;
      loadAll(el);
    }
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }
  const root = () => document.querySelector('[data-panel="cast"]');

  function renderNarratorPlaceholder(el) {
    $("#narratorCard", el).innerHTML = `<div class="placeholder">Pick a series and load to set the narrator's voice.</div>`;
  }

  async function loadVoices(el) {
    try {
      const r = await PF.getJson("/api/voices");
      S.voices = r.voices || r || [];
    } catch (e) {
      S.voices = [];
    }
  }

  async function loadAll(el) {
    if (!S.series) return;
    const grid = $("#castGrid", el);
    grid.innerHTML = `<div class="placeholder">Loading…</div>`;
    if (!S.voices.length) await loadVoices(el);
    await loadFirstLines();
    try {
      const r = await PF.readWithFallback(
        `/api/series/${encodeURIComponent(S.series)}/cast`,
        `/data/series/${encodeURIComponent(S.series)}/cast.json`
      );
      S.cast = r.cast || [];
      S.narrator = r.narrator || { voice: null };
      await loadApps();
      renderNarrator(el);
      renderCast(el);
      renderBench(el);
    } catch (e) {
      PF.handleLoadError(grid, e, "No cast yet \u2014 run Analyze on this chapter.");
      renderNarratorPlaceholder(el);
    }
    ["extras", "backgrounds", "props"].forEach((kind) => loadAssets(el, kind));
  }

  async function loadApps() {
    S.apps = [];
    const chapter = PF.state.chapter;
    if (!chapter) return;
    try {
      const r = await PF.getJson(
        `/api/series/${encodeURIComponent(S.series)}/cast/appearances?chapter=${encodeURIComponent(chapter)}`
      );
      S.apps = r.items || [];
    } catch (e) {
      S.apps = []; // no scene.json for this chapter yet
    }
  }

  async function loadFirstLines() {
    S.firstLines = {};
    const s = S.series,
      c = PF.state.chapter;
    if (!s || !c) return;
    try {
      const script = await PF.readWithFallback(`/api/chapters/${s}/${c}/script`, `/data/series/${s}/chapters/${c}/script.json`);
      (script.lines || []).forEach((l) => {
        const key = l.speaker || "narrator";
        if (!S.firstLines[key] && l.text) S.firstLines[key] = l.text;
      });
    } catch (e) {
      /* fall back to bubbles below */
    }
    try {
      const bubbles = await PF.readWithFallback(`/api/chapters/${s}/${c}/bubbles`, `/data/series/${s}/chapters/${c}/bubbles.json`);
      (bubbles.bubbles || []).forEach((b) => {
        const key = b.speaker || (b.kind === "caption" ? "narrator" : null);
        if (key && !S.firstLines[key] && b.text) S.firstLines[key] = b.text;
      });
    } catch (e) {
      /* no bubbles yet either -- audition falls back to a stock line */
    }
  }

  async function castVoicesAuto(el) {
    if (!S.series) return toast("Load a series first", "err");
    const btn = $("#castVoicesAuto", el);
    btn.disabled = true;
    try {
      const r = await PF.postJson(`/api/series/${S.series}/cast/voices/auto`, {});
      toast("Casting voices: the model is looking at the pictures");
      PF.watchJob(r.job_id, {
        onDone: (res) => {
          btn.disabled = false;
          const n = res && res.result ? res.result.voices : undefined;
          toast(n === undefined ? "Voices cast" : `${n} voices chosen`);
          loadAll(el);
        },
        onError: (msg) => {
          btn.disabled = false;
          toast(`Casting failed: ${msg}`, "err");
        },
      });
    } catch (e) {
      btn.disabled = false;
      toast(`Couldn't start casting: ${e.message}`, "err");
    }
  }

  function voiceOptions(current) {
    const opts = [`<option value="">— pick a voice —</option>`];
    S.voices.forEach((v) => {
      const id = typeof v === "string" ? v : v.id || v.name;
      const label = typeof v === "string" ? v : v.label || v.name || id;
      opts.push(`<option value="${PF.esc(id)}" ${current === id ? "selected" : ""}>${PF.esc(label)}</option>`);
    });
    return opts.join("");
  }

  function renderNarrator(el) {
    const box = $("#narratorCard", el);
    const v = S.narrator.voice || {};
    box.innerHTML = voicePickerHtml("narrator", v, S.firstLines["narrator"] || "This is the narrator's voice.");
    wireVoicePicker(box, "narrator", null);
  }

  function renderCast(el) {
    const grid = $("#castGrid", el);
    if (!S.cast.length) {
      grid.innerHTML = `<div class="placeholder">No named cast yet — run analyze on a chapter in the Chapter tab.</div>`;
      return;
    }
    grid.innerHTML = `<div class="grid-cards">${S.cast
      .map((c) => {
        const sample = (c.samples || [])[0];
        const sampleUrl = sample ? `/data/${sample.replace(/^assets\//, `series/${S.series}/assets/`)}` : null;
        return `
        <div class="card tight cast-card" data-id="${PF.esc(c.id)}">
          ${sampleUrl ? `<img class="thumb" src="${sampleUrl}" onerror="this.style.display='none'">` : `<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:22px">🙂</div>`}
          <div class="row" style="align-items:center;gap:6px">
            <input type="checkbox" class="mergeBox" data-id="${PF.esc(c.id)}" style="width:auto">
            <input type="text" class="nameInput" data-id="${PF.esc(c.id)}" value="${PF.esc(c.name || "")}" placeholder="${PF.esc(
          c.auto_name || "unnamed"
        )}" style="flex:1;font-size:12.5px">
          </div>
          <div class="voicePickerSlot" data-id="${PF.esc(c.id)}"></div>
          ${c.voice && c.voice.source === "model" ? `<div class="muted" style="font-size:11px">model's pick: ${PF.esc(c.voice.why || "")}</div>` : ""}
          <button class="btn small cropsBtn" data-id="${PF.esc(c.id)}" style="margin-top:6px">Crops (${
          S.apps.filter((a) => a.cast_id === c.id).length
        })</button>
        </div>`;
      })
      .join("")}</div>`;
    grid.querySelectorAll(".cropsBtn").forEach((b) => b.addEventListener("click", () => openBench(b.dataset.id)));
    grid.querySelectorAll(".nameInput").forEach((inp) =>
      inp.addEventListener("change", () => renameCast(inp.dataset.id, inp.value))
    );
    grid.querySelectorAll(".mergeBox").forEach((cb) =>
      cb.addEventListener("change", () => {
        if (cb.checked) S.mergeSet.add(cb.dataset.id);
        else S.mergeSet.delete(cb.dataset.id);
      })
    );
    grid.querySelectorAll(".voicePickerSlot").forEach((slot) => {
      const c = S.cast.find((x) => x.id === slot.dataset.id);
      slot.innerHTML = voicePickerHtml(c.id, c.voice || {}, S.firstLines[c.id] || `Hi, I'm ${c.name || c.auto_name}.`);
      wireVoicePicker(slot, c.id, c);
    });
  }

  function voicePickerHtml(who, v, sampleText) {
    return `
      <div class="voice-row">
        <select class="voiceSelect">${voiceOptions(v.kokoro || null)}</select>
        <button class="btn audBtn" title="Speak this character's line with the picked voice">▶ audition</button>
      </div>
      <div class="slider-row">speed <input type="range" class="spd" min="0.6" max="1.6" step="0.05" value="${v.speed ?? 1.0}"><span class="val spdVal">${(v.speed ?? 1.0).toFixed(2)}</span></div>
      <div class="slider-row">pitch <input type="range" class="pit" min="-6" max="6" step="0.5" value="${v.pitch ?? 0}"><span class="val pitVal">${v.pitch ?? 0}</span></div>
      <div class="slider-row">gain <input type="range" class="gan" min="-12" max="12" step="1" value="${v.gain_db ?? 0}"><span class="val ganVal">${v.gain_db ?? 0}</span></div>
      <p class="muted" style="margin:6px 0 0;font-size:11px">line: "${PF.esc((sampleText || "").slice(0, 60))}"</p>
      <audio class="audPlayer" controls style="width:100%;margin-top:6px;display:none"></audio>
    `;
  }

  function wireVoicePicker(box, who, castItem) {
    const sel = box.querySelector(".voiceSelect");
    const spd = box.querySelector(".spd"),
      spdVal = box.querySelector(".spdVal");
    const pit = box.querySelector(".pit"),
      pitVal = box.querySelector(".pitVal");
    const gan = box.querySelector(".gan"),
      ganVal = box.querySelector(".ganVal");
    const commit = async () => {
      const body = {
        kokoro: sel.value || null,
        speed: parseFloat(spd.value),
        pitch: parseFloat(pit.value),
        gain_db: parseFloat(gan.value),
      };
      const path =
        who === "narrator"
          ? `/api/series/${encodeURIComponent(S.series)}/narrator/voice`
          : `/api/series/${encodeURIComponent(S.series)}/cast/${encodeURIComponent(who)}/voice`;
      try {
        await PF.putJson(path, body);
      } catch (e) {
        toast(`Couldn't save voice: ${e.message}`, "err");
      }
    };
    sel.addEventListener("change", commit);
    [
      [spd, spdVal, (v) => v.toFixed(2)],
      [pit, pitVal, (v) => v],
      [gan, ganVal, (v) => v],
    ].forEach(([input, out, fmt]) => {
      input.addEventListener("input", () => (out.textContent = fmt(parseFloat(input.value))));
      input.addEventListener("change", commit);
    });
    box.querySelector(".audBtn").addEventListener("click", () => audition(box, who));
  }

  async function audition(box, who) {
    const sel = box.querySelector(".voiceSelect");
    if (!sel.value) return toast("Pick a voice first", "err");
    const text = (S.firstLines[who] || `Hi, this is a voice test.`).slice(0, 300);
    const speed = parseFloat(box.querySelector(".spd").value);
    const player = box.querySelector(".audPlayer");
    try {
      const res = await fetch("/api/voices/audition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice: sel.value, text, kind: "speech", speed }),
      });
      if (!res.ok) throw new PF.PfError(`audition failed (${res.status})`, res.status);
      const blob = await res.blob();
      player.src = URL.createObjectURL(blob);
      player.style.display = "block";
      player.play().catch(() => {});
    } catch (e) {
      if (e.status === 404) toast("That voice could not be auditioned. Check /api/health.", "err");
      else toast(`Audition failed: ${e.message}`, "err");
    }
  }

  async function renameCast(id, name) {
    const c = S.cast.find((x) => x.id === id);
    if (!c) return;
    c.name = name;
    try {
      await PF.putJson(`/api/series/${encodeURIComponent(S.series)}/cast`, { cast: S.cast, narrator: S.narrator });
      toast("Renamed");
    } catch (e) {
      toast(`Couldn't save: ${e.message}`, "err");
    }
  }

  async function mergeSelected() {
    if (S.mergeSet.size < 2) return toast("Check at least two cast cards first", "err");
    // the server does the merge and writes it to the assignment ledger, so
    // it survives the next analyze run
    const ids = Array.from(S.mergeSet);
    S.mergeSet.clear();
    await castEdit({ merge: [ids], chapter: PF.state.chapter }, "Merged");
  }

  async function castEdit(edit, doneMsg) {
    try {
      const r = await PF.putJson(`/api/series/${encodeURIComponent(S.series)}/cast`, edit);
      S.cast = r.cast || [];
      await loadApps();
      const el = root();
      renderCast(el);
      renderBench(el);
      toast(doneMsg);
    } catch (e) {
      toast(`Couldn't save: ${e.message}`, "err");
    }
  }

  /* Crop bench: the crops of one character, or the unsorted ones, with
     tick boxes and a "move to" control. Every move is a ledger assignment on
     the server (a cast id, a new character, or not a person). */
  function openBench(id) {
    S.bench = S.bench === id ? null : id;
    S.checked.clear();
    renderBench(root());
  }

  function benchItems() {
    if (S.bench === "unsorted") return S.apps.filter((a) => a.placement === "unplaced" || a.placement === "rejected");
    return S.apps.filter((a) => a.cast_id === S.bench);
  }

  function renderBench(el) {
    const box = $("#cropBench", el);
    if (!box) return;
    if (!S.bench) {
      box.innerHTML = "";
      return;
    }
    if (!PF.state.chapter) {
      box.innerHTML = `<div class="placeholder">Pick a chapter in the Library tab to see its crops.</div>`;
      return;
    }
    const items = benchItems();
    const who = S.bench === "unsorted" ? null : S.cast.find((c) => c.id === S.bench);
    const title =
      S.bench === "unsorted"
        ? `Unsorted crops in chapter ${PF.esc(PF.state.chapter)} (${items.length})`
        : `Crops of ${PF.esc((who && (who.name || who.auto_name)) || S.bench)} in chapter ${PF.esc(PF.state.chapter)} (${items.length})`;
    const targets = S.cast
      .filter((c) => c.id !== S.bench)
      .map((c) => `<option value="${PF.esc(c.id)}">${PF.esc(c.name || c.auto_name || c.id)}</option>`)
      .join("");
    box.innerHTML = `
      <div class="crop-bench">
        <div class="row" style="align-items:center;gap:8px;margin:10px 0 8px">
          <strong>${title}</strong>
          <span class="spacer" style="flex:1"></span>
          <label>Move ticked to
            <select id="benchTarget">
              <option value="">…</option>
              ${targets}
              <option value="new">a new character</option>
              <option value="none">not a person</option>
            </select>
          </label>
          <button class="btn small" id="benchMove">Move</button>
          <button class="btn small" id="benchAll">Tick all</button>
          <button class="btn small" id="benchClose">Close</button>
        </div>
        ${
          items.length
            ? `<div class="crop-grid">${items
                .map(
                  (a) => `<label class="crop ${S.checked.has(a.key) ? "on" : ""}" title="${PF.esc(a.key)}">
                <input type="checkbox" data-key="${PF.esc(a.key)}" ${S.checked.has(a.key) ? "checked" : ""}>
                ${a.image ? `<img src="${PF.esc(a.image)}" loading="lazy">` : `<div class="crop-none">?</div>`}
                <span class="crop-cap">${PF.esc(a.panel_id)}${a.placement === "rejected" ? " · not a person" : ""}${a.face ? "" : " · no face"}</span>
              </label>`
                )
                .join("")}</div>`
            : `<div class="placeholder">Nothing here.</div>`
        }
      </div>`;
    box.querySelectorAll(".crop input").forEach((cb) =>
      cb.addEventListener("change", () => {
        if (cb.checked) S.checked.add(cb.dataset.key);
        else S.checked.delete(cb.dataset.key);
        cb.closest(".crop").classList.toggle("on", cb.checked);
      })
    );
    $("#benchClose", box).addEventListener("click", () => openBench(S.bench));
    $("#benchAll", box).addEventListener("click", () => {
      items.forEach((a) => S.checked.add(a.key));
      renderBench(el);
    });
    $("#benchMove", box).addEventListener("click", async () => {
      const target = $("#benchTarget", box).value;
      if (!target) return toast("Pick where the ticked crops go", "err");
      if (!S.checked.size) return toast("Tick at least one crop first", "err");
      const assign = {};
      S.checked.forEach((k) => (assign[k] = target));
      const n = S.checked.size;
      S.checked.clear();
      await castEdit({ assign, chapter: PF.state.chapter }, `Moved ${n} crop${n === 1 ? "" : "s"}`);
    });
  }

  async function loadAssets(el, kind) {
    const grid = $(`#${kind === "backgrounds" ? "bg" : kind}Grid`, el);
    if (!grid) return;
    grid.innerHTML = `<div class="placeholder">Loading…</div>`;
    try {
      const r = await PF.getJson(`/api/series/${encodeURIComponent(S.series)}/assets/${kind}`);
      const items = r.items || r[kind] || r || [];
      if (!items.length) {
        grid.innerHTML = `<div class="placeholder">None yet.</div>`;
        return;
      }
      grid.innerHTML = `<div class="grid-cards">${items
        .map((it) => {
          const pic = it.image || (it.samples || [])[0];
          const img = pic ? `/data/series/${S.series}/${pic}` : null;
          return `<div class="card tight">
            ${img ? `<img class="cover" src="${img}">` : `<div class="cover-fallback">🖼</div>`}
            <div class="name">${PF.esc(it.label || it.id)}</div>
          </div>`;
        })
        .join("")}</div>`;
    } catch (e) {
      PF.handleLoadError(grid, e, "No cast yet \u2014 run Analyze on this chapter.");
    }
  }


  // ---------------------------------------------------------------- lines --
  // Every line of one chapter with the balloon as drawn, so the speaker can
  // be fixed by clicking a face. Edits set `edited` on the line and are
  // saved to script.json; the script builder keeps edited lines.

  function castPic(c) {
    const sample = (c.samples || [])[0];
    return sample ? `/data/${sample.replace(/^assets\//, `series/${S.series}/assets/`)}` : null;
  }

  async function loadLines(el) {
    S.chapter = $("#linesChapter", el).value.trim();
    const list = $("#linesList", el);
    if (!S.series || !S.chapter) {
      list.innerHTML = `<div class="placeholder">Load a series and type a chapter number first.</div>`;
      return;
    }
    list.innerHTML = `<div class="placeholder">Loading…</div>`;
    try {
      S.script = await PF.getJson(`/api/chapters/${S.series}/${S.chapter}/script`);
    } catch (e) {
      PF.handleLoadError(list, e, "No script yet \u2014 build the script on the Timeline tab first.");
      return;
    }
    renderLines(el);
  }

  // The speaker filter lists the narrator and every cast member, with how
  // many lines each has in this chapter.
  function fillWho(el) {
    const sel = $("#linesWho", el);
    const lines = (S.script && S.script.lines) || [];
    const count = (id) => lines.filter((l) => (l.speaker || "") === id).length;
    const opts = [["", `everyone (${lines.length})`], ["narrator", `Narrator (${count("narrator")})`]]
      .concat(S.cast.map((c) => [c.id, `${c.name || c.auto_name || c.id} (${count(c.id)})`]))
      .filter(([id]) => id === "" || count(id) > 0);
    sel.innerHTML = opts.map(([id, label]) => `<option value="${PF.esc(id)}" ${S.linesWho === id ? "selected" : ""}>${PF.esc(label)}</option>`).join("");
  }

  function lineUnsure(line) {
    const m = line.llm || {};
    const b = line.bubble || {};
    if (m.vision_speaker && m.vision_speaker !== line.speaker) return true;
    if (line.kind !== "caption" && line.speaker === "narrator") return true;
    return !line.edited && (b.speaker_conf || 0) < 0.5 && !m.model;
  }

  function renderLines(el) {
    const list = $("#linesList", el);
    const lines = (S.script && S.script.lines) || [];
    if (!lines.length) {
      list.innerHTML = `<div class="placeholder">This chapter has no lines yet.</div>`;
      return;
    }
    fillWho(el);
    const shown = lines.filter((ln) => {
      if (S.linesUnsure && !lineUnsure(ln)) return false;
      if (S.linesWho && (ln.speaker || "") !== S.linesWho) return false;
      if (S.linesFilter && !(ln.text || "").toLowerCase().includes(S.linesFilter)) return false;
      return true;
    });
    const base = `/api/chapters/${S.series}/${S.chapter}`;
    const faces = (line) => {
      const pick = (id, label, inner) =>
        `<button class="face-pick ${line.speaker === id ? "on" : ""}" data-speaker="${PF.esc(id)}" title="${PF.esc(label)}">${inner}</button>`;
      const cast = S.cast.map((c) => {
        const pic = castPic(c);
        const name = c.name || c.auto_name || c.id;
        return pick(c.id, name, pic ? `<img src="${pic}" loading="lazy" alt="">` : `<span>${PF.esc(name.slice(0, 2))}</span>`);
      });
      return pick("narrator", "Narrator", "<span>🎙</span>") + cast.join("") + pick("", "Nobody (skip this line)", "<span>–</span>");
    };
    list.innerHTML =
      `<div class="sub" style="margin-bottom:6px">${shown.length} of ${lines.length} lines</div>` +
      shown
        .map((ln) => {
          const who = ln.speaker === "narrator" ? "Narrator" : (S.cast.find((c) => c.id === ln.speaker) || {}).name || ln.speaker || "nobody";
          const why = (ln.llm && ln.llm.why) || "";
          const audio = ln.audio ? `/data/series/${S.series}/chapters/${S.chapter}/${ln.audio}?t=${ln.dur || 0}` : null;
          return `<div class="line-row ${lineUnsure(ln) ? "unsure" : ""}" data-id="${PF.esc(ln.id)}">
            ${ln.bubble_id ? `<img class="balloon" src="${base}/bubbles/${PF.esc(ln.bubble_id)}/image" loading="lazy" alt="">` : `<div class="balloon"></div>`}
            <div class="line-body">
              <div class="line-text">${PF.esc(ln.text || "")}</div>
              <div class="sub">${PF.esc(who)}${ln.edited ? " · your choice" : ""}${why ? ` · ${PF.esc(why)}` : ""}</div>
              <div class="faces">${faces(ln)}</div>
            </div>
            <div class="line-tools">
              ${audio ? `<audio controls preload="none" src="${audio}"></audio>` : `<span class="sub">no sound yet</span>`}
              <div class="row" style="gap:4px"><button class="btn small" data-act="hear" title="Hear these words in the picked speaker's voice without saving anything">▶ hear</button>
              <button class="btn small" data-act="respeak">Re-speak</button>
              <button class="btn small" data-act="edit">${S.openLine === ln.id ? "Close" : "Edit"}</button></div>
            </div>
          </div>${S.openLine === ln.id ? lineEditor(ln) : ""}`;
        })
        .join("");
  }

  const EXPRESSIONS = ["neutral", "angry", "happy", "sad", "scared", "surprised", "smug", "pained", "determined"];

  // The editor under a line: its words, a voice of its own, and how it is
  // said. Words and voice are saved to script.json; the expression goes
  // through the emotion route, which re-runs the delivery rules and speaks
  // the line again.
  function lineEditor(ln) {
    const ov = ln.voice_override || {};
    const em = ln.emotion || {};
    const face = (em.face && em.face.label) || (em.expression || "");
    const intensity = em.face && em.face.intensity != null ? em.face.intensity : 0.7;
    const opts = S.voices
      .map((v) => `<option value="${PF.esc(v.id)}" ${ov.voice === v.id ? "selected" : ""}>${PF.esc(v.label || v.id)}</option>`)
      .join("");
    return `<div class="line-editor" data-id="${PF.esc(ln.id)}">
      <div class="field"><label>Words</label><textarea class="edText" rows="2">${PF.esc(ln.text || "")}</textarea></div>
      <div class="row" style="gap:10px;flex-wrap:wrap">
        <div class="field"><label>Voice for this line only</label>
          <select class="edVoice"><option value="">— the speaker's own —</option>${opts}</select></div>
        <div class="field"><label>Expression</label>
          <select class="edFace"><option value="">— automatic —</option>${EXPRESSIONS.map((x) => `<option value="${x}" ${face === x ? "selected" : ""}>${x}</option>`).join("")}</select></div>
        <div class="field"><label>How strongly <span class="edIntVal">${intensity.toFixed(1)}</span></label>
          <input type="range" class="edInt" min="0" max="1" step="0.1" value="${intensity}"></div>
      </div>
      <div class="sub">Words and voice are kept when you leave; expression speaks the line again straight away.</div>
    </div>`;
  }

  async function onLineEditorChange(el, e) {
    const box = e.target.closest(".line-editor");
    if (!box || !S.script) return;
    const line = S.script.lines.find((l) => l.id === box.dataset.id);
    if (!line) return;
    const t = e.target;
    if (t.classList.contains("edText")) {
      const words = t.value.trim();
      if (words && words !== line.text) {
        line.text = words;
        line.edited = true;
        markDirty(el, line);
        saveScript();
      }
    } else if (t.classList.contains("edVoice")) {
      const ov = { ...(line.voice_override || {}) };
      if (t.value) ov.voice = t.value;
      else delete ov.voice;
      line.voice_override = ov;
      line.edited = true;
      markDirty(el, line);
      saveScript();
    } else if (t.classList.contains("edFace") || t.classList.contains("edInt")) {
      if (t.classList.contains("edInt")) box.querySelector(".edIntVal").textContent = Number(t.value).toFixed(1);
      const face = box.querySelector(".edFace").value;
      const body = face
        ? { expression: face, intensity: Number(box.querySelector(".edInt").value), speak: true }
        : { reset: true, speak: true };
      try {
        clearTimeout(S.saveTimer);
        await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/script`, S.script);
        const r = await PF.postJson(`/api/chapters/${S.series}/${S.chapter}/script/lines/${line.id}/emotion`, body);
        if (r && r.line) Object.assign(line, r.line);
        toast(r && r.spoken ? "Spoken with that expression" : "Expression set");
        renderLines(el);
      } catch (err) {
        toast("Could not set the expression: " + (err.message || err), "err");
      }
    }
  }

  function markDirty(el, line) {
    if (line.speaker) S.dirty.add(line.id);
    else S.dirty.delete(line.id); // nobody says it: nothing to speak
    updateSpeakButton(el);
  }

  function updateSpeakButton(el) {
    const b = $("#linesSpeak", el);
    b.disabled = !S.dirty.size;
    b.textContent = S.dirty.size ? `Speak ${S.dirty.size} changed line${S.dirty.size === 1 ? "" : "s"}` : "Speak changed lines";
  }

  // One click after a round of edits: every changed line is spoken again
  // with its new speaker, voice or words, one after the other.
  async function speakChanged(el) {
    if (!S.dirty.size || !S.script) return;
    const ids = [...S.dirty];
    const b = $("#linesSpeak", el);
    b.disabled = true;
    clearTimeout(S.saveTimer);
    try {
      await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/script`, S.script);
    } catch (e) {
      toast("Could not save the script: " + (e.message || e), "err");
      updateSpeakButton(el);
      return;
    }
    let done = 0;
    for (const id of ids) {
      const line = S.script.lines.find((l) => l.id === id);
      if (!line) continue;
      b.textContent = `Speaking ${done + 1} of ${ids.length}…`;
      try {
        const r = await PF.postJson(`/api/chapters/${S.series}/${S.chapter}/lines/${id}/voice`, line.voice_override || {});
        if (r && r.audio) Object.assign(line, { audio: r.audio, dur: r.dur });
        S.dirty.delete(id);
        done += 1;
      } catch (err) {
        toast(`Line ${id}: ${err.message || err}`, "err");
      }
    }
    toast(`Spoke ${done} line${done === 1 ? "" : "s"} again`);
    updateSpeakButton(el);
    renderLines(el);
  }

  // The end of the editing loop without leaving the tab: the scroll-reader
  // film, with the Render tab's aspect and sound settings.
  async function renderScroll(el) {
    if (!S.series || !S.chapter) return toast("Load a chapter's lines first", "err");
    if (S.dirty.size) return toast("Speak the changed lines first, so the film has them", "err");
    const st = PF.getSettings();
    const body = {
      mode: "scroll",
      aspect: st.render_aspect || "16:9",
      sound: st.render_sound || "full",
      subtitles: st.render_subtitles,
      pace: st.render_pace,
      out_name: `scroll-${(st.render_aspect || "16:9").replace(":", "x")}`,
    };
    try {
      const r = await PF.postJson(`/api/chapters/${S.series}/${S.chapter}/render`, body);
      toast(r.job_id ? "Rendering the scroll film -- watch Jobs; the file lands in the Render tab's list" : "Render started");
    } catch (e) {
      toast(`Couldn't start the render: ${e.message || e}`, "err");
    }
  }

  // The voice a line would be spoken with right now: its own override,
  // else the picked speaker's cast voice, else the narrator's.
  function voiceForLine(line) {
    const ov = line.voice_override || {};
    if (ov.voice) return ov.voice;
    if (line.speaker === "narrator") return S.narrator && S.narrator.voice && S.narrator.voice.kokoro;
    const c = S.cast.find((x) => x.id === line.speaker);
    return c && c.voice && c.voice.kokoro;
  }

  // A quick listen before committing: the line's words in the voice its
  // current pick would get, straight from the audition route, nothing saved.
  async function hearLine(el, line, btn) {
    const voice = voiceForLine(line);
    if (!voice) return toast("That speaker has no voice yet -- pick one on their card", "err");
    const text = (line.text || "").slice(0, 300);
    if (!text) return toast("Nothing to say", "err");
    btn.disabled = true;
    try {
      const res = await fetch("/api/voices/audition", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ voice, text, kind: line.kind === "caption" ? "caption" : "speech" }),
      });
      if (!res.ok) throw new Error(`audition failed (${res.status})`);
      const player = $("#linesHear", el);
      player.src = URL.createObjectURL(await res.blob());
      player.play().catch(() => {});
    } catch (e) {
      toast(`Could not play it: ${e.message || e}`, "err");
    }
    btn.disabled = false;
  }

  function saveScript() {
    clearTimeout(S.saveTimer);
    S.saveTimer = setTimeout(async () => {
      try {
        await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/script`, S.script);
      } catch (e) {
        toast("Could not save the script: " + (e.message || e));
      }
    }, 400);
  }

  async function onLinesClick(el, e) {
    const row = e.target.closest(".line-row");
    if (!row || !S.script) return;
    const line = S.script.lines.find((l) => l.id === row.dataset.id);
    if (!line) return;
    const face = e.target.closest(".face-pick");
    if (face) {
      line.speaker = face.dataset.speaker || null;
      line.edited = true;
      if (!line.speaker) {
        line.audio = null; // nobody says it: the old sound must not play
        line.dur = null;
      }
      markDirty(el, line);
      saveScript();
      renderLines(el);
      return;
    }
    const hearBtn = e.target.closest("button[data-act=hear]");
    if (hearBtn) {
      hearLine(el, line, hearBtn);
      return;
    }
    const editBtn = e.target.closest("button[data-act=edit]");
    if (editBtn) {
      S.openLine = S.openLine === line.id ? null : line.id;
      renderLines(el);
      return;
    }
    const btn = e.target.closest("button[data-act=respeak]");
    if (btn) {
      btn.disabled = true;
      btn.textContent = "Speaking…";
      try {
        clearTimeout(S.saveTimer);
        await PF.putJson(`/api/chapters/${S.series}/${S.chapter}/script`, S.script);
        const r = await PF.postJson(`/api/chapters/${S.series}/${S.chapter}/lines/${line.id}/voice`, line.voice_override || {});
        if (r && r.line) Object.assign(line, r.line);
        else if (r && r.audio) Object.assign(line, { audio: r.audio, dur: r.dur });
        S.dirty.delete(line.id);
        updateSpeakButton(el);
        toast("Spoken again");
      } catch (err) {
        toast("Could not speak the line: " + (err.message || err));
      }
      renderLines(el);
    }
  }

  PF.registerTab("cast", { label: "Cast & voices", mount });
})();
