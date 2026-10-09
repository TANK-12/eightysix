/* Mission Control's Messages view: every note Emerson sent from here (Note
   to everyone, or Message to one session) with the answers that came back,
   one thread per message and a line per session. The server gathers the
   answers (mc/replies.py): board replies (crew ack --note) and replies the
   session wrote in its own chat after the note was handed over.

   Reads /api/messages while the view is open, and now and then in the
   background so the nav badge can count answers not seen yet. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const A = () => window.MissionApp;
  const L = window.MissionLogic;
  const SEEN_KEY = "mission.messages.seen";
  const OPEN_MS = 8000;
  const AWAY_MS = 60000;
  let list = null;
  let error = "";
  let busy = false;
  let timer = 0;
  let seenAt = Number(localStorage.getItem(SEEN_KEY) || 0);

  const isOn = () => $("view-messages").classList.contains("on");
  const shownPage = () => (window.ForgeIdle ? window.ForgeIdle.shown() : document.visibilityState !== "hidden");
  const secs = (at) => (typeof at === "number" ? at : Date.parse(at) / 1000 || 0);

  async function load() {
    if (busy) return;
    busy = true;
    try {
      const r = await fetch("/api/messages", { cache: "no-store" });
      if (!r.ok) throw new Error(r.statusText || "No answer");
      list = (await r.json()).messages || [];
      error = "";
    } catch (e) {
      error = e.message;
    } finally {
      busy = false;
    }
    if (isOn()) markSeen();
    draw();
    badge();
  }
  function tick() {
    clearTimeout(timer);
    if (shownPage()) load();
    timer = setTimeout(tick, isOn() ? OPEN_MS : AWAY_MS);
  }
  function markSeen() {
    seenAt = Date.now() / 1000;
    try { localStorage.setItem(SEEN_KEY, String(seenAt)); } catch (e) { /* private mode */ }
  }
  function badge() {
    const nav = document.querySelector('.views [data-view="messages"]');
    if (!nav) return;
    let n = 0;
    for (const m of list || []) for (const r of m.replies) if (secs(r.at) > seenAt) n += 1;
    let b = nav.querySelector(".n-badge");
    if (!n) { if (b) b.remove(); return; }
    if (!b) { b = document.createElement("span"); b.className = "n-badge"; nav.appendChild(b); }
    b.textContent = n > 99 ? "99+" : String(n);
    b.title = `${n} new answer${n === 1 ? "" : "s"}`;
  }

  function who(name) {
    const d = A().data;
    const s = d && d.sessions.find((x) => x.name === name);
    return { s, label: (s && (s.label || s.name)) || name };
  }
  function reply(r) {
    const esc = A().esc;
    const { s, label } = who(r.from);
    const at = secs(r.at);
    const via = r.via === "board" ? `on the board${r.note ? ` · #${r.note}` : ""}` : "in its chat";
    return `<div class="m-reply">
      ${A().avatar("session", r.from, "", label, "", s ? s.group : "ended")}
      <div class="m-r-body">
        <div class="m-r-top">
          <span class="m-r-name">${esc(label)}</span>
          <span class="m-via ${r.via === "board" ? "board" : "inchat"}">${esc(via)}</span>
          ${at ? `<span class="m-when" data-at="${at}">${esc(L.ago(A().nowS() - at))}</span>` : ""}
          <span class="spacer"></span>
          ${r.session ? `<button type="button" class="ghost mini" data-open="${esc(r.session)}">Open chat</button>` : ""}
        </div>
        <div class="m-r-text fc"><div class="bubble">${window.ForgeConvo.markdown(String(r.text || ""))}</div></div>
      </div>
    </div>`;
  }
  function thread(m) {
    const esc = A().esc;
    const total = m.replies.length + m.seen.length + m.waiting.length;
    const to = m.kind === "all" ? "To everyone" : `To ${who(m.to).label}`;
    const chips = [
      ...m.seen.map((n) => `<span class="m-chip seen" title="Marked it seen, no answer yet">${esc(who(n).label)} · saw it</span>`),
      ...m.waiting.map((n) => `<span class="m-chip waiting" title="Not picked up yet">${esc(who(n).label)} · waiting</span>`),
    ];
    return `<article class="m-thread" id="msg-${esc(m.crew)}-${esc(m.id)}">
      <div class="m-head">
        <span class="m-to">${A().icon("msg")}${esc(to)}</span>
        <span class="m-when" data-at="${m.at}">${esc(L.ago(A().nowS() - m.at))}</span>
        <span class="spacer"></span>
        <span class="m-count ${m.replies.length ? "some" : ""}">${m.replies.length} of ${total || m.replies.length || 1} answered</span>
      </div>
      <div class="m-ask">${esc(m.text)}</div>
      ${m.replies.length ? `<div class="m-replies">${m.replies.map(reply).join("")}</div>` : '<div class="m-none">No answers yet. Each session sees the note at its next step.</div>'}
      ${chips.length ? `<div class="m-chips">${chips.join("")}</div>` : ""}
    </article>`;
  }
  function draw() {
    const box = $("messages");
    if (!box || !isOn() || !A() || !A().data) return;
    let html;
    if (!list) html = error ? `<div class="muted">${A().esc(error)}</div>` : '<div class="skel"></div>';
    else if (!list.length) {
      html = `<div class="empty"><div class="e-art">${A().icon("msg")}</div><h3>Nothing asked yet</h3>
        <p>Ask everyone something, or Message one session. Their answers gather here, one thread per message.</p>
        <button type="button" class="btn btn-primary" data-ask-all>Ask everyone</button></div>`;
    } else html = list.map(thread).join("");
    if (box._html !== html) { box.innerHTML = html; box._html = html; }
  }

  window.MissionMessages = {
    shown() { markSeen(); badge(); draw(); tick(); },
    draw,
    refresh: load,
  };
  document.addEventListener("visibilitychange", () => { if (shownPage() && isOn()) tick(); });
  // First look once the page has its data, then on the timer.
  const boot = setInterval(() => { if (A() && A().data) { clearInterval(boot); tick(); } }, 300);
})();
