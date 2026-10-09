// AI Studio core: small helpers every section shares. Everything hangs off
// one global, AS, so nothing collides with the shared Forge scripts.
"use strict";
window.AS = window.AS || {};
(function (AS) {
  AS.OFFLINE = "Can't reach the AI Studio server right now.";
  AS.$ = (id) => document.getElementById(id);

  // el("button", {className: "btn", onclick}, "text", child...)
  AS.el = function (tag, props, ...kids) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(props || {})) {
      if (v === undefined || v === null || v === false) continue;
      if (k === "dataset") Object.assign(node.dataset, v);
      else if (k in node) node[k] = v;
      else node.setAttribute(k, v === true ? "" : v);
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      node.append(kid instanceof Node ? kid : String(kid));
    }
    return node;
  };

  // ---- tiny event bus between sections ----
  const bus = new Map();
  AS.on = (name, fn) => { if (!bus.has(name)) bus.set(name, new Set()); bus.get(name).add(fn); };
  AS.emit = (name, data) => (bus.get(name) || []).forEach((fn) => { try { fn(data); } catch (e) { console.error(e); } });

  // ---- one heavy job at a time ----
  // A model video, a camera-move video or a running world each hold a big
  // model in memory; two at once freeze the laptop. While one runs, the
  // other sections' Go buttons and the Models panel's Use this wait, with
  // a line saying why. Sources: this page's own jobs, and the server's
  // busy report (another window).
  const heavy = new Map(); // source -> {form, text}
  AS.heavy = {
    set(source, text, form) {
      if (text) heavy.set(source, { text, form: form || null }); else heavy.delete(source);
      AS.emit("heavy");
    },
    // the server's report {kind, id, detail} or null; a job this page began
    // itself is already known here, so it is not counted twice
    server(b) {
      const ours = b && heavy.has(b.kind === "world" ? "world" : "video");
      const text = b && !ours ? b.detail || "Another big job is running. Wait for it to finish." : "";
      if (text !== AS.heavy.text("server")) AS.heavy.set("server", text);
    },
    has: (source) => heavy.has(source),
    text: (source) => (heavy.get(source) || {}).text || "",
    // the reason a form (or, with no form, the Models panel) must wait, or ""
    reason(form) {
      for (const h of heavy.values()) if (!form || h.form !== form) return h.text;
      return "";
    },
  };

  // ---- talking to the server ----
  // The words a failed request should show: FastAPI sends a string, or for a
  // rejected field a list of {loc, msg}; a dead server throws a TypeError.
  AS.errorText = async function (res, fallback) {
    const err = await res.json().catch(() => ({}));
    const d = err.detail ?? err.message;
    if (Array.isArray(d)) {
      return d.map((x) => `${(x.loc || []).filter((k) => k !== "body").join(" ") || "request"}: ${x.msg}`).join("; ");
    }
    return typeof d === "string" && d ? d : `${fallback} (${res.status})`;
  };
  AS.failText = (e) => (e instanceof TypeError ? AS.OFFLINE : e && e.message ? e.message : String(e));

  async function call(url, opts, fallback) {
    const res = await fetch(url, opts);
    if (!res.ok) {
      const err = new Error(await AS.errorText(res, fallback || "That didn't work"));
      err.status = res.status;
      err.fromServer = !/\(\d{3}\)$/.test(err.message); // the server gave its own words
      throw err;
    }
    return res.status === 204 ? {} : res.json().catch(() => ({}));
  }
  AS.get = (url, fallback) => call(url, {}, fallback);
  AS.post = (url, body, fallback, method = "POST") =>
    call(url, {
      method,
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }, fallback);
  AS.del = (url, fallback) => call(url, { method: "DELETE" }, fallback);

  // ---- numbers and words ----
  // A number field as a number inside its own min/max; empty or junk gives
  // the fallback, so the server never gets null or NaN.
  AS.num = function (id, fallback, float) {
    const node = AS.$(id);
    let n = float ? parseFloat(node.value) : parseInt(node.value, 10);
    if (!Number.isFinite(n)) return fallback;
    if (node.min !== "" && n < Number(node.min)) n = Number(node.min);
    if (node.max !== "" && n > Number(node.max)) n = Number(node.max);
    return n;
  };

  // Bytes in plain words: "3.4 GB", "850 MB". Only dialogs and the delete
  // list use it; model cards never show a size.
  AS.size = function (n) {
    n = Math.max(0, Number(n) || 0);
    const GB = 1e9, MB = 1e6;
    if (n >= 100 * GB) return Math.round(n / GB) + " GB";
    if (n >= GB) return (n / GB).toFixed(1).replace(/\.0$/, "") + " GB";
    if (n >= MB) return Math.max(1, Math.round(n / MB)) + " MB";
    return Math.max(1, Math.round(n / 1e3)) + " KB";
  };

  AS.seconds = function (s) {
    s = Math.round(Number(s) || 0);
    if (s < 90) return s === 1 ? "1 second" : `${s} seconds`;
    const m = Math.floor(s / 60), r = s % 60;
    return r ? `${m} min ${r} s` : `${m} min`;
  };

  // ---- segmented choices: <div class="chips" data-value="x"><button data-value> ----
  AS.chips = function (box, onChange) {
    const buttons = () => [...box.querySelectorAll(":scope > button[data-value]")];
    const paint = () => buttons().forEach((b) => {
      const on = b.dataset.value === box.dataset.value;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
    });
    box.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-value]");
      if (!b || b.parentElement !== box || b.disabled) return;
      if (box.dataset.value === b.dataset.value) return;
      box.dataset.value = b.dataset.value;
      paint();
      if (onChange) onChange(b.dataset.value);
    });
    paint();
    return {
      get value() { return box.dataset.value; },
      set value(v) { box.dataset.value = String(v); paint(); },
      paint,
    };
  };

  // Width and height for a shape, built round the model's usual size (both
  // multiples of 64); "usual" leaves both to the server.
  AS.shapeSize = function (shape, base) {
    const b = Number(base) || 512;
    const r64 = (x) => Math.max(64, Math.round(x / 64) * 64);
    if (shape === "square") return { width: r64(b), height: r64(b) };
    if (shape === "tall") return { width: r64(b * 0.75), height: r64(b * 4 / 3) };
    if (shape === "wide") return { width: r64(b * 4 / 3), height: r64(b * 0.75) };
    return {};
  };

  // ---- toast ----
  let toastTimer = 0;
  AS.toast = function (msg, kind) {
    const t = AS.$("toast");
    t.textContent = msg;
    t.className = "toast" + (kind ? " " + kind : "");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.add("hidden"), 4200);
  };

  // ---- a file or library picture as a data URL ----
  AS.fileToDataURL = (file) => new Promise((done, fail) => {
    const r = new FileReader();
    r.onload = () => done(String(r.result));
    r.onerror = () => fail(new Error("That file could not be read."));
    r.readAsDataURL(file);
  });

  // ---- videos rest while AI Studio is hidden ----
  // Another hub app in front, or the window minimised: every playing video
  // pauses, and carries on when shown again (not one that was paused by
  // hand). A video that lands while hidden starts when it is shown.
  const resting = new Set();
  AS.playWhenShown = function (video) {
    if (ForgeIdle.shown()) video.play().catch(() => {});
    else resting.add(video);
  };
  function rest() {
    if (!ForgeIdle.shown()) {
      document.querySelectorAll("video").forEach((v) => { if (!v.paused) { v.pause(); resting.add(v); } });
    } else {
      resting.forEach((v) => { if (v.isConnected) v.play().catch(() => {}); });
      resting.clear();
    }
  }
  document.addEventListener("visibilitychange", rest);
  document.addEventListener("forge-visible", rest);

  // A picture or video element for a result or a library item.
  AS.media = function (url, kind, opts = {}) {
    if (kind === "video") {
      const v = AS.el("video", { src: url, loop: true, muted: !!opts.muted, controls: opts.controls !== false, playsInline: true });
      if (opts.play) AS.playWhenShown(v);
      return v;
    }
    return AS.el("img", { src: url, alt: opts.alt || "", loading: opts.lazy ? "lazy" : "eager", decoding: "async" });
  };
})(window.AS);
