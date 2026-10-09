/* Mission Control's Conversations view, rebuilt for reading (Relay task 109).

   The chat is the whole window. Mission's top bar, side nav and needs band
   step aside (body.focus-chat); the conversation sits in one centred column
   in big type (14 to 28 px, 19 to start), and everything else is tucked away:
     - the composer's chip ("Opus · Max") opens Claude or Jan, the model
       cards, the effort gauge and ultrathink;
     - Session (top right) slides in a sheet: what it may do, Normal /
       Ultracode and helper limits (the Claude app's run_controls.js), plan
       and progress, text size, reasoning, steps, the facts, and Open in
       Claude / Go to it / Details / Resume here;
     - Chats (top left, Ctrl+K) slides in every session, the ones waiting on
       Emerson first, and Mission's other views. Alt+Up / Alt+Down step
       through the chats; Esc closes whatever is open.

   One chat UI serves every session. Source "claude": the session runs in a
   Claude app chat (or was resumed into one from here); its events come by
   long poll through Mission's allowlisted door /api/claude/...
   (mc/claude_proxy.py), and send, stop, settings and files go the same way.
   Source "log": a terminal, Relay or ended session; its transcript comes
   from /api/sessions/{id}/events and a reply goes through /say (a board
   note, or a resume into the Claude app for an ended one). Source "relay":
   Emerson's WhatsApp chat with Relay, pinned on top of the Chats (and a
   header button): the thread live from /api/relay-chat, and what he types
   goes through `relay as-whatsapp`, handled exactly as on his phone (a
   command, a chat line, or a question for the boss).

   Messages are drawn by the shared renderer (/shared/forge_convo.js). Its
   step hook hands every tool call and kept thought to this file, which folds
   a run of them into one "N steps" bar between two messages, so the words
   stay together. The first reply after each message of Emerson's gets the
   session's portrait and name. The parts with no DOM are in chat_logic.js.

   app.js calls draw() on every poll while the view is open, shown() when it
   opens, left() when another view opens, and select(id) when something asks
   for a session. */
