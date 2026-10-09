/* Emberfield — the interface: the HUD, the hotbar, the tutorial, every screen.
 *
 * Split out of index.html in session 5. Everything here is DOM: the heads-up
 * display and hotbar redrawn from state, the data-driven tutorial, the shop
 * screen, and the veil screens (title, settings, pause) with their handlers.
 * Full-screen toggling lives here too because it is a UI concern. Game state is
 * read, not owned -- the verbs are in play.js.
 *
 * Loaded as a classic script after play.js. `S`, `TILE`, the utilities,
 * `Sound`, `ForgeArt` and everything in world.js / render.js / play.js are in
 * scope.
 */
"use strict";

/* ------------------------------------------------------------------ HUD */
function hud() {
  const m = Math.floor(S.clock.minutes);
  const hh = String(Math.floor(m / 60)).padStart(2, "0");
  const mm = String(m % 60).padStart(2, "0");
  const region = S.inInterior
    ? "indoors"
    : S.inWilds
      ? (S.world.regions.night ? "the wilds, after dark" : "the wilds")
      : regionAt(S.player.x / TILE, S.player.y / TILE);
  const hearts = "♥".repeat(Math.max(0, S.player.hp)) +
    `<span style="opacity:.28">${"♥".repeat(Math.max(0, S.player.maxHp - S.player.hp))}</span>`;
  $("#hud").innerHTML =
    `<b>Day ${S.clock.day}</b> &nbsp; ${hh}:${mm} &nbsp;·&nbsp; ${S.clock.season}` +
    (region ? ` &nbsp;·&nbsp; ${region}` : "") +
    `<br><span id="hearts">${hearts}</span> &nbsp;·&nbsp; ${S.gold}g` +
    `<br><span class="pill${S.settings.llm_mode !== "off" ? " on" : ""}">llm ${S.settings.llm_mode}</span>` +
    `<span class="pill${S.settings.voice_mode !== "off" ? " on" : ""}">voice ${S.settings.voice_mode}</span>`;
}

/* Hotbar icons are the real sprites, drawn once per rebuild into small
   canvases rather than every frame -- it changes when you pick something up,
   not sixty times a second. */
function drawHotbar() {
  const bar = $("#bar");
  bar.innerHTML = "";
  S.hotbar.forEach((entry, index) => {
    const def = lookup(entry.kind, entry.id);
    const slot = document.createElement("div");
    slot.className = "slot" + (index === S.slot ? " on" : "");
    const count = entry.kind === "items" ? (S.inv[entry.id] || 0) : 0;
    slot.innerHTML = `<span class="k">${index + 1}</span>` +
      (count ? `<span class="q">${count}</span>` : "");
    const sprite = def && def.sprite && S.atlas && S.atlas.get(def.sprite);
    if (sprite) {
      const canvas = document.createElement("canvas");
      canvas.width = sprite.w * 2; canvas.height = sprite.h * 2;
      const ctx = ForgeArt.crisp(canvas.getContext("2d"));
      ctx.setTransform(2, 0, 0, 2, 0, 0);
      S.atlas.draw(ctx, def.sprite, 0, 0, 0, 1);
      canvas.style.width = Math.min(30, sprite.w * 2) + "px";
      slot.appendChild(canvas);
    }
    const name = document.createElement("span");
    name.className = "n";
    name.textContent = def ? def.label : entry.id;
    slot.appendChild(name);
    bar.appendChild(slot);
  });
}

function regionAt(tx, ty) {
  for (const [name, r] of Object.entries(S.world.regions)) {
    if (typeof r !== "object" || !("w" in r)) continue;
    if (tx >= r.x && tx < r.x + r.w && ty >= r.y && ty < r.y + r.h)
      return name === "cave" ? "the cave mouth" : "the " + name;
  }
  return "";
}

