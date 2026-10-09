"use strict";
/* PanelForge shell: tab wiring, the jobs drawer, the settings drawer, and
   the series/chapter context badge. Tab modules (static/js/tabs/*.js) have
   already registered themselves into PF.tabs by the time this runs. */

const TAB_ORDER = ["library", "editor", "cast", "previews", "timeline", "render"];

function $(sel, root) {
  return (root || document).querySelector(sel);
}

function buildNav() {
  const nav = $("#tabNav");
  const main = $("#tabMain");
  TAB_ORDER.forEach((id, i) => {
    const mod = PF.tabs[id];
    if (!mod) return;
    const tab = document.createElement("div");
    tab.className = "tab" + (i === 0 ? " active" : "");
    tab.dataset.tab = id;
    tab.textContent = mod.label;
    nav.appendChild(tab);
    const panel = document.createElement("div");
    panel.className = "panel" + (i === 0 ? " active" : "");
    panel.dataset.panel = id;
    main.appendChild(panel);
  });
}

const mounted = {};
function selectTab(id) {
  const mod = PF.tabs[id];
  if (!mod) return;
  const panel = document.querySelector(`.panel[data-panel="${id}"]`);
  if (!mounted[id]) {
    mod.mount(panel);
    mounted[id] = true;
  } else if (mod.enter) {
    mod.enter();
  }
  history.replaceState(null, "", "#" + id);
}

function renderContextBadge() {
  const el = $("#ctxBadge");
  if (!el) return;
  el.textContent = PF.state.series ? `${PF.state.series} / ${PF.state.chapter || "—"}` : "no chapter selected";
}
PF.renderContextBadge = renderContextBadge;

/* -------------------------------------------------------------------------
   Jobs drawer
   ------------------------------------------------------------------------- */
function jobStateClass(j) {
  return j.state || "queued";
}

async function refreshJobsDrawer() {
  const body = $("#jobsDrawerBody");
  try {
    const r = await PF.getJson("/api/jobs");
    const jobs = (r.jobs || []).slice().sort((a, b) => (b.created || 0) - (a.created || 0));
    const running = jobs.filter((j) => j.state === "running" || j.state === "queued").length;
    const badge = $("#jobsBadge");
    badge.textContent = running;
    badge.classList.toggle("hidden", running === 0);
    if (!jobs.length) {
      body.innerHTML = `<div class="placeholder">No jobs yet.</div>`;
      return;
    }
    body.innerHTML = jobs
      .slice(0, 30)
      .map(
        (j) => `
      <div class="job-item">
        <div class="top">
          <span class="title">${PF.esc(j.title || j.kind)}</span>
          <span class="state ${jobStateClass(j)}">${PF.esc(j.state)}</span>
        </div>
        <div class="progress-bar"><div style="width:${Math.round((j.progress || 0) * 100)}%"></div></div>
        ${j.error ? `<div class="muted" style="color:var(--bad)">${PF.esc(j.error)}</div>` : ""}
        ${j.state === "running" || j.state === "queued" ? `<button class="btn btn-danger" data-cancel="${j.id}" style="margin-top:6px;font-size:11px;padding:3px 9px">Cancel</button>` : ""}
      </div>`
      )
      .join("");
    body.querySelectorAll("[data-cancel]").forEach((b) =>
      b.addEventListener("click", async () => {
        await fetch(`/api/jobs/${b.dataset.cancel}/cancel`, { method: "POST" });
        refreshJobsDrawer();
      })
    );
  } catch (e) {
    body.innerHTML = `<div class="placeholder">Couldn't reach /api/jobs.</div>`;
    return false;
  }
}

function setDrawer(el, open) {
  el.classList.toggle("open", open);
  $("#scrim").classList.toggle("open", open);
}

/* -------------------------------------------------------------------------
   Settings drawer -- real, persisted settings (localStorage; see
   PF.getSettings/saveSettings in core.js), not fixed values. Render and
   export tabs read these as their defaults.
   ------------------------------------------------------------------------- */