(function () {
  "use strict";
  const C = window.ForgeConvo;
  const L = window.MissionLogic;
  const X = window.MissionChatLogic;
  const A = () => window.MissionApp;
  const $ = (id) => document.getElementById(id);
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const HEAD = { "Content-Type": "application/json", "X-Mission": "1" };
  const GROUP = { needs_you: "needs you", working: "working", idle: "idle", ended: "ended" };
  const LIVE_MS = { working: 2000, needs_you: 3000, idle: 6000, ended: 20000 };
  const STEPS = ["folded", "open", "hidden"];
  const STEP_WORDS = { folded: "Folded", open: "Open", hidden: "Hidden" };
  const ULTRA_WORDS = { off: "Off", next: "Next message", always: "Every message" };
  const VIEWS = [["sessions", "Sessions"], ["swarm", "Swarm"], ["map", "Map"], ["messages", "Messages"], ["crews", "Crews"], ["relay", "Relay"]];
  const KEY = "mission.convos.";
  const WA = "whatsapp"; // the WhatsApp chat with Relay (Emerson's note 1295)
  const WA_S = { id: WA, name: "Relay", label: "Relay", group: "idle", title: "" };
  const WA_MS = 2500; // its look while open (15 s while the page is hidden)
  const WA_WORDS = { relay: "Relay", boss: "Boss", jan: "Jan", local: "Local" };
  const PENDING_MS = 600000; // a "sending…" line waits up to 10 minutes for the chat to show it
  const OLD_SERVER = "Mission's server is older than this page. Close Mission in Forge's top bar and open it again.";
  // attached pictures in Claude app chats load through Mission's proxy (mc/claude_proxy.py)
  C.filesBase = "/api/claude";
  const store = {
    get(k, d) { try { const v = JSON.parse(localStorage.getItem(KEY + k)); return v ?? d; } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(KEY + k, JSON.stringify(v)); } catch (e) { /* private mode */ } },
  };
  const V = {
    sel: store.get("sel", ""),
    find: "",
    size: X.clampSize(store.get("size", X.SIZE.start)),
    reasoning: store.get("reasoning", true) !== false,
    steps: STEPS.includes(store.get("steps", "")) ? store.get("steps", "") : "folded",
    engine: "claude",
    options: null, optionsAt: 0,
    run: null, // the Claude app's Normal / Ultracode and limits, for the open chat
    chat: null, // the open conversation
    gen: 0, // bumps whenever the open chat changes; a late answer checks it
    mode: "", // "claude:<conv>" or "log:<session id>": what is drawn now
    resumed: {}, // session id -> the Claude app chat it was resumed into here
    ultra: store.get("ultra", {}), // session id -> "off" | "next" | "always"
    picks: {}, // session id -> {model, effort} for a reply that resumes it
    panel: "", // "chats" | "sheet" | ""
    waBoss: store.get("waBoss", false) === true, // the WhatsApp chat sends to the boss line
    back: "", // the chat open before the WhatsApp one (its button goes back there)
    waLast: null, // the WhatsApp chat's last line, for its row in Chats
    waPeek: 0, // when the Chats panel last fetched that line
    knobsBusy: 0,
    drafts: {}, // chat key -> {text, files}: what was typed and not sent, kept across chat switches
    sending: new Set(), // chat keys with a message on its way (Send waits for it)
    pending: new Map(), // chat key -> [{text, how, at, box}]: "sending…" lines not in the chat yet
    showArchived: false,
    stopArm: 0, // a Relay run's Stop asks to be pressed twice
  };
  const jan = new Map(); // session id -> [{q, a, model, error}]
  const isOn = () => { const v = $("view-convos"); return !!v && v.classList.contains("on"); };
  const shownPage = () => (window.ForgeIdle ? window.ForgeIdle.shown() : document.visibilityState !== "hidden");
  const toast = (m, k) => A() && A().toast(m, k);
  const nameOf = (s) => (s && (s.label || s.name)) || "this session"; // who speaks
  const plainName = (s) => (s ? L.displayName(s) : "this session"); // what it is (task + description)
  const convOf = (s) => (s && (s.claude_tab || V.resumed[s.id])) || "";
  const sessions = () => (A() && A().data && A().data.sessions) || [];
  const keyOf = (chat) => (chat.source === "relay" ? WA : chat.sid);

  async function req(url, opts) {
    const r = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
    if (!r.ok) {
      let d = r.statusText;
      try { d = (await r.json()).detail || d; } catch (e) { /* not json */ }
      // FastAPI's own words for a route it does not have: the backend was
      // started before this page's routes existed (our own 404s say more)
      if (r.status === 404 && d === "Not Found" && /^\/api\/(claude\/|relay-chat|relay\/tasks\/)/.test(url)) d = OLD_SERVER;
      throw new Error(d);
    }
    return r.json();
  }
  const post = (url, body) => req(url, { method: "POST", headers: HEAD, body: JSON.stringify(body || {}) });
  const capi = (chat, path) => `/api/claude/conversations/${encodeURIComponent(chat.conv)}/${path}`;
  const live = (chat) => !!chat && V.chat === chat && chat.gen === V.gen;

  // The pickers' choices are the Claude app's own (runner.MODELS, EFFORTS,
  // MODES, AGENT_LIMITS); Mission's /api/options has the first two when the
  // Claude app is down.
  async function loadOptions() {
    if (V.options && !V.options.partial && Date.now() - V.optionsAt < 60000) return V.options;
    let o = null;
    try { o = await req("/api/claude/options"); } catch (e) {
      try { o = Object.assign(await req("/api/options"), { partial: true }); } catch (e2) { o = null; }
    }
    if (o) { V.options = o; V.optionsAt = Date.now(); }
    return V.options;
  }

  /* --------------------------------------------------------------- shell */
  const ICON = {
    clip: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16.5 7.5l-7.2 7.2a1.8 1.8 0 0 0 2.5 2.5l7.4-7.4a3.6 3.6 0 0 0-5.1-5.1L6.6 12.2a5.4 5.4 0 0 0 7.6 7.6l5.3-5.3"/></svg>',
    send: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4.5 12h13M12.5 6l6 6-6 6"/></svg>',
    stop: '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="2"/></svg>',
    wa: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.6a8.4 8.4 0 0 0-7.3 12.6l-1.1 4.2 4.3-1.1A8.4 8.4 0 1 0 12 3.6z"/><path d="M9.3 8.4c.3-.4.7-.4.9 0l.8 1.6c.1.3 0 .6-.2.8l-.5.5c.5 1 1.3 1.8 2.3 2.3l.5-.5c.2-.2.5-.3.8-.2l1.6.8c.4.2.4.6 0 .9-1.7 1.5-6.8-1.4-6.2-6.2z"/></svg>',
    spark: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.5l1.9 5.6 5.6 1.9-5.6 1.9L12 18.5l-1.9-5.6-5.6-1.9 5.6-1.9z"/></svg>',
  };
  function mount() {
    if ($("fxLog")) return;
    const root = $("fx");
    root.innerHTML = `
      <div class="fx-sky" aria-hidden="true"></div>
      <div id="fxStage" class="fx-stage" aria-hidden="true"></div>
      <header class="fx-head">
        <button type="button" class="fx-hbtn" data-fx="chats" title="All chats (Ctrl+K)" aria-label="All chats"><svg class="ic"><use href="#i-chat"/></svg><span>Chats</span><b id="fxBadge" class="fx-badge" hidden></b></button>
        <button type="button" id="fxWaBtn" class="fx-hbtn fx-wa-btn" data-fx="wa" aria-pressed="false" title="Your WhatsApp chat with Relay, live (press again to go back)">${ICON.wa}<span>WhatsApp</span></button>
        <div id="fxWho" class="fx-who"></div>
        <button type="button" id="fxPlan" class="fx-plan" data-fx="sheet" hidden></button>
        <button type="button" id="fxStop" class="fx-hbtn fx-stop" hidden title="Stop what it is doing now">${ICON.stop}<span>Stop</span></button>
        <span class="fx-sizeq" role="group" aria-label="Text size"><button type="button" class="fx-hbtn fx-abtn" data-fx-size="-2" title="Smaller text" aria-label="Smaller text">A−</button><button type="button" class="fx-hbtn fx-abtn big" data-fx-size="2" title="Bigger text" aria-label="Bigger text">A+</button></span>
        <button type="button" class="fx-hbtn" data-fx="sheet" title="What it may do, Ultracode, text size and more" aria-label="Session settings"><svg class="ic"><use href="#i-gear"/></svg><span>Session</span></button>
        <button type="button" class="fx-hbtn" data-fx="back" title="Back to Mission Control's sessions"><svg class="ic"><use href="#i-sessions"/></svg><span>Mission</span></button>
      </header>
      <div id="fxScroll" class="fx-scroll">
        <div class="fx-col">
          <button type="button" id="fxOlder" class="fx-older" hidden>Load earlier messages</button>
          <p id="fxEmpty" class="fx-empty"></p>
          <div id="fxLog" class="fc fx-log" aria-live="polite"></div>
        </div>
      </div>
      <footer class="fx-foot">
        <button type="button" id="fxNew" class="fx-new" hidden>New messages ↓</button>
        <div class="fx-col">
          <div id="fxPop" class="fx-pop" role="dialog" aria-label="Who answers, model and effort" hidden></div>
          <p id="fxNote" class="fx-note" hidden></p>
          <form id="fxForm" class="fx-composer" autocomplete="off">
            <div id="fxFiles" class="fx-files"></div>
            <textarea id="fxInput" rows="1" aria-label="Your message"></textarea>
            <div class="fx-row">
              <button type="button" id="fxChip" class="fx-chip" aria-haspopup="dialog" aria-expanded="false" title="Who answers, model, effort and ultrathink"></button>
              <label id="fxAttach" class="fx-attach" title="Attach files or pictures (or paste or drop them)">${ICON.clip}<input id="fxFile" type="file" multiple hidden></label>
              <span id="fxStatus" class="fx-status" aria-live="polite"></span>
              <button type="submit" id="fxSend" class="fx-send" title="Send (Enter; Shift+Enter for a new line)">Send ${ICON.send}</button>
            </div>
          </form>
        </div>
      </footer>
      <div id="fxShade" class="fx-shade" hidden></div>
      <aside id="fxChats" class="fx-panel fx-left" aria-label="Chats" hidden>
        <div class="fx-ph"><h2>Chats</h2><button type="button" class="fx-x" data-fx="close" aria-label="Close">×</button></div>
        <label class="fx-find"><svg class="ic"><use href="#i-search"/></svg><input id="fxFind" type="search" placeholder="Find a chat" aria-label="Find a chat"></label>
        <ul id="fxList" class="fx-list" role="listbox" aria-label="Chats"></ul>
        <nav class="fx-views" aria-label="Mission Control">${VIEWS.map(([v, label]) => `<button type="button" data-fx-view="${v}">${esc(label)}</button>`).join("")}</nav>
        <p class="fx-keys">Ctrl+K opens this · Alt+↑ / Alt+↓ the next chat · Esc closes</p>
      </aside>
      <aside id="fxSheet" class="fx-panel fx-right" aria-label="Session" hidden>
        <div class="fx-ph"><h2>Session</h2><button type="button" class="fx-x" data-fx="close" aria-label="Close">×</button></div>
        <div id="fxSheetBody" class="fx-sheet-body"></div>
      </aside>`;
    applySize();
    $("fxLog").classList.toggle("hide-thinking", !V.reasoning);
    root.dataset.steps = V.steps;
    const sc = $("fxScroll");
    sc.addEventListener("scroll", () => {
      const chat = V.chat;
      if (!chat) return;
      chat.follow = sc.scrollHeight - sc.scrollTop - sc.clientHeight < 90;
      if (chat.follow) $("fxNew").hidden = true;
    }, { passive: true });
    $("fxNew").addEventListener("click", () => scrollDown(true));
    $("fxOlder").addEventListener("click", older);
    const ta = $("fxInput");
    ta.addEventListener("input", autosize);
    ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
    if (window.ForgeVoice) {
      // speak into the box through the Forge voice service; the speaker button reads replies aloud
      const mic = ForgeVoice.micButton(ta, { app: "mission" });
      const speak = ForgeVoice.speakRepliesToggle("mission");
      for (const b of [mic, speak]) { b.classList.remove("tool"); b.classList.add("fx-attach", "fx-voice"); }
      $("fxAttach").after(mic, speak);
    }
    ta.addEventListener("paste", onPaste);
    $("fxForm").addEventListener("submit", (e) => { e.preventDefault(); send(); });
    $("fxFile").addEventListener("change", (e) => { attach([...e.target.files]); e.target.value = ""; });
    $("fxStop").addEventListener("click", stop);
    $("fxChip").addEventListener("click", () => (isPopOpen() ? closePop() : openPop()));
    $("fxShade").addEventListener("click", closePanels);
    $("fxFind").addEventListener("input", (e) => { V.find = e.target.value; drawList(); });
    root.addEventListener("click", onClick);
    root.addEventListener("change", onChange);
    root.addEventListener("input", onInput);
    const files = (e) => [...((e.dataTransfer && e.dataTransfer.types) || [])].includes("Files");
    // a file dropped where it cannot go is refused here, never opened in the window
    root.addEventListener("dragover", (e) => { if (!files(e)) return; e.preventDefault(); root.classList.toggle("fx-drop", canAttach()); });
    root.addEventListener("dragleave", (e) => { if (!root.contains(e.relatedTarget)) root.classList.remove("fx-drop"); });
    root.addEventListener("drop", (e) => {
      root.classList.remove("fx-drop");
      if (!files(e)) return;
      e.preventDefault();
      if (canAttach()) attach([...e.dataTransfer.files]);
      else toast("Files and pictures go only into Claude app chats.", "err");
    });
  }
  function applySize() {
    const root = $("fx");
    if (root) root.style.setProperty("--fx-px", `${V.size}px`);
  }

  /* ---------------------------------------------------------------- draw */
  function draw() {
    if (!isOn() || !A() || !A().data) return;
    mount();
    const all = sessions();
    if (V.sel !== WA && !all.some((s) => s.id === V.sel) && all.length) pick(X.chatOrder(all, "")[0].id, true);
    drawBadge(all);
    if (V.panel === "chats") drawList();
    if (V.sel === WA) {
      if (V.mode !== "relay" || !V.chat) openRelay();
      else { drawHead(); drawComposer(); waFaces(V.chat); if (V.panel === "sheet") fillSheet(); }
      return;
    }
    const s = all.find((x) => x.id === V.sel);
    if (!s) { close(); blank(); return; }
    const conv = convOf(s);
    const mode = conv ? "claude:" + conv : "log:" + s.id;
    if (mode !== V.mode || !V.chat) open(s, conv, mode);
    else refresh(s);
  }
  function pick(id, quiet) {
    if (!id) return;
    if (id === WA && V.sel !== WA) V.back = V.sel;
    V.sel = id;
    store.set("sel", id);
    if (A() && A().markSeen) A().markSeen(id);
    if (!quiet) draw();
  }
  function blank() {
    V.mode = "";
    $("fxWho").innerHTML = "";
    $("fxWho")._html = "";
    $("fxWaBtn").setAttribute("aria-pressed", "false");
    $("fxLog").replaceChildren();
    drawStage("", "");
    setEmpty(sessions().length ? "" : "No Claude sessions yet. Start one in a terminal or the Claude app and it shows up here.");
    $("fxForm").hidden = true;
    $("fxNote").hidden = true;
  }
  function setEmpty(text, bad) {
    const e = $("fxEmpty");
    e.textContent = text || "";
    e.hidden = !text;
    e.classList.toggle("bad", !!bad);
  }
  function drawBadge(all) {
    const n = all.filter((s) => s.group === "needs_you" && s.id !== V.sel).length;
    const b = $("fxBadge");
    b.hidden = !n;
    b.textContent = n ? String(n) : "";
    b.title = n ? `${n} waiting on you` : "";
  }

  /* --------------------------------------------------------- open, close */
  function open(s, conv, mode) {
    close();
    V.mode = mode;
    const view = C.newView(conv || s.id);
    view.thinking = true;
    view.times = true;
    const chat = {
      gen: ++V.gen, sid: s.id, s, source: conv ? "claude" : "log", conv, view,
      busy: false, meta: null, files: [], sending: false, follow: true,
      plan: window.EnjoyLogic ? window.EnjoyLogic.emptyPlan() : { plan: "", todos: [], done: 0, total: 0, now: "" },
      after: 0, before: null, more: false, timer: 0,
    };
    V.chat = chat;
    $("fxLog").replaceChildren(view.box);
    $("fxForm").hidden = false;
    $("fxOlder").hidden = true;
    $("fxNew").hidden = true;
    restoreDraft(chat);
    setEmpty("Loading the conversation…");
    drawHead();
    drawComposer();
    if (V.panel === "sheet") drawSheet();
    loadOptions().then(() => {
      if (!live(chat)) return;
      ensureRun();
      drawComposer();
      if (V.panel === "sheet") drawSheet();
    });
    if (chat.source === "claude") openClaude(chat);
    else openLog(chat);
  }
  function close() {
    const chat = V.chat;
    if (chat) {
      clearTimeout(chat.timer);
      keepDraft(chat);
    }
    V.gen += 1;
    V.chat = null;
    V.mode = "";
    closePop();
  }
  // What was typed (and attached) and not sent stays with its chat.
  function keepDraft(chat) {
    const ta = $("fxInput");
    const text = ta ? ta.value : "";
    if (text.trim() || chat.files.length) V.drafts[keyOf(chat)] = { text, files: chat.files.slice() };
    else delete V.drafts[keyOf(chat)];
  }
  function restoreDraft(chat) {
    const d = V.drafts[keyOf(chat)];
    $("fxInput").value = d ? d.text : "";
    if (d) chat.files = keptFiles(chat, d.files);
    autosize();
    drawFiles();
    syncSend();
  }
  // A message that failed after its chat was left goes back to that chat's draft.
  function giveBack(chat, text, files) {
    if (live(chat)) {
      const ta = $("fxInput");
      if (!ta.value.trim()) { ta.value = text; autosize(); }
      if (files && files.length && !chat.files.length) { chat.files = files; drawFiles(); }
      return;
    }
    const d = V.drafts[keyOf(chat)];
    if (!d || !d.text.trim()) V.drafts[keyOf(chat)] = { text, files: files || [] };
  }
  function syncSend() {
    const b = $("fxSend");
    if (b) b.disabled = !!V.chat && V.sending.has(keyOf(V.chat));
  }

  // The Claude app's Normal / Ultracode switch and helper limits: made once
  // (it listens on the page for its fold), redrawn from each chat's meta.
  function ensureRun() {
    const o = V.options;
    if (V.run || !o || o.partial || !window.RunControls || !(o.agent_limits || o.ultracode)) return;
    V.run = window.RunControls.create(o, saveSettings);
    if (V.chat && V.chat.meta && V.chat.source === "claude") V.run.apply(V.chat.meta);
  }
  function refresh(s) {
    const chat = V.chat;
    chat.s = s;
    drawHead();
    drawComposer();
    if (V.panel === "sheet") fillSheet();
    queueDecorate(); // a portrait that was a letter until the sprites loaded
  }

  /* ----------------------------------------------------------- the head */
  function stateOf(chat) {
    if (chat.source === "claude" && chat.busy) return "working";
    return chat.s.group;
  }
  // The line under the name: what the session is doing now, else its full
  // title when the name is a cut-down one.
  function titleOf(chat) {
    const s = chat.s;
    const full = (chat.source === "claude" && chat.meta && chat.meta.title) || (s.relay && s.relay.title) || s.title || "";
    // "ended" under an "ended" pill says nothing new
    const said = (GROUP[stateOf(chat)] || stateOf(chat) || "").toLowerCase();
    const act = s.action && s.action.trim().toLowerCase() !== said ? s.action : "";
    return act || (full && !plainName(s).endsWith(full) ? full : "");
  }
  function drawHead() {
    const chat = V.chat;
    if (!chat) return;
    $("fxWaBtn").setAttribute("aria-pressed", String(chat.source === "relay"));
    if (chat.source === "relay") { drawRelayHead(chat); return; }
    const s = chat.s;
    const st = stateOf(chat);
    const html = `<span class="fx-who-ava">${A().avatar("session", s.name || s.id, "", nameOf(s), "", st)}</span>
      <span class="fx-who-t"><span class="fx-who-name"><span class="fx-who-txt" title="${esc(plainName(s))}">${esc(plainName(s))}</span>${L.personaTag(s) ? `<span class="fx-tagname">${esc(L.personaTag(s))}</span>` : ""}<span class="fx-pill ${esc(st)}">${esc(GROUP[st] || st)}</span></span>
      <span class="fx-who-title" title="${esc(titleOf(chat))}">${esc(titleOf(chat))}</span></span>`;
    const who = $("fxWho");
    if (who._html !== html) { who.innerHTML = html; who._html = html; }
    const relayRun = !!(s.relay && s.relay.task) && s.group !== "ended" && chat.source !== "claude";
    const stopBtn = $("fxStop");
    stopBtn.hidden = !((chat.source === "claude" && chat.busy) || relayRun);
    stopBtn.title = relayRun ? `Stop Relay task #${s.relay.task} (press twice)` : "Stop what it is doing now";
    drawStage(s.name || s.id, nameOf(s));
    const p = chat.plan;
    const plan = $("fxPlan");
    plan.hidden = !p.total;
    if (p.total) {
      plan.innerHTML = `<i style="--done:${Math.round((p.done / p.total) * 100)}%"></i><span>${p.done} of ${p.total}</span>`;
      plan.title = p.now ? `Plan: now ${p.now}` : "Plan and progress";
    }
  }

  // The session's chibi stands beside the composer on wide windows (a still
  // frame: Mission stays low power).
  function drawStage(key, label) {
    const st = $("fxStage");
    if (!st) return;
    const html = key ? A().avatar("session", key, "", label, "", "") : "";
    if (st._html !== html) { st.innerHTML = html; st._html = html; }
  }

  /* ------------------------------------------------------- the composer */
  function routeOf(chat) {
    return X.route(chat.s, chat.source === "claude" ? chat.conv : "");
  }
  // Claude app chats upload to that app's conversation; the Relay chat and
  // transcript chats upload to Mission (/api/attach) and send the paths
  // (Relay task 118). Jan reads text only.
  const canAttach = () => !!V.chat && (V.chat.source === "relay" || V.engine !== "jan");
  const ownUpload = (chat) => chat.source !== "claude";
  const uploadUrl = (chat, what) => (ownUpload(chat) ? `/api/attach${what === "paste-image" ? "/paste-image" : ""}` : capi(chat, what));
  const keptFiles = (chat, files) => files.filter((f) => !!f.mission === ownUpload(chat));
  function current(chat) {
    // the model and effort this chat answers with, and whether they can change
    const r = routeOf(chat);
    if (r.kind === "claude") { const m = chat.meta || {}; return { model: m.model || "", effort: m.effort || "", pick: true, own: false }; }
    if (r.kind === "resume") { const p = V.picks[chat.sid] || {}; return { model: p.model ?? "", effort: p.effort ?? "", pick: true, own: false }; }
    return { model: chat.s.model || "", effort: chat.s.effort || "", pick: false, own: true };
  }
  function ultraOf(chat) {
    const u = V.ultra[chat.sid];
    return X.ULTRA.includes(u) ? u : "off";
  }
  function chipHtml(chat) {
    if (V.engine === "jan") return '<span class="fx-dot jan"></span><span>Jan · local</span><span class="fx-caret">▾</span>';
    const o = V.options || {};
    const c = current(chat);
    const fam = X.family(c.model);
    const hue = (X.FAMILIES[fam] || X.FAMILIES[""]).hue;
    const text = c.own ? `${L.modelName(c.model) || "its model"} · ${c.effort ? X.effortLabel(o.efforts, c.effort) : "its effort"}` : X.chipText(o.models, o.efforts, c.model, c.effort);
    const u = ultraOf(chat);
    return `<span class="fx-dot" style="background:${hue}"></span><span>${esc(text)}</span>${u !== "off" && !c.own ? `<span class="fx-ultra-tag" title="Ultrathink: ${esc(ULTRA_WORDS[u].toLowerCase())}">${ICON.spark}ultrathink</span>` : ""}<span class="fx-caret">▾</span>`;
  }
  function drawComposer() {
    const chat = V.chat;
    if (!chat) return;
    if (chat.source === "relay") { drawRelayComposer(chat); return; }
    const r = routeOf(chat);
    const isJan = V.engine === "jan";
    const chip = $("fxChip");
    const html = chipHtml(chat);
    if (chip._html !== html) { chip.innerHTML = html; chip._html = html; }
    chip.title = "Who answers, model, effort and ultrathink";
    $("fxAttach").hidden = !canAttach();
    syncSend();
    $("fxForm").classList.toggle("jan", isJan);
    const name = nameOf(chat.s);
    const ta = $("fxInput");
    ta.placeholder = isJan ? "Ask Jan about this chat…" : r.kind === "board" ? `Note to ${name}…` : `Talk to ${name}…`;
    let note = "";
    if (isJan) note = "Jan, the local model, reads the end of this chat and answers here. The session never sees it.";
    else if (chat.source === "claude" && chat.busy) note = `${name} is working. What you send now joins this turn.`;
    else if (r.kind === "board") note = "Runs in a terminal or Relay: your message arrives as a board note at its next step.";
    else if (r.kind === "resume") note = "Ended: your message resumes it in the Claude app.";
    const n = $("fxNote");
    n.textContent = note;
    n.hidden = !note;
    n.classList.toggle("busy", !isJan && chat.source === "claude" && chat.busy);
    if (isPopOpen()) drawPop();
  }
  function autosize() {
    const ta = $("fxInput");
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = `${Math.min(ta.scrollHeight, Math.round(innerHeight * 0.4))}px`;
  }
  function drawFiles() {
    const chat = V.chat;
    $("fxFiles").innerHTML = (chat ? chat.files : []).map((f, i) => `<span class="fx-file">${esc(f.name)}<button type="button" data-fx-unfile="${i}" title="Remove" aria-label="Remove ${esc(f.name)}">×</button></span>`).join("");
  }

  /* ------------------------------------------- model, effort, ultrathink */
  const isPopOpen = () => !!$("fxPop") && !$("fxPop").hidden;
  function openPop() {
    if (!V.chat) return;
    closePanels();
    $("fxPop").hidden = false;
    $("fxChip").setAttribute("aria-expanded", "true");
    drawPop();
    const on = $("fxPop").querySelector("button.on") || $("fxPop").querySelector("button");
    if (on) on.focus();
    loadOptions().then(() => { if (isPopOpen()) drawPop(); });
  }
  function closePop() {
    const p = $("fxPop");
    if (!p || p.hidden) return;
    p.hidden = true;
    $("fxChip").setAttribute("aria-expanded", "false");
  }
  function drawPop() {
    const chat = V.chat;
    if (!chat) return;
    if (chat.source === "relay") { paintPop(relayPopHtml()); return; }
    const o = V.options || { models: {}, efforts: {} };
    const r = routeOf(chat);
    const c = current(chat);
    const isJan = V.engine === "jan";
    const dis = c.pick ? "" : " disabled";
    const seg = (key, items, value) => `<div class="fx-seg" role="radiogroup">${items.map(([v, label]) => `<button type="button" role="radio" data-fx-${key}="${esc(v)}" aria-checked="${v === value}" class="${v === value ? "on" : ""}"${key === "ultra" ? dis : ""}>${label}</button>`).join("")}</div>`;
    let html = `<h3>Who answers</h3>${seg("eng", [["claude", '<span class="fx-dot claude"></span>Claude'], ["jan", '<span class="fx-dot jan"></span>Jan (local, free)']], V.engine)}`;
    if (isJan) {
      html += '<p class="fx-pop-foot">Jan reads the end of this chat and answers here only. The session never sees it, and it costs nothing.</p>';
    } else {
      const cards = X.modelCards(o.models, c.model);
      const steps = X.effortSteps(o.efforts, c.effort);
      const why = !c.own ? "" : chat.s.relay ? "Relay started this run with this model and effort, so they stay as they are until the run ends. Your messages reach it as board notes." : "It runs in a terminal and keeps the model and effort it started with. Your messages reach it as board notes.";
      html += `${why ? `<p class="fx-pop-why">${esc(why)}</p>` : ""}<h3>Model${c.own ? `<span class="fx-pop-note">its own: ${esc(L.modelName(c.model) || "unknown")}</span>` : ""}</h3>
        <div class="fx-models">${cards.map((m) => `<button type="button" class="fx-card${m.on ? " on" : ""}" data-fx-model="${esc(m.id)}" aria-pressed="${m.on}" style="--hue:${m.hue}"${dis}><b>${esc(m.label)}</b><span>${esc(m.blurb)}</span></button>`).join("")}</div>
        <h3>Effort<span class="fx-pop-note">how hard it thinks</span></h3>
        <div class="fx-gauge" role="radiogroup" aria-label="Effort"><button type="button" role="radio" data-fx-effort="" aria-checked="${!c.effort}" class="fx-auto${c.effort ? "" : " on"}" title="Claude Code picks"${dis}>${c.own ? "its own" : "Default"}</button>${steps.map((e) => `<button type="button" role="radio" data-fx-effort="${esc(e.id)}" aria-checked="${e.on}" class="${e.on ? "on" : ""}${e.lit ? " lit" : ""}" style="--lvl:${e.level}"${dis}><i></i><span>${esc(e.label)}</span></button>`).join("")}</div>
        <h3>Ultrathink<span class="fx-pop-note">the keyword for the hardest thinking</span></h3>
        ${seg("ultra", X.ULTRA.map((u) => [u, ULTRA_WORDS[u]]), c.own ? "off" : ultraOf(chat))}
        <p class="fx-pop-foot">${c.own ? "" : r.kind === "resume" ? "Used when your next message resumes it." : "Changes apply from your next message."}${o.partial ? " The Claude app is not answering, so this list may be short." : ""}</p>`;
    }
    paintPop(html);
  }
  // Redrawn in place: the button that had focus keeps it.
  function paintPop(html) {
    const pop = $("fxPop");
    if (pop._html === html) return; // unchanged: a click on its way is not lost
    pop._html = html;
    const had = document.activeElement && pop.contains(document.activeElement) ? document.activeElement : null;
    const focusKey = had ? [...had.attributes].filter((a) => a.name.startsWith("data-fx-")).map((a) => `[${a.name}="${CSS.escape(a.value)}"]`).join("") : "";
    pop.innerHTML = html;
    if (focusKey) { const b = pop.querySelector(focusKey); if (b) b.focus(); }
  }
  async function setPick(key, value) {
    const chat = V.chat;
    if (!chat) return;
    const r = routeOf(chat);
    if (r.kind === "claude") { await saveSettings({ [key]: value }); return; }
    if (r.kind === "resume") {
      V.picks[chat.sid] = Object.assign({}, V.picks[chat.sid], { [key]: value });
      drawComposer();
    }
  }
  async function saveSettings(changes) {
    const chat = V.chat;
    if (!chat || chat.source !== "claude") return;
    V.knobsBusy += 1;
    try {
      const meta = await post(capi(chat, "settings"), changes);
      if (live(chat)) chat.meta = meta;
      status(chat.busy ? "Saved. It applies from your next message." : "Saved.");
    } catch (e) {
      toast("Could not change it: " + e.message, "err");
    }
    V.knobsBusy -= 1;
    if (!V.knobsBusy) applyMeta(chat, chat.meta, chat.busy);
  }
  function status(text) {
    const n = $("fxStatus");
    n.textContent = text;
    clearTimeout(status.t);
    status.t = setTimeout(() => { n.textContent = ""; }, 2600);
  }

  /* ------------------------------------------------------------ panels */
  function openPanel(which) {
    closePop();
    V.panel = which;
    $("fxChats").hidden = which !== "chats";
    $("fxSheet").hidden = which !== "sheet";
    $("fxShade").hidden = !which;
    if (which === "chats") {
      peekWa();
      drawList();
      const sel = $("fxList").querySelector(".fx-item.on");
      if (sel) sel.scrollIntoView({ block: "nearest" });
      $("fxFind").focus();
    }
    if (which === "sheet") { drawSheet(); const x = $("fxSheet").querySelector(".fx-x"); if (x) x.focus(); }
  }
  function closePanels() {
    if (!V.panel) return;
    V.panel = "";
    $("fxChats").hidden = true;
    $("fxSheet").hidden = true;
    $("fxShade").hidden = true;
  }

  function itemHtml(s) {
    const when = s.last_active ? L.ago(A().nowS() - s.last_active) : "";
    const kind = convOf(s) ? "Claude app" : s.relay ? "Relay" : s.group === "ended" ? "ended" : "terminal";
    const last = s.group === "ended" ? s.title || s.action : s.action || s.title;
    const where = s.place || (s.cwd || "").split("/").pop() || "";
    return `<li class="fx-item${s.id === V.sel ? " on" : ""}${s.group === "needs_you" ? " needs" : ""}" role="option" aria-selected="${s.id === V.sel}" data-fx-sel="${esc(s.id)}" tabindex="0">
      ${A().avatar("session", s.name || s.id, "", nameOf(s), "small", s.group)}
      <span class="fx-it">
        <span class="fx-it-top"><i class="dot ${esc(s.group)}"></i><b>${esc(plainName(s))}</b>${L.personaTag(s) ? `<span class="fx-tagname">${esc(L.personaTag(s))}</span>` : ""}${s.group === "needs_you" ? '<span class="fx-needs">needs you</span>' : ""}<span class="fx-when">${esc(when)}</span></span>
        <span class="fx-it-sub">${esc(where)}${s.model ? ` · ${esc(L.modelName(s.model))}` : ""} · ${esc(kind)}</span>
        <span class="fx-it-last">${esc(last || "")}</span>
      </span>
    </li>`;
  }
  // In Mission's sections and calm order (a row moves at most once a
  // minute); Archived stays folded unless opened, found, or holding the
  // open chat.
  function drawList() {
    const secs = X.chatSections(sessions(), V.find);
    let html = waHit(V.find) ? waItemHtml() : "";
    for (const g of secs) {
      const arch = g.section === "archived";
      const open = !arch || V.showArchived || !!V.find || g.items.some((s) => s.id === V.sel);
      html += arch
        ? `<li class="fx-sec-h" role="presentation"><button type="button" data-fx="archived" aria-expanded="${open}">${esc(g.label)}<span class="fx-sec-n">${g.items.length}</span><span class="fx-caret">${open ? "▾" : "▸"}</span></button></li>`
        : `<li class="fx-sec-h ${esc(g.section)}" role="presentation">${esc(g.label)}<span class="fx-sec-n">${g.items.length}</span></li>`;
      if (open) html += g.items.map(itemHtml).join("");
    }
    if (!secs.length) html += `<li class="fx-none">${V.find ? "No session matches." : "No Claude sessions yet."}</li>`;
    const box = $("fxList");
    if (box._html !== html) { box.innerHTML = html; box._html = html; }
  }
  function step(dir) {
    const order = [WA_S, ...X.chatOrder(sessions(), "")];
    const id = X.neighbour(order, V.sel, dir);
    if (id && id !== V.sel) pick(id);
  }

  /* ----------------------------------------------------------- the sheet */
  // Built when it opens or the chat changes; fillSheet() keeps the values
  // current without rebuilding, so a slider being dragged keeps its place.
  function drawSheet() {
    const chat = V.chat;
    const body = $("fxSheetBody");
    if (!chat) { body.innerHTML = '<p class="fx-muted">No chat open.</p>'; return; }
    if (chat.source === "relay") { body.innerHTML = relaySheetHtml(); fillSheet(); return; }
    const o = V.options || {};
    const claude = chat.source === "claude";
    const s = chat.s;
    const modes = claude && o.modes ? Object.entries(o.modes) : [];
    body.innerHTML = `
      ${claude ? `<section class="fx-sec"><h3>Title</h3><input id="fxTitle" class="fx-input" placeholder="untitled" aria-label="Title"></section>` : ""}
      ${modes.length ? `<section class="fx-sec"><h3>What it may do</h3><div class="fx-modes" role="radiogroup" aria-label="What it may do">${modes.map(([k, v]) => `<label class="fx-mode"><input type="radio" name="fxMode" value="${esc(k)}"><span>${esc(v)}</span></label>`).join("")}</div></section>` : ""}
      ${claude ? `<section class="fx-sec" id="fxRunSec"><h3>How it works</h3><div id="fxRun" class="fx-run"></div><p class="fx-muted fx-small">Ultracode plans the work and runs helpers for it. Limits cap the helpers.</p></section>` : ""}
      <section class="fx-sec" id="fxPlanSec" hidden><h3>Plan and progress</h3><div class="fx-bar"><i id="fxBar"></i></div><p id="fxPlanNow" class="fx-small fx-muted"></p><ol id="fxTodos" class="fx-todos"></ol><details id="fxPlanBox" hidden><summary>The plan</summary><div id="fxPlanText" class="fx-plan-text"></div></details></section>
      <section class="fx-sec"><h3>Reading</h3>
        ${sizeHtml()}
        <label class="fx-switch"><input type="checkbox" id="fxReasoning"${V.reasoning ? " checked" : ""}><span class="track"><span class="knob"></span></span><span>Show Claude's reasoning where it was kept</span></label>
        <div class="fx-line"><span>Steps between messages</span><div class="fx-seg" role="radiogroup" aria-label="Steps">${STEPS.map((k) => `<button type="button" role="radio" data-fx-steps="${k}" aria-checked="${k === V.steps}" class="${k === V.steps ? "on" : ""}">${STEP_WORDS[k]}</button>`).join("")}</div></div>
      </section>
      <section class="fx-sec"><h3>About</h3><dl id="fxFacts" class="fx-facts"></dl></section>
      <section class="fx-sec fx-acts" id="fxActs"></section>`;
    if ($("fxRunSec")) {
      if (V.run) $("fxRun").append(V.run.root);
      $("fxRunSec").hidden = !V.run;
    }
    fillSheet();
  }
  const sizeHtml = () => `<div class="fx-size"><label for="fxSize">Text size</label><span class="fx-a small">A</span><input type="range" id="fxSize" min="${X.SIZE.min}" max="${X.SIZE.max}" step="1" value="${V.size}"><span class="fx-a big">A</span><input type="number" id="fxSizeN" min="${X.SIZE.min}" max="${X.SIZE.max}" step="1" value="${V.size}" aria-label="Text size in pixels"></div>`;
  function fillSheet() {
    const chat = V.chat;
    if (!chat || !$("fxFacts")) return;
    if (chat.source === "relay") { fillRelaySheet(chat); return; }
    const s = chat.s;
    const m = chat.meta || {};
    const claude = chat.source === "claude";
    const t = $("fxTitle");
    if (t && document.activeElement !== t) t.value = m.title || "";
    const mode = m.mode || (V.options && V.options.default_mode) || "";
    document.querySelectorAll('#fxSheet input[name="fxMode"]').forEach((r) => { if (!V.knobsBusy) r.checked = r.value === mode; });
    if (V.run && claude && chat.meta && !V.knobsBusy) V.run.apply(chat.meta);
    const p = chat.plan;
    $("fxPlanSec").hidden = !(p.total || p.plan);
    $("fxBar").style.width = p.total ? `${Math.round((p.done / p.total) * 100)}%` : "0";
    $("fxPlanNow").textContent = p.total ? `${p.done} of ${p.total} done${p.now ? ` · now: ${p.now}` : p.done === p.total ? " ✓" : ""}` : "";
    $("fxTodos").innerHTML = p.todos.map((x) => `<li class="${esc(x.status)}">${esc(x.content)}</li>`).join("");
    $("fxPlanBox").hidden = !p.plan;
    if (p.plan && $("fxPlanText")._raw !== p.plan) { $("fxPlanText").innerHTML = C.markdown(p.plan); $("fxPlanText")._raw = p.plan; }
    const cost = m.cost_usd ? `$${Number(m.cost_usd).toFixed(2)} at API list prices (not billed)` : "";
    const where = claude ? "a Claude app chat" : s.relay ? "a Relay run" : s.group === "ended" ? "ended" : "a terminal";
    const rows = [
      ["runs in", where],
      ["folder", (claude && m.cwd) || s.cwd],
      ["account", claude ? m.profile || "default" : ""],
      ["model", claude ? (V.options && V.options.models && V.options.models[m.model || ""]) || m.model || "Claude Code's default" : L.modelName(s.model)],
      ["effort", claude ? X.effortLabel(V.options && V.options.efforts, m.effort) : s.effort],
      ["worth", cost],
      ["board name", s.name],
      ["session", s.id],
    ];
    const facts = rows.filter((r) => r[1]).map(([k, v]) => `<dt>${esc(k)}</dt><dd title="${esc(v)}">${esc(v)}</dd>`).join("");
    if ($("fxFacts")._html !== facts) { $("fxFacts").innerHTML = facts; $("fxFacts")._html = facts; }
    const acts = [
      claude || s.claude_tab ? `<button type="button" class="fx-btn" data-claude="${esc(s.id)}">Open in the Claude app</button>` : "",
      !claude && s.group === "ended" ? `<button type="button" class="fx-btn fx-primary" data-fx="resume">Resume here</button><button type="button" class="fx-btn" data-claude="${esc(s.id)}">Resume in the Claude app</button>` : "",
      s.group !== "ended" && s.name ? `<button type="button" class="fx-btn" data-go="${esc(s.name)}">Go to its window</button>` : "",
      `<button type="button" class="fx-btn" data-fx="details">Details and helpers</button>`,
    ].join("");
    if ($("fxActs")._html !== acts) { $("fxActs").innerHTML = acts; $("fxActs")._html = acts; }
  }
  function setSize(n) {
    V.size = X.clampSize(n);
    store.set("size", V.size);
    applySize();
    const r = $("fxSize"), num = $("fxSizeN");
    if (r && document.activeElement !== r) r.value = V.size;
    if (num && document.activeElement !== num) num.value = V.size;
  }
  function setSteps(k) {
    if (!STEPS.includes(k)) return;
    V.steps = k;
    store.set("steps", k);
    $("fx").dataset.steps = k;
    document.querySelectorAll("#fxLog .fx-steps").forEach((g) => { g.open = k === "open"; });
    document.querySelectorAll("[data-fx-steps]").forEach((b) => { const on = b.dataset.fxSteps === k; b.classList.toggle("on", on); b.setAttribute("aria-checked", String(on)); });
  }
  function setReasoning(on) {
    V.reasoning = !!on;
    store.set("reasoning", V.reasoning);
    $("fxLog").classList.toggle("hide-thinking", !V.reasoning);
    document.querySelectorAll("#fxLog .fx-steps").forEach(paintGroup);
  }

  /* ------------------------------------------------- steps and portraits */
  function stepItem(card) {
    const name = card.querySelector("summary .name");
    const brief = card.querySelector("summary .brief");
    const think = card.classList.contains("thinking");
    return {
      name: X.stepName(name && name.textContent),
      brief: (brief && brief.textContent) || "",
      think,
      state: card.classList.contains("pending") ? "running" : card.classList.contains("error") ? "failed" : "done",
    };
  }
  function makeGroup() {
    const g = C.el("details", "fx-steps");
    g.open = V.steps === "open";
    const sum = C.el("summary");
    sum.append(C.el("span", "fx-st-dot"), C.el("b", "fx-st-label"), C.el("span", "fx-st-names"), C.el("span", "fx-st-now"));
    g.append(sum, C.el("div", "fx-st-list"));
    return g;
  }
  // Words Claude says on the way ("Let me check the tests.") are not the
  // answer: a step follows them in the same turn. Short ones (and no
  // pictures, code or tables) fold into the steps bar with the tool calls,
  // so Emerson's messages and the answers stay together on screen (L2).
  function isAsideBox(n) {
    if (!n || !n.classList.contains("msg") || !n.classList.contains("claude") || n.classList.contains("fx-wa")) return false;
    const words = [...n.querySelectorAll(":scope > .bubble")];
    if (!words.length || n.querySelector("img, figure, pre, table")) return false;
    return X.isAside(words.map((b) => b.textContent).join(" "));
  }
  function absorb(g, n) {
    const f = n.querySelector(":scope > .fx-face");
    if (f) {
      const at = f.querySelector("time.at");
      if (at) n.prepend(at);
      f.remove();
    }
    n.classList.remove("fx-first");
    n.classList.add("fx-aside");
    g.querySelector(".fx-st-list").append(n);
  }
  // The group the next step joins: the last one, when nothing but empty
  // Claude boxes (a reply with no words yet) and short words on the way
  // came after it; those words join it first. A new group goes in before
  // them, so words that arrive later follow it.
  function groupFor(view) {
    let n = view.box.lastElementChild;
    let firstEmpty = null;
    while (n && n.classList.contains("claude") && !n.querySelector(":scope > .bubble")) { firstEmpty = n; n = n.previousElementSibling; }
    const asides = [];
    while (isAsideBox(n)) { asides.unshift(n); n = n.previousElementSibling; }
    let g = n && n.classList.contains("fx-steps") ? n : null;
    if (!g) {
      g = makeGroup();
      view.box.insertBefore(g, asides[0] || firstEmpty);
    }
    for (const a of asides) absorb(g, a);
    return g;
  }
  function paintGroup(g) {
    const all = [...g.querySelector(".fx-st-list").children];
    const cards = all.filter((c) => !c.classList.contains("msg"));
    const said = all.filter((c) => c.classList.contains("fx-aside"));
    const items = cards.map(stepItem).filter((x) => V.reasoning || !x.think);
    const sum = X.stepsSummary(items);
    g.classList.toggle("running", sum.state === "running");
    g.classList.toggle("failed", sum.state === "failed");
    g.classList.toggle("fx-think-only", !cards.some((c) => !c.classList.contains("thinking")));
    g.hidden = !items.length && !said.length;
    // the bar says what Claude last said on the way, else the tools it used
    const last = said.length ? said[said.length - 1].querySelector(":scope > .bubble") : null;
    const lastText = last ? last.textContent.replace(/\s+/g, " ").trim() : "";
    const names = g.querySelector(".fx-st-names");
    names.textContent = lastText || sum.names;
    names.classList.toggle("said", !!lastText);
    g.querySelector("summary").title = sum.names;
    g.querySelector(".fx-st-label").textContent = sum.count || !said.length ? sum.label : "On the way";
    g.querySelector(".fx-st-now").textContent = sum.now ? `now: ${sum.now}` : sum.failed ? `${sum.failed} failed` : "";
  }
  let decorateQueued = 0;
  function queueDecorate() {
    if (decorateQueued) return;
    decorateQueued = requestAnimationFrame(() => { decorateQueued = 0; decorate(); });
  }
  // The first reply after each message of Emerson's (or a turn's end) gets
  // the session's portrait and name; the rest of the run sits under it.
  function decorate() {
    const chat = V.chat;
    if (!chat || chat.source === "relay") return;
    const s = chat.s;
    const ava = A().avatar("session", s.name || s.id, "", nameOf(s), "", "");
    const name = nameOf(s);
    let need = true;
    for (const n of chat.view.box.children) {
      const cl = n.classList;
      if (cl.contains("user") || cl.contains("jan") || cl.contains("turn-end") || cl.contains("divider")) { need = true; continue; }
      if (!cl.contains("msg") || !cl.contains("claude")) continue;
      const words = !!n.querySelector(":scope > .bubble");
      const first = words && need;
      if (words) need = false;
      let f = n.querySelector(":scope > .fx-face");
      if (first) {
        if (!f) { f = C.el("div", "fx-face"); f.append(C.el("span", "fx-ava"), C.el("span", "fx-tag")); n.prepend(f); }
        if (f.firstChild._html !== ava) { f.firstChild.innerHTML = ava; f.firstChild._html = ava; }
        if (f.children[1].textContent !== name) f.children[1].textContent = name;
        const at = n.querySelector(":scope > time.at");
        if (at) f.append(at);
      } else if (f) {
        const at = f.querySelector("time.at");
        if (at) n.prepend(at);
        f.remove();
      }
      cl.toggle("fx-first", first);
    }
  }
  const hooks = {
    scroll(view, force) {
      if (view.bulk || !V.chat || V.chat.view !== view) return;
      scrollDown(force);
      queueDecorate();
    },
    shown(view) { if (V.chat && V.chat.view === view && !$("fxEmpty").classList.contains("bad")) setEmpty(""); },
    assistant(message, view) {
      const said = ((message || {}).content || []).filter((b) => b.type === "text").map((b) => b.text).join("\n").trim();
      if (said) view.voiceText = said; // the last words of a turn are what gets spoken
      const chat = V.chat;
      if (!chat || chat.view !== view || !window.EnjoyLogic) return;
      chat.plan = window.EnjoyLogic.planStep(chat.plan, message);
      chat.planDirty = true;
    },
    browserTool() {},
    step(card, view, block) {
      // a thought Claude Code did not keep says nothing: leave it out
      if (block.type === "thinking" && !String(block.thinking || "").trim()) return;
      const g = groupFor(view);
      g.querySelector(".fx-st-list").append(card);
      paintGroup(g);
    },
    stepDone(card) {
      const g = card.closest(".fx-steps");
      if (g) paintGroup(g);
    },
    turnEnd(view, event) {
      view.box.querySelectorAll(".fx-steps.running").forEach(paintGroup);
      // "took 18 min" in place of "1070.5s · $17.34" (list price, not what he pays)
      const t = view.box.lastElementChild;
      if (t && t.classList.contains("turn-end") && event) {
        const words = X.tookWords(event.duration_ms);
        if (words) t.textContent = words;
        else t.remove();
      }
      const said = view.voiceText || "";
      view.voiceText = "";
      const ok = !event || (!event.is_error && (!event.subtype || event.subtype === "success"));
      // only a turn that just finished in the open chat, never a history replay
      if (said && ok && !view.bulk && V.chat && V.chat.view === view && window.ForgeVoice && ForgeVoice.speakReplies("mission")) {
        ForgeVoice.speak(said, { app: "mission" }).catch(() => {});
      }
    },
  };
  function drawEvents(chat, events, bulk) {
    const view = chat.view;
    view.bulk = !!bulk;
    try { for (const ev of events) C.draw(ev, view, hooks); } finally { view.bulk = false; }
    if (chat.planDirty) { chat.planDirty = false; drawHead(); if (V.panel === "sheet") fillSheet(); }
    queueDecorate();
  }
  function scrollDown(force) {
    const sc = $("fxScroll");
    const chat = V.chat;
    if (!sc || !chat) return;
    if (force || chat.follow) { sc.scrollTop = sc.scrollHeight; chat.follow = true; $("fxNew").hidden = true; }
    else $("fxNew").hidden = false;
  }

  /* --------------------------------------------- source: a Claude app chat */
  async function openClaude(chat) {
    try {
      const body = await req(capi(chat, "events?after=-1"));
      if (!live(chat)) return;
      drawEvents(chat, body.events, true);
      if (body.events.length) chat.view.seq = body.events[body.events.length - 1].seq;
      chat.view.boot = body.boot;
      setEmpty(body.events.length ? "" : "Nothing said yet. Say what you want below.");
      drawJan(chat);
      chat.fails = 0;
      applyMeta(chat, body.meta, body.busy);
      decorate();
      scrollDown(true);
    } catch (e) {
      if (!live(chat)) return;
      // tried again in place, slower each time: the box and what is typed stay
      chat.fails = (chat.fails || 0) + 1;
      setEmpty("Could not open it: " + e.message, true);
      chat.timer = setTimeout(() => { if (live(chat)) openClaude(chat); }, Math.min(60000, 4000 * 2 ** chat.fails));
      return;
    }
    post(capi(chat, "seen")).catch(() => {});
    follow(chat);
  }
  async function follow(chat) {
    while (live(chat)) {
      if (!shownPage() || !isOn()) { await new Promise((r) => setTimeout(r, 3000)); continue; }
      try {
        const body = await req(capi(chat, `events?after=${chat.view.seq ?? -1}&wait=25&boot=${encodeURIComponent(chat.view.boot || "")}`));
        if (!live(chat)) return;
        if (body.reset) { V.mode = ""; draw(); return; } // the Claude app restarted: its numbers start again
        if (body.events.length) {
          drawEvents(chat, body.events, false);
          chat.view.seq = body.events[body.events.length - 1].seq;
        }
        const was = chat.busy;
        applyMeta(chat, body.meta, body.busy);
        if (was && !body.busy) post(capi(chat, "seen")).catch(() => {});
      } catch (e) {
        if (!live(chat)) return;
        status("Lost the Claude app for a moment; trying again…");
        await new Promise((r) => setTimeout(r, 3000));
      }
    }
  }
  function applyMeta(chat, meta, busy) {
    if (!live(chat) || !meta) return;
    chat.meta = meta;
    chat.busy = !!busy;
    drawHead();
    drawComposer();
    if (V.run && !V.knobsBusy) V.run.apply(meta);
    if (V.panel === "sheet") fillSheet();
  }
  async function stop() {
    const chat = V.chat;
    if (!chat) return;
    if (chat.source === "claude" && chat.busy) {
      try { await post(capi(chat, "stop")); status("Stopping…"); } catch (e) { toast(e.message, "err"); }
      return;
    }
    const task = chat.s.relay && chat.s.relay.task;
    if (!task) return;
    const btn = $("fxStop");
    if (Date.now() - V.stopArm > 4000) {
      V.stopArm = Date.now();
      btn.classList.add("armed");
      btn.querySelector("span").textContent = `Stop #${task}?`;
      setTimeout(() => { if (Date.now() - V.stopArm >= 4000) { btn.classList.remove("armed"); btn.querySelector("span").textContent = "Stop"; } }, 4100);
      return;
    }
    V.stopArm = 0;
    btn.classList.remove("armed");
    btn.querySelector("span").textContent = "Stop";
    try {
      const got = await post(`/api/relay/tasks/${encodeURIComponent(task)}/stop`);
      toast(got.message || `Stopping Relay task #${task}`, "ok");
      A().pollNow();
    } catch (e) { toast(e.message, "err"); }
  }

  /* ------------------------------------- source: a transcript (log) chat */
  function logUrl(chat, extra) {
    const q = new URLSearchParams(extra || {}).toString();
    return `/api/sessions/${encodeURIComponent(chat.sid)}/events${q ? "?" + q : ""}`;
  }
  async function openLog(chat) {
    try {
      const got = await req(logUrl(chat));
      if (!live(chat)) return;
      settle(chat, got.events);
      drawEvents(chat, got.events, true);
      chat.after = got.after;
      chat.before = got.before;
      chat.more = got.more;
      chat.loaded = true;
      $("fxOlder").hidden = !chat.more;
      setEmpty(got.events.length || pendingOf(chat).length ? "" : "Nothing said yet.");
      drawJan(chat);
      showPending(chat);
      decorate();
      scrollDown(true);
      fillColumn(chat);
    } catch (e) {
      if (!live(chat)) return;
      setEmpty("Could not read it: " + e.message, true);
    }
    tickLater(chat);
  }
  function tickLater(chat, ms) {
    if (!live(chat)) return;
    clearTimeout(chat.timer);
    chat.timer = setTimeout(() => tick(chat), ms ?? (LIVE_MS[chat.s.group] || 6000));
  }
  async function tick(chat) {
    if (!live(chat)) return;
    if (!shownPage() || !isOn()) { tickLater(chat); return; }
    if (!chat.loaded) { setEmpty("Loading the conversation…"); openLog(chat); return; } // the first read failed
    try {
      const got = await req(logUrl(chat, { after: chat.after }));
      if (!live(chat)) return;
      if (got.reset) { V.mode = ""; draw(); return; }
      if (got.events.length) {
        settle(chat, got.events);
        drawEvents(chat, got.events, false);
        scrollDown(false);
      }
      chat.after = got.after;
      if (got.more) { tickLater(chat, 50); return; }
    } catch (e) {
      /* a missed look is tried again on the next tick */
    }
    tickLater(chat);
  }
  // A chat that opens with less than a screenful reads up to three earlier
  // pages first, so a Relay run does not open nearly empty.
  async function fillColumn(chat) {
    const sc = $("fxScroll");
    for (let i = 0; i < 3 && live(chat) && chat.more; i++) {
      if (sc.scrollHeight > sc.clientHeight * 1.5) break;
      await older();
    }
    if (live(chat) && chat.follow) scrollDown(true);
  }
  async function older() {
    const chat = V.chat;
    if (!chat || chat.source !== "log" || !chat.more || chat.loadingOlder) return;
    chat.loadingOlder = true;
    const btn = $("fxOlder");
    btn.disabled = true;
    try {
      const got = await req(logUrl(chat, { before: chat.before }));
      if (!live(chat)) return;
      const v = C.newView(chat.sid);
      v.thinking = true;
      v.times = true;
      for (const ev of got.events) C.draw(ev, v, hooks);
      v.box.querySelectorAll(".toolcard.pending").forEach((c) => c.classList.replace("pending", "done"));
      v.box.querySelectorAll(".fx-steps").forEach(paintGroup);
      const sc = $("fxScroll");
      const h = sc.scrollHeight;
      const top = sc.scrollTop;
      chat.view.box.prepend(...v.box.childNodes);
      sc.scrollTop = top + (sc.scrollHeight - h); // the line being read stays put
      chat.before = got.before;
      chat.more = got.more;
      btn.hidden = !chat.more;
      decorate();
    } catch (e) {
      toast(e.message, "err");
    } finally {
      chat.loadingOlder = false;
      btn.disabled = false;
    }
  }
  // "sending…" lines: kept per chat (not per visit) until the chat shows
  // the line or ten minutes pass, and drawn again when the chat reopens.
  const pendingOf = (chat) => (V.pending.get(keyOf(chat)) || []).filter((g) => Date.now() - g.at < PENDING_MS);
  function ghostBox(chat, g) {
    const box = C.el("div", "msg user ghost");
    box.append(C.el("div", "bubble", g.text), C.el("div", "joined", g.how));
    chat.view.box.insertBefore(box, chat.typing || null);
    g.box = box;
    return box;
  }
  function ghost(chat, text, how) {
    const key = keyOf(chat);
    const g = { text, how, at: Date.now(), box: null };
    V.pending.set(key, [...pendingOf(chat), g]);
    ghostBox(chat, g);
    setTimeout(() => dropPending(key, g), PENDING_MS);
    scrollDown(true);
    return g;
  }
  function setHow(g, how) {
    g.how = how;
    const j = g.box && g.box.querySelector(".joined");
    if (j) j.textContent = how;
  }
  function dropPending(key, g) {
    const list = V.pending.get(key) || [];
    const i = list.indexOf(g);
    if (i >= 0) list.splice(i, 1);
    if (g.box) g.box.remove();
    if (!list.length) V.pending.delete(key);
  }
  function dropGhost(chat, text) {
    const g = pendingOf(chat).find((x) => X.sameLine(x.text, text));
    if (g) dropPending(keyOf(chat), g);
  }
  function showPending(chat) {
    for (const g of pendingOf(chat)) if (!g.box || !g.box.isConnected || !chat.view.box.contains(g.box)) ghostBox(chat, g);
  }
  // Emerson's lines that reached the chat take their "sending…" line away.
  function settle(chat, events) {
    for (const ev of events) if (ev.type === "forge_user") dropGhost(chat, ev.text);
  }
  async function resumeHere() {
    const chat = V.chat;
    if (!chat || chat.source !== "log") return;
    const s = chat.s;
    try {
      const got = await post(`/api/sessions/${encodeURIComponent(s.id)}/open`, { state: s.group, cwd: s.cwd, name: nameOf(s), show: false });
      if (!got.id) throw new Error("The Claude app did not say which chat it is");
      const picks = V.picks[s.id] || {};
      const changes = Object.fromEntries(["model", "effort"].filter((k) => picks[k] !== undefined && picks[k] !== null).map((k) => [k, picks[k]]));
      if (Object.keys(changes).length) await post(`/api/claude/conversations/${encodeURIComponent(got.id)}/settings`, changes).catch(() => {});
      V.resumed[s.id] = got.id;
      toast("Resumed in the Claude app. Talk to it here.", "ok");
      closePanels();
      V.mode = "";
      draw();
      A().pollNow();
    } catch (e) { toast(e.message, "err"); }
  }

  /* ------------------------------ source: the WhatsApp chat with Relay */
  // Emerson's note 1295: his WhatsApp thread with Relay, live, and a way to
  // type into it. /api/relay-chat (mc/relay_chat.py) reads the chat task's
  // Messages (the last 40 lines); a line he sends goes through `relay
  // as-whatsapp`, so Relay handles it exactly as one from his phone, and
  // the phone thread shows it too ("From Mission Control").
  function noteWaLast(rows) {
    const last = rows[rows.length - 1];
    V.waLast = last ? { me: last.me, text: last.text, time: last.time, day: last.day } : null;
    if (V.panel === "chats") drawList();
  }
  // The WhatsApp row in Chats shows its last line even before the chat is opened.
  async function peekWa() {
    if (V.mode === "relay" || Date.now() - V.waPeek < 30000) return;
    V.waPeek = Date.now();
    try {
      const got = await req("/api/relay-chat");
      if (got.task && V.mode !== "relay") noteWaLast(X.waRuns(got.messages || [], new Date()));
    } catch (e) { /* the row just has no last line */ }
  }
  const waHit = (find) => {
    const q = String(find || "").trim().toLowerCase();
    return !q || ["whatsapp", "relay", "boss", "phone"].some((w) => w.includes(q) || q.includes(w));
  };
  const firstId = () => (X.chatOrder(sessions(), "")[0] || {}).id;
  function openRelay() {
    close();
    V.mode = "relay";
    const chat = {
      gen: ++V.gen, sid: WA, s: WA_S, source: "relay", conv: "", view: C.newView(WA),
      busy: false, meta: null, files: [], sending: false, follow: true,
      plan: { plan: "", todos: [], done: 0, total: 0, now: "" },
      timer: 0, version: "", nodes: new Map(), typing: null,
      answering: false, task: null, state: "", fails: 0, ticking: false, again: false, loaded: false,
    };
    V.chat = chat;
    $("fxLog").replaceChildren(chat.view.box);
    $("fxForm").hidden = false;
    $("fxOlder").hidden = true;
    $("fxNew").hidden = true;
    restoreDraft(chat);
    setEmpty("Loading your WhatsApp chat…");
    drawHead();
    drawComposer();
    if (V.panel === "sheet") drawSheet();
    tickRelay(chat);
  }
  function relaySoon(chat, ms) {
    if (!live(chat)) return;
    clearTimeout(chat.timer);
    chat.timer = setTimeout(() => tickRelay(chat), ms);
  }
  // One look at a time; a look asked for meanwhile runs right after it.
  // Unchanged chats cost one tiny answer (`seen` = the version shown).
  async function tickRelay(chat) {
    if (!live(chat)) return;
    if (chat.ticking) { chat.again = true; return; }
    clearTimeout(chat.timer);
    if (!shownPage() || !isOn()) { relaySoon(chat, 15000); return; }
    chat.ticking = true;
    chat.again = false;
    try {
      const got = await req(`/api/relay-chat?seen=${encodeURIComponent(chat.version)}`);
      if (!live(chat)) return;
      chat.fails = 0;
      chat.task = got.task;
      chat.state = got.status || "";
      chat.answering = !!got.answering;
      if (!got.task) {
        chat.version = "";
        chat.nodes.forEach((n) => n.remove());
        chat.nodes.clear();
        setEmpty("Relay has no WhatsApp chat yet. It starts with your first WhatsApp message to Relay.");
      } else if (!got.same) {
        chat.version = got.version;
        drawRelay(chat, got.messages || []);
      }
      drawTyping(chat);
      drawHead();
      if (V.panel === "sheet") fillSheet();
    } catch (e) {
      if (!live(chat)) return;
      chat.fails += 1;
      if (!chat.loaded) setEmpty("Could not read the WhatsApp chat: " + e.message, true);
      else status("Lost the WhatsApp chat for a moment; trying again…");
    } finally {
      chat.ticking = false;
    }
    if (live(chat)) relaySoon(chat, chat.again ? 0 : chat.fails ? Math.min(30000, WA_MS * 2 ** chat.fails) : WA_MS);
  }
  // Lines are kept by key: a new one is added, one Relay no longer keeps
  // goes, the rest stay as they are (no flicker, the place being read stays).
  function drawRelay(chat, messages) {
    const box = chat.view.box;
    const rows = X.waRuns(messages, new Date());
    const keep = new Set();
    const want = [];
    let added = false;
    for (const m of rows) {
      if (m.day) {
        const k = "day:" + m.key;
        let d = chat.nodes.get(k);
        if (!d) { d = C.el("div", "fx-wa-day"); d.dataset.key = k; chat.nodes.set(k, d); }
        if (d.textContent !== m.day) d.textContent = m.day;
        keep.add(k);
        want.push(d);
      }
      let n = chat.nodes.get(m.key);
      if (!n) {
        n = waNode(m);
        chat.nodes.set(m.key, n);
        added = true;
        if (m.me) dropGhost(chat, m.text);
      }
      paintWa(n, m);
      keep.add(m.key);
      want.push(n);
    }
    for (const [k, n] of chat.nodes) if (!keep.has(k)) { n.remove(); chat.nodes.delete(k); }
    const now = [...box.children].filter((n) => n.dataset.key);
    if (now.length !== want.length || now.some((n, i) => n !== want[i])) box.prepend(...want);
    noteWaLast(rows);
    if (!chat.loaded) { chat.loaded = true; showPending(chat); }
    setEmpty(rows.length || pendingOf(chat).length ? "" : "Nothing said yet. Say hello below: it shows on WhatsApp too.");
    if (!chat.scrolled) { chat.scrolled = true; scrollDown(true); } else if (added) scrollDown(false);
  }
  function waNode(m) {
    const n = C.el("div", `msg ${m.me ? "user" : "claude"} fx-wa`);
    n.dataset.key = m.key;
    n.dataset.who = m.kind;
    const b = C.el("div", "bubble");
    b.innerHTML = X.waText(m.text) + (m.time ? `<time class="fx-wa-at">${esc(m.time)}</time>` : "");
    n._bubble = b;
    return n;
  }
  function paintWa(n, m) {
    const sig = `${m.first}|${m.mark}`;
    if (n._sig === sig) return;
    n._sig = sig;
    n.classList.toggle("fx-first", m.first);
    const parts = [];
    if (m.first && !m.me) parts.push(waFace(m.kind));
    parts.push(n._bubble);
    if (m.mark) parts.push(C.el("div", "joined", m.mark === "read" ? "✓✓ read" : "✓ sent"));
    n.replaceChildren(...parts);
  }
  // Relay, the boss, Jan and the local model each have a face of their own.
  function waAva(kind) {
    if (kind === "jan") return "J";
    return A().avatar(kind === "local" ? "model" : "session", "relay-" + kind, "", WA_WORDS[kind] || "Relay", "", "");
  }
  function paintAva(a, kind) {
    const html = waAva(kind);
    if (a._html !== html) { a.innerHTML = html; a._html = html; }
  }
  function waFace(kind) {
    const f = C.el("div", "fx-face");
    f.dataset.kind = kind;
    const a = C.el("span", "fx-ava" + (kind === "jan" ? " jan" : ""));
    f.append(a, C.el("span", "fx-tag", WA_WORDS[kind] || "Relay"));
    paintAva(a, kind);
    return f;
  }
  // a face drawn as a letter before the sprites loaded gets its portrait
  function waFaces(chat) {
    chat.view.box.querySelectorAll(".fx-face[data-kind]").forEach((f) => paintAva(f.firstChild, f.dataset.kind));
  }
  // Relay's chat is on it (queued or running): three dots at the end.
  function drawTyping(chat) {
    const box = chat.view.box;
    if (chat.answering && !chat.typing) {
      const t = C.el("div", "msg claude fx-wa fx-typing");
      const b = C.el("div", "bubble");
      b.innerHTML = '<p class="thinking-dots" role="img" aria-label="Relay is answering"><i></i><i></i><i></i></p>';
      t.append(b);
      chat.typing = t;
      box.append(t);
      scrollDown(false);
    } else if (!chat.answering && chat.typing) {
      chat.typing.remove();
      chat.typing = null;
    } else if (chat.typing && box.lastElementChild !== chat.typing) box.append(chat.typing);
  }
  function drawRelayHead(chat) {
    const st = chat.answering ? "working" : "wa-live";
    const pill = chat.answering ? "answering" : chat.task ? "live" : "not set up";
    const html = `<span class="fx-who-ava">${waAva("relay")}</span>
      <span class="fx-who-t"><span class="fx-who-name"><span class="fx-who-txt">WhatsApp</span><span class="fx-tagname">Relay</span><span class="fx-pill ${st}">${esc(pill)}</span></span>
      <span class="fx-who-title">Your phone chat with Relay, live. What you send here shows on WhatsApp too.</span></span>`;
    const who = $("fxWho");
    if (who._html !== html) { who.innerHTML = html; who._html = html; }
    $("fxStop").hidden = true;
    $("fxPlan").hidden = true;
    drawStage("relay-relay", "Relay");
  }
  function drawRelayComposer(chat) {
    const chip = $("fxChip");
    const html = `<span class="fx-dot ${V.waBoss ? "boss" : "wa"}"></span><span>${V.waBoss ? "To the boss" : "To Relay"}</span><span class="fx-caret">▾</span>`;
    if (chip._html !== html) { chip.innerHTML = html; chip._html = html; }
    chip.title = "Who answers: Relay's chat or its boss";
    $("fxAttach").hidden = false;
    $("fxForm").classList.remove("jan");
    $("fxInput").placeholder = V.waBoss ? "Ask Relay's boss…" : "Message Relay…";
    $("fxNote").hidden = true;
    if (isPopOpen()) drawPop();
  }
  function relayPopHtml() {
    const b = (v, label) => {
      const on = V.waBoss === (v === "boss");
      return `<button type="button" role="radio" data-fx-wa="${v}" aria-checked="${on}" class="${on ? "on" : ""}"><span class="fx-dot ${v === "boss" ? "boss" : "wa"}"></span>${label}</button>`;
    };
    return `<h3>Who answers</h3><div class="fx-seg" role="radiogroup" aria-label="Who answers">${b("relay", "Relay")}${b("boss", "The boss")}</div>
      <p class="fx-pop-foot">Relay answers as it does on WhatsApp, and its commands work here too (status, stop 12 and the rest). The boss is Relay's boss line, the same as starting a line with "boss:" on your phone. Either way your line shows on WhatsApp too.</p>`;
  }
  function relaySheetHtml() {
    return `<section class="fx-sec"><h3>Reading</h3>${sizeHtml()}</section>
      <section class="fx-sec"><h3>About</h3><dl id="fxFacts" class="fx-facts"></dl></section>
      <section class="fx-sec fx-acts"><button type="button" class="fx-btn" data-fx-view="relay">Open Relay</button></section>`;
  }
  function fillRelaySheet(chat) {
    const rows = [
      ["what", "your WhatsApp chat with Relay, live"],
      ["chat task", chat.task ? "#" + chat.task : "none yet"],
      ["now", chat.answering ? "answering" : chat.state],
      ["shows", "the last 40 lines Relay keeps"],
      ["you send", "goes to Relay as if typed on WhatsApp, and to your phone (when WhatsApp is on) marked From Mission Control"],
    ];
    const facts = rows.filter((r) => r[1]).map(([k, v]) => `<dt>${esc(k)}</dt><dd title="${esc(v)}">${esc(v)}</dd>`).join("");
    if ($("fxFacts")._html !== facts) { $("fxFacts").innerHTML = facts; $("fxFacts")._html = facts; }
  }
  function waItemHtml() {
    const l = V.waLast;
    return `<li class="fx-item fx-wa-item${V.sel === WA ? " on" : ""}" role="option" aria-selected="${V.sel === WA}" data-fx-sel="${WA}" tabindex="0">
      <span class="fx-wa-ico">${ICON.wa}</span>
      <span class="fx-it">
        <span class="fx-it-top"><b>WhatsApp</b><span class="fx-tagname">Relay</span>${l && l.time ? `<span class="fx-when">${esc(l.time)}</span>` : ""}</span>
        <span class="fx-it-sub">your phone chat with Relay, live · the boss too</span>
        ${l ? `<span class="fx-it-last">${esc((l.me ? "You: " : "") + l.text)}</span>` : ""}
      </span>
    </li>`;
  }
  // Files sent with a Relay or transcript message: taken off the composer,
  // shown on the ghost by name, given back if the send fails.
  function takeFiles(chat) {
    const files = chat.files;
    chat.files = [];
    drawFiles();
    return files;
  }
  const ghostText = (text, files) => X.withFiles(text, files.map((f) => f.path));
  async function sendRelay(chat, text) {
    const ta = $("fxInput");
    const boss = V.waBoss;
    const files = takeFiles(chat);
    const g = ghost(chat, ghostText(text, files), boss ? "to the boss · sending…" : "sending…");
    ta.value = "";
    autosize();
    setEmpty("");
    try {
      await post("/api/relay-chat/say", { text, boss, files: files.map((f) => f.path) });
      setHow(g, boss ? "to the boss · sent" : "sent");
      if (live(chat)) tickRelay(chat);
    } catch (e) {
      dropPending(WA, g);
      giveBack(chat, text, files);
      toast("Not sent: " + e.message, "err");
    }
  }

  /* ---------------------------------------------------------- sending */
  async function send() {
    const chat = V.chat;
    if (!chat) return;
    const key = keyOf(chat);
    if (V.sending.has(key)) return; // one message on its way per chat, even after leaving and coming back
    const ta = $("fxInput");
    const text = ta.value;
    if (chat.source !== "relay" && V.engine === "jan") { askJan(chat, text); return; }
    if (!text.trim() && !chat.files.length) return;
    V.sending.add(key);
    syncSend();
    const mode = ultraOf(chat);
    try {
      if (chat.source === "relay") await sendRelay(chat, text.trim());
      else if (chat.source === "claude") await sendClaude(chat, text, mode);
      else await sendLog(chat, text.trim(), mode);
    } finally {
      V.sending.delete(key);
      syncSend();
    }
  }
  function setUltra(chat, mode) {
    V.ultra[chat.sid] = X.ULTRA.includes(mode) ? mode : "off";
    // only "every message" outlives the page
    store.set("ultra", Object.fromEntries(Object.entries(V.ultra).filter(([, u]) => u === "always")));
    drawComposer();
  }
  const sent = (chat, mode) => setUltra(chat, X.afterSend(mode));
  async function sendClaude(chat, text, mode) {
    const files = chat.files;
    const ta = $("fxInput");
    ta.value = "";
    chat.files = [];
    drawFiles();
    autosize();
    try {
      await post(capi(chat, "send"), { text: X.withUltra(text, mode), files: files.map((f) => f.name) });
      sent(chat, mode);
      chat.follow = true;
      applyMeta(chat, chat.meta, true);
    } catch (e) {
      giveBack(chat, text, files);
      toast("Not sent: " + e.message, "err");
    }
  }
  async function sendLog(chat, text, mode) {
    const s = chat.s;
    const r = routeOf(chat);
    const files = takeFiles(chat);
    const body = { text, files: files.map((f) => f.path), state: s.group, cwd: s.cwd, name: nameOf(s), ultrathink: r.kind === "resume" && mode !== "off" };
    if (r.kind === "resume") {
      const p = V.picks[s.id] || {};
      if (p.model !== undefined && p.model !== null) body.model = p.model;
      if (p.effort !== undefined && p.effort !== null) body.effort = p.effort;
    }
    const ta = $("fxInput");
    const g = ghost(chat, ghostText(text, files), "sending…");
    ta.value = "";
    autosize();
    try {
      const got = await post(`/api/sessions/${encodeURIComponent(s.id)}/say`, body);
      if (r.kind === "resume") sent(chat, mode);
      if (got.via === "board") {
        setHow(g, `board note #${got.id} · arrives at its next step`);
        toast(`Posted as board note #${got.id}`, "ok");
      } else {
        setHow(g, "sent");
        toast(got.via === "resumed" ? "Resumed in the Claude app and sent" : "Sent", "ok");
      }
      if (got.via === "resumed" && got.conversation && live(chat)) {
        V.resumed[s.id] = got.conversation;
        V.mode = "";
        draw();
        A().pollNow();
        return;
      }
      tickLater(chat, 900);
    } catch (e) {
      dropPending(keyOf(chat), g);
      giveBack(chat, text, files);
      toast("Not sent: " + e.message, "err");
    }
  }
  // Jan reads the end of this session's transcript and answers here only.
  function drawJan(chat) {
    chat.view.box.querySelectorAll(".msg.jan, .msg.jan-q").forEach((n) => n.remove());
    for (const item of jan.get(chat.sid) || []) janItem(chat, item);
  }
  function janItem(chat, item) {
    const q = C.el("div", "msg user jan-q");
    q.append(C.el("div", "bubble", item.q), C.el("div", "joined", "asked Jan, not the session"));
    const a = C.el("div", "msg jan");
    const head = C.el("div", "fx-face");
    head.innerHTML = `<span class="fx-ava jan">J</span><span class="fx-tag">Jan${item.model ? ` <span class="fx-muted">· ${esc(item.model)}</span>` : ""}</span>`;
    const b = C.el("div", "bubble");
    b.innerHTML = item.error ? `<p class="bad">${esc(item.error)}</p>` : item.a ? C.markdown(item.a) : '<p class="thinking-dots"><i></i><i></i><i></i></p>';
    a.append(head, b);
    chat.view.box.append(q, a);
  }
  async function askJan(chat, text) {
    if (!text.trim()) return;
    const item = { q: text.trim() };
    const list = jan.get(chat.sid) || [];
    list.push(item);
    jan.set(chat.sid, list);
    $("fxInput").value = "";
    autosize();
    janItem(chat, item);
    setEmpty("");
    scrollDown(true);
    try {
      const got = await post(`/api/sessions/${encodeURIComponent(chat.sid)}/ask-jan`, { text: item.q, agent: "" });
      item.a = got.answer;
      item.model = got.model;
    } catch (e) { item.error = e.message; }
    if (live(chat)) { drawJan(chat); decorate(); scrollDown(true); }
  }

  /* -------------------------------------------------------- attachments */
  async function attach(list) {
    const chat = V.chat;
    if (!chat || !canAttach()) return;
    for (const file of list) {
      try {
        const got = await post(uploadUrl(chat, "files"), { name: file.name || "pasted.png", data: await C.readBase64(file) });
        if (ownUpload(chat)) got.mission = true;
        if (live(chat)) { chat.files.push(got); drawFiles(); }
      } catch (e) { toast(`Could not attach ${file.name}: ${e.message}`, "err"); }
    }
  }
  function onPaste(e) {
    if (!canAttach()) return;
    const dt = e.clipboardData;
    const images = dt ? [...dt.files] : [];
    if (!images.length && dt) [...dt.items].forEach((it) => { const f = it.kind === "file" && it.getAsFile(); if (f) images.push(f); });
    if (images.length) { e.preventDefault(); attach(images); return; }
    const types = dt ? [...dt.types] : [];
    // a paste that holds a picture, or nothing WebKit will say, reads the
    // desktop clipboard; text, HTML or a copied file never brings an old
    // screenshot along
    if (types.includes("text/plain") || (types.length && !types.some((t) => t.startsWith("image/")))) return;
    if (types.length) e.preventDefault();
    // WebKit hands a screenshot over only as a type: the Claude app reads
    // the desktop clipboard itself
    const chat = V.chat;
    post(uploadUrl(chat, "paste-image")).then((f) => { if (ownUpload(chat)) f.mission = true; if (live(chat)) { chat.files.push(f); drawFiles(); } }).catch(() => {});
  }

  /* ------------------------------------------------------------- events */
  // A link in a reply opens in Forge's Browser (through the Claude app, as
  // in its own chats); with the Claude app away, in a new window.
  async function openLink(url) {
    try {
      await post("/api/claude/open-link", { url });
      status("Opened in Forge's Browser.");
    } catch (e) {
      window.open(url, "_blank", "noopener");
    }
  }
  function onClick(e) {
    const a = e.target.closest("#fxLog a[data-url], #fxLog a[href]");
    if (a) {
      const url = a.dataset.url || a.getAttribute("href") || "";
      e.preventDefault();
      if (/^https?:\/\//i.test(url)) openLink(url);
      return;
    }
    const it = e.target.closest("[data-fx-sel]");
    if (it) { pick(it.dataset.fxSel); closePanels(); return; }
    const b = e.target.closest("button");
    if (!b || b.disabled) return;
    const d = b.dataset;
    if (d.fx === "chats") return V.panel === "chats" ? closePanels() : openPanel("chats");
    if (d.fx === "sheet") return V.panel === "sheet" ? closePanels() : openPanel("sheet");
    if (d.fx === "close") return closePanels();
    if (d.fx === "archived") { V.showArchived = !V.showArchived; drawList(); return; }
    if (d.fxSize) { setSize(V.size + Number(d.fxSize)); status(`Text size ${V.size}`); return; }
    if (d.fx === "wa") { closePanels(); return pick(V.sel === WA ? V.back || firstId() : WA); }
    if (d.fxWa) { V.waBoss = d.fxWa === "boss"; store.set("waBoss", V.waBoss); drawComposer(); return; }
    if (d.fx === "back") { closePanels(); A().setView("sessions"); return; }
    if (d.fx === "resume") return resumeHere();
    if (d.fx === "details") { closePanels(); if (V.chat) A().openDrawer(V.chat.sid); return; }
    if (d.fxView) { closePanels(); A().setView(d.fxView); return; }
    if (d.fxEng) { V.engine = d.fxEng; drawComposer(); return; }
    if (d.fxModel !== undefined) return setPick("model", d.fxModel);
    if (d.fxEffort !== undefined) return setPick("effort", d.fxEffort);
    if (d.fxUltra && V.chat) { setUltra(V.chat, d.fxUltra); return; }
    if (d.fxSteps) return setSteps(d.fxSteps);
    if (d.fxUnfile !== undefined && V.chat) { V.chat.files.splice(Number(d.fxUnfile), 1); drawFiles(); }
  }
  function onChange(e) {
    const t = e.target;
    const chat = V.chat;
    if (t.id === "fxTitle" && chat && chat.source === "claude") { saveSettings({ title: t.value.trim() }); return; }
    if (t.name === "fxMode" && chat) { saveSettings({ mode: t.value }); return; }
    if (t.id === "fxReasoning") { setReasoning(t.checked); return; }
    if (t.id === "fxSize") { setSize(t.value); return; }
    if (t.id === "fxSizeN") {
      const n = X.sizeFrom(t.value);
      if (n === null) t.value = V.size; // emptied or not a number: the text stays put
      else { setSize(n); t.value = V.size; }
    }
  }
  function onInput(e) {
    const t = e.target;
    if (t.id === "fxSize") setSize(t.value);
    if (t.id === "fxSizeN") {
      // while typing, only a whole size in range applies ("2" on the way to "22" does not)
      const n = X.sizeFrom(t.value);
      if (n !== null && Number(t.value) >= X.SIZE.min && Number(t.value) <= X.SIZE.max) setSize(n);
    }
  }
  // Keys work only while this view is open; Esc closes the nearest thing.
  window.addEventListener("keydown", (e) => {
    if (!isOn() || document.querySelector("dialog[open]")) return;
    if (e.key === "Escape" && (isPopOpen() || V.panel)) {
      if (isPopOpen()) { closePop(); $("fxChip").focus(); } else { closePanels(); if (!$("fxForm").hidden) $("fxInput").focus(); }
      e.preventDefault();
      e.stopPropagation();
      return;
    }
    if ((e.ctrlKey || e.metaKey) && !e.altKey && (e.key === "k" || e.key === "K")) {
      e.preventDefault();
      if (V.panel === "chats") closePanels(); else openPanel("chats");
      return;
    }
    if (e.altKey && !e.ctrlKey && (e.key === "ArrowUp" || e.key === "ArrowDown")) {
      e.preventDefault();
      step(e.key === "ArrowDown" ? 1 : -1);
      return;
    }
    const it = e.target.closest && e.target.closest("[data-fx-sel]");
    if (it && (e.key === "Enter" || e.key === " ")) { e.preventDefault(); pick(it.dataset.fxSel); closePanels(); }
  }, true);
  document.addEventListener("pointerdown", (e) => {
    if (isPopOpen() && !$("fxPop").contains(e.target) && !$("fxChip").contains(e.target)) closePop();
  });
  const wake = () => {
    const chat = V.chat;
    if (!chat || !shownPage()) return;
    if (chat.source === "log") tickLater(chat, 0);
    else if (chat.source === "relay") relaySoon(chat, 0);
  };
  document.addEventListener("forge-visible", wake);
  document.addEventListener("visibilitychange", wake);

  window.MissionConvos = {
    draw,
    shown() { V.mode = ""; draw(); },
    left() { close(); closePanels(); if ($("fxLog")) $("fxLog").replaceChildren(); },
    select(id) { pick(id); },
    get selected() { return V.sel; },
    get current() { return V.chat; },
  };
})();
