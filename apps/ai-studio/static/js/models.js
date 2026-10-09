// Models: the panel (tabs Images / Video / 3D worlds), the per-model cards
// and the "Using ..." line at the top of every section.
//
// API (docs/2026-10-08-rebuild-plan.md, HTTP API contract):
//   GET  /api/models               {models: [card], disk: {free_bytes}}
//   GET  /api/models/{id}/quote    {total_bytes, needed_bytes, free_bytes, fits, message}
//   POST /api/models/{id}/download | /cancel | /activate,  DELETE /api/models/{id}
//   GET/POST /api/models/delete-all
"use strict";
(function (AS) {
  const $ = AS.$, el = AS.el;
  const KIND_WORDS = { image: "picture model", video: "video model", world: "3D world model" };
  const TAB_EMPTY = {
    image: "No picture models are listed.",
    video: "No video models are listed yet.",
    world: "No 3D world models are listed yet.",
  };
  const HEAVY = "Large, probably too heavy for this laptop";

  const M = (AS.models = {
    cards: [],
    disk: null,
    loaded: false,
    error: "",
    active(kind) {
      return M.cards.find((c) => c.kind === kind && c.active && c.installed && c.can_run !== false) || null;
    },
    get(id) { return M.cards.find((c) => c.id === id) || null; },
  });

  // The server's card in the shape this page uses. The older backend sent a
  // bare list with `description` and `download.status`; both are understood
  // so the page keeps working while the new backend lands.
  function normalise(raw) {
    const c = { ...raw };
    c.kind = c.kind || "image";
    c.blurb = c.blurb ?? c.description ?? "";
    c.tier = c.tier || "compact";
    c.can_run = c.can_run !== false;
    const d = c.download;
    if (d && !d.state && d.status) {
      c.download = d.status === "failed"
        ? { state: "failed", message: d.error || "" }
        : { state: "running", done_bytes: d.progress || 0, total_bytes: 100 };
    }
    return c;
  }
  M.normalise = normalise;

  // World models are started from the 3D worlds section, not switched on in
  // the server, so the chosen one is kept here (and in this browser).
  const WORLD_KEY = "ai-studio:world-model";
  function pickWorld() {
    const ready = M.cards.filter((c) => c.kind === "world" && c.installed && c.can_run);
    let want = null;
    try { want = localStorage.getItem(WORLD_KEY); } catch (e) { /* private window */ }
    const chosen = ready.find((c) => c.id === want) || ready[0] || null;
    M.cards.forEach((c) => { if (c.kind === "world") c.active = c === chosen; });
  }
  function chooseWorld(m) {
    try { localStorage.setItem(WORLD_KEY, m.id); } catch (e) { /* private window */ }
    pickWorld();
    key = "";
    paintAll();
    close();
    AS.show("worlds");
  }

  const modal = $("modelsModal"), list = $("modelsList");
  const tabs = AS.chips($("modelTabs"), () => { key = ""; paintList(); });
  let key = "", pollTimer = null, bgTimer = null, retryTimer = null;
  const busy = new Map(); // model id -> {kind, text} of the request running for it

  AS.on("heavy", () => { key = ""; paintList(); }); // Use this follows the heavy-job wait

  // ---- loading ----
  M.load = async function () {
    let data;
    try {
      data = await AS.get("/api/models", "The models list didn't load");
    } catch (e) {
      M.error = AS.failText(e);
      key = "";
      paintAll();
      if (!retryTimer && !M.loaded) {
        // calm retry: 2 s growing to 30 s, resting while hidden
        retryTimer = ForgeIdle.poll(async () => {
          const ok = await M.load();
          if (ok && retryTimer) { retryTimer.stop(); retryTimer = null; }
          return ok;
        }, 2000, { backoff: 2, maxMs: 30000 });
      }
      return false;
    }
    M.error = "";
    M.loaded = true;
    M.cards = (Array.isArray(data) ? data : data.models || []).map(normalise);
    pickWorld();
    M.disk = Array.isArray(data) ? null : data.disk || null;
    if (!Array.isArray(data) && "busy" in data) AS.heavy.server(data.busy);
    paintAll();
    watchDownloads();
    return true;
  };

  function paintAll() {
    paintList();
    paintLines();
    AS.emit("models", M);
  }

  // While a download runs and the panel is closed, check now and then so
  // the sections notice when it lands. Stops when nothing is running.
  function watchDownloads() {
    const running = M.cards.some((c) => c.download && c.download.state === "running");
    if (running && !bgTimer && modal.hidden) bgTimer = ForgeIdle.poll(M.load, 5000, { backoff: 2, maxMs: 30000 });
    if ((!running || !modal.hidden) && bgTimer) { bgTimer.stop(); bgTimer = null; }
  }

  // ---- the "Using ..." line in each section ----
  function paintLines() {
    document.querySelectorAll(".model-line[data-kind]").forEach((line) => {
      const kind = line.dataset.kind;
      line.replaceChildren();
      line.classList.remove("missing");
      if (!M.loaded) {
        line.append(M.error ? M.error + " Trying again by itself..." : "Checking the models...");
        return;
      }
      const act = M.active(kind);
      const open = (text) => el("button", { type: "button", className: "btn", onclick: () => M.open(kind) }, text);
      if (act) {
        line.append(el("span", {}, "Using ", el("b", {}, act.label)), el("span", { className: "spacer" }), open("Change"));
        return;
      }
      line.classList.add("missing");
      const ready = M.cards.some((c) => c.kind === kind && c.installed && c.can_run);
      line.append(
        ready ? `No ${KIND_WORDS[kind]} is switched on.` : `No ${KIND_WORDS[kind]} yet.`,
        el("span", { className: "spacer" }),
        open(ready ? "Pick one" : "Get one"),
      );
    });
  }
  M.paintLines = paintLines;

  // ---- the panel ----
  M.open = function (kind) {
    if (kind) tabs.value = kind;
    modal.hidden = false;
    showDeleteAll(false);
    key = "";
    M.load();
    if (pollTimer) pollTimer.stop(); // a second open must not start a second poll
    // every 1.2 s while open and shown; a failing server stretches the wait to 30 s
    pollTimer = ForgeIdle.poll(M.load, 1200, { backoff: 2, maxMs: 30000 });
    watchDownloads();
  };
  function close() {
    modal.hidden = true;
    showDeleteAll(false, true);
    if (pollTimer) { pollTimer.stop(); pollTimer = null; }
    watchDownloads();
  }
  $("modelsBtn").addEventListener("click", () => M.open());
  $("closeModelsBtn").addEventListener("click", close);
  modal.addEventListener("mousedown", (e) => { if (e.target === modal) close(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.hidden && !document.querySelector(".forge-dialog-back")) close();
  });

  function paintList() {
    const kind = tabs.value;
    const disk = $("diskLine");
    disk.textContent = M.disk && Number.isFinite(M.disk.free_bytes) ? `Free space on this laptop: ${AS.size(M.disk.free_bytes)}` : "";
    if (!M.loaded || M.error) {
      key = "";
      list.replaceChildren(el("div", { className: "models-note" },
        M.error ? M.error + " Trying again by itself..." : "Loading the models..."));
      return;
    }
    const cards = M.cards.filter((c) => c.kind === kind);
    const k = kind + JSON.stringify(cards) + JSON.stringify([...busy]);
    if (k === key) return; // nothing changed: keep the cards (and any hover) as they are
    key = k;
    list.replaceChildren(...(cards.length ? cards.map(card) : [el("div", { className: "models-note" }, TAB_EMPTY[kind])]));
  }

  function sentence(s) {
    s = String(s || "").trim();
    return s && !/[.!?]$/.test(s) ? s + "." : s;
  }

  function card(m) {
    const d = m.download;
    const running = d && d.state === "running";
    const box = el("div", { className: "model-card" + (m.active && m.installed ? " active" : ""), dataset: { id: m.id } },
      el("div", { className: "name" }, m.label),
      m.blurb ? el("div", { className: "blurb" }, m.blurb) : null,
    );
    if (m.tier === "big") box.append(el("div", { className: "note heavy" }, HEAVY));
    if (!m.can_run && m.run_note) box.append(el("div", { className: "note cant" }, sentence(m.run_note)));

    if (running) {
      const pct = d.total_bytes > 0 ? Math.min(100, Math.floor((100 * (d.done_bytes || 0)) / d.total_bytes)) : 0;
      const fill = el("div");
      fill.style.width = pct + "%";
      box.append(
        el("div", { className: "progress-bar", role: "progressbar", ariaValueNow: pct, ariaValueMin: 0, ariaValueMax: 100 }, fill),
        el("div", { className: "progress-text" }, `Downloading... ${pct}%`),
      );
    } else if (d && d.state === "failed") {
      box.append(el("div", { className: "note bad" },
        "The download stopped" + (d.message ? ": " + sentence(d.message) : ".") + " Try again to carry on from where it stopped."));
    } else if (d && d.state === "cancelled" && !m.installed) {
      box.append(el("div", { className: "note cant" }, "Download cancelled. Pressing Download carries on from where it stopped."));
    }

    const actions = el("div", { className: "actions" });
    const btn = (cls, text, kind, onclick) => {
      const b = el("button", { type: "button", className: "btn " + cls, dataset: { act: kind }, onclick: () => onclick(b) }, text);
      const job = busy.get(m.id);
      if (job) { b.disabled = true; if (job.kind === kind) b.textContent = job.text; }
      actions.append(b);
      return b;
    };
    if (m.installed) {
      if (m.active) actions.append(el("span", { className: "in-use" }, "In use"));
      else if (m.can_run && m.kind !== "world") btn("btn-primary", "Use this", "activate", (b) => activate(b, m));
      if (m.kind === "world" && m.can_run) btn("btn-primary", "Play", "play", () => chooseWorld(m));
      btn("btn-danger", "Delete", "delete", (b) => remove(b, m));
    } else if (running) {
      btn("", "Cancel", "cancel", (b) => cancel(b, m));
    } else {
      btn("btn-primary", d && d.state === "failed" ? "Try again" : "Download", "download", (b) => download(b, m));
    }
    box.append(actions);
    return box;
  }

  // ---- actions: one request per click; the button stays busy (and
  // survives the poll rebuilding the cards) until the server answers ----
  async function act(b, m, kind, text, job) {
    if (busy.has(m.id)) return;
    busy.set(m.id, { kind, text });
    b.disabled = true;
    b.textContent = text;
    try {
      await job((t) => { busy.set(m.id, { kind, text: t }); b.textContent = t; });
    } catch (e) {
      // a 409 with no words of its own (say, already downloading) needs no
      // dialog; one with the server's reason shows it
      if (e.status !== 409 || e.fromServer) await ForgeDialog.alert(AS.failText(e));
    } finally {
      busy.delete(m.id);
      key = "";
      await M.load();
    }
  }

  // The words of the download dialog, built from the quote.
  M.quoteText = function (m, q) {
    const free = Number(q.free_bytes) || 0;
    const total = Number(q.total_bytes) || 0;
    const need = Number.isFinite(Number(q.needed_bytes)) ? Number(q.needed_bytes) : total;
    if (!q.fits) {
      return `${m.label} won't fit right now, sorry.\n\n` +
        `It needs ${AS.size(need)} of space and ${AS.size(free)} is free. ` +
        `AI Studio keeps 5 GB spare so the laptop keeps running well.\n\n` +
        `Deleting a model you don't use would make room.`;
    }
    const lines = [`Download ${m.label}?`, ""];
    if (need <= 0) lines.push("Everything it needs is already on this laptop, so nothing new has to download.");
    else {
      lines.push(`The download is ${AS.size(need)}` + (total > need ? `; the rest of its ${AS.size(total)} is already here.` : "."));
      lines.push(`You have ${AS.size(free)} free, so about ${AS.size(free - need)} will be left afterwards.`);
    }
    if (m.tier === "big") lines.push("", "This one is large and probably too heavy for this laptop: it may be very slow, or not run at all.");
    if (!m.can_run && m.run_note) lines.push("", `It can't be used yet: ${sentence(m.run_note)} You can still download it now.`);
    return lines.join("\n");
  };

  function download(b, m) {
    return act(b, m, "download", "Checking space...", async (say) => {
      const q = await AS.get(`/api/models/${encodeURIComponent(m.id)}/quote`, "Couldn't check the free space");
      const text = M.quoteText(m, q);
      if (!q.fits) { await ForgeDialog.alert(text); return; }
      say("Download");
      if (!(await ForgeDialog.confirm(text, { ok: "Download", cancel: "Not now" }))) return;
      say("Starting...");
      await AS.post(`/api/models/${encodeURIComponent(m.id)}/download`, undefined, "The download didn't start");
    });
  }
  function cancel(b, m) {
    return act(b, m, "cancel", "Cancel", async (say) => {
      if (!(await ForgeDialog.confirm(`Stop downloading ${m.label}?\n\nWhat has come down so far is kept, so it can carry on later.`,
        { ok: "Stop it", cancel: "Keep going" }))) return;
      say("Stopping...");
      await AS.post(`/api/models/${encodeURIComponent(m.id)}/cancel`, undefined, "Couldn't stop the download");
    });
  }
  function activate(b, m) {
    const wait = AS.heavy.reason(null);
    if (wait) { ForgeDialog.alert(wait); return; }
    return act(b, m, "activate", "Switching...", async () => {
      await AS.post(`/api/models/${encodeURIComponent(m.id)}/activate`, undefined, "Couldn't switch to it");
      AS.toast(`Now using ${m.label}.`);
    });
  }
  function remove(b, m) {
    return act(b, m, "delete", "Delete", async (say) => {
      const note = m.active ? " It is the one in use: AI Studio switches to another downloaded one, or to none." : "";
      if (!(await ForgeDialog.confirm(`Delete ${m.label} from this laptop?${note}\n\nYou can download it again later.`,
        { ok: "Delete", cancel: "Keep it" }))) return;
      say("Deleting...");
      const out = await AS.del(`/api/models/${encodeURIComponent(m.id)}`, "Couldn't delete it");
      AS.toast(out && out.freed_bytes ? `Deleted ${m.label}. That freed ${AS.size(out.freed_bytes)}.` : `Deleted ${m.label}.`);
    });
  }

  // ---- delete all models ----
  const delPanel = $("deleteAllPanel"), delItems = $("deleteAllItems"), delGo = $("deleteAllGo");
  let plan = [];
  function showDeleteAll(open, quiet) {
    delPanel.hidden = !open;
    list.hidden = open;
    $("modelTabs").hidden = open;
    $("deleteAllBtn").hidden = open;
    if (!open && !quiet && !modal.hidden && !pollTimer) {
      pollTimer = ForgeIdle.poll(M.load, 1200, { backoff: 2, maxMs: 30000 });
      M.load();
    }
    if (open && pollTimer) { pollTimer.stop(); pollTimer = null; }
  }
  function ticked() { return plan.filter((i) => $("del-" + i.id) && $("del-" + i.id).checked); }
  function updateTotal() {
    const t = ticked();
    delGo.disabled = !t.length;
    delGo.textContent = t.length ? `Delete ticked (frees ${AS.size(t.reduce((s, i) => s + i.bytes, 0))})` : "Nothing ticked";
  }
  $("deleteAllBtn").addEventListener("click", async (ev) => {
    const b = ev.currentTarget;
    if (b.disabled) return;
    b.disabled = true;
    try {
      plan = await AS.get("/api/models/delete-all", "Couldn't list the model files");
    } catch (e) {
      ForgeDialog.alert(AS.failText(e));
      return;
    } finally {
      b.disabled = false;
    }
    delItems.replaceChildren(...(plan.length ? plan.map((item) => el("label", { className: "del-item" },
      el("input", { type: "checkbox", id: "del-" + item.id, checked: !!item.default, onchange: updateTotal }),
      el("span", {}, item.label + (item.active ? " (in use)" : "")),
      el("span", { className: "size" }, `${AS.size(item.bytes)} · ${item.files.length} file${item.files.length === 1 ? "" : "s"}`),
      el("span", { className: "files" }, [item.note, item.files.map((f) => f.split("/").pop()).join(", ")].filter(Boolean).join(" ")),
    )) : [el("p", {}, "No model files on disk.")]));
    updateTotal();
    showDeleteAll(true);
  });
  $("deleteAllCancel").addEventListener("click", () => showDeleteAll(false));
  delGo.addEventListener("click", async () => {
    const ids = ticked().map((i) => i.id);
    if (!ids.length || delGo.disabled) return;
    delGo.disabled = true;
    delGo.textContent = "Deleting...";
    let msg;
    try {
      const out = await AS.post("/api/models/delete-all", { ids }, "Delete failed");
      msg = `Deleted. Freed ${AS.size(out.freed_bytes)}.`;
    } catch (e) {
      msg = AS.failText(e);
    }
    key = "";
    showDeleteAll(false);
    delItems.replaceChildren();
    ForgeDialog.alert(msg);
  });
})(window.AS);
