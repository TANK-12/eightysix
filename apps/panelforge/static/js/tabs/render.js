"use strict";
/* Render tab: aspect/bubbles/subtitles/style/pace/motion/mode settings, a
   render queue with progress and log, and an outputs list with players. */

(function () {
  const S = { styles: [], queue: [] }; // queue: [{jobId, title}]

  function mount(el) {
    const s = PF.getSettings();
    el.innerHTML = `
      <div class="card">
        <h3 style="margin-top:0">Render settings</h3>
        <div class="row">
          <span class="ctx-picker">series <input type="text" id="rdSeries" style="width:140px">
            chapter <input type="text" id="rdChapter" style="width:70px"></span>
        </div>
        <div class="render-settings" style="margin-top:10px">
          <div class="field"><label>Aspect</label>
            <select id="rdAspect">
              <option value="16:9" ${s.render_aspect === "16:9" ? "selected" : ""}>16:9</option>
              <option value="9:16" ${s.render_aspect === "9:16" ? "selected" : ""}>9:16 (vertical)</option>
            </select></div>
          <div class="field"><label>Bubbles</label>
            <select id="rdBubbles">
              <option value="keep" ${s.render_bubbles === "keep" ? "selected" : ""}>Keep originals</option>
              <option value="erase" ${s.render_bubbles === "erase" ? "selected" : ""}>Erase + subtitles</option>
            </select></div>
          <div class="field"><label><input type="checkbox" id="rdSubs" ${s.render_subtitles ? "checked" : ""} style="width:auto"> Subtitles</label></div>
          <div class="field"><label>Style</label><select id="rdStyle"><option value="">chapter default</option></select></div>
          <div id="rdStyleSettings" class="row" style="gap:10px;flex-wrap:wrap"></div>
          <div class="row" id="rdPolicy" style="gap:10px;flex-wrap:wrap;align-items:center" title="What every film does unless you placed the sound by hand on the Timeline tab">
            <div class="field"><label>Voice echo</label>
              <select id="plEcho">
                <option value="none">None (dry voices)</option>
                <option value="comms">Only the radio filter on comms</option>
                <option value="scene">The scene's guess (hall, void…)</option>
              </select></div>
            <div class="field"><label><input type="checkbox" id="plSfx" style="width:auto"> Auto sound effects</label></div>
            <div class="field"><label><input type="checkbox" id="plMusic" style="width:auto"> Auto music</label></div>
            <div class="sub" style="flex-basis:100%">Changing the echo needs the lines spoken again (Cast &amp; voices tab, or the voice step); sound and music changes take effect at the next render.</div>
          </div>
          <div class="field"><label>Mode</label>
            <select id="rdMode">
              <option value="panel-to-panel" ${s.render_mode === "panel-to-panel" ? "selected" : ""}>Panel to panel</option>
              <option value="page-reveal" ${s.render_mode === "page-reveal" ? "selected" : ""}>Page reveal</option>
              <option value="scroll" ${s.render_mode === "scroll" ? "selected" : ""}>Scroll reader (the strip as drawn, nothing cut)</option>
            </select></div>
          <div class="field"><label>Pace <span id="rdPaceVal">${s.render_pace}</span></label>
            <input type="range" id="rdPace" min="0.5" max="2" step="0.1" value="${s.render_pace}"></div>
          <div class="field"><label>Motion strength <span id="rdMotionVal">${s.render_motion}</span></label>
            <input type="range" id="rdMotion" min="0" max="2" step="0.1" value="${s.render_motion}"></div>
          <div class="field"><label>Around the panel</label>
            <select id="rdBackdrop">
              <option value="auto" ${s.render_backdrop === "auto" ? "selected" : ""}>Auto</option>
              <option value="stretch" ${s.render_backdrop === "stretch" ? "selected" : ""}>Stretch the art</option>
              <option value="blur" ${s.render_backdrop === "blur" ? "selected" : ""}>Blurred copy</option>
              <option value="black" ${s.render_backdrop === "black" ? "selected" : ""}>Black</option>
            </select></div>
          <div class="field"><label>Sound</label>
            <select id="rdSound">
              <option value="full" ${s.render_sound === "full" ? "selected" : ""}>Voices, sound and music</option>
              <option value="music" ${s.render_sound === "music" ? "selected" : ""}>Just watch: sound and music, no voices</option>
              <option value="silent" ${s.render_sound === "silent" ? "selected" : ""}>Silent</option>
            </select></div>
          <div class="field"><label>Character layers (3D style) <span id="rdLayersVal">${s.render_layers}</span></label>
            <input type="range" id="rdLayers" min="0" max="1" step="0.05" value="${s.render_layers}"></div>
          <div class="field"><label>First seconds only</label>
            <input type="number" id="rdSeconds" min="0" step="5" placeholder="whole chapter" style="width:130px"></div>
          <div class="field"><label>File name</label>
            <input type="text" id="rdName" placeholder="auto" style="width:150px"></div>
        </div>
        <button class="btn btn-primary" id="rdQueue">Queue render</button>
      </div>
      <div class="card">
        <h3 style="margin-top:0">Render queue</h3>
        <div id="rdQueueList"><div class="placeholder">Nothing queued this session.</div></div>
      </div>
      <div class="card">
        <div class="section-head"><h3>Outputs</h3><button class="btn" id="rdRefreshOut">Refresh</button></div>
        <div id="rdOutputs" class="outputs-list"><div class="placeholder">Loading…</div></div>
      </div>
    `;
    $("#rdSeries", el).value = PF.state.series || "";
    $("#rdChapter", el).value = PF.state.chapter || "";
    document.addEventListener("pf:context", () => {
      $("#rdSeries", el).value = PF.state.series || "";
      $("#rdChapter", el).value = PF.state.chapter || "";
    });
    $("#rdPace", el).addEventListener("input", () => ($("#rdPaceVal", el).textContent = $("#rdPace", el).value));
    $("#rdMotion", el).addEventListener("input", () => ($("#rdMotionVal", el).textContent = $("#rdMotion", el).value));
    $("#rdLayers", el).addEventListener("input", () => ($("#rdLayersVal", el).textContent = $("#rdLayers", el).value));
    $("#rdQueue", el).addEventListener("click", () => queueRender(el));
    $("#rdRefreshOut", el).addEventListener("click", () => loadOutputs(el));
    loadStyles(el);
    loadPolicy(el);
    loadOutputs(el);
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  // The sound policy (audio/policy.py): dry voices, no auto sound effects,
  // no auto music unless asked for -- Emerson's defaults of 2026-09-20.
  async function loadPolicy(el) {
    try {
      const p = await PF.getJson("/api/sound");
      $("#plEcho", el).value = p.echo || "none";
      $("#plSfx", el).checked = !!p.sfx;
      $("#plMusic", el).checked = !!p.music;
    } catch (e) {
      /* older backend without the route: the block stays at its defaults */
    }
    $("#rdPolicy", el).addEventListener("change", async () => {
      const body = { echo: $("#plEcho", el).value, sfx: $("#plSfx", el).checked, music: $("#plMusic", el).checked };
      try {
        await PF.putJson("/api/sound", body);
        toast("Sound policy saved");
      } catch (e) {
        toast(`Could not save the sound policy: ${e.message}`, "err");
      }
    });
  }

  let STYLES = []; // the styles listing, each with its settings schema

  // The chosen style's own knobs (each style declares them in its
  // `settings`): a slider with a number field for numbers, a tick box for
  // yes/no. In scroll mode the scroll style's knobs show whatever the style
  // select says, since every shot is drawn by it. Values live in the
  // editor settings under render_style_settings[style][key] and go to the
  // render as style_settings.
  function styleForKnobs(el) {
    const mode = $("#rdMode", el).value;
    return mode === "scroll" ? "scroll" : $("#rdStyle", el).value;
  }

  function drawStyleSettings(el) {
    const box = $("#rdStyleSettings", el);
    const name = styleForKnobs(el);
    const st = STYLES.find((x) => x.name === name);
    const schema = (st && st.settings) || {};
    const saved = (PF.getSettings().render_style_settings || {})[name] || {};
    box.innerHTML = Object.entries(schema)
      .map(([key, spec]) => {
        const val = saved[key] != null ? saved[key] : spec.default;
        if (spec.type === "bool") {
          return `<div class="field"><label><input type="checkbox" class="rdKnob" data-key="${PF.esc(key)}" ${val ? "checked" : ""} style="width:auto"> ${PF.esc(spec.label || key)}</label></div>`;
        }
        return `<div class="field"><label>${PF.esc(spec.label || key)}</label>
          <div class="row" style="gap:6px;align-items:center">
            <input type="range" class="rdKnob" data-key="${PF.esc(key)}" min="${spec.min}" max="${spec.max}" step="${spec.step || 0.01}" value="${val}">
            <input type="number" class="rdKnobNum" data-key="${PF.esc(key)}" min="${spec.min}" max="${spec.max}" step="${spec.step || 0.01}" value="${val}" style="width:70px">
          </div></div>`;
      })
      .join("");
  }

  function styleSettingsFromForm(el) {
    const name = styleForKnobs(el);
    if (!name) return null;
    const out = {};
    $("#rdStyleSettings", el).querySelectorAll(".rdKnob").forEach((k) => {
      out[k.dataset.key] = k.type === "checkbox" ? k.checked : parseFloat(k.value);
    });
    const all = { ...(PF.getSettings().render_style_settings || {}), [name]: out };
    PF.saveSettings({ render_style_settings: all });
    return Object.keys(out).length ? { [name]: out } : null;
  }

  async function loadStyles(el) {
    try {
      const r = await PF.getJson("/api/styles");
      const styles = r.styles || r || [];
      STYLES = styles.filter((s) => s && typeof s === "object");
      const sel = $("#rdStyle", el);
      styles.forEach((s) => {
        if (s && s.enabled === false) return; // a stub would render as Motion comic
        const id = typeof s === "string" ? s : s.name || s.id;
        const label = typeof s === "string" ? s : s.label || s.name || s.id;
        sel.insertAdjacentHTML("beforeend", `<option value="${PF.esc(id)}">${PF.esc(label)}</option>`);
      });
      drawStyleSettings(el);
      // The scroll reader draws every shot with the scroll style, so a
      // picked style (2.5D, 3D depth, ...) would be silently ignored while
      // the mode is scroll (the default since 2026-09-19). Picking a style
      // therefore switches to panel to panel, and picking scroll clears it.
      sel.addEventListener("change", () => {
        const mode = $("#rdMode", el);
        if (sel.value && sel.value !== "scroll" && mode.value === "scroll") {
          mode.value = "panel-to-panel";
          toast("Scroll reader draws the strip flat, so the mode is now panel to panel for this style");
        }
        drawStyleSettings(el);
      });
      $("#rdMode", el).addEventListener("change", () => {
        if ($("#rdMode", el).value === "scroll") sel.value = "";
        drawStyleSettings(el);
      });
      $("#rdStyleSettings", el).addEventListener("input", (e) => {
        // keep the slider and its number field together
        const t = e.target;
        const twin = t.classList.contains("rdKnob") ? ".rdKnobNum" : t.classList.contains("rdKnobNum") ? ".rdKnob" : null;
        if (!twin) return;
        const other = $(`${twin}[data-key="${t.dataset.key}"]`, $("#rdStyleSettings", el));
        if (other && other.type !== "checkbox") other.value = t.value;
      });
    } catch (e) {
      /* style list not ready; default-only select is still usable */
    }
  }

  function ctx(el) {
    return { s: $("#rdSeries", el).value.trim(), c: $("#rdChapter", el).value.trim() };
  }

  async function queueRender(el) {
    const { s, c } = ctx(el);
    if (!s || !c) return toast("Enter series and chapter", "err");
    const settings = PF.saveSettings({
      render_aspect: $("#rdAspect", el).value,
      render_bubbles: $("#rdBubbles", el).value,
      render_subtitles: $("#rdSubs", el).checked,
      render_mode: $("#rdMode", el).value,
      render_pace: parseFloat($("#rdPace", el).value),
      render_motion: parseFloat($("#rdMotion", el).value),
      render_backdrop: $("#rdBackdrop", el).value,
      render_sound: $("#rdSound", el).value,
      render_layers: parseFloat($("#rdLayers", el).value),
    });
    const body = {
      aspect: settings.render_aspect,
      bubbles: settings.render_bubbles,
      subtitles: settings.render_subtitles,
      mode: settings.render_mode,
      pace: settings.render_pace,
      motion_strength: settings.render_motion,
      backdrop: settings.render_backdrop,
      sound: settings.render_sound,
      layers: settings.render_layers,
    };
    const style = $("#rdStyle", el).value;
    if (style) body.style = style;
    const knobs = styleSettingsFromForm(el);
    if (knobs) body.style_settings = knobs;
    const seconds = parseFloat($("#rdSeconds", el).value);
    if (seconds > 0) body.max_seconds = seconds;
    const name = $("#rdName", el).value.trim();
    if (name) body.out_name = name;
    try {
      const r = await PF.postJson(`/api/chapters/${s}/${c}/render`, body);
      if (r.job_id) {
        addQueueItem(el, r.job_id, `${s} / ${c} · ${settings.render_aspect}`);
      } else {
        toast("Render started");
      }
    } catch (e) {
      if (e.status === 404) toast("The render backend did not answer. Check /api/health.", "err");
      else toast(`Couldn't queue render: ${e.message}`, "err");
    }
  }

  function addQueueItem(el, jobId, title) {
    const list = $("#rdQueueList", el);
    if (list.querySelector(".placeholder")) list.innerHTML = "";
    const item = PF.el(`
      <div class="queue-item" data-job="${jobId}">
        <span class="name">${PF.esc(title)}</span>
        <div class="progress-bar" style="flex:1"><div style="width:0%"></div></div>
        <span class="state" style="font-size:11px;color:var(--muted)">queued</span>
      </div>
    `);
    list.prepend(item);
    const bar = item.querySelector(".progress-bar > div");
    const stateEl = item.querySelector(".state");
    PF.watchJob(jobId, {
      onProgress: (f) => (bar.style.width = Math.round(f * 100) + "%"),
      onDone: () => {
        stateEl.textContent = "done";
        stateEl.style.color = "var(--good)";
        toast("Render finished");
        loadOutputs(document.querySelector('[data-panel="render"]'));
      },
      onError: (msg) => {
        stateEl.textContent = "failed";
        stateEl.style.color = "var(--bad)";
        toast(`Render failed: ${msg}`, "err");
      },
    });
    stateEl.textContent = "running";
  }

  async function loadOutputs(el) {
    if (!el) return;
    const box = $("#rdOutputs", el);
    try {
      const r = await PF.getJson("/api/renders");
      const items = r.renders || r || [];
      if (!items.length) {
        box.innerHTML = `<div class="placeholder">No renders yet.</div>`;
        return;
      }
      box.innerHTML = items
        .map((it) => {
          const url = it.url || it.file;
          return `<div class="out-row">
            <video src="${PF.esc(url)}" controls preload="none"></video>
            <div style="flex:1">
              <div style="font-size:12.5px">${PF.esc(it.series || "")} / ${PF.esc(it.chapter || "")}</div>
              <div class="muted" style="font-size:11px">${PF.esc([it.style, it.sound, it.aspect, it.seconds ? Math.round(it.seconds) + " s" : ""].filter(Boolean).join(" · "))}${it.mtime ? " · " + new Date(it.mtime * 1000).toLocaleString() : ""}</div>
            </div>
          </div>`;
        })
        .join("");
    } catch (e) {
      PF.handleLoadError(box, e, "No renders yet.");
    }
  }

  PF.registerTab("render", { label: "Render", mount });
})();