/* ----------------------------------------------------------------- shop */
function shopScreen() {
  S.running = false;
  const buying = stock().map((item) => `
    <div class="choice trade${S.gold < item.buy ? " poor" : ""}" data-buy="${item.id}">
      <b>${item.label}</b><span>${item.buy}g${
        S.inv[item.id] ? ` · you have ${S.inv[item.id]}` : ""}</span></div>`).join("");
  const selling = sellable().map((item) => `
    <div class="choice trade" data-sell="${item.id}">
      <b>${item.label} <span style="opacity:.6">x${S.inv[item.id]}</span></b>
      <span>sells for ${item.sell}g</span></div>`).join("");

  showVeil(`
    <h2>The stall</h2>
    <p class="sub">You have <b style="color:var(--accent)">${S.gold} gold</b>.</p>
    <label>for sale</label>
    <div class="choices" id="buying">${buying || '<p class="note">Nothing in stock.</p>'}</div>
    <label>they will buy</label>
    <div class="choices" id="selling">${selling ||
      '<p class="note">You are carrying nothing they want.</p>'}</div>
    <div class="row"><button class="btn" id="leave">Done</button></div>
    <p class="note">Stock is whatever carries a buy price in
      <code>~/ForgeGameData/items</code>. Set one and it appears here.</p>
  `);
  document.querySelectorAll("#buying .choice").forEach((el) =>
    el.addEventListener("click", () => buyItem(el.dataset.buy)));
  document.querySelectorAll("#selling .choice").forEach((el) =>
    el.addEventListener("click", () => sellItem(el.dataset.sell)));
  $("#leave").addEventListener("click", resume);
}

/* --------------------------------------------------------- crafting */
function craftScreen(station) {
  S.running = false;
  const title = station === "cook" ? "The hearth" : "The workbench";
  const rows = craftable(station).map((r) => {
    const out = lookup("items", r.output);
    const cost = Object.entries(r.inputs || {}).map(([id, qty]) => {
      const item = lookup("items", id);
      const have = S.inv[id] || 0;
      return `<span style="color:${have >= qty ? "var(--muted)" : "#d9807a"}">${qty}× ${
        item ? item.label : id}${have < qty ? ` (have ${have})` : ""}</span>`;
    }).join(" · ");
    return `<div class="choice trade${canCraft(r) ? "" : " poor"}" data-make="${r.id}">
      <b>${r.label}</b><span>${cost}</span></div>`;
  }).join("");

  showVeil(`
    <h2>${title}</h2>
    <p class="sub">Turn what the wilds and the farm give you into something worth
      keeping.</p>
    <div class="choices" id="recipes">${rows ||
      '<p class="note">No recipes for this station yet.</p>'}</div>
    <div class="row"><button class="btn" id="leave">Done</button></div>
    <p class="note">Recipes are files in <code>~/ForgeGameData/recipes</code>.
      Add one and it appears here.</p>
  `);
  document.querySelectorAll("#recipes .choice").forEach((el) =>
    el.addEventListener("click", () => { craftRecipe(el.dataset.make); craftScreen(station); }));
  $("#leave").addEventListener("click", resume);
}

/* --------------------------------------------------------- the chest */
function storageScreen() {
  S.running = false;
  const list = (bag, action, verb) => Object.entries(bag)
    .filter(([id, n]) => n > 0 && lookup("items", id))  // tools and the bow stay out of the chest
    .map(([id, n]) => {
      const item = lookup("items", id);
      return `<div class="choice trade" data-${action}="${id}">
        <b>${item.label} <span style="opacity:.6">x${n}</span></b>
        <span>${verb}</span></div>`;
    }).join("");

  showVeil(`
    <h2>The chest</h2>
    <p class="sub">What you leave here stays here — it is saved with the valley.</p>
    <label>your pack</label>
    <div class="choices" id="pack">${list(S.inv, "put", "store one") ||
      '<p class="note">Your pack is empty.</p>'}</div>
    <label>in the chest</label>
    <div class="choices" id="chest">${list(S.storage, "take", "take one") ||
      '<p class="note">The chest is empty.</p>'}</div>
    <div class="row"><button class="btn" id="leave">Done</button></div>
  `);
  document.querySelectorAll("#pack .choice").forEach((el) =>
    el.addEventListener("click", () => { deposit(el.dataset.put, 1); storageScreen(); }));
  document.querySelectorAll("#chest .choice").forEach((el) =>
    el.addEventListener("click", () => { withdraw(el.dataset.take, 1); storageScreen(); }));
  $("#leave").addEventListener("click", resume);
}

