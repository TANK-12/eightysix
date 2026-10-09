/* Mission Control's Swarm view: every live agent at once, who is doing what.
   One lane per commander with its helpers beside it, a lane for Relay runs
   and one for sessions on their own. A tile shows the agent, its model and
   effort, what it is doing right now, its last few steps and how full its
   context is. Click a tile for its chat. Drawn from the same poll as every
   other view (MissionApp.data); nothing extra is fetched. */
(function () {
  "use strict";
  const $ = (id) => document.getElementById(id);
  const A = () => window.MissionApp;
  const L = window.MissionLogic;
  const EFFORTS = ["low", "medium", "high", "xhigh", "max"];
  let showDone = false;

  function pips(effort) {
    const n = EFFORTS.indexOf(effort) + 1;
    if (!n) return "";
    return `<span class="sw-pips" title="effort ${A().esc(effort)}">${EFFORTS.map((_, i) => `<i class="${i < n ? "lit" : ""}"></i>`).join("")}</span>`;
  }
  function ctx(used, window_) {
    if (!used) return "";
    const p = Math.round(L.pct(used, window_ || 200000));
    return `<div class="sw-ctx" title="Context: ${L.tokens(used)} of ${L.tokens(window_)}"><span class="sw-bar"><i class="${p >= 92 ? "bad" : p >= 70 ? "warn" : ""}" style="width:${Math.min(100, p)}%"></i></span><span>${p}%</span></div>`;
  }
  function tile(o) {
    const esc = A().esc;
    const feed = (o.feed || []).filter((f) => f.text !== o.now).slice(-2).reverse();
    return `<button type="button" class="sw-tile ${esc(o.state)} ${o.small ? "small" : ""}" data-open="${esc(o.session)}" ${o.agent ? `data-agent="${esc(o.agent)}"` : ""} title="Open the chat">
      <div class="sw-top">
        ${A().avatar(o.kind, o.key, o.type || "", o.name, o.small ? "small" : "", o.state)}
        <div class="sw-who"><span class="sw-name">${esc(o.name)}</span><span class="sw-sub">${esc(o.sub || "")}</span></div>
        <span class="sw-dot ${esc(o.state)}" title="${esc(o.stateText)}"></span>
      </div>
      <div class="sw-model">${o.model ? `<span class="m-model ${esc(o.family || "")}"><i class="fam ${esc(o.family || "")}"></i>${esc(L.modelName(o.model))}</span>` : ""}${pips(o.effort)}</div>
      <div class="sw-now">${esc(o.now || "…")}</div>
      ${feed.length ? `<ol class="sw-feed">${feed.map((f) => `<li>${esc(f.text)}</li>`).join("")}</ol>` : ""}
      ${ctx(o.context, o.window)}
    </button>`;
  }
  const STATE_TEXT = { working: "Working", needs_you: "Needs you", idle: "Idle", ended: "Ended" };
  function sessionTile(s) {
    return tile({
      kind: "session", key: s.name || s.id, session: s.id, name: L.displayName(s),
      sub: s.relay ? `Relay #${s.relay.task}` : s.name, state: s.group, stateText: STATE_TEXT[s.group],
      model: s.model, family: s.family, effort: s.effort, now: s.action, feed: s.feed, context: s.context, window: s.window,
    });
  }
  function helperTile(s, h) {
    const st = h.state === "working" ? "working" : "ended";
    return tile({
      kind: "helper", key: h.id, type: h.type, session: s.id, agent: h.id, small: true,
      name: L.helperName(h), sub: h.task,
      state: st, stateText: st === "working" ? "Working" : "Done",
      model: h.model, family: h.family, effort: h.effort, now: st === "working" ? h.action || h.task : h.task, feed: h.feed, context: h.context, window: h.window,
    });
  }
  function lane(title, sub, cls, body) {
    return `<section class="sw-lane ${cls}"><div class="sw-lane-head"><h3>${title}</h3><span class="muted small">${sub}</span></div><div class="sw-row">${body}</div></section>`;
  }

  function draw() {
    const box = $("swarm");
    if (!box || !$("view-swarm").classList.contains("on") || !A() || !A().data) return;
    const esc = A().esc;
    const d = A().data;
    const live = d.sessions.filter((s) => s.group !== "ended");
    const lanes = [];
    let agents = 0;
    let busy = 0;
    // Commanders: a session with helpers at work (or any helpers, while
    // finished ones are shown) leads its own lane.
    const led = live.filter((s) => (s.helpers || []).some((h) => showDone || h.state === "working"));
    for (const s of led) {
      const hs = s.helpers.filter((h) => showDone || h.state === "working");
      const done = s.helpers.length - s.helpers.filter((h) => h.state === "working").length;
      agents += 1 + hs.length;
      busy += (s.group === "working" ? 1 : 0) + hs.filter((h) => h.state === "working").length;
      const crew = (s.crews || []).find((c) => c.commander);
      lanes.push(lane(
        `${esc(s.label || s.name)}'s ${crew ? `crew <span class="sw-crew">${esc(crew.crew)}</span>` : "helpers"}`,
        `${hs.filter((h) => h.state === "working").length} working${done ? ` · ${done} done${showDone ? "" : " (hidden)"}` : ""}`,
        "led",
        `<div class="sw-lead">${sessionTile(s)}</div><div class="sw-helpers">${hs.map((h) => helperTile(s, h)).join("") || '<span class="muted small">No helper working right now.</span>'}</div>`,
      ));
    }
    const relay = live.filter((s) => !led.includes(s) && s.relay);
    const solo = live.filter((s) => !led.includes(s) && !s.relay);
    for (const [list, title, sub, cls] of [
      [relay, "Relay runs", "Sessions Relay started, one per task", "relay"],
      [solo, "On their own", "Terminal and Claude app sessions", "solo"],
    ]) {
      if (!list.length) continue;
      agents += list.length;
      busy += list.filter((s) => s.group === "working").length;
      lanes.push(lane(title, `${list.length} · ${sub}`, cls, list.map(sessionTile).join("")));
    }
    const head = `<div class="sw-sum"><span><b>${agents}</b> agents live</span><span><b>${busy}</b> working now</span>
      <label class="switch"><input type="checkbox" id="swDone" ${showDone ? "checked" : ""}><span class="track"><span class="knob"></span></span><span>Show finished helpers</span></label></div>`;
    const html = head + (lanes.join("") || '<div class="muted">Nobody is running right now.</div>');
    if (box._html !== html) { box.innerHTML = html; box._html = html; }
  }
  document.addEventListener("change", (e) => {
    if (e.target.id === "swDone") { showDone = e.target.checked; draw(); }
  });
  window.MissionSwarm = { draw };
})();
