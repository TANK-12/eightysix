/* Mission Control's conversation view: one session's chat drawn with the
   Claude app's own renderer (/shared/forge_convo.js), kept live by reading
   what the transcript gained since the last look (/events?after=), and a
   reply box with pickers for engine (Claude or Jan), model, effort,
   ultrathink and visible reasoning.

   Where a reply goes is decided by the server (actions.say): straight into
   a Claude app chat, a resumed Claude app chat for an ended session, or a
   board note for a terminal or Relay session. Jan answers questions about
   the chat locally and never reaches the session.

   app.js calls MissionChat.show(box, session, agent) from its drawer and
   MissionChat.hide() when the drawer closes. */
(function () {
  "use strict";
  const C = window.ForgeConvo;
  C.copyImageUrl = null; // the Claude app's clipboard route is not here
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HEAD = { "Content-Type": "application/json", "X-Mission": "1" };
  const LIVE_MS = { working: 2000, needs_you: 3000, idle: 6000, ended: 20000 };
  const store = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem("mission.chat." + k)); return v ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem("mission.chat." + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const prefs = { engine: store.get("engine", "claude"), reasoning: store.get("reasoning", true), ultra: false, model: null, effort: null };
  const EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"];
  let options = null;
  const jan = new Map(); // session key -> [{q, a, model, error}]
  let attach = null; // ForgeAttach handle: busy() while a file uploads
  let cur = null; // {key, session, agent, view, after, before, more, timer, el}

  const shownPage = () => (window.ForgeIdle ? window.ForgeIdle.shown() : document.visibilityState !== "hidden");
  async function getJson(url) {
    const r = await fetch(url, { cache: "no-store" });
    if (!r.ok) {
      let d = r.statusText;
      try { d = (await r.json()).detail || d; } catch (e) { /* not json */ }
      throw new Error(d);
    }
    return r.json();
  }
  async function postJson(url, body) {
    const r = await fetch(url, { method: "POST", headers: HEAD, body: JSON.stringify(body || {}) });
    if (!r.ok) {
      let d = r.statusText;
      try { d = (await r.json()).detail || d; } catch (e) { /* not json */ }
      throw new Error(d);
    }
    return r.json();
  }
  async function loadOptions() {
    if (options) return options;
    try { options = await getJson("/api/options"); } catch (e) { options = { models: { "": "Claude Code's default" }, efforts: {}, claude_app: false }; }
    return options;
  }

  /* -------------------------------------------------------------- where */
  // How a reply reaches this session, in plain words, and what can be picked.
  function route(s, agent) {
    if (agent) return { kind: "none", text: "A helper takes work only from its commander. Message the commander, or ask Jan about this chat." };
    if (s.claude_tab) return { kind: "claude", text: "Goes straight into its Claude app chat." };
    if (s.group === "ended") return { kind: "resume", text: "Resumes it in the Claude app, then sends this." };
    return { kind: "board", text: "Arrives as a board note at its next step. It keeps its own model." };
  }

  /* ---------------------------------------------------------------- dom */
  function skeleton(box) {
    box.innerHTML = `
      <div class="chat">
        <div class="chat-bar">
          <button type="button" class="chip-btn" data-chat="older" hidden>Load earlier</button>
          <span class="chat-meta" id="chatMeta"></span>
          <span class="spacer"></span>
          <label class="switch" title="Show Claude's reasoning (thinking blocks) where the transcript kept it">
            <input type="checkbox" id="chatReasoning"><span class="track"><span class="knob"></span></span><span>Reasoning</span>
          </label>
        </div>
        <div class="chat-log fc" id="chatLog" tabindex="0" aria-live="polite"></div>
        <button type="button" class="new-pill" id="chatNew" hidden>New messages ↓</button>
        <form class="composer-x" id="chatForm" autocomplete="off">
          <div class="pickers" id="chatPickers"></div>
          <div class="cx-files" id="chatFiles"></div>
          <div class="cx-row">
            <label class="cx-attach" id="chatAttach" title="Attach files or pictures (or paste or drop them)" aria-label="Attach files"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M20 11.5l-8 8a5 5 0 0 1-7-7l8.5-8.5a3.5 3.5 0 0 1 5 5L10 17.5a2 2 0 0 1-3-3l7.5-7.5"/></svg><input id="chatFile" type="file" multiple hidden></label>
            <textarea id="chatText" rows="1" maxlength="4000" placeholder="Reply…"></textarea>
            <button type="submit" class="send" id="chatSend" title="Send (Enter)" aria-label="Send"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h12M12 6l6 6-6 6"/></svg></button>
          </div>
          <div class="cx-hint" id="chatHint"></div>
        </form>
      </div>`;
    $("chatReasoning").checked = prefs.reasoning;
    $("chatReasoning").addEventListener("change", (e) => {
      prefs.reasoning = e.target.checked;
      store.set("reasoning", prefs.reasoning);
      $("chatLog").classList.toggle("hide-thinking", !prefs.reasoning);
    });
    const log = $("chatLog");
    log.classList.toggle("hide-thinking", !prefs.reasoning);
    log.addEventListener("scroll", () => { if (nearBottom()) $("chatNew").hidden = true; });
    $("chatNew").addEventListener("click", () => scrollDown(true));
    const ta = $("chatText");
    ta.addEventListener("input", autosize);
    ta.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("chatForm").requestSubmit(); }
    });
    $("chatForm").addEventListener("submit", (e) => { e.preventDefault(); send(); });
    // files go to Mission (/api/attach) and the reply names their paths
    // (Relay task 118); Jan reads text only, so its mode has no paperclip
    if (window.ForgeAttach) {
      attach = ForgeAttach.wire({
        box: ta,
        zone: $("chatForm"),
        picker: $("chatFile"),
        upload: async (file) => postJson("/api/attach", { name: file.name || "pasted.png", data: await ForgeAttach.readBase64(file) }),
        pasteDesktop: () => postJson("/api/attach/paste-image", {}),
        refuse: () => (!cur ? "Open a chat first" : prefs.engine === "jan" ? "Jan reads text only; pick Claude to send files" : ""),
        onAdd: (saved) => { if (cur) { cur.files.push(saved); drawFiles(); } },
        onError: (msg) => window.MissionApp && window.MissionApp.toast(msg, "err"),
      });
    }
    box.addEventListener("click", onClick);
  }
  function autosize() {
    const ta = $("chatText");
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 220) + "px";
  }
  const nearBottom = () => { const l = $("chatLog"); return !l || l.scrollHeight - l.scrollTop - l.clientHeight < 80; };
  function scrollDown(force) {
    const l = $("chatLog");
    if (!l) return;
    if (force || cur.follow) { l.scrollTop = l.scrollHeight; $("chatNew").hidden = true; }
    else $("chatNew").hidden = false;
  }
  const hooks = { scroll: () => {} };

  /* ------------------------------------------------------------- pickers */
  function seg(name, items, value, disabled) {
    return `<div class="seg${disabled ? " off" : ""}" role="radiogroup" data-seg="${name}">${items.map(([v, label, cls]) => `<button type="button" role="radio" aria-checked="${v === value}" class="${v === value ? "on " : ""}${cls || ""}" data-v="${esc(v)}" ${disabled ? "disabled" : ""}>${label}</button>`).join("")}</div>`;
  }
  function effortPips(level) {
    const n = Math.max(0, EFFORT_ORDER.indexOf(level)) + 1;
    return `<span class="pips">${EFFORT_ORDER.map((_, i) => `<i class="${i < n ? "lit" : ""}"></i>`).join("")}</span>`;
  }
  function drawPickers() {
    if (!cur) return;
    const s = cur.session;
    const r = route(s, cur.agent);
    const isJan = prefs.engine === "jan";
    const can = !isJan && (r.kind === "claude" || r.kind === "resume");
    const opts = options || { models: {}, efforts: {} };
    const L = window.MissionLogic;
    const curModel = L ? L.modelName(s.model) : s.model;
    const models = Object.entries(opts.models || {}).filter(([k]) => k);
    const modelVal = prefs.model ?? "";
    const effortVal = prefs.effort ?? "";
    const effortNow = s.effort || "";
    $("chatPickers").innerHTML = `
      ${seg("engine", [["claude", '<span class="eng-dot claude"></span>Claude'], ["jan", '<span class="eng-dot jan"></span>Jan']], prefs.engine, false)}
      ${isJan ? `<span class="pk-note">Local model, free. The session never sees this.</span>` : `
      <label class="pk model ${can ? "" : "off"}" title="${can ? "Model for the next message" : "This session keeps its own model"}">
        <span class="pk-k">Model</span>
        <select id="chatModel" ${can ? "" : "disabled"}>
          <option value="">${esc(curModel ? "Keep · " + curModel : "Keep")}</option>
          ${models.map(([k, v]) => `<option value="${esc(k)}" ${k === modelVal ? "selected" : ""}>${esc(v)}</option>`).join("")}
        </select>
      </label>
      <div class="pk effort ${can ? "" : "off"}" title="${can ? "Effort: how hard Claude thinks" : "This session keeps its own effort"}">
        <span class="pk-k">Effort ${effortPips(effortVal || effortNow || "medium")}</span>
        ${seg("effort", [["", "Keep"], ...EFFORT_ORDER.map((e) => [e, e === "xhigh" ? "X-high" : e[0].toUpperCase() + e.slice(1)])], effortVal, !can)}
      </div>
      <button type="button" class="ultra ${prefs.ultra ? "on" : ""}" data-chat="ultra" aria-pressed="${prefs.ultra}" title="Adds the ultrathink keyword: Claude Code thinks as hard as it can for this message">ultrathink</button>`}`;
    const sel = $("chatModel");
    if (sel) sel.addEventListener("change", (e) => { prefs.model = e.target.value || null; drawPickers(); });
    $("chatHint").textContent = isJan ? "Jan reads the end of this chat and answers here." : r.text;
    const ta = $("chatText");
    ta.placeholder = isJan ? "Ask Jan about this chat…" : r.kind === "none" ? "Helpers can't be messaged directly" : `Reply to ${s.label || s.name || "this session"}…`;
    const blocked = !isJan && r.kind === "none";
    ta.disabled = blocked;
    $("chatSend").disabled = blocked;
    $("chatForm").classList.toggle("jan", isJan);
    $("chatAttach").hidden = isJan || blocked || !window.ForgeAttach;
    drawFiles();
  }
  function drawFiles() {
    const box = $("chatFiles");
    if (!box) return;
    const list = cur && prefs.engine !== "jan" ? cur.files : [];
    box.replaceChildren(...list.map((f, i) => {
      const chip = document.createElement("span");
      chip.className = "cx-file";
      chip.textContent = f.name;
      const x = document.createElement("button");
      x.type = "button";
      x.textContent = "×";
      x.title = "Remove";
      x.addEventListener("click", () => { cur.files.splice(i, 1); drawFiles(); });
      chip.append(x);
      return chip;
    }));
    box.hidden = !list.length;
  }
  function onClick(e) {
    const b = e.target.closest("button");
    if (!b) return;
    const segEl = b.closest("[data-seg]");
    if (segEl && !b.disabled) {
      const v = b.dataset.v;
      if (segEl.dataset.seg === "engine") { prefs.engine = v; store.set("engine", v); }
      if (segEl.dataset.seg === "effort") prefs.effort = v || null;
      drawPickers();
      return;
    }
    if (b.dataset.chat === "ultra") { prefs.ultra = !prefs.ultra; drawPickers(); return; }
    if (b.dataset.chat === "older") { older(); return; }
  }

  /* --------------------------------------------------------------- load */
  function url(extra) {
    const q = new URLSearchParams(extra || {});
    if (cur.agent) q.set("agent", cur.agent);
    const qs = q.toString();
    return `/api/sessions/${encodeURIComponent(cur.session.id)}/events${qs ? "?" + qs : ""}`;
  }
  function freshView() {
    const v = C.newView(cur.key);
    v.thinking = true;
    v.times = true;
    v.box.className = "view";
    return v;
  }
  async function first() {
    const mine = cur;
    const log = $("chatLog");
    log.innerHTML = '<div class="chat-empty">Loading the conversation…</div>';
    try {
      const got = await getJson(url());
      if (cur !== mine) return;
      cur.view = freshView();
      cur.view.bulk = true;
      for (const ev of got.events) C.draw(ev, cur.view, hooks);
      cur.view.bulk = false;
      cur.after = got.after;
      cur.before = got.before;
      cur.more = got.more;
      log.innerHTML = "";
      if (!got.events.length) log.innerHTML = '<div class="chat-empty">Nothing said yet.</div>';
      log.appendChild(cur.view.box);
      drawJan();
      cur.follow = true;
      scrollDown(true);
      document.querySelector('[data-chat="older"]').hidden = !cur.more;
    } catch (e) {
      if (cur !== mine) return;
      log.innerHTML = `<div class="chat-empty bad">${esc(e.message)}</div>`;
    }
    live();
  }
  async function older() {
    if (!cur || !cur.more || cur.loadingOlder) return;
    const mine = cur;
    cur.loadingOlder = true;
    const btn = document.querySelector('[data-chat="older"]');
    btn.disabled = true;
    try {
      const got = await getJson(url({ before: cur.before }));
      if (cur !== mine) return;
      const v = freshView();
      for (const ev of got.events) C.draw(ev, v, hooks);
      v.box.querySelectorAll(".toolcard.pending").forEach((c) => c.classList.replace("pending", "done"));
      const log = $("chatLog");
      const h = log.scrollHeight;
      const top = log.scrollTop;
      cur.view.box.prepend(...v.box.childNodes);
      log.scrollTop = top + (log.scrollHeight - h); // keep the reader's line still
      cur.before = got.before;
      cur.more = got.more;
      btn.hidden = !cur.more;
    } catch (e) {
      window.MissionApp && window.MissionApp.toast(e.message, "err");
    } finally {
      cur.loadingOlder = false;
      btn.disabled = false;
    }
  }
  function live() {
    if (!cur) return;
    clearTimeout(cur.timer);
    const st = cur.agent ? ((cur.session.helpers.find((h) => h.id === cur.agent) || {}).state === "working" ? "working" : "ended") : cur.session.group;
    cur.timer = setTimeout(tick, LIVE_MS[st] || 6000);
  }
  async function tick() {
    if (!cur) return;
    if (!shownPage()) { live(); return; }
    if (!cur.view) { first(); return; } // the first load failed: try again
    const mine = cur;
    try {
      const got = await getJson(url({ after: cur.after }));
      if (cur !== mine) return;
      if (got.reset) { first(); return; }
      if (got.events.length) {
        cur.follow = nearBottom();
        const empty = $("chatLog").querySelector(".chat-empty");
        if (empty) empty.remove();
        for (const ev of got.events) {
          if (ev.type === "forge_user") dropGhost(ev.text);
          C.draw(ev, cur.view, hooks);
        }
        scrollDown(false);
      }
      cur.after = got.after;
      if (got.more) { cur.timer = setTimeout(tick, 50); return; }
    } catch (e) {
      /* a missed look is retried on the next tick */
    }
    live();
  }

  /* --------------------------------------------------------------- send */
  function ghost(text) {
    const box = C.el("div", "msg user ghost");
    box.appendChild(C.el("div", "bubble", text));
    box.appendChild(C.el("div", "joined", "sending…"));
    cur.view.box.appendChild(box);
    cur.ghosts = (cur.ghosts || []).concat([{ box, text, at: Date.now() }]);
    setTimeout(() => box.remove(), 30000);
    cur.follow = true;
    scrollDown(true);
    return box;
  }
  function dropGhost(text) {
    if (!cur || !cur.ghosts) return;
    const i = cur.ghosts.findIndex((g) => String(text || "").includes(g.text.slice(0, 60)));
    if (i >= 0) { cur.ghosts[i].box.remove(); cur.ghosts.splice(i, 1); }
  }
  function drawJan() {
    if (!cur || !cur.view) return;
    cur.view.box.querySelectorAll(".msg.jan, .msg.jan-q").forEach((n) => n.remove());
    for (const item of jan.get(cur.key) || []) janItem(item);
  }
  function janItem(item) {
    const q = C.el("div", "msg user jan-q");
    q.appendChild(C.el("div", "bubble", item.q));
    q.appendChild(C.el("div", "joined", "asked Jan, not the session"));
    const a = C.el("div", "msg jan");
    const head = C.el("div", "jan-head");
    head.innerHTML = `<span class="eng-dot jan"></span>Jan${item.model ? ` <span class="muted">· ${esc(item.model)}</span>` : ""}`;
    const body = C.el("div", "bubble");
    if (item.error) body.innerHTML = `<p class="bad">${esc(item.error)}</p>`;
    else if (item.a) body.innerHTML = C.markdown(item.a);
    else body.innerHTML = '<p class="thinking-dots"><i></i><i></i><i></i></p>';
    a.append(head, body);
    cur.view.box.append(q, a);
    item.node = a;
    return a;
  }
  async function send() {
    if (!cur) return;
    const ta = $("chatText");
    const text = ta.value.trim();
    const isJan = prefs.engine === "jan";
    const files = isJan ? [] : cur.files.slice();
    if (!text && !files.length) return;
    if (!isJan && attach && attach.busy()) { if (window.MissionApp) window.MissionApp.toast("A file is still uploading; send again in a moment", "err"); return; }
    const s = cur.session;
    const btn = $("chatSend");
    btn.disabled = true;
    const mine = cur;
    try {
      if (prefs.engine === "jan") {
        const item = { q: text };
        const list = jan.get(cur.key) || [];
        list.push(item);
        jan.set(cur.key, list);
        ta.value = "";
        autosize();
        if (cur.view) janItem(item);
        cur.follow = true;
        scrollDown(true);
        try {
          const got = await postJson(`/api/sessions/${encodeURIComponent(s.id)}/ask-jan`, { text, agent: cur.agent || "" });
          item.a = got.answer;
          item.model = got.model;
        } catch (e) {
          item.error = e.message;
        }
        if (cur === mine) { drawJan(); scrollDown(true); }
        return;
      }
      const body = { text, state: s.group, cwd: s.cwd, name: s.label || s.name, ultrathink: prefs.ultra, files: files.map((f) => f.path) };
      const r = route(s, cur.agent);
      if (r.kind === "claude" || r.kind === "resume") {
        if (prefs.model !== null) body.model = prefs.model;
        if (prefs.effort !== null) body.effort = prefs.effort;
      }
      const g = cur.view ? ghost(text) : null;
      ta.value = "";
      cur.files = [];
      drawFiles();
      autosize();
      try {
        const got = await postJson(`/api/sessions/${encodeURIComponent(s.id)}/say`, body);
        const done = { claude: "Sent into its Claude app chat", resumed: "Resumed in the Claude app and sent", board: `Posted as board note #${got.id}; it arrives at its next step` }[got.via] || "Sent";
        if (g) g.querySelector(".joined").textContent = got.via === "board" ? `board note #${got.id} · waits for its next step` : "sent · waiting for it to show in the chat";
        window.MissionApp && window.MissionApp.toast(done, "ok");
        prefs.ultra = false;
        drawPickers();
        if (cur === mine) { clearTimeout(cur.timer); cur.timer = setTimeout(tick, 900); }
      } catch (e) {
        if (g) g.remove();
        ta.value = text; // keep the words
        if (cur === mine) { cur.files = files.concat(cur.files); drawFiles(); } // and the files
        autosize();
        window.MissionApp && window.MissionApp.toast(e.message, "err");
      }
    } finally {
      btn.disabled = false;
    }
  }

  /* ---------------------------------------------------------------- api */
  function show(box, session, agent) {
    const key = session.id + "|" + (agent || "");
    if (cur && cur.key === key && box.querySelector(".chat")) {
      cur.session = session; // fresh facts from the poll; the chat keeps going
      drawMeta();
      drawPickers();
      return;
    }
    hide();
    cur = { key, box, session, agent: agent || "", view: null, after: 0, before: null, more: false, timer: 0, follow: true, files: [] };
    prefs.model = null;
    prefs.effort = null;
    prefs.ultra = false;
    skeleton(box);
    drawMeta();
    drawPickers();
    loadOptions().then(() => cur && cur.key === key && drawPickers());
    first();
  }
  function drawMeta() {
    const s = cur.session;
    const h = cur.agent ? s.helpers.find((x) => x.id === cur.agent) : null;
    const L = window.MissionLogic;
    const model = L ? L.modelName((h || s).model) : (h || s).model;
    const bits = [model, (h || s).effort ? `effort ${(h || s).effort}` : ""].filter(Boolean);
    $("chatMeta").innerHTML = bits.map((b) => `<span class="tag">${esc(b)}</span>`).join("");
  }
  // The chat's ids are page-wide (chatLog, chatText...), so a chat that
  // stops leaves no copy behind for the next box (drawer or Conversations).
  function hide() {
    if (cur) {
      clearTimeout(cur.timer);
      if (cur.box) cur.box.innerHTML = "";
    }
    cur = null;
  }
  document.addEventListener("forge-visible", () => { if (cur && shownPage()) { clearTimeout(cur.timer); tick(); } });
  document.addEventListener("visibilitychange", () => { if (cur && shownPage()) { clearTimeout(cur.timer); tick(); } });

  window.MissionChat = { show, hide, route, get current() { return cur; } };
})();
