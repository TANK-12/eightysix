/* Avatar Studio: browse the Live2D models and puppets, play every motion,
 * make new motions (improvised or described to Jan), generate and edit
 * puppets, and choose each persona's avatar and voice. The avatar itself is
 * /shared/forge_avatar.js; storage is shared/forge_avatars.py through this
 * app's /api/avatars routes. */

const $ = (id) => document.getElementById(id);
const HEADERS = { "Content-Type": "application/json", "X-Forge": "1" };
async function api(path, options = {}) {
  const r = await fetch(path, { ...options, headers: { ...HEADERS, ...(options.headers || {}) } });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.blob();
}
const post = (path, body) => api(path, { method: "POST", body: JSON.stringify(body || {}) });
const del = (path) => api(path, { method: "DELETE" });
const status = (t) => { $("status").textContent = t || ""; };

const S = { data: null, personas: null, prefs: null, current: null, motions: {}, draft: null, puppet: null, undo: [], redo: [] };
const avatar = new ForgeAvatar($("stage"), { base: "/shared/avatars" });
avatar.interactive("studio");
const VOICES = ["af_heart", "af_bella", "af_nicole", "af_sky", "af_nova", "af_river", "af_sarah", "af_kore", "af_aoede", "af_jessica", "af_alloy",
  "am_puck", "am_michael", "am_fenrir", "am_adam", "am_echo", "am_eric", "am_liam", "am_onyx",
  "bf_emma", "bf_alice", "bf_isabella", "bf_lily", "bm_george", "bm_lewis", "bm_daniel", "bm_fable",
  "jf_alpha", "jf_gongitsune", "jf_nezumi", "jf_tebukuro", "jm_kumo"];
const HELLO = {
  tetsu: "Tetsu here. The forge is hot, the manifests are written, and it's not done till it's run.",
  kira: "Let's GO! What are we building today? Make it huge!",
  shizu: "I'm here. Tell me what broke, and I'll tell you exactly what I changed.",
  archchan: "Status report: everything's fine. Probably. I use Arch, by the way.",
  yui: "Oh, you came to talk to me? Cute. I'm listening.",
  ren: "Hey, you. Taking a break? Good. Stay a while.",
  shiori: "Shiori here. I checked that twice. Well, once and a half. Let me check it again.",
};

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

/* ------------------------------------------------------------ showing */

async function show(spec, persona) {
  status("Loading…");
  S.current = spec;
  try {
    let motions = {};
    if (spec.kind === "live2d") motions = (await api(`/api/avatars/live2d/${spec.id}/motions`)).motions;
    S.motions = motions;
    await avatar.show(spec, { ...S.data, motions }, persona || personaFor(spec));
    const model = S.data.models.find((m) => m.id === spec.id);
    const name = spec.kind === "live2d" ? (model ? model.name : spec.id) : ((spec.puppet || S.data.puppets.find((p) => p.id === spec.id) || {}).name || spec.id);
    $("now-title").textContent = name;
    const own = model ? model.own_motion_count : 0;
    const generated = spec.kind === "live2d" ? Object.keys(motions).length : Object.keys(S.data.recipes).length;
    $("now-sub").textContent = spec.kind === "live2d" ? `Live2D · ${own} own motions + ${generated} generated` : `Puppet · ${generated} motions`;
    status("");
  } catch (e) {
    status("Could not show it: " + e.message);
  }
  drawTiles();
  drawMotions();
}

function personaFor(spec) {
  return Object.values(S.personas || {}).find((p) => p.avatar && p.avatar.kind === spec.kind && p.avatar.id === spec.id) || null;
}

/* ------------------------------------------------------------ avatars tab */

