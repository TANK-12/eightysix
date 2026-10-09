/* Mission Control's page logic that needs no DOM: filters, grouping, the
   poll backoff and formatting. Loaded by the page as a plain script
   (window.MissionLogic) and by node --test as a CommonJS module. */
(function (root, factory) {
  const isNode = typeof module === "object" && module.exports;
  const api = factory(isNode ? require("../../../shared/forge_session_title.js") : root.ForgeSessionTitle);
  if (isNode) module.exports = api;
  else root.MissionLogic = api;
})(typeof self !== "undefined" ? self : this, function (Title) {
  "use strict";

  const FILTERS = ["all", "needs_you", "working", "unread", "idle", "archived"];

  /* Sections on the page (Emerson, 2026-10-08). Needs you stays on top;
     a session that ended, or sat idle for ARCHIVE_S seconds, goes to
     Archived, where it stays readable. A working session never archives:
     a long tool call writes nothing until it ends. app.js sets s.section on
     each poll; a row without one (tests, old data) falls back to its group. */
  const ARCHIVE_S = 1800;
  function section(s, now) {
    if (s.group === "needs_you" || s.group === "working") return s.group;
    if (s.group === "ended" || now - (s.last_active || 0) >= ARCHIVE_S) return "archived";
    return s.group;
  }
  const sectionOf = (s) => s.section || (s.group === "ended" ? "archived" : s.group);

  /* Unread: a session that stopped working (finished a turn, waits on
     Emerson, or ended) after Emerson last looked at it. One still working
     is not unread yet: there is nothing finished to read.
     seen: {session id: epoch seconds}. A session the page never saw before
     is marked read on first sight, so a fresh page is not all unread. */
  function isUnread(s, seen) {
    const at = seen[s.id];
    return s.group !== "working" && at !== undefined && (s.last_active || 0) > at + 1;
  }

  function matches(s, filter, seen, place) {
    if (place && s.place !== place) return false;
    switch (filter) {
      case "needs_you":
      case "working":
      case "idle":
      case "archived":
        return sectionOf(s) === filter;
      case "unread": return isUnread(s, seen);
      default: return true;
    }
  }

  function counts(sessions, seen) {
    const c = { all: 0, needs_you: 0, working: 0, unread: 0, idle: 0, archived: 0 };
    for (const s of sessions) {
      c.all++;
      if (c[sectionOf(s)] !== undefined) c[sectionOf(s)]++;
      if (isUnread(s, seen)) c.unread++;
    }
    return c;
  }

  /* Folder -> sessions in it, busiest first. */
  function places(sessions) {
    const map = new Map();
    for (const s of sessions) {
      const key = s.place || "?";
      const p = map.get(key) || { place: key, cwd: s.cwd, total: 0, live: 0 };
      p.total++;
      if (s.group !== "ended") p.live++;
      map.set(key, p);
    }
    return [...map.values()].sort((a, b) => b.live - a.live || b.total - a.total || a.place.localeCompare(b.place));
  }

  /* Next poll delay: back to `min` after a change, else stretch by 1.6x up
     to `max`. Seconds in, seconds out. */
  function nextDelay(current, changed, min, max) {
    if (changed) return min;
    return Math.min(max, Math.max(min, current * 1.6));
  }

  function ago(seconds) {
    if (!(seconds >= 0) || !isFinite(seconds)) return "";
    if (seconds < 45) return "just now";
    if (seconds < 3600) return Math.round(seconds / 60) + "m ago";
    if (seconds < 86400) return Math.round(seconds / 3600) + "h ago";
    return Math.round(seconds / 86400) + "d ago";
  }

  function tokens(n) {
    n = Number(n) || 0;
    if (n >= 1e6) return (n / 1e6).toFixed(n >= 1e7 ? 0 : 1) + "M";
    if (n >= 1000) return Math.round(n / 1000) + "k";
    return String(n);
  }

  /* "claude-opus-5-5" -> "Opus 5.5"; unknown ids come back unchanged. */
  function modelName(id) {
    if (!id) return "";
    const m = /(opus|sonnet|haiku|fable)[-_]?(\d+)(?:[-_.](\d+))?/i.exec(id);
    if (!m) return id;
    const fam = m[1][0].toUpperCase() + m[1].slice(1).toLowerCase();
    return fam + " " + m[2] + (m[3] && m[3].length <= 2 ? "." + m[3] : "");
  }

  function pct(context, windowSize) {
    if (!windowSize) return 0;
    return Math.max(0, Math.min(100, Math.round((100 * (context || 0)) / windowSize)));
  }

  /* Crew Room sprite name for a session or helper (packs/crewroom-characters). */
  function hash(text) {
    let h = 2166136261;
    for (const ch of String(text)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    return h >>> 0;
  }
  const HELPER_KIND = { "crew-light": "light", "crew-worker": "worker", "crew-deep": "deep" };
  function spriteFor(kind, key, type) {
    if (kind === "helper") return "helper_" + (HELPER_KIND[type] || "other") + "_" + "abc"[hash(key) % 3] + "_idle";
    if (kind === "model") return "jan_" + "abc"[hash(key) % 3] + "_idle";
    return "person" + (1 + (hash(key) % 8)) + "_idle";
  }

  /* Calm order by recent activity (Emerson, 2026-10-08: the cards swapped
     places too often, then: newest activity first). Each section (needs you,
     working, idle, archived) is sorted by last activity, but the times used
     are frozen and refreshed at most every RESORT_S seconds, so busy
     sessions do not trade places on every poll. A session that first shows
     up or changes section takes its current time, which usually puts it on
     top of its new section straight away. memo ({at, sortedAt}) carries the
     frozen times from one poll to the next; a new array is returned. */
  const SECTION_RANK = { needs_you: 0, working: 1, idle: 2, archived: 3 };
  const RESORT_S = 60;
  function calmOrder(sessions, memo, now) {
    const fresh = !(now - memo.sortedAt < RESORT_S);
    if (fresh) memo.sortedAt = now;
    const at = {};
    for (const s of sessions) {
      const sec = sectionOf(s);
      const was = memo.at[s.id];
      at[s.id] = !fresh && was && was.section === sec ? was : { section: sec, key: s.last_active || 0 };
    }
    memo.at = at;
    const rank = (s) => SECTION_RANK[at[s.id].section] ?? 9;
    return sessions.slice().sort((a, b) => rank(a) - rank(b) || at[b.id].key - at[a.id].key);
  }

  /* Plain names (Emerson, 2026-10-08): one rule for every page, in
     shared/forge_session_title.js. */
  const { shortTitle, displayName, personaTag } = Title;

  /* Gentle leaving (Emerson, 2026-10-08): a session that drops out of the
     backend's list stays on the page, marked ended (gone: true), for `secs`
     seconds, and for as long as `keep` (a Set of the ids open in the drawer
     or Conversations) holds it, so nothing he is reading is pulled away.
     memo: {last: {id: row}, gone: {id: {row, at}}}. Returns rows plus the
     lingering ones. lingerDue says whether one is due to leave, so a poll
     that brought nothing new still lets it go. */
  function linger(rows, memo, now, keep, secs) {
    const live = {};
    for (const s of rows) live[s.id] = s;
    for (const id in memo.last) if (!live[id] && !memo.gone[id]) memo.gone[id] = { row: { ...memo.last[id], group: "ended", gone: true }, at: now };
    for (const id in memo.gone) if (live[id] || (now - memo.gone[id].at > secs && !keep.has(id))) delete memo.gone[id];
    memo.last = live;
    return rows.concat(Object.values(memo.gone).map((g) => g.row));
  }
  function lingerDue(memo, now, keep, secs) {
    return Object.entries(memo.gone).some(([id, g]) => now - g.at > secs && !keep.has(id));
  }

  /* What "Go to it" does with the Board's answer. A session in no window
     (Relay runs them headless) opens its chat in Conversations instead. */
  function goResult(r) {
    if (r.ok) return { chat: false, kind: "ok", text: r.app ? "Opened in the Claude app" : "Brought its terminal tab forward" };
    if (r.nowhere) return { chat: true, kind: "ok", text: "It runs in no window, so its chat opened here" };
    return { chat: false, kind: "err", text: r.reason || "Could not reach it" };
  }

  /* A helper's name on a card: its persona or crew name, else its type
     ("crew-" dropped). Ultracode's workflow helpers all share one type, so
     they go by their own label ("legs:landing"). */
  function helperName(h) {
    if (h.persona || h.crew_member) return h.persona || h.crew_member;
    if (h.type === "workflow-subagent" && h.task) return h.task;
    return (h.type || "helper").replace(/^crew-/, "");
  }

  return { goResult, helperName, FILTERS, ARCHIVE_S, section, isUnread, matches, counts, places, nextDelay, ago, tokens, modelName, pct, hash, spriteFor, calmOrder, shortTitle, displayName, personaTag, linger, lingerDue };
});
