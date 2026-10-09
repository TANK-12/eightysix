"use strict";
/* Previews tab: a style-comparison grid for the same panels, and a quick
   look (about 10s) for any single panel. */

(function () {
  const S = { styles: [] };

  function mount(el) {
    el.innerHTML = `
      <div class="card">
        <h3 style="margin-top:0">Compare styles</h3>
        <div class="row">
          <span class="ctx-picker">series <input type="text" id="pvSeries" style="width:140px">
            chapter <input type="text" id="pvChapter" style="width:70px"></span>
        </div>
        <div class="field" style="margin-top:8px">
          <label>Panel ids (comma separated) — leave blank for the first 5 with dialogue</label>
          <input type="text" id="pvPanels" placeholder="p0001,p0002,p0003,p0004,p0005">
        </div>
        <button class="btn btn-primary" id="pvCompare">Compare styles</button>
        <div id="pvGrid" class="preview-grid" style="margin-top:14px"></div>
      </div>
      <div class="card">
        <h3 style="margin-top:0">Quick look</h3>
        <div class="row">
          <div class="field" style="width:160px"><label>Panel id</label><input type="text" id="qlPanel" placeholder="p0001"></div>
          <div class="field" style="width:160px"><label>Style (optional)</label><select id="qlStyle"><option value="">chapter default</option></select></div>
        </div>
        <button class="btn btn-primary" id="qlRun">Quick look (~10s)</button>
        <div id="qlOut" style="margin-top:12px"></div>
      </div>
    `;
    $("#pvSeries", el).value = PF.state.series || "";
    $("#pvChapter", el).value = PF.state.chapter || "";
    $("#pvCompare", el).addEventListener("click", () => compare(el));
    $("#qlRun", el).addEventListener("click", () => quickLook(el));
    document.addEventListener("pf:context", () => {
      $("#pvSeries", el).value = PF.state.series || "";
      $("#pvChapter", el).value = PF.state.chapter || "";
    });
    loadStyles(el);
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  async function loadStyles(el) {
    try {
      const r = await PF.getJson("/api/styles");
      S.styles = r.styles || r || [];
      const sel = $("#qlStyle", el);
      S.styles.forEach((s) => {
        const id = typeof s === "string" ? s : s.id;
        const label = typeof s === "string" ? s : s.label || s.id;
        sel.insertAdjacentHTML("beforeend", `<option value="${PF.esc(id)}">${PF.esc(label)}</option>`);
      });
    } catch (e) {
      /* styles list not ready; the style select stays at "chapter default" */
    }
  }

  function ctx(el) {
    return { s: $("#pvSeries", el).value.trim(), c: $("#pvChapter", el).value.trim() };
  }

  async function compare(el) {
    const { s, c } = ctx(el);
    if (!s || !c) return toast("Enter series and chapter", "err");
    const grid = $("#pvGrid", el);
    grid.innerHTML = `<div class="placeholder">Rendering previews for every style…</div>`;
    const panelsRaw = $("#pvPanels", el).value.trim();
    const body = { kind: "styles" };
    if (panelsRaw) body.panels = panelsRaw.split(",").map((x) => x.trim()).filter(Boolean);
    try {
      const result = await PF.runJob(`/api/chapters/${s}/${c}/preview`, body);
      const videos = (result && result.videos) || {};
      const keys = Object.keys(videos);
      if (!keys.length) {
        grid.innerHTML = `<div class="placeholder">No styles came back.</div>`;
        return;
      }
      grid.innerHTML = keys
        .map(
          (style) => `
        <div class="preview-cell">
          <video src="${PF.esc(videos[style])}" autoplay muted loop playsinline></video>
          <div class="label">${PF.esc(style)}</div>
        </div>`
        )
        .join("");
    } catch (e) {
      PF.handleLoadError(grid, e, "No style previews yet \u2014 analyse the chapter first, then try again.");
    }
  }

  async function quickLook(el) {
    const { s, c } = ctx(el);
    const panelId = $("#qlPanel", el).value.trim();
    if (!s || !c || !panelId) return toast("Enter series, chapter and a panel id", "err");
    const out = $("#qlOut", el);
    out.innerHTML = `<div class="placeholder">Rendering a quick look…</div>`;
    const body = { kind: "panel", panel_id: panelId };
    const style = $("#qlStyle", el).value;
    if (style) body.style = style;
    try {
      const result = await PF.runJob(`/api/chapters/${s}/${c}/preview`, body);
      const url = result && result.video;
      out.innerHTML = url
        ? `<video src="${PF.esc(url)}" controls autoplay loop style="max-width:360px;border-radius:8px"></video>`
        : `<div class="placeholder">No video came back.</div>`;
    } catch (e) {
      PF.handleLoadError(out, e, "No quick look yet \u2014 analyse the chapter first, then try again.");
    }
  }

  PF.registerTab("previews", { label: "Previews", mount });
})();