/* ------------------------------------------------------------- tutorial */
/* Kept as data so it can grow into the real quest/script system later rather
   than being rewritten: each step is a prompt plus a condition to advance. */
const TUTORIAL = [
  { text: "<b>Emberfield.</b> You've inherited the plot at the bottom of the valley. Walk with <b>WASD</b> or the arrow keys.",
    done: () => S.player.moved > 40 },
  { text: "Pick your <b>hoe</b> with <b>1</b> and press <b>space</b> to till the ground you're facing.",
    done: () => Object.values(S.tileEdits).some((t) => t === "tilled" || t === "tilled_wet") },
  { text: "Now choose <b>seeds</b> from the bar and press <b>space</b> on the tilled soil. Then <b>water</b> them — dry ground grows nothing.",
    done: () => Object.keys(S.crops).length > 0 },
  { text: "Go inside your <b>house</b> — press <b>space</b> at the door — and sleep in the bed to end the day. Watered crops grow overnight.",
    done: () => S.clock.day > 1 },
  { text: "Walk the road to <b>town</b>. Press <b>space</b> at the stall, or at anyone standing about, to talk. A village and two farmsteads lie further out.",
    done: () => S.gold !== 0 || Object.keys(S.inv).length > 3 },
  { text: "After dark the open valley isn't safe. Hold your <b>bow</b> and <b>click</b> to shoot — every settlement stays clear.",
    done: () => S.clock.day > 2 },
  { text: "Press <b>q</b> to roll — a quick dart that shrugs off a hit. It has a short cooldown, so it's an escape, not a way to travel.",
    done: () => (S.player.rolls || 0) > 0 },
  { text: "A cave breaks the cliffs to the north. Press <b>space</b> at its mouth to go down — the wilds are different every day, and worse at night.",
    done: () => S.inWilds },
  { text: "Press <b>space</b> at the way you came in to climb back out. Nothing down here is ever the same twice.",
    done: () => false },
];

function tutorial() {
  const el = $("#tut");
  const stepDef = TUTORIAL[S.tutStep];
  if (!stepDef) { el.hidden = true; stopTutorialCheck(); return; }
  el.hidden = false;
  el.innerHTML = stepDef.text;
  clearInterval(S.tutTimer);
  S.tutTimer = setInterval(() => {
    // nobody can see the hint: skip the check (the step stays where it is)
    if (offScreen()) return;
    const s = TUTORIAL[S.tutStep];
    if (s && s.done()) { S.tutStep++; tutorial(); }
  }, 400);
}
function stopTutorialCheck() { clearInterval(S.tutTimer); S.tutTimer = 0; }

/* ----------------------------------------------------------- full screen */
/* Two mechanisms, because inside Forge the game is an iframe in a shell that
   owns a sidebar, and outside Forge it is an ordinary page.

   Asking the shell to drop its sidebar works everywhere and is instant. Real
   fullscreen is asked for as well, and simply does nothing if the embedding
   context refuses it -- so the worst case is still a game filling the window
   rather than a game that half-hid its own furniture. */
function setFullscreen(on) {
  S.fullscreen = on;
  try {
    if (window.parent && window.parent !== window) {
      window.parent.postMessage({ forge: "chrome", hidden: on }, "*");
    }
  } catch (e) { /* a stricter embedder; the fullscreen call below still tries */ }
  try {
    if (on && !document.fullscreenElement) {
      document.documentElement.requestFullscreen().catch(() => {});
    } else if (!on && document.fullscreenElement) {
      document.exitFullscreen().catch(() => {});
    }
  } catch (e) { /* not permitted here; the sidebar is already out of the way */ }
  resize();
}