function renderSettings() {
  const body = $("#settingsDrawerBody");
  const s = PF.getSettings();
  body.innerHTML = `
    <div class="settings-group">
      <h4>Render defaults</h4>
      <div class="field"><label>Aspect</label>
        <select id="setAspect">
          <option value="16:9" ${s.render_aspect === "16:9" ? "selected" : ""}>16:9</option>
          <option value="9:16" ${s.render_aspect === "9:16" ? "selected" : ""}>9:16 (vertical)</option>
        </select></div>
      <div class="field"><label>Bubbles</label>
        <select id="setBubbles">
          <option value="keep" ${s.render_bubbles === "keep" ? "selected" : ""}>Keep originals</option>
          <option value="erase" ${s.render_bubbles === "erase" ? "selected" : ""}>Erase + subtitles</option>
        </select></div>
      <div class="field"><label><input type="checkbox" id="setSubs" ${s.render_subtitles ? "checked" : ""} style="width:auto"> Subtitles</label></div>
      <div class="field"><label>Mode</label>
        <select id="setMode">
          <option value="panel-to-panel" ${s.render_mode === "panel-to-panel" ? "selected" : ""}>Panel to panel</option>
          <option value="page-reveal" ${s.render_mode === "page-reveal" ? "selected" : ""}>Page reveal</option>
          <option value="scroll" ${s.render_mode === "scroll" ? "selected" : ""}>Scroll reader</option>
        </select></div>
      <div class="field"><label>Pace <span id="paceVal">${s.render_pace}</span></label>
        <input type="range" id="setPace" min="0.5" max="2" step="0.1" value="${s.render_pace}"></div>
      <div class="field"><label>Motion strength <span id="motionVal">${s.render_motion}</span></label>
        <input type="range" id="setMotion" min="0" max="2" step="0.1" value="${s.render_motion}"></div>
      <div class="field"><label>Around the panel</label>
        <select id="setBackdrop">
          <option value="auto" ${s.render_backdrop === "auto" ? "selected" : ""}>Auto</option>
          <option value="stretch" ${s.render_backdrop === "stretch" ? "selected" : ""}>Stretch the art</option>
          <option value="blur" ${s.render_backdrop === "blur" ? "selected" : ""}>Blurred copy</option>
          <option value="black" ${s.render_backdrop === "black" ? "selected" : ""}>Black</option>
        </select></div>
      <div class="field"><label>Sound</label>
            <select id="setSound">
              <option value="full" ${s.render_sound === "full" ? "selected" : ""}>Voices, sound and music</option>
              <option value="music" ${s.render_sound === "music" ? "selected" : ""}>Just watch: sound and music, no voices</option>
              <option value="silent" ${s.render_sound === "silent" ? "selected" : ""}>Silent</option>
            </select></div>
      <div class="field"><label>Character layers (3D style) <span id="layersVal">${s.render_layers}</span></label>
            <input type="range" id="setLayers" min="0" max="1" step="0.05" value="${s.render_layers}"></div>
    </div>
    <div class="settings-group">
      <h4>Library</h4>
      <div class="field"><label>Kindle export preset</label>
        <select id="setExportPreset">
          <option value="kindle" ${s.export_preset === "kindle" ? "selected" : ""}>Kindle</option>
          <option value="full" ${s.export_preset === "full" ? "selected" : ""}>Full resolution</option>
        </select></div>
    </div>
    <div class="settings-group">
      <h4>Timeline</h4>
      <div class="field"><label>Pixels per second <span id="pxVal">${s.timeline_px_per_sec}</span></label>
        <input type="range" id="setPxPerSec" min="15" max="120" step="5" value="${s.timeline_px_per_sec}"></div>
    </div>
    <div class="settings-group">
      <h4>Local model (Jan)</h4>
      <div class="muted" style="font-size:11.5px;margin-bottom:6px">The model that reads pages (who speaks, how, word fixes). Loaded when needed, released when idle; Jan is started if it is not running.</div>
      <div id="jan-settings"><div class="placeholder">Loading…</div></div>
    </div>
  `;
  if (window.ForgeJan && ForgeJan.panel) {
    try {
      ForgeJan.panel(document.getElementById("jan-settings"), { labels: { script: "Page reading" } });
    } catch (e) {
      document.getElementById("jan-settings").innerHTML = `<div class="placeholder">Jan settings not available: ${e.message}</div>`;
    }
  }
  const save = () =>
    PF.saveSettings({
      render_aspect: $("#setAspect").value,
      render_bubbles: $("#setBubbles").value,
      render_subtitles: $("#setSubs").checked,
      render_mode: $("#setMode").value,
      render_pace: parseFloat($("#setPace").value),
      render_motion: parseFloat($("#setMotion").value),
      render_backdrop: $("#setBackdrop").value,
      render_sound: $("#setSound").value,
      render_layers: parseFloat($("#setLayers").value),
      export_preset: $("#setExportPreset").value,
      timeline_px_per_sec: parseFloat($("#setPxPerSec").value),
    });
  body.querySelectorAll("input, select").forEach((inp) =>
    inp.addEventListener("input", () => {
      const pv = $("#paceVal"),
        mv = $("#motionVal"),
        xv = $("#pxVal");
      if (pv) pv.textContent = $("#setPace").value;
      if (mv) mv.textContent = $("#setMotion").value;
      const lv = $("#layersVal");
      if (lv) lv.textContent = $("#setLayers").value;
      if (xv) xv.textContent = $("#setPxPerSec").value;
      save();
    })
  );
}

