// Voice page: status, models, per-app picks, mic and speaker tests, history.
"use strict";

const H = { "X-Forge": "1" };
const $ = (id) => document.getElementById(id);
let registry = { models: [], defaults: {} };

async function api(path, opts = {}) {
  const res = await fetch(path, { ...opts, headers: { ...H, ...(opts.headers || {}) } });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).detail || msg; } catch (e) { /* not JSON */ }
    throw new Error(msg);
  }
  return res;
}
const getJSON = async (p) => (await api(p)).json();
const postJSON = (p, body) => api(p, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body || {}) });

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "text") e.textContent = v; else e.setAttribute(k, v);
  }
  kids.forEach((k) => e.append(k));
  return e;
}

async function refreshStatus() {
  try {
    const s = await (await fetch("/api/status")).json();
    $("state").textContent = s.state;
    $("state").className = "pill " + s.state;
    $("loaded").textContent = s.loaded.length ? "loaded: " + s.loaded.map((m) => m.id).join(", ") : "nothing loaded";
    document.querySelectorAll("#models tbody tr").forEach((tr) => {
      tr.lastChild.textContent = s.loaded.some((m) => m.id === tr.dataset.id) ? "yes" : "";
    });
  } catch (e) { $("state").textContent = "offline"; }
}

async function loadModels() {
  registry = await getJSON("/api/registry");
  const body = $("models").tBodies[0];
  body.replaceChildren(...registry.models.map((m) => {
    const tr = el("tr", {}, el("td", { text: m.label }), el("td", { text: m.kind }), el("td", { text: m.tier || "" }),
      el("td", { text: m.size_mb ? m.size_mb + " MB" : "" }), el("td", { text: m.present ? "yes" : "missing" }), el("td"));
    tr.dataset.id = m.id;
    return tr;
  }));
  $("disk").textContent = `Free disk: ${registry.disk_free_gb} GB`;
  const best = $("best");
  best.disabled = !registry.defaults.tts_best;
  best.textContent = best.disabled ? "Best voice not installed" : "Hear the best voice";
}

function select(kind, value) {
  const s = el("select");
  s.append(el("option", { value: "", text: "default" }));
  registry.models.filter((m) => m.kind === kind).forEach((m) => s.append(el("option", { value: m.id, text: m.label })));
  s.value = value || "";
  return s;
}

async function loadApps() {
  const [{ apps }, settings] = await Promise.all([getJSON("/api/apps"), getJSON("/api/settings")]);
  const body = $("apps").tBodies[0];
  body.replaceChildren(...apps.map((a) => {
    const own = a.name === "anywhere" ? {} : (settings.apps[a.name] || {});
    const stt = select("stt", own.stt && own.stt.model);
    const tts = select("tts", own.tts && own.tts.model);
    const voice = el("select");
    const fill = () => {
      const row = registry.models.find((m) => m.id === (tts.value || a.tts)) || { voices: [] };
      voice.replaceChildren(el("option", { value: "", text: "default" }), ...(row.voices || []).map((v) => el("option", { value: v, text: v })));
      voice.value = (own.tts && own.tts.voice) || "";
    };
    fill();
    const speed = el("input", { type: "number", min: "0.5", max: "2", step: "0.05", value: String(a.speed) });
    const speak = el("input", { type: "checkbox" });
    speak.checked = a.speak_replies;
    const save = async () => {
      const tt = { model: tts.value || null, voice: voice.value || null, speed: Number(speed.value) || 1 };
      const patch = a.name === "anywhere"
        ? { stt: { model: stt.value || null }, tts: tt, anywhere: { speak_replies: speak.checked } }
        : { apps: { [a.name]: { stt: { model: stt.value || null }, tts: tt, speak_replies: speak.checked } } };
      try { await postJSON("/api/settings", patch); if (window.toast) toast("Saved"); }
      catch (e) { if (window.toast) toast(e.message, "error"); }
    };
    tts.addEventListener("change", () => { fill(); save(); });
    [stt, voice, speed, speak].forEach((x) => x.addEventListener("change", save));
    return el("tr", {}, el("td", { text: a.label }), el("td", {}, stt), el("td", {}, tts), el("td", {}, voice), el("td", {}, speed), el("td", {}, speak));
  }));
}

async function loadHistory() {
  const { history } = await getJSON("/api/history");
  $("history").replaceChildren(...history.map((h) => el("li", {},
    el("div", { text: h.heard || "(nothing heard)" }),
    el("div", { class: "who", text: `${h.at} · ${h.target} · ${h.handled_by} · ${h.ms} ms` }),
    ...(h.reply ? [el("div", { text: h.reply })] : []))));
}

async function hear(model) {
  const row = (registry.models || []).find((m) => m.id === model);
  $("sayOut").textContent = row && row.tier === "best"
    ? "Making speech with the best voice. It is about five times slower than speaking, so a sentence takes 20 to 40 s..."
    : "Making speech...";
  const t0 = performance.now();
  try {
    const res = await postJSON("/api/tts", { text: $("sayText").value, app: "anywhere", model });
    const wav = await res.blob();
    const took = ((performance.now() - t0) / 1000).toFixed(1);
    const fell = res.headers.get("X-Voice-Fell-Back");
    $("sayOut").textContent = `${res.headers.get("X-Voice-Model")} · ${res.headers.get("X-Voice-Voice")} · ${res.headers.get("X-Voice-Seconds")} s of speech made in ${took} s`
      + (fell ? ` · the fast voice spoke instead: ${fell}` : "");
    new Audio(URL.createObjectURL(wav)).play();
  } catch (e) { $("sayOut").textContent = e.message; }
}

async function micTest() {
  const out = $("micOut");
  try {
    // a WAV through Web Audio: MediaRecorder gives 0 bytes in Forge's WebKit (shared/forge_mic.js)
    const rec = await ForgeMic.start();
    out.textContent = "Listening for 3 seconds...";
    await new Promise((r) => setTimeout(r, 3000));
    const wav = await rec.stop();
    if (rec.silent()) {
      out.textContent = "The microphone gave only silence. Is it muted?";
      return;
    }
    out.textContent = "Transcribing...";
    const res = await api("/api/stt?app=anywhere", { method: "POST", body: wav });
    const r = await res.json();
    out.textContent = r.text ? `"${r.text}" (${r.model}, ${r.ms} ms)` : "Heard nothing.";
  } catch (e) { out.textContent = e.message; }
}

$("tap").addEventListener("click", () => api("/api/ptt/tap", { method: "POST" }).then(refreshStatus));
$("hush").addEventListener("click", () => api("/api/hush", { method: "POST" }).then(refreshStatus));
$("unload").addEventListener("click", () => api("/api/unload", { method: "POST" }).then(refreshStatus));
$("fast").addEventListener("click", () => hear(registry.defaults.tts));
$("best").addEventListener("click", () => hear(registry.defaults.tts_best));
$("mic").addEventListener("click", micTest);

(async () => {
  await loadModels();
  await Promise.all([loadApps(), loadHistory(), refreshStatus()]);
  setInterval(refreshStatus, 1500);
  setInterval(loadHistory, 5000);
})();