function drawTiles() {
  const on = (kind, id) => S.current && S.current.kind === kind && S.current.id === id;
  $("models").replaceChildren();
  $("models2").replaceChildren();
  S.data.models.forEach((m) => {
    const models = $(m.cubism === 2 ? "models2" : "models");
    const b = el("button", "tile" + (on("live2d", m.id) ? " on" : ""), m.name);
    const who = personaFor({ kind: "live2d", id: m.id });
    b.appendChild(el("span", "sub", m.supported ? `${m.own_motion_count} own + generated${who ? " · " + who.name : ""}` : "Newer file format: needs a newer viewer"));
    if (!m.supported) { b.disabled = true; b.title = "This model's file format (Cubism 5.3) is newer than the viewer Forge uses."; }
    b.addEventListener("click", () => show({ kind: "live2d", id: m.id }));
    models.appendChild(b);
  });
  const puppets = $("puppets");
  puppets.replaceChildren();
  S.data.puppets.forEach((p) => {
    const b = el("button", "tile" + (on("puppet", p.id) ? " on" : ""), p.name);
    const who = personaFor({ kind: "puppet", id: p.id });
    b.appendChild(el("span", "sub", `${p.body} · ${p.hair_style}${who ? " · " + who.name : ""}`));
    b.addEventListener("click", () => { show({ kind: "puppet", id: p.id }); openPuppet(p); });
    puppets.appendChild(b);
  });
}

/* ------------------------------------------------------------ motions tab */

function opts() { return { intensity: +$("intensity").value, speed: +$("speed").value }; }

function drawMotions() {
  const list = $("motion-list");
  list.replaceChildren();
  const names = S.current && S.current.kind === "live2d" ? Object.keys(S.motions) : Object.keys(S.data.recipes);
  names.forEach((name) => {
    const r = S.data.recipes[name] || {};
    const b = el("button", r.source === "custom" ? "custom" : "", r.label || name);
    b.title = (r.mood || []).join(", ");
    b.addEventListener("click", () => avatar.play(name, opts()));
    if (r.source === "custom") {
      const x = el("span", "x", "×");
      x.title = "Delete this motion";
      x.addEventListener("click", async (e) => {
        e.stopPropagation();
        if (!await ForgeDialog.confirm(`Delete the motion "${r.label || name}"?`)) return;
        S.data.recipes = (await del(`/api/avatars/motions/${name}`)).recipes;
        refreshCurrent();
      });
      b.appendChild(x);
    }
    list.appendChild(b);
  });
  const own = $("own-list");
  own.replaceChildren();
  const model = S.current && S.current.kind === "live2d" && S.data.models.find((m) => m.id === S.current.id);
  if (!model) { own.appendChild(el("span", "muted small", "Puppets play the shared motions above.")); return; }
  Object.entries(model.motions).forEach(([group, items]) => items.forEach((name, i) => {
    const b = el("button", "", `${name || group + " " + (i + 1)}`);
    b.addEventListener("click", () => avatar.backend && avatar.backend.playOwn(group, i));
    own.appendChild(b);
  }));
}

function setDraft(recipe, info) {
  S.draft = recipe;
  $("draft-info").textContent = info;
  $("draft-play").disabled = $("draft-save").disabled = !recipe;
  if (recipe && !$("draft-name").value) $("draft-name").value = (recipe.label || "motion").toLowerCase().replace(/[^a-z0-9]+/g, "_").slice(0, 24);
  playDraft();
}

function playDraft() {
  if (!S.draft) return;
  if (avatar.kind === "puppet") avatar.playRecipe(S.draft, opts());
  else status("Live2D models play a new motion once it is saved; the preview runs on a puppet.");
}

async function refreshCurrent() {
  S.data = await api("/api/avatars");
  if (S.current) await show(S.current);
}

/* ------------------------------------------------------------ generator tab */

function field(label, input) {
  const l = el("label");
  l.appendChild(document.createTextNode(label));
  l.appendChild(input);
  return l;
}

function drawFields() {
  const box = $("fields");
  box.replaceChildren();
  const p = S.puppet;
  if (!p) return;
  const nice = (s) => s.replace(/_/g, " ");
  Object.entries(S.data.puppet_fields).forEach(([key, allowed]) => {
    const sel = el("select");
    allowed.forEach((v) => { const o = el("option", "", nice(v)); o.value = v; sel.appendChild(o); });
    sel.value = p[key];
    sel.addEventListener("change", () => edit(() => { p[key] = sel.value; }));
    box.appendChild(field(nice(key), sel));
  });
  S.data.puppet_colours.forEach((key) => {
    const c = el("input");
    c.type = "color";
    c.value = p.colours[key];
    c.addEventListener("input", () => edit(() => { p.colours[key] = c.value; }, true));
    box.appendChild(field(nice(key) + " colour", c));
  });
  Object.entries(S.data.puppet_numbers).forEach(([key, [lo, hi]]) => {
    const wrap = el("div", "num");
    const r = el("input"), n = el("input");
    r.type = "range"; n.type = "number";
    [r, n].forEach((i) => { i.min = lo; i.max = hi; i.step = (hi - lo) / 100; i.value = p[key]; });
    const set = (v) => edit(() => { p[key] = +v; r.value = n.value = v; }, true);
    r.addEventListener("input", () => set(r.value));
    n.addEventListener("change", () => set(n.value));
    wrap.append(r, n);
    box.appendChild(field(nice(key), wrap));
  });
}