/* -------------------------------------------------------------------------
   Health strip -- a small note under the tab bar when a module failed to
   import, so a blank tab has an explanation instead of just being blank.
   ------------------------------------------------------------------------- */
function renderHealthNote() {
  const el = $("#healthNote");
  if (!PF.reachable) {
    el.classList.remove("hidden");
    el.textContent = "The PanelForge server is not answering. Retrying every half minute or so.";
    return false;
  }
  const failed = Object.keys(PF.health.failed || {});
  if (!failed.length) {
    el.classList.add("hidden");
    return;
  }
  el.classList.remove("hidden");
  el.textContent = `Not loaded yet: ${failed.join(", ")} — those tabs will show a "not ready" message until they land.`;
}

document.addEventListener("DOMContentLoaded", () => {
  buildNav();
  const select = initTabs(selectTab);
  const startTab = (location.hash || "").slice(1);
  select(TAB_ORDER.includes(startTab) ? startTab : TAB_ORDER[0]);

  renderContextBadge();
  document.addEventListener("pf:context", renderContextBadge);

  $("#jobsBtn").addEventListener("click", () => {
    setDrawer($("#jobsDrawer"), true);
    refreshJobsDrawer();
  });
  $("#settingsBtn").addEventListener("click", () => {
    setDrawer($("#settingsDrawer"), true);
    renderSettings();
  });
  $("#scrim").addEventListener("click", () => {
    setDrawer($("#jobsDrawer"), false);
    setDrawer($("#settingsDrawer"), false);
  });
  document.querySelectorAll("[data-close-drawer]").forEach((b) =>
    b.addEventListener("click", () => {
      setDrawer($("#jobsDrawer"), false);
      setDrawer($("#settingsDrawer"), false);
    })
  );

  PF.refreshHealth().then(renderHealthNote);
  // both polls stretch their wait while the server is not answering
  ForgeIdle.poll(() => PF.refreshHealth().then(renderHealthNote), 15000, {
    backoff: 2,
    maxMs: 30000,
  });
  ForgeIdle.poll(
    () => {
      if ($("#jobsDrawer").classList.contains("open")) return refreshJobsDrawer();
    },
    2000,
    { backoff: 2, maxMs: 30000 }
  );
  refreshJobsDrawer();
});