function toggleFullscreen() { setFullscreen(!S.fullscreen); }

/* Leaving fullscreen by Escape or by the window manager must put the sidebar
   back, or the shell is left hidden with nothing on screen saying why. */
addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement && S.fullscreen) setFullscreen(false);
});

/* ------------------------------------------------------------------- UI */
function hideVeil() {
  $("#veil").hidden = true; $("#hud").hidden = false;
  $("#hint").hidden = false; $("#bar").hidden = false;
}
function showVeil(html) {
  $("#veil").hidden = false; $("#card").innerHTML = html;
  $("#hud").hidden = true; $("#hint").hidden = true;
  $("#bar").hidden = true; $("#tut").hidden = true;
}

async function titleScreen() {
  S.running = false;
  let saved = [];
  try { saved = await (await fetch("/api/saves")).json(); } catch (e) { saved = []; }

  const savedHtml = saved.length ? `
    <label>continue a valley</label>
    <div class="choices" id="saves">
      ${saved.map((s) => `<div class="choice" data-slot="${esc(s.slot)}">
        <b>${esc(s.name)} — day ${esc(s.day)}</b>
        <span>seed ${esc(s.seed)} · ${esc(s.death_rule)} death</span></div>`).join("")}
    </div>` : "";

  showVeil(`
    <h1>Emberfield</h1>
    <p class="sub">A valley to farm, and a night that isn't safe to cross.</p>
    ${savedHtml}
    <label>new world seed <span style="opacity:.6">— leave blank for a new valley</span></label>
    <input type="text" id="seed" placeholder="random">
    <label>if you die out there</label>
    <div class="choices" id="rules">
      <div class="choice" data-rule="soft"><b>Soft</b><span>You lose half your gold and wake up at home. Nothing else is ever lost.</span></div>
      <div class="choice on" data-rule="character"><b>Character permadeath</b><span>The farm, the valley and your stored goods persist. Death costs the adventurer you built.</span></div>
      <div class="choice" data-rule="full"><b>Full permadeath</b><span>Death deletes the save and rolls a new valley. Runs are short and sharp.</span></div>
    </div>
    <div class="row">
      <button class="btn" id="begin">Begin</button>
      <button class="btn ghost" id="toSettings">Settings</button>
      <div class="spacer"></div>
      <span style="font-size:11.5px;color:var(--muted)">session 2 · farming, saves, night</span>
    </div>
    ${S.content.problems.length ? `<p class="warn">${S.content.problems.length} content
      file(s) could not be read: ${esc(S.content.problems[0])}</p>` : ""}
  `);

  document.querySelectorAll("#rules .choice").forEach((el) =>
    el.addEventListener("click", () => {
      document.querySelectorAll("#rules .choice").forEach((n) => n.classList.remove("on"));
      el.classList.add("on"); S.deathRule = el.dataset.rule;
    }));
  document.querySelectorAll("#saves .choice").forEach((el) =>
    el.addEventListener("click", () => continueSave(el.dataset.slot)));

  $("#begin").addEventListener("click", async () => {
    if (S.starting) return;   // a double click must not grow the valley twice
    const raw = $("#seed").value.trim();
    const seed = raw === "" ? null : seedFrom(raw);
    S.starting = true;
    $("#begin").textContent = "Growing the valley…";
    try {
      const data = await api("/api/world/new", {
        json: { seed, death_rule: S.deathRule, name: "Emberfield" },
      });
      await startWorld(data, null);
    } catch (e) {
      $("#begin").textContent = "Begin";
      toast("could not grow the valley: " + e.message, 4000);
    } finally { S.starting = false; }
  });
  $("#toSettings").addEventListener("click", settingsScreen);
}

/* A typed seed: a number as itself, anything else (or a number too long to
   hold exactly) hashed, so every seed that is typed is a seed that works. */
function seedFrom(raw) {
  const n = parseInt(raw, 10);
  return Number.isSafeInteger(n) && n !== 0 ? n : hashString(raw);
}