let lastSnap = 0;
function edit(change, coalesce) {
  const now = Date.now();
  if (!coalesce || now - lastSnap > 800) S.undo.push(JSON.stringify(S.puppet));
  lastSnap = now;
  S.redo = [];
  change();
  preview();
}

function preview() {
  if (!S.puppet) return;
  avatar.show({ kind: "puppet", puppet: S.puppet }, S.data, personaFor({ kind: "puppet", id: S.puppet.id }));
  S.current = { kind: "puppet", id: S.puppet.id || "_draft", puppet: S.puppet };
  $("now-title").textContent = S.puppet.name || "New puppet";
  $("now-sub").textContent = "Puppet · editing";
}

function openPuppet(p) {
  S.puppet = JSON.parse(JSON.stringify(p));
  S.undo = []; S.redo = [];
  $("p-name").value = p.name || "";
  $("open-puppet").value = p.id || "";
  drawFields();
}

function drawPuppetPicker() {
  const sel = $("open-puppet");
  sel.replaceChildren();
  const blank = el("option", "", "(new)"); blank.value = ""; sel.appendChild(blank);
  S.data.puppets.forEach((p) => { const o = el("option", "", p.name); o.value = p.id; sel.appendChild(o); });
  if (S.puppet) sel.value = S.puppet.id || "";
}

/* ------------------------------------------------------------ personas tab */

function avatarOptions(sel, current) {
  const add = (kind, id, label) => { const o = el("option", "", label); o.value = `${kind}:${id}`; sel.appendChild(o); };
  // Cubism 4 models, then Cubism 2, then generated puppets last.
  [4, 2].forEach((level) => S.data.models.filter((m) => m.supported && m.cubism === level).forEach((m) => add("live2d", m.id, `${m.name} (Live2D${level === 2 ? ", Cubism 2" : ""})`)));
  S.data.puppets.forEach((p) => add("puppet", p.id, `${p.name} (puppet)`));
  sel.value = `${current.kind}:${current.id}`;
}

// The chooser: the avatar on show becomes what the picked persona wears in
// the chat. (The per-persona dropdowns on the Personas tab do the same.)
function drawUseFor() {
  const sel = $("use-for");
  const keep = sel.value;
  sel.replaceChildren();
  Object.values(S.personas).forEach((p) => { const o = el("option", "", p.name); o.value = p.id; sel.appendChild(o); });
  const fallback = S.prefs.pinned !== "auto" && S.personas[S.prefs.pinned] ? S.prefs.pinned : Object.keys(S.personas)[0];
  sel.value = keep && S.personas[keep] ? keep : fallback;
}

async function useCurrent() {
  const pid = $("use-for").value;
  if (!S.current || !pid) return status("Pick an avatar tile first.");
  try {
    const r = await post("/api/personas/prefs", { overrides: { [pid]: { avatar: { kind: S.current.kind, id: S.current.id } } } });
    S.personas = r.personas; S.prefs = r.prefs;
    drawTiles(); drawPersonas();
    status(`${S.personas[pid].name} now wears ${$("now-title").textContent} in the chat.`);
  } catch (e) {
    status("Could not save: " + e.message);
  }
}
$("use-it").addEventListener("click", useCurrent);

