"use strict";
/* Library tab: fetch by link, import folders/archives, browse MediaForge
   downloads, a series/chapter browser with covers, and Kindle PDF export. */

(function () {
  const state = {
    fetchResult: null, // {title, series, chapters:[{number,title,url,group}], groups}
    group: null, // chosen scan group when the site lists more than one
    series: [], // [{series,...}] from GET /api/series
    seriesChapters: {}, // series -> chapters list
    exportSeries: null,
    exportChapters: new Set(),
  };

  function mount(el) {
    el.innerHTML = `
      <div class="card">
        <h3 style="margin-top:0">Fetch from a link</h3>
        <div class="row">
          <div class="field" style="flex:1">
            <label>Title or chapter link</label>
            <input type="text" id="libUrl" placeholder="https://comix.to/title/...">
          </div>
        </div>
        <div class="row">
          <button class="btn btn-primary" id="libLookup">Look up</button>
          <span class="muted" id="libSourcesNote"></span>
        </div>
        <div id="libFetchResult" style="margin-top:12px"></div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Run chapters</h3>
        <div class="muted" style="font-size:12px;margin-bottom:8px">Every chosen step, chapter after chapter, as one job. Missing chapters are fetched first when "fetch" is ticked.</div>
        <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap">
          <label>series <input type="text" id="runSeries" style="width:150px"></label>
          <label>from <input type="number" id="runFirst" min="1" value="1" style="width:70px"></label>
          <label>to <input type="number" id="runLast" min="1" value="10" style="width:70px"></label>
          <label>scan group <input type="text" id="runGroup" placeholder="e.g. WebToon" style="width:110px"></label>
        </div>
        <div class="row" id="runSteps" style="gap:10px;flex-wrap:wrap;margin:8px 0">
          ${["fetch", "detect", "analyze", "script", "llm", "voice", "audio", "timeline", "render"]
            .map((st) => `<label class="chip"><input type="checkbox" class="runStep" value="${st}" checked style="width:auto"> ${st}</label>`)
            .join("")}
        </div>
        <div class="row" style="align-items:center;gap:8px;flex-wrap:wrap">
          <button class="btn btn-primary" id="runStart">Run chapters</button>
          <label class="chip"><input type="checkbox" id="runCast" checked style="width:auto"> cast voices with the model first</label>
          <span class="muted" style="font-size:11.5px">fetch, detect and analyze run for every chapter before the rest, so the cast is complete; render uses the Render tab's settings; the preview voice covers anyone still without a voice</span>
        </div>
        <div id="runJobLog" style="margin-top:10px"></div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Import a folder, CBZ, CBR or PDF</h3>
        <div class="row">
          <div class="field" style="flex:1">
            <label>Path on disk</label>
            <input type="text" id="importPath" placeholder="/home/ejb/Downloads/chapter-1.cbz">
          </div>
          <div class="field" style="width:140px">
            <label>Series (optional)</label>
            <input type="text" id="importSeries" placeholder="auto">
          </div>
          <div class="field" style="width:100px">
            <label>Number</label>
            <input type="text" id="importNumber" placeholder="auto">
          </div>
        </div>
        <button class="btn btn-primary" id="importPathBtn">Import path</button>
        <div id="dropzone" class="dropzone" style="margin-top:12px">
          Drag and drop a folder, CBZ, CBR or PDF here, or
          <label style="color:var(--accent);cursor:pointer">choose files<input type="file" id="fileInput" multiple style="display:none"></label>
        </div>
        <div id="importLog" style="margin-top:8px"></div>
      </div>

      <div class="card">
        <div class="section-head">
          <h3>MediaForge downloads</h3>
          <button class="btn" id="mfRefresh">Refresh</button>
        </div>
        <div id="mfList"><div class="placeholder">Loading…</div></div>
      </div>

      <div class="card">
        <div class="section-head">
          <h3>Series and chapters</h3>
          <button class="btn" id="seriesRefresh">Refresh</button>
        </div>
        <div id="seriesList"><div class="placeholder">Loading…</div></div>
        <div id="chapterBrowser" style="margin-top:14px"></div>
      </div>

      <div class="card">
        <h3 style="margin-top:0">Kindle PDF export</h3>
        <div class="row">
          <div class="field" style="width:200px">
            <label>Series</label>
            <select id="exportSeries"><option value="">choose a series above</option></select>
          </div>
          <div class="field" style="width:160px">
            <label>Preset</label>
            <select id="exportPreset">
              <option value="kindle">Kindle (fit to e-reader)</option>
              <option value="full">Full resolution</option>
            </select>
          </div>
        </div>
        <div id="exportChapterList" class="muted" style="margin:6px 0 10px">Pick a series to list its chapters.</div>
        <div class="row">
          <button class="btn" id="exportAll">Whole series</button>
          <button class="btn btn-primary" id="exportSelected">Export selected</button>
        </div>
        <div id="exportLog" style="margin-top:10px"></div>
      </div>
    `;

    $("#libLookup", el).addEventListener("click", () => lookup(el));
    $("#runStart", el).addEventListener("click", () => runChapters(el));
    $("#runSeries", el).value = PF.state.series || "";
    $("#importPathBtn", el).addEventListener("click", () => importPath(el));
    $("#mfRefresh", el).addEventListener("click", () => loadMediaForge(el));
    $("#seriesRefresh", el).addEventListener("click", () => loadSeries(el));
    $("#fileInput", el).addEventListener("change", (e) => uploadFiles(el, e.target.files));
    wireDropzone(el);

    $("#exportSeries", el).addEventListener("change", (e) => selectExportSeries(el, e.target.value));
    $("#exportAll", el).addEventListener("click", () => runExport(el, "all"));
    $("#exportSelected", el).addEventListener("click", () => runExport(el, "selected"));

    loadSources(el);
    loadMediaForge(el);
    loadSeries(el);
  }

  function $(sel, root) {
    return (root || document).querySelector(sel);
  }

  async function loadSources(el) {
    try {
      const r = await PF.getJson("/api/sources");
      const names = (r.sources || r || []).map((s) => (typeof s === "string" ? s : s.name)).join(", ");
      $("#libSourcesNote", el).textContent = names ? `known sites: ${names}` : "";
    } catch (e) {
      $("#libSourcesNote", el).textContent = "";
    }
  }

  async function lookup(el) {
    const url = $("#libUrl", el).value.trim();
    if (!url) return toast("Paste a link first", "err");
    const box = $("#libFetchResult", el);
    box.innerHTML = `<div class="placeholder">Looking up…</div>`;
    try {
      const result = await PF.runJob("/api/fetch/title", { url });
      state.fetchResult = result;
      renderFetchResult(el);
    } catch (e) {
      PF.handleLoadError(box, e, "The fetcher did not answer. Check /api/health.");
    }
  }

  async function runChapters(el) {
    const series = $("#runSeries", el).value.trim() || PF.state.series;
    if (!series) return toast("Enter a series (the folder name, e.g. bad-born-blood)", "err");
    const first = Number($("#runFirst", el).value), last = Number($("#runLast", el).value);
    if (!(first >= 1) || !(last >= first)) return toast("Give a chapter range like 1 to 10", "err");
    const steps = Array.from(el.querySelectorAll(".runStep:checked")).map((b) => b.value);
    if (!steps.length) return toast("Tick at least one step", "err");
    const s = PF.getSettings();
    const body = {
      first, last, steps,
      group: $("#runGroup", el).value.trim() || null,
      preview_voice: "am_michael",
      cast: $("#runCast", el).checked,
      render: {
        aspect: s.render_aspect, bubbles: s.render_bubbles, subtitles: s.render_subtitles,
        mode: s.render_mode, pace: s.render_pace, motion_strength: s.render_motion,
        backdrop: s.render_backdrop, sound: s.render_sound, layers: s.render_layers,
      },
    };
    const logBox = $("#runJobLog", el);
    logBox.innerHTML = `<div class="progress-bar"><div style="width:0%"></div></div><div class="logbox short" id="runLog"></div>`;
    const bar = logBox.querySelector(".progress-bar > div");
    const log = $("#runLog", el);
    try {
      const res = await PF.runJob(`/api/series/${encodeURIComponent(series)}/run`, body, {
        onProgress: (f) => (bar.style.width = Math.round(f * 100) + "%"),
        onLog: (lines) => {
          log.textContent += lines.join("\n") + "\n";
          log.scrollTop = log.scrollHeight;
        },
      });
      toast(`Done: ${(res.done || []).length} chapters, ${(res.failed || []).length} failed`);
    } catch (e) {
      toast(`Run failed: ${e.message}`, "err");
    }
  }

  function renderFetchResult(el) {
    const box = $("#libFetchResult", el);
    const r = state.fetchResult;
    if (!r || !r.chapters || !r.chapters.length) {
      box.innerHTML = `<div class="placeholder">No chapters found.</div>`;
      return;
    }
    box.innerHTML = `
      <div class="row" style="align-items:center;margin-bottom:8px">
        <strong>${PF.esc(r.title || r.series || "series")}</strong>
        <span class="muted">${r.chapters.length} chapters</span>
      </div>
      ${
        (r.groups || []).length > 1
          ? `<div class="row" style="margin-bottom:8px;align-items:center;gap:8px">
        <label>Scan group <select id="chGroup">${r.groups
          .map((g) => `<option value="${PF.esc(g)}" ${g === (state.group || r.groups[0]) ? "selected" : ""}>${PF.esc(g)}</option>`)
          .join("")}</select></label>
        <span class="muted" style="font-size:11.5px">this site lists each chapter once per group; the chosen group is fetched, the first listed when a chapter lacks it</span>
      </div>`
          : ""
      }
      <div class="row" style="margin-bottom:8px">
        <label class="chip"><input type="checkbox" id="chAll" style="width:auto"> all</label>
        <div class="field" style="width:180px;margin:0">
          <input type="text" id="chRange" placeholder="range e.g. 1-12,15">
        </div>
        <button class="btn" id="chRangeApply">Apply range</button>
      </div>
      <div id="chCheckList" style="max-height:220px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;padding:8px"></div>
      <button class="btn btn-primary" style="margin-top:10px" id="fetchSelected">Fetch selected</button>
      <div id="fetchJobLog" style="margin-top:10px"></div>
    `;
    const list = $("#chCheckList", el);
    const groupSel = $("#chGroup", el);
    if (groupSel) {
      state.group = groupSel.value;
      groupSel.addEventListener("change", () => {
        state.group = groupSel.value;
        renderFetchResult(el);
      });
    }
    // one row per chapter number: the chosen group's entry when it exists
    const seen = new Set();
    const rows = r.chapters
      .slice()
      .sort((a, b) => a.number - b.number || (a.group === state.group ? -1 : 1))
      .filter((c) => (seen.has(c.number) ? false : (seen.add(c.number), true)));
    list.innerHTML = rows
      .map(
        (c) =>
          `<label style="display:flex;gap:8px;align-items:center;padding:3px 0;font-size:12.5px">
             <input type="checkbox" class="chBox" value="${PF.esc(c.number)}" style="width:auto">
             ${PF.esc(c.number)} — ${PF.esc(c.title || "")}${c.group && c.group !== (state.group || c.group) ? ` <span class="muted">(only ${PF.esc(c.group)})</span>` : ""}
           </label>`
      )
      .join("");
    $("#chAll", el).addEventListener("change", (e) => {
      list.querySelectorAll(".chBox").forEach((b) => (b.checked = e.target.checked));
    });
    $("#chRangeApply", el).addEventListener("click", () => {
      const nums = parseRange($("#chRange", el).value);
      list.querySelectorAll(".chBox").forEach((b) => {
        if (nums.has(Number(b.value))) b.checked = true;
      });
    });
    $("#fetchSelected", el).addEventListener("click", () => fetchSelected(el));
  }

  function parseRange(text) {
    const out = new Set();
    (text || "").split(",").forEach((part) => {
      part = part.trim();
      if (!part) return;
      const m = part.match(/^(\d+)\s*-\s*(\d+)$/);
      if (m) {
        for (let n = Number(m[1]); n <= Number(m[2]); n++) out.add(n);
      } else if (!isNaN(Number(part))) {
        out.add(Number(part));
      }
    });
    return out;
  }

  async function fetchSelected(el) {
    const nums = Array.from(el.querySelectorAll(".chBox:checked")).map((b) => Number(b.value));
    if (!nums.length) return toast("Pick at least one chapter", "err");
    const logBox = $("#fetchJobLog", el);
    logBox.innerHTML = `<div class="progress-bar"><div style="width:0%"></div></div><div class="logbox short" id="fetchLog"></div>`;
    const bar = logBox.querySelector(".progress-bar > div");
    const log = $("#fetchLog", el);
    try {
      await PF.runJob(
        "/api/fetch/chapters",
        { url: $("#libUrl", el).value.trim(), chapters: nums, group: state.group || null },
        {
          onProgress: (f) => (bar.style.width = Math.round(f * 100) + "%"),
          onLog: (lines) => {
            log.textContent += lines.join("\n") + "\n";
            log.scrollTop = log.scrollHeight;
          },
        }
      );
      toast(`Fetched ${nums.length} chapter(s)`);
      loadSeries(el);
    } catch (e) {
      toast(`Fetch failed: ${e.message}`, "err");
    }
  }

  async function importPath(el) {
    const path = $("#importPath", el).value.trim();
    if (!path) return toast("Enter a path", "err");
    const body = { path };
    const series = $("#importSeries", el).value.trim();
    const number = $("#importNumber", el).value.trim();
    if (series) body.series = series;
    if (number) body.number = Number(number);
    const logBox = $("#importLog", el);
    logBox.innerHTML = `<div class="placeholder">Importing…</div>`;
    try {
      await PF.runJob("/api/import/path", body);
      toast("Import complete");
      logBox.innerHTML = "";
      loadSeries(el);
    } catch (e) {
      PF.handleLoadError(logBox, e, "The importer did not answer. Check /api/health.");
    }
  }

  function wireDropzone(el) {
    const zone = $("#dropzone", el);
    ["dragenter", "dragover"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.add("over");
      })
    );
    ["dragleave", "drop"].forEach((ev) =>
      zone.addEventListener(ev, (e) => {
        e.preventDefault();
        zone.classList.remove("over");
      })
    );
    zone.addEventListener("drop", (e) => {
      if (e.dataTransfer.files && e.dataTransfer.files.length) uploadFiles(el, e.dataTransfer.files);
    });
  }

  async function uploadFiles(el, files) {
    if (!files || !files.length) return;
    const fd = new FormData();
    Array.from(files).forEach((f) => fd.append("files", f));
    const logBox = $("#importLog", el);
    logBox.innerHTML = `<div class="placeholder">Uploading ${files.length} file(s)…</div>`;
    try {
      const r = await PF.postForm("/api/import/upload", fd);
      if (r.job_id) {
        await new Promise((resolve, reject) =>
          PF.watchJob(r.job_id, { onDone: resolve, onError: (m) => reject(new Error(m)) })
        );
      }
      toast("Upload imported");
      logBox.innerHTML = "";
      loadSeries(el);
    } catch (e) {
      PF.handleLoadError(logBox, e, "The importer did not answer. Check /api/health.");
    }
  }

  async function loadMediaForge(el) {
    const box = $("#mfList", el);
    try {
      const r = await PF.getJson("/api/mediaforge/downloads");
      const items = r.downloads || r.items || r || [];
      if (!items.length) {
        box.innerHTML = `<div class="placeholder">No manga downloads found in MediaForge.</div>`;
        return;
      }
      box.innerHTML = items
        .map(
          (it) => `
          <div class="row" style="justify-content:space-between;border-bottom:1px solid var(--border);padding:6px 0">
            <span style="font-size:12.5px">${PF.esc(it.title || it.name || it.path)}</span>
            <button class="btn" data-path="${PF.esc(it.path)}">Import</button>
          </div>`
        )
        .join("");
      box.querySelectorAll("button[data-path]").forEach((b) =>
        b.addEventListener("click", async () => {
          try {
            await PF.runJob("/api/import/mediaforge", { path: b.dataset.path });
            toast("Imported from MediaForge");
            loadSeries(el);
          } catch (e) {
            toast(`Import failed: ${e.message}`, "err");
          }
        })
      );
    } catch (e) {
      PF.handleLoadError(box, e, "MediaForge downloads are not reachable from here.");
    }
  }

  async function loadSeries(el) {
    const listBox = $("#seriesList", el);
    const exSel = $("#exportSeries", el);
    try {
      const r = await PF.getJson("/api/series");
      state.series = r.series || r || [];
      if (!state.series.length) {
        listBox.innerHTML = `<div class="placeholder">No series yet — fetch or import one above.</div>`;
        exSel.innerHTML = `<option value="">none yet</option>`;
        return;
      }
      listBox.innerHTML = `<div class="grid-cards">${state.series
        .map((s) => {
          const name = s.series || s.name || s;
          const title = s.title || name;
          return `<div class="card tight chapter-card" data-series="${PF.esc(name)}">
            <div class="cover-fallback">📚</div>
            <div class="name">${PF.esc(title)}</div>
            <div class="sub">${PF.esc(name)}</div>
          </div>`;
        })
        .join("")}</div>`;
      listBox.querySelectorAll("[data-series]").forEach((c) =>
        c.addEventListener("click", () => showChapters(el, c.dataset.series))
      );
      exSel.innerHTML =
        `<option value="">choose…</option>` +
        state.series.map((s) => {
          const name = s.series || s.name || s;
          return `<option value="${PF.esc(name)}">${PF.esc(name)}</option>`;
        }).join("");
    } catch (e) {
      PF.handleLoadError(listBox, e, "The library did not answer. Check /api/health.");
    }
  }

  async function showChapters(el, series) {
    const box = $("#chapterBrowser", el);
    box.innerHTML = `<div class="placeholder">Loading chapters…</div>`;
    try {
      const r = await PF.getJson(`/api/series/${encodeURIComponent(series)}/chapters`);
      const chapters = r.chapters || r || [];
      state.seriesChapters[series] = chapters;
      if (!chapters.length) {
        box.innerHTML = `<div class="placeholder">No chapters fetched yet for ${PF.esc(series)}.</div>`;
        return;
      }
      box.innerHTML = `<h4 style="color:var(--muted);font-size:11px;text-transform:uppercase">${PF.esc(
        series
      )}</h4><div class="grid-cards">${chapters
        .map((c) => {
          const chap = c.chapter || c.number || c;
          const cover = c.cover || (c.pages && c.pages[0] && c.pages[0].file);
          const coverUrl = cover ? `/data/series/${encodeURIComponent(series)}/chapters/${encodeURIComponent(chap)}/${cover}` : null;
          return `<div class="card tight chapter-card" data-chapter="${PF.esc(chap)}">
            ${coverUrl ? `<img class="cover" loading="lazy" src="${coverUrl}">` : `<div class="cover-fallback">📄</div>`}
            <div class="name">Chapter ${PF.esc(c.number ?? chap)}</div>
            <div class="sub">${PF.esc(c.title || "")}</div>
          </div>`;
        })
        .join("")}</div>`;
      box.querySelectorAll("[data-chapter]").forEach((c) =>
        c.addEventListener("click", () => {
          PF.setContext(series, c.dataset.chapter);
          toast(`Working chapter set to ${series} / ${c.dataset.chapter}`);
        })
      );
    } catch (e) {
      PF.handleLoadError(box, e, "The library did not answer. Check /api/health.");
    }
  }

  async function selectExportSeries(el, series) {
    state.exportSeries = series || null;
    state.exportChapters = new Set();
    const box = $("#exportChapterList", el);
    if (!series) {
      box.textContent = "Pick a series to list its chapters.";
      return;
    }
    box.innerHTML = `<div class="placeholder">Loading…</div>`;
    try {
      const chapters = state.seriesChapters[series] || (await PF.getJson(`/api/series/${encodeURIComponent(series)}/chapters`)).chapters;
      if (!chapters || !chapters.length) {
        box.innerHTML = `No chapters for ${PF.esc(series)} yet.`;
        return;
      }
      box.innerHTML = chapters
        .map((c) => {
          const chap = c.chapter || c.number || c;
          return `<label class="chip" style="margin:2px 4px 2px 0"><input type="checkbox" class="exCh" value="${PF.esc(
            chap
          )}" style="width:auto"> ${PF.esc(c.number ?? chap)}</label>`;
        })
        .join("");
    } catch (e) {
      PF.handleLoadError(box, e, "The library did not answer. Check /api/health.");
    }
  }

  async function runExport(el, mode) {
    if (!state.exportSeries) return toast("Choose a series first", "err");
    const preset = $("#exportPreset", el).value;
    let chapters = "all";
    if (mode === "selected") {
      chapters = Array.from(el.querySelectorAll(".exCh:checked")).map((b) => b.value);
      if (!chapters.length) return toast("Pick at least one chapter, or use Whole series", "err");
    }
    const logBox = $("#exportLog", el);
    logBox.innerHTML = `<div class="placeholder">Building PDF…</div>`;
    try {
      const result = await PF.runJob("/api/export/pdf", { series: state.exportSeries, chapters, preset });
      const file = result && result.file;
      logBox.innerHTML = file
        ? `<div class="chip on">done</div> <span class="muted">${PF.esc(file)}</span>`
        : `<div class="chip on">done</div>`;
      toast("Kindle PDF ready");
    } catch (e) {
      PF.handleLoadError(logBox, e, "PDF export did not answer. Check /api/health.");
    }
  }

  PF.registerTab("library", { label: "Library", mount });
})();
