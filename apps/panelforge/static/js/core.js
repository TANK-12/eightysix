"use strict";
/* PanelForge editor core: small shared helpers every tab module uses.
   Loaded after /shared/forge.js (toast, initTabs, errText) and before
   app.js and the tab modules. Exposes everything on window.PF. */

class PfError extends Error {
  constructor(msg, status) {
    super(msg);
    this.status = status;
  }
}

const PF = (window.PF = window.PF || {});
PF.PfError = PfError;

PF.state = {
  series: null,
  chapter: null,
};
try {
  PF.state.series = localStorage.getItem("pf.series") || null;
  PF.state.chapter = localStorage.getItem("pf.chapter") || null;
} catch (e) {
  /* private window or blocked storage; context just won't persist */
}

PF.tabs = {}; // id -> { label, mount(el), enter(), leave() }
PF.registerTab = (id, mod) => {
  PF.tabs[id] = mod;
};

/** Set the working series/chapter. Every context-dependent tab listens for
 * the "pf:context" event and reloads. */
PF.setContext = (series, chapter) => {
  PF.state.series = series || null;
  PF.state.chapter = chapter || null;
  try {
    if (series) localStorage.setItem("pf.series", series);
    else localStorage.removeItem("pf.series");
    if (chapter) localStorage.setItem("pf.chapter", chapter);
    else localStorage.removeItem("pf.chapter");
  } catch (e) {
    /* ignore */
  }
  document.dispatchEvent(new CustomEvent("pf:context"));
  PF.renderContextBadge && PF.renderContextBadge();
};

PF.esc = (s) =>
  String(s ?? "").replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]
  );

PF.el = (html) => {
  const t = document.createElement("template");
  t.innerHTML = html.trim();
  return t.content.firstElementChild;
};

/* -------------------------------------------------------------------------
   Fetch helpers. A missing backend module means a plain 404 with no JSON
   body (FastAPI's own "Not Found"), so PfError.status is what callers check
   to show a "not ready yet" state instead of an error banner. */
async function pfRawFetch(path, opts) {
  let res;
  try {
    res = await fetch(path, opts);
  } catch (e) {
    throw new PfError(`could not reach the server (${e.message})`, 0);
  }
  if (!res.ok) {
    let msg = `request failed (HTTP ${res.status})`;
    try {
      const body = await res.clone().json();
      if (body && body.detail) msg = body.detail;
    } catch (e) {
      /* not JSON */
    }
    throw new PfError(msg, res.status);
  }
  return res;
}

PF.getJson = (path) => pfRawFetch(path).then((r) => r.json());
PF.postJson = (path, body) =>
  pfRawFetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then((r) => r.json());
PF.putJson = (path, body) =>
  pfRawFetch(path, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  }).then((r) => r.json());
PF.postForm = (path, formData) =>
  pfRawFetch(path, { method: "POST", body: formData }).then((r) => r.json());

/** Try the real API endpoint; on a 404 (module not loaded, or no data yet)
 * fall back to reading the raw JSON file under /data (served straight off
 * disk, so it works even while the owning module is still missing). Used
 * for read-only display; saving always goes through the API. */
PF.readWithFallback = async (apiPath, dataPath) => {
  try {
    return await PF.getJson(apiPath);
  } catch (e) {
    if (e.status === 404 && dataPath) {
      try {
        return await PF.getJson(dataPath);
      } catch (e2) {
        throw e;
      }
    }
    throw e;
  }
};

PF.notReady = (el, note) => {
  el.innerHTML = `<div class="placeholder">Nothing to show here yet.${
    note ? `<div class="muted" style="margin-top:6px">${PF.esc(note)}</div>` : ""
  }</div>`;
};

PF.errorBox = (el, err) => {
  const msg = err instanceof Error ? err.message : String(err);
  el.innerHTML = `<div class="placeholder err">Couldn't load this: ${PF.esc(msg)}</div>`;
};

PF.handleLoadError = (el, err, note) => {
  if (err instanceof PfError && err.status === 404) PF.notReady(el, note);
  else PF.errorBox(el, err);
};

/* -------------------------------------------------------------------------
   Jobs. web_app.py's job shape (panelforge/jobs.py) is
   {id, kind, title, lane, state: queued|running|done|failed|cancelled,
    progress: 0..1, log: [...], result, error} -- note "state", not
   "status", so this polls rather than reusing forge.js's pollJob/forgeStream
   (those assume an /events SSE endpoint and a "status" field this app
   doesn't have). */