function drawPersonas() {
  drawUseFor();
  const pinned = $("pp-pinned"), downtime = $("pp-downtime");
  pinned.replaceChildren(); downtime.replaceChildren();
  const opt = (s, v, t) => { const o = el("option", "", t); o.value = v; s.appendChild(o); };
  opt(pinned, "auto", "By mood (auto)");
  opt(downtime, "alternate", "Yui and Ren take turns");
  Object.values(S.personas).forEach((p) => { opt(pinned, p.id, p.name); opt(downtime, p.id, p.name); });
  pinned.value = S.prefs.pinned; downtime.value = S.prefs.downtime;
  $("pp-enabled").checked = S.prefs.enabled; $("pp-speak").checked = S.prefs.speak;

  const list = $("persona-list");
  list.replaceChildren();
  Object.values(S.personas).forEach((p) => {
    const card = el("div", "persona");
    const top = el("div", "top");
    top.append(el("b", "", p.name), el("span", "moods", p.moods.join(" · ")));
    card.append(top, el("div", "muted small", p.tagline));
    const row = el("div", "gen");
    const av = el("select"), vo = el("select");
    avatarOptions(av, p.avatar);
    VOICES.forEach((v) => { const o = el("option", "", v); o.value = v; vo.appendChild(o); });
    if (!VOICES.includes(p.voice)) { const o = el("option", "", p.voice); o.value = p.voice; vo.appendChild(o); }
    vo.value = p.voice;
    const save = async () => {
      const [kind, id] = av.value.split(":");
      try {
        const r = await post("/api/personas/prefs", { overrides: { [p.id]: { avatar: { kind, id }, voice: vo.value } } });
        S.personas = r.personas; S.prefs = r.prefs;
        drawTiles(); drawUseFor();
        status(`${p.name} saved; the chat uses it now.`);
      } catch (e) {
        status("Could not save: " + e.message);
      }
    };
    av.addEventListener("change", save);
    vo.addEventListener("change", save);
    const see = el("button", "btn", "Show");
    see.addEventListener("click", () => show(p.avatar, p));
    const hear = el("button", "btn", "🔊");
    hear.title = "Hear this voice";
    hear.addEventListener("click", async () => { await show(p.avatar, p); sayHello(p); });
    row.append(field("Avatar", av), field("Voice", vo), see, hear);
    card.appendChild(row);
    list.appendChild(card);
  });
}

async function savePrefs(changes) {
  try {
    const r = await post("/api/personas/prefs", changes);
    S.personas = r.personas; S.prefs = r.prefs;
  } catch (e) { status(e.message); }
}

async function sayHello(persona) {
  const p = persona || avatar.persona || S.personas.tetsu;
  status("Warming up the voice…");
  try {
    const blob = await api("/api/voice", { method: "POST", body: JSON.stringify({ text: HELLO[p.id] || `Hi, I'm ${p.name}.`, voice: p.voice }) });
    status("");
    avatar.react("talking");
    await avatar.speakBlob(blob);
  } catch (e) {
    status("No voice: " + e.message);
  }
}

/* ------------------------------------------------------------ wiring */

document.querySelectorAll("#tabs button").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll("#tabs button").forEach((x) => x.classList.toggle("on", x === b));
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("hidden", t.id !== "tab-" + b.dataset.tab));
  if (b.dataset.tab === "maker" && !S.puppet) {
    const tetsu = S.data.puppets.find((p) => p.id === "tetsu") || S.data.puppets[0];
    if (tetsu) { openPuppet(tetsu); show({ kind: "puppet", id: tetsu.id }); }
  }
}));

[["intensity", "intensity-n"], ["speed", "speed-n"]].forEach(([a, b]) => {
  $(a).addEventListener("input", () => { $(b).value = $(a).value; });
  $(b).addEventListener("change", () => { $(a).value = $(b).value; });
});

$("improvise").addEventListener("click", async () => {
  const seed = $("imp-seed").value;
  const r = await post("/api/avatars/motions/improvise", { seed: seed === "" ? null : +seed, mood: $("imp-mood").value });
  setDraft(r, `Improvised: ${r.duration}s, ${Object.keys(r.curves).length} curves.`);
});
$("describe-go").addEventListener("click", async () => {
  const text = $("describe").value.trim();
  if (!text) return;
  $("describe-go").disabled = true;
  status("Asking Jan… (the model loads on demand)");
  try {
    const r = await post("/api/avatars/motions/describe", { text });
    setDraft(r, `From Jan: ${r.duration}s, ${Object.keys(r.curves).length} curves.`);
    status("");
  } catch (e) { status(e.message); }
  $("describe-go").disabled = false;
});
$("draft-play").addEventListener("click", playDraft);
$("draft-save").addEventListener("click", async () => {
  try {
    const r = await post("/api/avatars/motions", { name: $("draft-name").value || "motion", recipe: S.draft });
    status(`Saved as ${r.name}.`);
    S.data.recipes = r.recipes;
    $("draft-name").value = "";
    setDraft(null, "Saved. It is in the list above now.");
    refreshCurrent();
  } catch (e) { status(e.message); }
});

