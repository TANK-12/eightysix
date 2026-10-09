/* ==========================================================================
   Forge shared frontend helpers.
   ==========================================================================

   Served by each app's own backend at /shared/forge.js (each web_app.py
   mounts this directory), so a fix here reaches all three tools at once.
   Load it before the app's own <script>:

       <script src="/shared/forge.js"></script>

   Everything here is deliberately DOM-agnostic where it can be: forgeStream()
   hands you raw events and lets each app decide where the text goes, because
   the three tools genuinely differ on that and pretending otherwise is how
   the old per-app copies drifted.
   ========================================================================== */

/* --------------------------------------------------------------------------
   Tiny DOM conveniences
   -------------------------------------------------------------------------- */
function val(id) { return document.getElementById(id).value; }
function setVal(id, v) { document.getElementById(id).value = v ?? ""; }
function checked(id) { return document.getElementById(id).checked; }
function setChecked(id, v) { document.getElementById(id).checked = !!v; }

function toast(msg, kind) {
  const el = document.getElementById("toast");
  if (!el) return;
  el.textContent = msg;
  el.className = "toast" + (kind ? " " + kind : "");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => el.classList.add("hidden"), 5000);
}

/* --------------------------------------------------------------------------
   Errors
   --------------------------------------------------------------------------
   A failed request does not always carry a JSON body: an unhandled server
   exception returns plain text, so res.json() throws there and the real error
   gets replaced by a confusing JSON parse error. Always go through this. */
async function errText(res, fallback) {
  try {
    const body = await res.json();
    return body.detail || fallback;
  } catch (e) {
    return `${fallback} (HTTP ${res.status})`;
  }
}

/* --------------------------------------------------------------------------
   Jobs
   --------------------------------------------------------------------------

   THE ONE RULE: exactly one EventSource per job.

   Job events travel through a queue.Queue on the server, which is
   single-consumer -- a second connection to the same job does not mirror the
   stream, it STEALS half of it, including (unpredictably) the terminal
   "done" event, so the panel hangs forever. This has been written as a bug
   twice already, once in NovelForge's audiobook panel and once in
   MediaForge's storage scan. If a panel needs log text AND progress AND a
   status line, they are all callbacks on this one call. */
function forgeStream(jobId, { onLog, onStream, onProgress, onDone, onError } = {}) {
  const es = new EventSource(`/api/jobs/${jobId}/events`);

  es.onmessage = (ev) => {
    const e = JSON.parse(ev.data);
    if (e.type === "log") onLog && onLog(e.text, e);
    else if (e.type === "stream") onStream && onStream(e.text, e);
    else if (e.type === "progress") onProgress && onProgress(e);
    else if (e.type === "done") { es.close(); onDone && onDone(); }
    else if (e.type === "error") { es.close(); onError && onError(e.error || "unknown error"); }
  };

  // EventSource reconnects on its own, which is right for a transient drop but
  // wrong for a job that has already ended -- that would spin forever with the
  // panel's buttons stuck disabled. Ask the server what actually happened and
  // settle the UI from the job's real status.
  es.onerror = async () => {
    try {
      const j = await (await fetch(`/api/jobs/${jobId}`)).json();
      if (j.status === "running") return;          // genuinely transient; let it retry
      es.close();
      if (j.status === "error") onError && onError(j.error || "connection lost");
      else onDone && onDone();
    } catch (e) {
      /* server unreachable -- keep retrying */
    }
  };

  return es;
}

/* Append log/stream text into a scrolling box. The common case for a panel
   that just wants to watch a job run. */
function forgeStreamInto(jobId, box, opts = {}) {
  const write = (text) => {
    if (!box) return;
    box.textContent += text;
    box.scrollTop = box.scrollHeight;
  };
  return forgeStream(jobId, Object.assign({}, opts, {
    onLog: (t, e) => { write(t + "\n"); opts.onLog && opts.onLog(t, e); },
    onStream: (t, e) => { write(t); opts.onStream && opts.onStream(t, e); },
  }));
}

/* Poll a job to completion. For panels that need the job's RESULT rather than
   its log stream. Reports failures instead of charging ahead into a result
   fetch that 400s and then throws on undefined fields. */
function pollJob(jobId, { onDone, onError, every = 700 } = {}) {
  const t = setInterval(async () => {
    let j;
    try { j = await (await fetch(`/api/jobs/${jobId}`)).json(); }
    catch (e) { return; }                          // transient; try again next tick
    if (j.status === "running") return;
    clearInterval(t);
    if (j.status === "error") onError && onError(j.error || "unknown error");
    else onDone && onDone(j);
  }, every);
  return t;
}