PF.jobs = {}; // id -> last known dict, for the drawer

PF.watchJob = (jobId, { onLog, onProgress, onDone, onError, every = 800 } = {}) => {
  let seen = 0;
  let missing = 0;
  let poller;
  const tick = async () => {
    let j;
    try {
      j = await PF.getJson(`/api/jobs/${jobId}`);
    } catch (e) {
      // a job the server no longer knows (restarted, jobs folder cleared)
      // will never finish: stop after three straight 404s instead of polling
      // it forever; anything else is transient and only slows the poll
      if (e instanceof PfError && e.status === 404 && ++missing >= 3) {
        poller && poller.stop();
        onError && onError("the server no longer knows this job");
      }
      return false;
    }
    missing = 0;
    PF.jobs[jobId] = j;
    document.dispatchEvent(new CustomEvent("pf:jobs"));
    if (j.log && j.log.length > seen) {
      onLog && onLog(j.log.slice(seen), j);
      seen = j.log.length;
    }
    onProgress && onProgress(j.progress || 0, j);
    if (j.state === "running" || j.state === "queued") return true;
    poller && poller.stop();
    if (j.state === "failed") onError && onError(j.error || "job failed", j);
    else if (j.state === "cancelled") onError && onError("cancelled", j);
    else onDone && onDone(j);
    return true;
  };
  // keeps checking every 5 s while hidden so a finished job still settles
  // its promise; backs off to 10 s while the server is not answering
  poller = ForgeIdle.poll(tick, every, { hiddenMs: 5000, backoff: 2, maxMs: 10000, immediate: true });
  return poller;
};

/** Run a POST-then-watch job and return a promise resolving with the job's
 * result on success, so most callers can just `await PF.runJob(...)`. */
PF.runJob = (path, body, { onLog, onProgress } = {}) =>
  new Promise((resolve, reject) => {
    PF.postJson(path, body)
      .then((r) => {
        if (!r.job_id) {
          resolve(r); // some endpoints may answer synchronously
          return;
        }
        PF.watchJob(r.job_id, {
          onLog,
          onProgress,
          onDone: (j) => resolve(j.result),
          onError: (msg) => reject(new Error(msg)),
        });
      })
      .catch(reject);
  });

/* -------------------------------------------------------------------------
   Health. /api/health lists which panelforge.api.* modules imported, so
   tabs can show "not ready" up front instead of only after a failed call. */
PF.health = { ok: true, modules: [], failed: {} };
PF.reachable = true;
PF.refreshHealth = async () => {
  try {
    PF.health = await PF.getJson("/api/health");
    PF.reachable = true;
  } catch (e) {
    // keep the last known module list; only a reply that never came counts
    // as the server being away (an HTTP error still means it answered)
    PF.reachable = e instanceof PfError && e.status > 0;
  }
  document.dispatchEvent(new CustomEvent("pf:health"));
  return PF.health;
};
PF.moduleReady = (name) => (PF.health.modules || []).includes(name);
PF.moduleError = (name) => (PF.health.failed || {})[name];

/* -------------------------------------------------------------------------
   Settings. No dedicated endpoint exists in CONTRACTS.md yet, so defaults
   live in localStorage under one key; the Settings tab is the only writer.
   Keep this in sync with static/js/tabs/settings.js if defaults change. */
PF.DEFAULT_SETTINGS = {
  export_preset: "kindle",
  render_aspect: "16:9",
  render_bubbles: "keep",
  render_subtitles: true,
  render_mode: "scroll", // the scroll reader: the strip as drawn, nothing cut (Emerson, 2026-09-19)
  render_pace: 1.0,
  render_motion: 1.0,
  render_backdrop: "auto",
  render_sound: "full", // full, music (just watch, no voices) or silent
  render_layers: 1.0, // cutout character layers in the 3D style, 0..1
  timeline_px_per_sec: 40,
};
PF.getSettings = () => {
  try {
    const raw = localStorage.getItem("pf.settings");
    return Object.assign({}, PF.DEFAULT_SETTINGS, raw ? JSON.parse(raw) : {});
  } catch (e) {
    return Object.assign({}, PF.DEFAULT_SETTINGS);
  }
};
PF.saveSettings = (patch) => {
  const s = Object.assign(PF.getSettings(), patch);
  try {
    localStorage.setItem("pf.settings", JSON.stringify(s));
  } catch (e) {
    /* ignore */
  }
  return s;
};
