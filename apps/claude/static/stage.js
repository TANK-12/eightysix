/* The avatar stage beside the conversation: the persona answering this turn,
 * shown as its Live2D model or generated puppet, reacting to what Claude is
 * doing (thinking, using a tool, done, failed), moving its lips while text
 * streams, speaking the reply in its own voice when "Speak" is on, and
 * following the mouse. app.js hands every event to Stage.event(event, live);
 * live is false while old history is replayed, so nothing reacts or speaks
 * then. Personas and the mood rules: personas.py and
 * ~/.claude/self/PERSONALITY.md. */

const Stage = (() => {
  const $ = (id) => document.getElementById(id);
  const H = { "Content-Type": "application/json", "X-Forge": "1" };
  const S = { sitting: false, personas: {}, prefs: null, data: null, avatar: null, persona: null, shownKey: "", turnText: "", open: true };

  async function get(path, opts = {}) {
    const r = await fetch(path, { ...opts, headers: { ...H, ...(opts.headers || {}) } });
    if (!r.ok) {
      let d = r.statusText;
      try { d = (await r.json()).detail || d; } catch (e) {}
      throw new Error(d);
    }
    return (r.headers.get("content-type") || "").includes("json") ? r.json() : r.blob();
  }

  function note(text) { $("stage-note").textContent = text || ""; }

  // The animated avatar is off at every page load (Emerson, 2026-10-07: "i dont
  // want the live 2d to happen automatically"); 🎭 or "Turn on the avatar"
  // turns it on for this sitting only (S.sitting, never saved, so the saved
  // prefs.avatar no longer starts it). While it is off nothing animated is built, so
  // pixi and Live2D never load; this stand-in keeps the voice working and
  // lets everything else ignore the difference.
  function quiet() {
    return {
      persona: null, speaking: null,
      show() {}, expression() {}, react() {}, reactTag() {}, talkPulse() {}, interactive() {},
      destroy() { this.stopSpeaking(); },
      async speakBlob(blob) {
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        this.speaking = audio;
        try {
          await audio.play();
          await new Promise((resolve) => { audio.onended = resolve; audio.onerror = resolve; });
        } finally { this.speaking = null; URL.revokeObjectURL(url); }
      },
      stopSpeaking() { if (this.speaking) { this.speaking.pause(); this.speaking.onended && this.speaking.onended(); } },
    };
  }

  const avatarOn = () => S.sitting;

  // A fresh stage view each time, so the old avatar's pointer handlers go with it.
  function build() {
    const old = $("stage-view");
    const view = old.cloneNode(false);
    old.replaceWith(view);
    S.shownKey = "";
    if (!avatarOn()) {
      const off = document.createElement("div");
      off.className = "stage-off";
      const on = document.createElement("button");
      on.type = "button";
      on.textContent = "Turn on the avatar";
      on.addEventListener("click", () => setAvatar(true));
      const why = document.createElement("p");
      why.className = "muted small";
      why.textContent = "The animated avatar starts off. Turning it on lasts until the page reloads; personas, voice and the chat below work either way.";
      off.append(why, on);
      view.appendChild(off);
      return quiet();
    }
    const avatar = new ForgeAvatar(view, { base: "/shared/avatars", frame: 0.55 });
    avatar.interactive("stage");
    view.addEventListener("dblclick", () => avatar.react(Math.random() < 0.5 ? "done" : "talking"));
    return avatar;
  }

  async function setAvatar(on) {
    S.sitting = !!on;
    rebuild();
    drawPicker();
  }

  function rebuild() {
    if (S.avatar) S.avatar.destroy();
    S.avatar = build();
    if (S.persona) wear(S.persona);
  }

  async function wear(persona) {
    if (!persona || !S.avatar) return;
    const changed = !S.persona || S.persona.id !== persona.id;
    S.persona = persona;
    if (changed) loadChat();
    $("stage-name").textContent = persona.name;
    drawLook();
    $("stage-name").title = persona.tagline || "";
    if (!avatarOn()) { S.avatar.persona = persona; return; }
    const spec = persona.avatar;
    const key = `${spec.kind}:${spec.id}`;
    if (key === S.shownKey) { S.avatar.persona = persona; S.avatar.expression(persona.expression || "neutral"); return; }
    S.shownKey = key;
    try {
      let motions = {};
      if (spec.kind === "live2d") motions = (await get(`/api/avatars/live2d/${spec.id}/motions`)).motions;
      await S.avatar.show(spec, { ...S.data, motions }, persona);
      note("");
    } catch (e) {
      note(`Could not show ${persona.name}: ${e.message}`);
      S.shownKey = "";
    }
  }

  function mood(m) { $("stage-mood").textContent = m || ""; $("stage-mood").classList.toggle("hidden", !m); }

  async function speak() {
    const text = S.turnText.trim();
    S.turnText = "";
    if (!S.prefs || !S.prefs.speak || !text || !S.persona) return;
    try {
      const blob = await get("/api/voice", { method: "POST", body: JSON.stringify({ text, voice: S.persona.voice }) });
      S.avatar.react("talking");
      await S.avatar.speakBlob(blob);
    } catch (e) {
      note("Voice: " + e.message);
    }
  }

  function event(ev, live) {
    if (!S.avatar) return;
    if (ev.type === "forge_persona") {
      const p = S.personas[ev.persona];
      if (p && S.prefs && S.prefs.enabled) { wear(p); mood(ev.mood); }
      if (live) { S.avatar.stopSpeaking(); S.turnText = ""; S.avatar.react("thinking"); }
      return;
    }
    if (!live) return;
    if (ev.type === "stream_event") {
      const e = ev.event || {};
      if (e.type === "content_block_delta" && e.delta && e.delta.type === "text_delta") S.avatar.talkPulse();
      if (e.type === "content_block_start" && e.content_block && e.content_block.type === "tool_use") S.avatar.react("tool");
    } else if (ev.type === "assistant") {
      const text = ((ev.message || {}).content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n");
      if (text) S.turnText = text; // the last text of the turn is what gets spoken
    } else if (ev.type === "result") {
      const bad = ev.is_error || (ev.subtype && ev.subtype !== "success");
      S.avatar.react(bad ? "error" : "done");
      if (!bad) speak();
    } else if (ev.type === "forge_exit") {
      S.avatar.react("error");
    }
  }

  // Every model and puppet, for the persona on stage. Cubism 4 first, as in the Studio.
  function drawLook() {
    const sel = $("stage-look");
    sel.replaceChildren();
    if (!S.persona || !S.data) return;
    const add = (kind, id, label) => { const o = document.createElement("option"); o.value = `${kind}:${id}`; o.textContent = label; sel.appendChild(o); };
    [4, 2].forEach((level) => (S.data.models || []).filter((m) => m.supported && m.cubism === level).forEach((m) => add("live2d", m.id, m.name)));
    (S.data.puppets || []).forEach((p) => add("puppet", p.id, `${p.name} (puppet)`));
    sel.value = `${S.persona.avatar.kind}:${S.persona.avatar.id}`;
    sel.classList.toggle("hidden", !S.prefs || !S.prefs.enabled || !avatarOn());
  }

  // Choices made in the Studio (or another window) show up without a reload.
  async function reread() {
    const was = avatarOn();
    try {
      const p = await get("/api/personas");
      S.personas = p.personas; S.prefs = p.prefs;
    } catch (e) { return; }
    drawPicker();
    if (was !== avatarOn()) rebuild();
    if (S.persona && S.personas[S.persona.id]) await wear(S.personas[S.persona.id]);
  }

  function drawPicker() {
    const sel = $("stage-who");
    sel.replaceChildren();
    const add = (v, t) => { const o = document.createElement("option"); o.value = v; o.textContent = t; sel.appendChild(o); };
    add("auto", "By mood");
    Object.values(S.personas).forEach((p) => add(p.id, p.name));
    add("off", "Off (plain Claude)");
    sel.value = !S.prefs.enabled ? "off" : S.prefs.pinned;
    $("stage-speak").classList.toggle("on", !!S.prefs.speak);
    $("stage-speak").textContent = S.prefs.speak ? "🔊" : "🔇";
    $("stage-avatar").classList.toggle("on", avatarOn());
    $("stage-avatar").title = avatarOn() ? "Turn the animated avatar off" : "Turn the animated avatar on until the page reloads";
    drawLook();
  }

  async function savePrefs(changes) {
    const r = await get("/api/personas/prefs", { method: "POST", body: JSON.stringify(changes) });
    S.personas = r.personas; S.prefs = r.prefs;
    drawPicker();
  }

  function setOpen(open) {
    S.open = open;
    $("app").classList.toggle("stage-closed", !open);
    $("stage-toggle").textContent = open ? "⟩" : "⟨";
    $("stage-toggle").title = open ? "Hide the avatar" : "Show the avatar";
  }

  /* ------------------------------------------------ chatting with the avatar */

  function bubble(cls, text) {
    const b = document.createElement("div");
    b.className = cls;
    b.textContent = text;
    $("stage-log").appendChild(b);
    $("stage-log").scrollTop = $("stage-log").scrollHeight;
    return b;
  }

  async function loadChat() {
    $("stage-log").replaceChildren();
    if (!S.persona) return;
    try {
      const h = (await get(`/api/avatars/chat/${S.persona.id}`)).history;
      h.slice(-8).forEach((m) => bubble(m.role === "user" ? "me" : "them", m.content));
    } catch (e) { /* no history yet */ }
  }

  async function chat(text) {
    const who = S.persona;
    if (!who || !text) return;
    bubble("me", text);
    const wait = bubble("them wait", `${who.name} is thinking…`);
    S.avatar.react("thinking");
    $("stage-input").disabled = true;
    try {
      const r = await get(`/api/avatars/chat/${who.id}`, { method: "POST", body: JSON.stringify({ text }) });
      wait.className = "them";
      wait.textContent = r.reply;
      wait.title = `${r.tag} · ${r.model}`;
      S.avatar.reactTag(r.tag);
      if (S.prefs && S.prefs.speak && r.reply) {
        const blob = await get("/api/voice", { method: "POST", body: JSON.stringify({ text: r.reply, voice: who.voice }) });
        await S.avatar.speakBlob(blob);
      } else S.avatar.talkPulse(Math.min(4000, 60 * r.reply.length));
    } catch (e) {
      wait.className = "them wait";
      wait.textContent = "Chat: " + e.message;
      S.avatar.react("error");
    } finally {
      $("stage-input").disabled = false;
      $("stage-input").focus();
    }
  }

  async function boot() {
    // The avatar pane starts shut at every page load (Emerson, 2026-10-08:
    // "the live 2d thing still opens on auto at claude start up i dont want
    // that"); the ⟨ button opens it for this sitting. Its old saved choice
    // is cleared so nothing reopens it.
    try { localStorage.removeItem("claude.stage.open"); } catch (e) {}
    setOpen(false);
    try {
      const [p, d] = await Promise.all([get("/api/personas"), get("/api/avatars")]);
      S.personas = p.personas; S.prefs = p.prefs; S.data = d;
    } catch (e) { note("Avatars unavailable: " + e.message); return; }
    S.avatar = build();
    drawPicker();
    const first = S.prefs.pinned !== "auto" && S.personas[S.prefs.pinned] ? S.personas[S.prefs.pinned] : S.personas.tetsu || Object.values(S.personas)[0];
    await wear(first);
    $("stage-who").addEventListener("change", async (e) => {
      const v = e.target.value;
      await savePrefs(v === "off" ? { enabled: false } : { enabled: true, pinned: v });
      if (v !== "off" && v !== "auto") wear(S.personas[v]);
      note(v === "off" ? "Personas are off; the next message starts plain." : "Applies from your next message.");
    });
    $("stage-look").addEventListener("change", async (e) => {
      if (!S.persona) return;
      const [kind, id] = e.target.value.split(":");
      const who = S.persona.id;
      try {
        await savePrefs({ overrides: { [who]: { avatar: { kind, id } } } });
        await wear(S.personas[who]);
        note(`${S.personas[who].name} now wears ${e.target.selectedOptions[0].textContent}.`);
      } catch (err) { note("Could not save: " + err.message); }
    });
    document.addEventListener("visibilitychange", () => { if (document.visibilityState === "visible") reread(); });
    $("stage-speak").addEventListener("click", () => savePrefs({ speak: !S.prefs.speak }));
    $("stage-avatar").addEventListener("click", () => setAvatar(!avatarOn()));
    $("stage-toggle").addEventListener("click", () => setOpen(!S.open));
    $("stage-say").addEventListener("submit", (e) => {
      e.preventDefault();
      const text = $("stage-input").value.trim();
      $("stage-input").value = "";
      chat(text);
    });
    $("stage-forget").addEventListener("click", async () => {
      if (!S.persona || !await ForgeDialog.confirm(`Forget the chat with ${S.persona.name}?`)) return;
      await get(`/api/avatars/chat/${S.persona.id}`, { method: "DELETE" });
      loadChat();
    });
  }

  const speaks = () => !!(S.avatar && S.prefs && S.prefs.speak);
  return { boot, event, speaks };
})();
