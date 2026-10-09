/* Acchan page: chat with streamed events, tool cards, conversation list,
   and the other Forge apps (Claude, Study Companion) as tabs. */
(() => {
  const $ = (id) => document.getElementById(id);
  const log = $("log");
  const input = $("input");
  let conversation = null;
  let busy = false;
  let controller = null;

  const EXAMPLES = [
    "open the file explorer",
    "what tabs do I have open?",
    "what am I looking at?",
    "pause the music",
    "find my lecture notes",
    "what's in my Downloads folder?",
  ];

  function esc(s) {
    return String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // Small, safe markdown: code blocks, inline code, bold, links, paragraphs.
  function md(text) {
    const blocks = String(text).split(/```/);
    return blocks
      .map((part, i) => {
        if (i % 2) {
          const body = part.replace(/^[\w+-]*\n/, "");
          return `<pre><code>${esc(body)}</code></pre>`;
        }
        return esc(part)
          .replace(/`([^`]+)`/g, "<code>$1</code>")
          .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
          .replace(/(https?:\/\/[^\s<)]+)/g, '<a href="$1" target="_blank" rel="noopener">$1</a>')
          .split(/\n{2,}/)
          .map((p) => (p.trim() ? `<p>${p.replace(/\n/g, "<br>")}</p>` : ""))
          .join("");
      })
      .join("");
  }

  function scroll() {
    log.scrollTop = log.scrollHeight;
  }

  function hideHello() {
    const hello = $("hello");
    if (hello) hello.remove();
  }

  function addUser(text) {
    hideHello();
    const el = document.createElement("div");
    el.className = "msg user";
    el.textContent = text;
    log.appendChild(el);
    scroll();
  }

  function addAssistant(text, meta) {
    hideHello();
    const el = document.createElement("div");
    el.className = "msg assistant";
    el.innerHTML = `<div class="body">${md(text)}</div>` + (meta ? `<div class="meta">${esc(meta)}</div>` : "");
    log.appendChild(el);
    scroll();
    return el;
  }

  function addNote(text, cls = "note") {
    const el = document.createElement("div");
    el.className = cls;
    el.textContent = text;
    log.appendChild(el);
    scroll();
  }

  function addThought(text) {
    hideHello();
    const el = document.createElement("details");
    el.className = "thought";
    el.innerHTML = `<summary>Thought it through</summary><div>${esc(text)}</div>`;
    log.appendChild(el);
    scroll();
  }

  // voice (acchan/voice.py): the mic types what you say, the speaker reads replies
  const voiceUI = { speak: false, voice: "am_michael", rec: null, audio: null, starting: false };
  async function loadPrefs() {
    try {
      const prefs = await (await fetch("/api/settings")).json();
      $("think").checked = !!prefs.thinking;
      $("persona").value = prefs.persona || "plain";
      $("terminal_view").value = prefs.terminal_view || "headless";
      $("browser_view").value = prefs.browser_view || "headless";
      voiceUI.speak = !!prefs.speak;
      voiceUI.voice = prefs.voice || voiceUI.voice;
      $("voice").value = voiceUI.voice;
      drawSpeak();
    } catch (e) { /* the defaults in the page are fine */ }
  }
  function savePrefs(changes) {
    fetch("/api/settings", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(changes) })
      .then((r) => { if (!r.ok) addNote("That setting was not saved.", "note error"); })
      .catch(() => addNote("That setting was not saved: Acchan's server is not answering.", "note error"));
  }

  const cards = {};
  function addTool(id, name, args) {
    hideHello();
    const el = document.createElement("details");
    el.className = "toolcard";
    const argText = Object.entries(args || {})
      .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
      .join(" ");
    el.innerHTML = `<summary><span class="name">${esc(name)}</span><span class="args">${esc(argText)}</span><span class="state">…</span></summary><pre></pre>`;
    log.appendChild(el);
    cards[id] = el;
    scroll();
  }

  function finishTool(id, ok, result) {
    const el = cards[id];
    if (!el) return;
    el.classList.add(ok ? "good" : "bad");
    el.querySelector(".state").textContent = ok ? "✓" : "✗";
    el.querySelector("pre").textContent = result;
  }

  function setBusy(on) {
    busy = on;
    $("send").hidden = on;
    $("stop").hidden = !on;
    input.disabled = false;
  }

  // "Qwen3_5-2B-Uncensored-HauhauCS-Aggressive-Q4_K_M" -> "2B"
  function shortModel(id) {
    const m = /(?:^|[-_])(\d+(?:[._]\d)?)b(?:[-_]|$)/i.exec(id || "");
    return m ? `${m[1].replace("_", ".")}B` : (id || "").slice(0, 24);
  }

  async function send(text) {
    if (!text.trim() || busy) return;
    addUser(text);
    setBusy(true);
    controller = new AbortController();
    let meta = "";
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, conversation, tier: $("tier").value || null, source: "web" }),
        signal: controller.signal,
      });
      if (!res.ok) throw new Error(await res.text());
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      let reply = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        let cut;
        while ((cut = buf.indexOf("\n\n")) >= 0) {
          const line = buf.slice(0, cut);
          buf = buf.slice(cut + 2);
          if (!line.startsWith("data:")) continue;
          const ev = JSON.parse(line.slice(5));
          if (ev.type === "start") conversation = ev.conversation;
          else if (ev.type === "route") meta = ev.fast ? "instant" : `${ev.tier} · ${ev.toolsets.join(", ") || "chat"}`;
          else if (ev.type === "model") meta = meta.replace(/^[^·]+/, `${shortModel(ev.model)} `);
          else if (ev.type === "memory") addNote(`tucking ${ev.folded} older messages into the chat's memory`);
          else if (ev.type === "tool") addTool(ev.id, ev.name, ev.args);
          else if (ev.type === "result") finishTool(ev.id, ev.ok, ev.result);
          else if (ev.type === "escalate") addNote(`switching up to the ${ev.to} model (${ev.why})`);
          else if (ev.type === "text") reply += ev.delta;
          else if (ev.type === "thinking") addThought(ev.text);
          else if (ev.type === "error") addNote(ev.message, "note error");
          else if (ev.type === "done") {
            const s = ev.stats || {};
            const secs = s.seconds != null ? ` · ${s.seconds}s` : "";
            if (reply || ev.text) { addAssistant(reply || ev.text, meta + secs); sayReply(reply || ev.text); }
          }
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") addNote(String(err.message || err), "note error");
    } finally {
      setBusy(false);
      loadChats();
    }
  }

  // Chats being deleted, so a double click on ✕ sends one request.
  const deleting = new Set();
  let chatsFailed = false;
  async function loadChats() {
    const box = $("chats");
    let conversations;
    try {
      const res = await fetch("/api/conversations");
      if (!res.ok) throw new Error(res.status);
      ({ conversations } = await res.json());
    } catch (_) {
      // keep the list on screen; the status poll reloads it when the server is back
      chatsFailed = true;
      if (!box.children.length) box.innerHTML = '<div class="empty small muted">Chats will show here when Acchan\'s server answers.</div>';
      return;
    }
    chatsFailed = false;
    box.innerHTML = "";
    if (!conversations.length) box.innerHTML = '<div class="empty small muted">No chats yet. Your conversations will show here.</div>';
    for (const c of conversations) {
      const el = document.createElement("div");
      el.className = "chat-item" + (c.id === conversation ? " active" : "");
      const src = c.source && c.source !== "web" ? `<span class="src">${esc(c.source)}</span>` : "";
      el.innerHTML = `<span class="t">${esc(c.title)}</span>${src}<button class="x" title="Delete">✕</button>`;
      el.onclick = () => openChat(c.id);
      el.querySelector(".x").onclick = async (e) => {
        e.stopPropagation();
        if (deleting.has(c.id)) return;
        deleting.add(c.id);
        el.classList.add("leaving");
        try {
          await fetch(`/api/conversations/${encodeURIComponent(c.id)}`, { method: "DELETE" });
          if (conversation === c.id) newChat();
        } catch (_) {
          el.classList.remove("leaving");
          addNote("Could not delete that chat: Acchan's server is not answering.", "note error");
        } finally {
          deleting.delete(c.id);
        }
        loadChats();
      };
      box.appendChild(el);
    }
  }

  async function openChat(id) {
    let data;
    try {
      const res = await fetch(`/api/conversations/${encodeURIComponent(id)}`);
      if (!res.ok) {
        // a link to a chat that is gone: still show the list
        loadChats();
        return;
      }
      data = await res.json();
    } catch (_) {
      addNote("Could not open that chat: Acchan's server is not answering.", "note error");
      return;
    }
    conversation = id;
    log.innerHTML = "";
    for (const m of data.messages) {
      if (m.role === "user" && !/^(\(Note:|You do have tools|Stop using tools)/.test(m.content))
        addUser(m.content.replace(/^\(Working folder: [^)]*\)\n/, ""));
      else if (m.role === "assistant") {
        for (const call of m.tool_calls || []) {
          let args = {};
          try { args = JSON.parse(call.function.arguments); } catch (_) {}
          addTool(call.id, call.function.name, args);
        }
        if (m.content) addAssistant(m.content);
      } else if (m.role === "tool") finishTool(m.tool_call_id, !m.content.startsWith("ERROR"), m.content);
    }
    loadChats();
  }

  function newChat() {
    conversation = null;
    log.innerHTML = `<div class="hello" id="hello"><div class="big">🐱</div><h2>Hi, I'm Acchan</h2><p class="muted">I run on your own Jan models. Ask me to open apps, manage windows and tabs, play music, read documents and videos, or work on code.</p><div class="chips" id="chips"></div></div>`;
    chips();
    loadChats();
    input.focus();
  }

  function chips() {
    const box = $("chips");
    if (!box) return;
    for (const text of EXAMPLES) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip";
      b.textContent = text;
      b.onclick = () => send(text);
      box.appendChild(b);
    }
  }

  // Returns false while the server is away, so the poll backs off (15 s up
  // to 30 s); when it answers again, whatever failed to load is fetched.
  async function status() {
    try {
      const res = await fetch("/api/status");
      if (!res.ok) throw new Error(res.status);
      const s = await res.json();
      const loaded = s.loaded.length ? ` · loaded: ${s.loaded.map((m) => m.split(/[-_]/).slice(0, 3).join("-")).join(", ")}` : "";
      $("status").innerHTML = `<span class="dot ${s.jan ? "up" : ""}"></span>${s.jan ? "Jan" : "Jan is off"} · ${esc(s.desktop)} · ${esc(s.tools)} tools${esc(loaded)}`;
      $("status").title = "";
      if (chatsFailed) loadChats();
      if (tabsFailed) tabs();
      return true;
    } catch (_) {
      $("status").innerHTML = '<span class="dot"></span>Server not answering, retrying';
      $("status").title = "Acchan's backend is not answering. The page tries again by itself.";
      return false;
    }
  }

  let tabsLoaded = false, tabsFailed = false;
  async function tabs() {
    let tabs;
    try {
      ({ tabs } = await (await fetch("/api/tabs")).json());
    } catch (_) {
      tabsFailed = true; // the status poll tries again once the server answers
      return;
    }
    tabsFailed = false;
    if (tabsLoaded) return;
    tabsLoaded = true;
    const bar = $("extra-tabs");
    for (const t of tabs) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "tab";
      b.dataset.tab = t.name;
      b.textContent = `${t.icon} ${t.label}`;
      bar.appendChild(b);
      const pane = document.createElement("section");
      pane.className = "pane frame-pane";
      pane.id = `pane-${t.name}`;
      pane.dataset.src = `http://127.0.0.1:${t.port}/`;
      $("frames").appendChild(pane);
    }
    document.querySelectorAll(".tab").forEach((b) => (b.onclick = () => showTab(b.dataset.tab)));
  }

  function showTab(name) {
    document.querySelectorAll(".tab").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
    document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("active", p.id === `pane-${name}`));
    const pane = $(`pane-${name}`);
    if (pane && pane.dataset.src && !pane.querySelector("iframe")) {
      // Loaded on first view, so a tab that is never opened costs nothing.
      const f = document.createElement("iframe");
      f.src = pane.dataset.src;
      f.allow = "fullscreen; clipboard-read; clipboard-write";
      pane.appendChild(f);
    }
  }

  async function settings() {
    const dlg = $("settings");
    if (window.ForgeJan && !$("jan-settings").dataset.done) {
      ForgeJan.panel($("jan-settings"));
      $("jan-settings").dataset.done = "1";
    }
    const list = $("tool-list");
    let data;
    try {
      data = await (await fetch("/api/tools")).json();
    } catch (_) {
      $("tool-count").textContent = "";
      list.innerHTML = '<div class="muted">The tool list could not be loaded: Acchan\'s server is not answering.</div>';
      if (!dlg.open) dlg.showModal();
      return;
    }
    $("tool-count").textContent = `(${data.tools.length})`;
    list.innerHTML = "";
    for (const [ts, summary] of Object.entries(data.toolsets)) {
      list.insertAdjacentHTML("beforeend", `<div class="ts">${esc(ts)} — <span class="muted">${esc(summary)}</span></div>`);
      for (const t of data.tools.filter((x) => x.toolset === ts)) {
        list.insertAdjacentHTML("beforeend", `<div><code>${esc(t.signature)}</code> <span class="muted">${esc(t.description)}</span></div>`);
      }
    }
    if (!dlg.open) dlg.showModal();
  }

  $("composer").onsubmit = (e) => {
    e.preventDefault();
    const text = input.value;
    input.value = "";
    input.style.height = "";
    send(text);
  };
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      $("composer").requestSubmit();
    }
  });
  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 200) + "px";
  });
  $("stop").onclick = async () => {
    await fetch("/api/stop", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ conversation }) });
    if (controller) controller.abort();
  };
  $("new-chat").onclick = newChat;
  $("settings-btn").onclick = settings;
  $("think").onchange = () => savePrefs({ thinking: $("think").checked });
  $("persona").onchange = () => savePrefs({ persona: $("persona").value });
  for (const key of ["terminal_view", "browser_view"]) $(key).onchange = () => savePrefs({ [key]: $(key).value });
  loadPrefs();

  chips();
  async function sayReply(text) {
    if (!voiceUI.speak || !text) return;
    try {
      const res = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, voice: voiceUI.voice }) });
      if (!res.ok) return addNote("Could not read that aloud: " + ((await res.json()).detail || res.status), "note error");
      if (voiceUI.audio) voiceUI.audio.pause();
      voiceUI.audio = new Audio(URL.createObjectURL(await res.blob()));
      voiceUI.audio.play().catch(() => {});
    } catch (e) { /* a reply that cannot be spoken is still on screen */ }
  }
  function drawSpeak() {
    $("speak").classList.toggle("on", voiceUI.speak);
    $("speak").setAttribute("aria-pressed", String(voiceUI.speak));
    $("speak").textContent = voiceUI.speak ? "🔊" : "🔈";
    $("speak").title = voiceUI.speak ? "Replies are read aloud (click to stop)" : "Read replies aloud";
  }
  $("speak").onclick = () => {
    voiceUI.speak = !voiceUI.speak;
    if (!voiceUI.speak && voiceUI.audio) voiceUI.audio.pause();
    drawSpeak();
    savePrefs({ speak: voiceUI.speak });
  };
  $("voice").onchange = () => { voiceUI.voice = $("voice").value; savePrefs({ voice: voiceUI.voice }); };
  // click to start listening, click again to stop; the words land in the box.
  // ForgeMic records a WAV through Web Audio: MediaRecorder hands over 0 bytes
  // for a real mic in Forge's WebKit (shared/forge_mic.js).
  $("mic").onclick = async () => {
    if (voiceUI.rec) return hear(voiceUI.rec);
    if (voiceUI.starting || $("mic").classList.contains("busy")) return;
    voiceUI.starting = true;
    try {
      voiceUI.rec = await ForgeMic.start({ onLimit: () => voiceUI.rec && hear(voiceUI.rec) });
    } catch (e) {
      return addNote("No microphone: " + e.message, "note error");
    } finally {
      voiceUI.starting = false;
    }
    $("mic").classList.add("on");
    $("mic").title = "Listening… click to stop";
  };
  async function hear(rec) {
    voiceUI.rec = null;
    $("mic").classList.replace("on", "busy");
    $("mic").title = "Turning speech into text…";
    try {
      const blob = await rec.stop();
      if (rec.silent()) return addNote("The microphone gave only silence. Is it muted?", "note error");
      const res = await fetch("/api/voice/listen", { method: "POST", headers: { "Content-Type": blob.type }, body: blob });
      const out = await res.json();
      if (!res.ok) addNote("Could not hear that: " + (out.detail || res.status), "note error");
      else if (out.text) { input.value = (input.value ? input.value + " " : "") + out.text; input.focus(); }
    } catch (e) {
      addNote("Could not hear that: " + e.message, "note error");
    } finally {
      $("mic").classList.remove("busy");
      $("mic").title = "Speak instead of typing";
    }
  }
  fetch("/api/voice/status").then((r) => r.json()).then((s) => {
    $("mic").hidden = !s.listen || !ForgeMic.supported();
    $("speak").hidden = !s.speak;
    $("voice").replaceChildren(...Object.entries(s.voices).map(([id, label]) => new Option(label, id)));
    $("voice").value = voiceUI.voice;
  }).catch(() => {});

  const linked = location.hash.match(/^#c=([\w-]+)/);
  if (linked) openChat(linked[1]);
  else loadChats();
  tabs();
  status();
  ForgeIdle.poll(status, 15000, { backoff: 2, maxMs: 30000 });
  input.focus();
})();