/* --------------------------------------------------------------------------
   Simple / Advanced mode
   --------------------------------------------------------------------------
   Everything marked class="adv" is hidden in Simple mode (the rule lives in
   forge.css). The choice persists to the app's own settings endpoint as
   advanced_mode, which both apps already had in config.py.

   Usage, once the app knows its stored setting:
       ForgeMode.init(settings.advanced_mode);
   and include `advanced_mode: ForgeMode.on` in any settings save so a later
   save does not reset it. */
const ForgeMode = {
  on: false,

  apply(state) {
    this.on = !!state;
    document.body.classList.toggle("advanced", this.on);
    const s = document.getElementById("modeSimple");
    const a = document.getElementById("modeAdvanced");
    if (s) s.classList.toggle("on", !this.on);
    if (a) a.classList.toggle("on", this.on);
  },

  async set(state) {
    if (!!state === this.on) return;
    this.apply(state);
    await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ values: { advanced_mode: this.on } }),
    });
  },

  init(state) {
    this.apply(state);
    const s = document.getElementById("modeSimple");
    const a = document.getElementById("modeAdvanced");
    if (s) s.addEventListener("click", () => this.set(false));
    if (a) a.addEventListener("click", () => this.set(true));
  },
};

/* --------------------------------------------------------------------------
   Clear ("x") buttons
   --------------------------------------------------------------------------
   Every element marked data-clearable gets a small x in its corner that
   empties it. Call once at startup; safe to call again after adding boxes. */
function initClearButtons() {
  document.querySelectorAll("[data-clearable]").forEach(box => {
    if (box.dataset.clearInit) return;
    box.dataset.clearInit = "1";
    const wrap = document.createElement("div");
    wrap.className = "clearable-wrap";
    box.parentNode.insertBefore(wrap, box);
    wrap.appendChild(box);
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "clear-x";
    btn.textContent = "×";
    btn.title = "Clear";
    btn.setAttribute("aria-label", "Clear this panel");
    btn.addEventListener("click", () => { box.textContent = ""; });
    wrap.appendChild(btn);
  });
}

/* --------------------------------------------------------------------------
   Thumbnails
   --------------------------------------------------------------------------
   Rendering one costs an ffmpeg spawn on the server for video, so these are
   loading="lazy": only rows the user actually scrolls to are ever rendered,
   and the server caches each result on disk. Requires the app's backend to
   expose GET /api/thumbnail?path=&w= (MediaForge does). */
function fileThumb(path, w = 96) {
  const img = document.createElement("img");
  img.className = "file-thumb blank";
  img.loading = "lazy";
  img.decoding = "async";
  img.alt = "";
  img.src = `/api/thumbnail?path=${encodeURIComponent(path)}&w=${w}`;
  img.addEventListener("load", () => img.classList.remove("blank"));
  // Formats ffmpeg/Pillow can't open, or a file that vanished, keep the
  // hatched placeholder rather than showing a broken-image icon.
  img.addEventListener("error", () => { img.removeAttribute("src"); });
  return img;
}

/* --------------------------------------------------------------------------
   Tabs
   --------------------------------------------------------------------------
   Both apps use the same nav .tab / .panel[data-panel] markup. onSelect fires
   with the tab name, which is where panels do their lazy loading. */
function initTabs(onSelect) {
  const select = (name) => {
    document.querySelectorAll("nav .tab").forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    document.querySelectorAll(".panel").forEach(p => p.classList.toggle("active", p.dataset.panel === name));
    onSelect && onSelect(name);
  };
  document.querySelectorAll("nav .tab").forEach(t => {
    t.addEventListener("click", () => select(t.dataset.tab));
  });
  return select;
}

/* --------------------------------------------------------------------------
   Fullscreen inside the hub

   Moved out to shared/forge_chrome.js, which every app loads on its own line:

       <script src="/shared/forge_chrome.js"></script>

   It lives in its own file because the apps that most want a full-screen
   button (AI Studio, PixelForge) do not load this one -- they have their own
   DOM helpers and the `val`/`toast`/`checked` globals here would collide with
   them. It also used to be a top-level `const` in this file, which meant it
   was never on `window` and every `if (window.ForgeChrome)` guard silently
   skipped wiring the button.
   -------------------------------------------------------------------------- */