function hashString(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h >>> 0;
}

function settingsScreen() {
  const r = S.caps.resources, v = S.caps.voice;
  S.running = false;
  showVeil(`
    <h2>Settings</h2>
    <p class="sub">The base game is complete on its own. Voice and the model layer stack on top.</p>

    <label>experiment: the world model</label>
    <select id="llm">
      <option value="off">off — the valley runs on its own rules</option>
      <option value="npcs">npcs — small models speak for named characters</option>
      <option value="director">director — a larger model shapes events, quests and the wilds</option>
      <option value="full">full — both</option>
    </select>

    <label>experiment: voice</label>
    <select id="voice">
      <option value="off">off — text and sound effects, like Stardew</option>
      <option value="narrator">narrator — pre-generated narration only</option>
      <option value="narrator_and_main">narrator and main characters</option>
    </select>

    <label>season palette (the same sprites, recoloured)</label>
    <select id="season">
      <option value="spring">spring</option><option value="summer">summer</option>
      <option value="autumn">autumn</option><option value="winter">winter</option>
    </select>

    <label>length of a day — <span id="dayv">${Math.round(dayLength() / 60)}</span> real minutes</label>
    <input type="range" id="day" min="1" max="30" step="1" value="${Math.round(dayLength() / 60)}">
    <p class="note">Minecraft's day is 20 minutes. Drop this to 1 or 2 while testing
      anything that depends on days passing — crops, seasons, nightfall — then put it back.</p>

    <label>zoom — <span id="zoomv">${S.zoom}</span>x</label>
    <input type="range" id="zoom" min="2" max="5" step="1" value="${S.zoom}">

    <label>sound — <span id="volv">${S.settings.volume != null ? S.settings.volume : 70}</span>%</label>
    <input type="range" id="vol" min="0" max="100" step="5"
           value="${S.settings.volume != null ? S.settings.volume : 70}">
    <p class="note">Every sound is synthesised from a recipe in
      <code>~/ForgeGameData/sounds</code> — there are no audio files in the game
      at all. If a sound is wrong, edit its numbers and reload.</p>

    <label>shadows</label>
    <select id="shadows">
      <option value="1">on — objects sit in the ground</option>
      <option value="0">off</option>
    </select>

    <label>background cores for voice and models</label>
    <input type="range" id="cores" min="1" max="${r.logical_cpus}" step="1"
           value="${S.settings.heavy_cores}">
    <p class="note">
      This machine has <b>${r.logical_cpus} logical CPUs</b>:
      ${r.performance_cpus.length} performance and ${r.efficiency_cpus.length} efficiency.
      Background work is pinned to <b>${r.background_cpus.join(", ")}</b>, leaving the
      performance cores free for the game.
      Speech runs on the CPU while the model runs on the iGPU, and both share one memory bus —
      so heavy jobs are <b>run one at a time</b> rather than together. Voice is always
      pre-generated and cached, never synthesised while you play.
      ${v.ready
        ? `Voices found in NovelForge's library (${v.voices_present.length} files), reused rather than re-downloaded.`
        : `<b>No voices found</b> at ${v.voices_dir} — voice mode will stay silent until NovelForge has downloaded some.`}
    </p>

    <div class="row">
      <button class="btn" id="save">Save</button>
      <button class="btn ghost" id="back">Back</button>
    </div>
  `);
  $("#llm").value = S.settings.llm_mode;
  $("#voice").value = S.settings.voice_mode;
  $("#season").value = S.clock.season;
  $("#shadows").value = S.settings.shadows ? "1" : "0";
  $("#zoom").addEventListener("input", (e) => { $("#zoomv").textContent = e.target.value; });
  /* Applied live rather than on Save, because setting a volume you cannot hear
     until you commit to it is guesswork. */
  $("#vol").addEventListener("input", (e) => {
    $("#volv").textContent = e.target.value;
    Sound.unlock();
    Sound.setVolume(parseInt(e.target.value, 10) / 100);
    Sound.play("select");
  });
  $("#day").addEventListener("input", (e) => { $("#dayv").textContent = e.target.value; });
  $("#save").addEventListener("click", async () => {
    if (S.savingSettings) return;
    const seasonChanged = S.clock.season !== $("#season").value;
    S.clock.season = $("#season").value;
    S.zoom = parseInt($("#zoom").value, 10);
    const values = {
      llm_mode: $("#llm").value, voice_mode: $("#voice").value,
      palette: SEASON_PALETTE[S.clock.season], zoom: S.zoom,
      shadows: $("#shadows").value === "1",
      volume: parseInt($("#vol").value, 10),
      day_seconds: parseInt($("#day").value, 10) * 60,
      heavy_cores: parseInt($("#cores").value, 10),
    };
    S.savingSettings = true;
    try {
      S.settings = await api("/api/settings", { json: { values } });
      S.caps = await api("/api/capabilities");
    } catch (e) {
      toast("settings not saved: " + e.message, 4000);
      return;
    } finally { S.savingSettings = false; }
    if (S.world) {
      if (seasonChanged) S.ground.clear();
      applyPalette(); resume();
    } else titleScreen();
  });
  $("#back").addEventListener("click", () => (S.world ? resume() : titleScreen()));
}

/* Off screen nobody plays. Inside Forge the hub posts {forge:"visible"} when
   another app or the home screen is in front (this page does not load
   forge_chrome.js, so it listens itself); a standalone tab can be hidden too.
   Either way pause exactly as Escape does: the frame loop stops instead of
   drawing for nobody, and the game state stays as it was. */
let hubShown = true; // what the hub last said; always true standalone
function offScreen() { return document.hidden || !hubShown; }
/* Sound rests too: the ambience is a looping bed, and a suspended audio
   context costs nothing. The next key or click wakes it (Sound.unlock). */
function pauseWhenHidden() {
  Sound.rest();
  if (S.world && S.running) pauseScreen();
}
addEventListener("message", (e) => {
  const m = e.data;
  if (e.source !== window.parent || !m || m.forge !== "visible") return;
  hubShown = !!m.visible;
  if (!hubShown) pauseWhenHidden();
});
document.addEventListener("visibilitychange", () => { if (document.hidden) pauseWhenHidden(); });

function pauseScreen() {
  S.running = false;
  stopTutorialCheck();
  Sound.rest();
  const planted = Object.keys(S.crops).length;
  showVeil(`
    <h2>Paused</h2>
    <p class="sub">${S.name} · day ${S.clock.day} · ${S.clock.season} · seed ${valleyWorld().seed}<br>
      ${planted} crop${planted === 1 ? "" : "s"} in the ground · ${S.gold} gold</p>
    <div class="row wrap">
      <button class="btn" id="resume">Resume</button>
      <button class="btn ghost" id="saveNow">Save</button>
      <button class="btn ghost" id="settings">Settings</button>
      <button class="btn ghost" id="full">${S.fullscreen ? "Leave full screen" : "Full screen"}</button>
      <button class="btn ghost" id="title">Save &amp; leave</button>
    </div>
  `);
  $("#resume").addEventListener("click", resume);
  $("#saveNow").addEventListener("click", async (e) => {
    const button = e.currentTarget;
    button.disabled = true;
    if (await autosave()) resume(); else button.disabled = false;
  });
  $("#settings").addEventListener("click", settingsScreen);
  $("#full").addEventListener("click", () => { toggleFullscreen(); resume(); });
  $("#title").addEventListener("click", async (e) => {
    const button = e.currentTarget;
    button.disabled = true;
    // Leave only once the day is safely on disk; otherwise stay paused, with
    // the toast saying why, rather than walk away from an unsaved valley.
    if (!(await autosave(true))) { button.disabled = false; return; }
    S.world = null;
    titleScreen();
  });
}

function resume() {
  hideVeil(); S.running = true; S.lastT = performance.now();
  Sound.unlock();
  if (TUTORIAL[S.tutStep]) tutorial();
  kickLoop();
}