$("randomise").addEventListener("click", async () => {
  const p = await post("/api/avatars/puppets/random", { body: $("gen-body").value, style: $("gen-style").value });
  if (S.puppet) S.undo.push(JSON.stringify(S.puppet));
  S.puppet = { ...p, id: "" };
  $("p-name").value = "";
  $("open-puppet").value = "";
  drawFields();
  preview();
});
$("open-puppet").addEventListener("change", () => {
  const p = S.data.puppets.find((x) => x.id === $("open-puppet").value);
  if (p) { openPuppet(p); preview(); }
});
const undo = () => { if (!S.undo.length) return; S.redo.push(JSON.stringify(S.puppet)); S.puppet = JSON.parse(S.undo.pop()); drawFields(); preview(); };
const redo = () => { if (!S.redo.length) return; S.undo.push(JSON.stringify(S.puppet)); S.puppet = JSON.parse(S.redo.pop()); drawFields(); preview(); };
$("undo").addEventListener("click", undo);
$("redo").addEventListener("click", redo);
document.addEventListener("keydown", (e) => {
  if (!(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z" || $("tab-maker").classList.contains("hidden")) return;
  if (["INPUT", "TEXTAREA"].includes(document.activeElement.tagName) && document.activeElement.type !== "range") return;
  e.preventDefault();
  (e.shiftKey ? redo : undo)();
});
$("p-save").addEventListener("click", async () => {
  if (!S.puppet) return;
  const name = $("p-name").value.trim() || S.puppet.name || "Puppet";
  try {
    const r = await post("/api/avatars/puppets", { ...S.puppet, name, id: S.puppet.id || name });
    S.data.puppets = r.puppets;
    S.puppet.id = r.id; S.puppet.name = name;
    drawPuppetPicker(); drawTiles();
    status(`Saved ${name}.`);
  } catch (e) { status(e.message); }
});
$("p-delete").addEventListener("click", async () => {
  if (!S.puppet || !S.puppet.id || !await ForgeDialog.confirm(`Delete the puppet "${S.puppet.name}"?`)) return;
  const r = await del(`/api/avatars/puppets/${S.puppet.id}`);
  S.data.puppets = r.puppets;
  S.puppet = null;
  drawPuppetPicker(); drawFields(); drawTiles();
});

$("expr").addEventListener("change", () => avatar.expression($("expr").value));
$("say-hi").addEventListener("click", () => sayHello());
$("pp-pinned").addEventListener("change", () => savePrefs({ pinned: $("pp-pinned").value }));
$("pp-downtime").addEventListener("change", () => savePrefs({ downtime: $("pp-downtime").value }));
$("pp-enabled").addEventListener("change", () => savePrefs({ enabled: $("pp-enabled").checked }));
$("pp-speak").addEventListener("change", () => savePrefs({ speak: $("pp-speak").checked }));

(async function boot() {
  Object.keys(ForgeAvatar.EXPRESSIONS).forEach((k) => { const o = el("option", "", k); o.value = k; $("expr").appendChild(o); });
  try {
    S.data = await api("/api/avatars");
    const r = await api("/api/personas");
    S.personas = r.personas; S.prefs = r.prefs;
  } catch (e) { status("Could not load: " + e.message); return; }
  drawPuppetPicker();
  drawPersonas();
  drawTiles(); // before the first model loads, so a model that fails cannot hide the chooser
  const hash = new URLSearchParams(location.hash.slice(1));
  const first = hash.get("live2d") ? { kind: "live2d", id: hash.get("live2d") }
    : hash.get("puppet") ? { kind: "puppet", id: hash.get("puppet") }
    : S.personas.tetsu ? S.personas.tetsu.avatar : { kind: "live2d", id: "arch" };
  await show(first);
  if (hash.get("play")) avatar.play(hash.get("play"));
  const tab = hash.get("tab");
  if (tab) document.querySelector(`#tabs button[data-tab="${tab}"]`)?.click();
})();
