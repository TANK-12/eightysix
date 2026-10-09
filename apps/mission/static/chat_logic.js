/* The Conversations view's logic that needs no DOM: the order of the chats,
   where a reply goes, the model cards and effort gauge, ultrathink, the
   "steps" summary and the text size. Loaded by the page as a plain script
   (window.MissionChatLogic) and by node --test as a CommonJS module. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.MissionChatLogic = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* Claude Code's --effort levels, weakest first. The Claude app's
     runner.EFFORTS names them; "" there means Claude Code's own default. */
  const EFFORTS = ["low", "medium", "high", "xhigh", "max"];

  /* How each model family looks on its card. The models themselves come
     from the Claude app's registry (runner.MODELS through /api/options), so
     a new model shows up without a change here; this only adds a line of
     words and a colour, and anything unknown gets the plain look. */
  const FAMILIES = {
    opus: { blurb: "Strongest. Most work runs here.", hue: "#c9a2ff" },
    fable: { blurb: "Big model, an alternative to Opus.", hue: "#ffcf7a" },
    sonnet: { blurb: "Quicker, for plain tasks.", hue: "#8fd3ff" },
    haiku: { blurb: "Fastest and lightest. No Ultracode.", hue: "#7ee0b0" },
    "": { blurb: "Whatever Claude Code picks.", hue: "#b8c0d8" },
  };

  const SIZE = { min: 14, max: 28, start: 19 };
  const GROUP_RANK = { needs_you: 0, working: 1, idle: 2, ended: 3 };

  function family(id) {
    const m = /(opus|sonnet|haiku|fable)/i.exec(String(id || ""));
    return m ? m[1].toLowerCase() : "";
  }

  /* The Chats list in sections, the same as Mission's session grid: needs
     you, working, idle, archived (ended, or idle 30+ minutes). Within a
     section the order is the one given: app.js hands over its calm order
     (newest activity first, re-sorted at most once a minute), so a row does
     not jump while it is being read. A find box narrows it first.
     -> [{section, label, items}], empty sections left out. */
  const SECTIONS = [["needs_you", "Needs you"], ["working", "Working"], ["idle", "Idle"], ["archived", "Archived"]];
  const sectionOf = (s) => s.section || (s.group === "ended" ? "archived" : s.group) || "idle";
  function chatSections(sessions, find) {
    const q = String(find || "").trim().toLowerCase();
    const relay = (s) => (s.relay ? ["#" + s.relay.task, s.relay.title] : []);
    const hit = (s) => !q || [s.label, s.name, s.title, s.action, s.place, s.cwd, ...relay(s)].some((x) => String(x || "").toLowerCase().includes(q));
    const list = (sessions || []).filter(hit);
    const known = SECTIONS.map(([k]) => k);
    return SECTIONS.map(([section, label]) => ({
      section,
      label,
      items: list.filter((s) => (known.includes(sectionOf(s)) ? sectionOf(s) : "idle") === section),
    })).filter((g) => g.items.length);
  }
  /* The chats in list order, for Alt+Up / Alt+Down and the first pick. */
  function chatOrder(sessions, find) {
    return chatSections(sessions, find).flatMap((g) => g.items);
  }

  /* The chat after (step 1) or before (step -1) the open one, wrapping. */
  function neighbour(order, id, step) {
    if (!order.length) return "";
    const i = order.findIndex((s) => s.id === id);
    if (i < 0) return order[0].id;
    return order[(i + step + order.length) % order.length].id;
  }

  /* Where a reply goes, in plain words, and whether model and effort can
     be picked for it. conv: the Claude app chat the session runs in (or was
     resumed into from here), "" when none. */
  function route(s, conv) {
    if (!s) return { kind: "none", pick: false, text: "" };
    if (conv) return { kind: "claude", pick: true, text: "Goes straight into its Claude app chat." };
    if (s.group === "ended") return { kind: "resume", pick: true, text: "Ended. Sending resumes it in the Claude app with these picks." };
    return { kind: "board", pick: false, text: "Runs in a terminal or Relay, so this arrives as a board note at its next step. It keeps its own model and effort." };
  }

  /* The model cards, in the registry's order with the default first. Two
     cards of one family say how they differ: a pinned version ("Sonnet
     5.5") stays on it, the plain alias ("sonnet") always takes the newest. */
  function modelCards(models, current) {
    const entries = Object.entries(models || {});
    if (!entries.some(([id]) => id === "")) entries.unshift(["", "Claude Code's default"]);
    entries.sort((a, b) => (a[0] === "" ? -1 : b[0] === "" ? 1 : 0));
    const fams = entries.map(([id]) => family(id));
    return entries.map(([id, label], i) => {
      const fam = fams[i];
      const look = id === "" ? FAMILIES[""] : FAMILIES[fam] || { blurb: "", hue: FAMILIES[""].hue };
      const twin = !!fam && fams.filter((f) => f === fam).length > 1;
      const name = String(label).replace(/\s*\(.*\)$/, "");
      const blurb = !twin ? look.blurb : /\d/.test(id) ? `Stays on ${name}. ${look.blurb}` : `Always the newest one. ${look.blurb}`;
      return { id, label: id === "" ? "Default" : String(label), family: id === "" ? "default" : fam || "other", blurb, hue: look.hue, on: id === (current || "") };
    });
  }

  /* The effort gauge: the known levels weakest first, each lit up to the
     current one; anything else the registry offers comes after them. */
  function effortSteps(efforts, current) {
    const have = Object.keys(efforts || {});
    const known = EFFORTS.filter((e) => have.includes(e));
    const extra = have.filter((e) => e && !EFFORTS.includes(e));
    const order = known.concat(extra);
    const at = order.indexOf(current || "");
    return order.map((id, i) => ({ id, label: String((efforts || {})[id] || id), level: i + 1, on: i === at, lit: at >= 0 && i <= at }));
  }

  function effortLabel(efforts, id) {
    if (!id) return "Default effort";
    return String((efforts || {})[id] || id);
  }

  /* The chip under the composer: "Opus · Max". */
  function chipText(models, efforts, model, effort) {
    const m = model ? String((models || {})[model] || model) : "Default model";
    return `${m} · ${effortLabel(efforts, effort)}`;
  }

  /* Ultrathink: "off", "next" (this message only) or "always". */
  const ULTRA = ["off", "next", "always"];
  function withUltra(text, mode) {
    const t = String(text || "");
    if (mode !== "next" && mode !== "always") return t;
    if (/\bultrathink\b/i.test(t)) return t;
    return `ultrathink. ${t}`;
  }
  const afterSend = (mode) => (mode === "next" ? "off" : ULTRA.includes(mode) ? mode : "off");
  const toggleUltra = (mode) => (mode === "off" || !ULTRA.includes(mode) ? "next" : "off");

  /* A tool card's name as shown: "⚙ Bash" -> "Bash", browser tools keep
     "Browser: open". */
  function stepName(raw) {
    return String(raw || "").replace(/^[^A-Za-z]+/, "").trim() || "step";
  }

  /* One line for a run of steps (tool calls and kept reasoning):
     [{name, state: running|done|failed, brief, think}] ->
     {count, names, state, now, failed}. Names are counted, most used first,
     at most `top` of them. */
  function stepsSummary(list, top = 4) {
    const items = list || [];
    const tools = items.filter((x) => !x.think);
    const counts = new Map();
    for (const x of tools) counts.set(x.name, (counts.get(x.name) || 0) + 1);
    const ranked = [...counts.entries()].sort((a, b) => b[1] - a[1]);
    let names = ranked.slice(0, top).map(([n, c]) => (c > 1 ? `${n} ×${c}` : n)).join(" · ");
    if (ranked.length > top) names += ` · +${ranked.length - top} more`;
    const thoughts = items.length - tools.length;
    if (thoughts) names = names ? `${names} · ${thoughts === 1 ? "a thought" : thoughts + " thoughts"}` : thoughts === 1 ? "a thought" : `${thoughts} thoughts`;
    const running = tools.filter((x) => x.state === "running");
    const failed = tools.filter((x) => x.state === "failed").length;
    const state = running.length ? "running" : failed ? "failed" : "done";
    const now = running.length ? `${running[running.length - 1].name}${running[running.length - 1].brief ? ": " + running[running.length - 1].brief : ""}` : "";
    const count = tools.length;
    const label = count ? `${count} ${count === 1 ? "step" : "steps"}` : thoughts === 1 ? "Thinking" : "Thoughts";
    return { count, label, names, state, now, failed };
  }

  function clampSize(n) {
    const v = Math.round(Number(n));
    if (!isFinite(v)) return SIZE.start;
    return Math.max(SIZE.min, Math.min(SIZE.max, v));
  }
  /* What the text-size box holds, as a size; null while it holds nothing
     usable (emptied to type a new number, "-", 0), so the text stays put. */
  function sizeFrom(raw) {
    const t = String(raw ?? "").trim();
    if (!/^\d+(\.\d+)?$/.test(t) || Number(t) < 1) return null;
    return clampSize(t);
  }

  /* How long a turn took, in words: "took 18 min". No dollars: the Claude
     app's figure is API list price, not what Emerson pays. */
  function tookWords(ms) {
    const s = Math.round(Number(ms) / 1000);
    if (!isFinite(s) || s < 1) return "";
    if (s < 60) return `took ${s} s`;
    const m = Math.round(s / 60);
    if (m < 60) return `took ${m} min`;
    const h = Math.floor(m / 60);
    return `took ${h} h${m % 60 ? ` ${m % 60} min` : ""}`;
  }

  /* Words Claude says on the way (between steps of one turn) are folded
     into the steps bar when no longer than this; the turn's answer and
     longer notes stay as messages. */
  const ASIDE_MAX = 320;
  const isAside = (text) => { const t = String(text || "").trim(); return !!t && t.length <= ASIDE_MAX; };

  /* A line shown as "sending…" until the chat has it: matched with spaces
     and line breaks squashed (Relay keeps one blank line at most). */
  const squash = (t) => String(t ?? "").replace(/\s+/g, " ").trim();
  function sameLine(sent, got) {
    const a = squash(sent).slice(0, 60);
    return !!a && squash(got).includes(a);
  }
  /* A message with files, as the session gets it (shared/forge_attach.py
     with_note): the text, then "Attached files:" and one "- /path" each. */
  function withFiles(text, paths) {
    const t = String(text ?? "").trim();
    const list = (paths || []).filter(Boolean);
    if (!list.length) return t;
    const note = "Attached files:\n" + list.map((p) => `- ${p}`).join("\n");
    return t ? `${t}\n\n${note}` : note;
  }

  /* The WhatsApp chat with Relay (Emerson's note 1295). Relay's lines use
     WhatsApp's own marks: *bold*, _italic_, ~struck~, `code`, ```a block```;
     links become links and line breaks stay. Everything else is escaped, so
     a line can add no markup of its own. */
  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const escHtml = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ESC[c]);
  const URL_RE = /https?:\/\/[^\s<>"'`]*[^\s<>"'`.,;:!?)\]]/g;
  const mark = (ch) => new RegExp(`(^|[\\s(])\\${ch}([^\\s${ch}](?:[^${ch}\\n]*[^\\s${ch}])?)\\${ch}(?=$|[\\s).,;:!?])`, "g");
  const MARKS = [[mark("*"), "b"], [mark("_"), "i"], [mark("~"), "s"]];
  function waMarks(safe) {
    let s = safe.replace(/`([^`\n]+)`/g, "<code>$1</code>");
    for (const [re, tag] of MARKS) s = s.replace(re, `$1<${tag}>$2</${tag}>`);
    return s;
  }
  function waInline(raw) {
    let out = "";
    let at = 0;
    for (const m of raw.matchAll(URL_RE)) {
      const url = escHtml(m[0]);
      out += waMarks(escHtml(raw.slice(at, m.index))) + `<a href="${url}" target="_blank" rel="noopener">${url}</a>`;
      at = m.index + m[0].length;
    }
    return out + waMarks(escHtml(raw.slice(at)));
  }
  function waText(text) {
    const parts = String(text ?? "").split("```");
    if (parts.length % 2 === 0) parts.push(parts.splice(-2).join("```")); // a fence never closed is text
    return parts.map((p, i) => (i % 2 ? `<code class="wa-mono">${escHtml(p.replace(/^\n|\n$/g, ""))}</code>` : waInline(p))).join("").replace(/\n/g, "<br>");
  }
  const WHO = { emerson: "me", relay: "relay", boss: "boss", jan: "jan", local: "local" };
  const waWho = (who) => WHO[String(who || "").trim().toLowerCase()] || "relay";
  const WEEK = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const DAYS = { Mon: "Monday", Tue: "Tuesday", Wed: "Wednesday", Thu: "Thursday", Fri: "Friday", Sat: "Saturday", Sun: "Sunday" };
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const splitAt = (at) => { const m = /^(\w{3}) (\d{1,2}):(\d{2})$/.exec(String(at || "")); return m && WEEK.includes(m[1]) ? [m[1], `${m[2]}:${m[3]}`, Number(m[2]) * 60 + Number(m[3])] : ["", "", 0]; };
  const midnight = (d) => new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const daysBefore = (d, n) => new Date(d.getFullYear(), d.getMonth(), d.getDate() - n);
  /* Relay stamps a line with a weekday and a time only ("Thu 11:52"), so
     each line's date is worked out backwards from now: the newest line is
     on the latest such weekday up to today; going back, a line on another
     weekday, or later in the day than the line after it on the same
     weekday, is on the latest such day before that one. -> [Date|null] */
  function waDates(list, now) {
    const out = list.map(() => null);
    let cur = null;
    let curMin = 0;
    for (let i = list.length - 1; i >= 0; i--) {
      const [day, , mins] = splitAt(list[i].at);
      if (!day) continue;
      const wd = WEEK.indexOf(day);
      if (!cur) {
        const back = (now.getDay() - wd + 7) % 7;
        cur = daysBefore(midnight(now), back || (mins > now.getHours() * 60 + now.getMinutes() + 1 ? 7 : 0));
      }
      else {
        const back = (cur.getDay() - wd + 7) % 7;
        cur = daysBefore(cur, back || (mins > curMin ? 7 : 0));
      }
      curMin = mins;
      out[i] = cur;
    }
    return out;
  }
  function dayWords(date, now) {
    const back = Math.round((midnight(now) - date) / 86400000);
    if (back === 0) return "Today";
    if (back === 1) return "Yesterday";
    if (back > 1 && back < 7) return DAYS[WEEK[date.getDay()]];
    return `${DAYS[WEEK[date.getDay()]]} ${date.getDate()} ${MONTHS[date.getMonth()]}`;
  }
  /* The chat's lines laid out: `first` starts a run of one speaker (the
     portrait and name go there), `day` names a new day (a chip above it:
     Today, Yesterday, a weekday this week, else "Thursday 1 Oct"), `time`
     is the clock part, and Emerson's last line is marked "sent" (Relay's
     chat has not read it yet) or "read". now: a Date (default: now). */
  function waRuns(messages, now) {
    const list = messages || [];
    const at = now instanceof Date ? now : new Date(now ?? Date.now());
    const dates = waDates(list, at);
    let mine = -1;
    list.forEach((m, i) => { if (m.me) mine = i; });
    let lastDay = 0;
    return list.map((m, i) => {
      const time = splitAt(m.at)[1];
      const kind = waWho(m.who);
      const d = dates[i];
      const newDay = !!d && d.getTime() !== lastDay;
      if (d) lastDay = d.getTime();
      const prev = list[i - 1];
      return Object.assign({}, m, {
        kind,
        time,
        first: !prev || newDay || waWho(prev.who) !== kind,
        day: newDay ? dayWords(d, at) : "",
        mark: i === mine ? (m.new ? "sent" : "read") : "",
      });
    });
  }

  return { EFFORTS, FAMILIES, SIZE, GROUP_RANK, ULTRA, ASIDE_MAX, SECTIONS, family, chatSections, chatOrder, neighbour, route, modelCards, effortSteps, effortLabel, chipText, withUltra, afterSend, toggleUltra, stepName, stepsSummary, clampSize, sizeFrom, tookWords, isAside, sameLine, withFiles, waText, waWho, waRuns };
});
