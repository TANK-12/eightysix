const test = require("node:test");
const assert = require("node:assert");
const L = require("../static/logic.js");

const S = (id, group, last, place = "~") => ({ id, group, last_active: last, place, cwd: "/x" });

test("unread only after a look, and only for newer activity", () => {
  const seen = { a: 100 };
  assert.equal(L.isUnread(S("a", "idle", 150), seen), true);
  assert.equal(L.isUnread(S("a", "working", 150), seen), false);
  assert.equal(L.isUnread(S("a", "idle", 100.5), seen), false);
  assert.equal(L.isUnread(S("b", "working", 999), seen), false);
});

test("every filter counts what it shows (sweep)", () => {
  const groups = ["needs_you", "working", "idle", "ended"];
  for (let n = 0; n < 300; n++) {
    const list = [];
    const seen = {};
    for (let i = 0; i < n % 17; i++) {
      const s = S("s" + i, groups[(i * 7 + n) % 4], (i * 13 + n) % 50, "p" + (i % 3));
      if (i % 2) s.section = L.section(s, 1830); // idle ones with last <= 30 archive
      list.push(s);
      if ((i + n) % 3) seen["s" + i] = (i * 5 + n) % 50;
    }
    const c = L.counts(list, seen);
    for (const f of L.FILTERS) assert.equal(list.filter((s) => L.matches(s, f, seen, "")).length, c[f], f);
    assert.equal(c.needs_you + c.working + c.idle + c.archived, c.all);
  }
});

test("place filter narrows", () => {
  const list = [S("a", "idle", 1, "Forge"), S("b", "idle", 1, "~")];
  assert.deepEqual(list.filter((s) => L.matches(s, "all", {}, "Forge")).map((s) => s.id), ["a"]);
  assert.equal(L.places(list).length, 2);
});

test("backoff stays inside its bounds and resets on change", () => {
  let d = 3;
  for (let i = 0; i < 50; i++) {
    d = L.nextDelay(d, false, 3, 30);
    assert.ok(d >= 3 && d <= 30);
  }
  assert.equal(d, 30);
  assert.equal(L.nextDelay(d, true, 3, 30), 3);
});

test("formatting", () => {
  assert.equal(L.modelName("claude-opus-5-5"), "Opus 5.5");
  assert.equal(L.modelName("claude-sonnet-4-5-20250929"), "Sonnet 4.5");
  assert.equal(L.modelName("weird"), "weird");
  assert.equal(L.tokens(130217), "130k");
  assert.equal(L.tokens(1500000), "1.5M");
  assert.equal(L.pct(100000, 200000), 50);
  assert.equal(L.pct(900000, 200000), 100);
  assert.equal(L.ago(10), "just now");
  assert.equal(L.ago(NaN), "");
  assert.ok(/^person[1-8]_idle$/.test(L.spriteFor("session", "abc")));
  assert.equal(L.spriteFor("helper", "x", "crew-deep").startsWith("helper_deep_"), true);
});

test("calm order: newest activity first, re-sorted at most once a minute", () => {
  const memo = { at: {} };
  const ids = (list) => list.map((s) => s.id).join(",");
  // first look: newest first inside each section
  assert.equal(ids(L.calmOrder([S("b", "working", 20), S("a", "working", 30), S("c", "idle", 10)], memo, 1000)), "a,b,c");
  // b is busier now: within the minute the page keeps a first
  assert.equal(ids(L.calmOrder([S("b", "working", 40), S("a", "working", 35), S("c", "idle", 10)], memo, 1010)), "a,b,c");
  // c starts working: changing section takes its current time, so top of working
  assert.equal(ids(L.calmOrder([S("c", "working", 50), S("b", "working", 40), S("a", "working", 35)], memo, 1020)), "c,a,b");
  // a new one goes on top of its section; one that left is forgotten
  assert.equal(ids(L.calmOrder([S("d", "needs_you", 60), S("c", "working", 50), S("a", "working", 45)], memo, 1030)), "d,c,a");
  assert.deepEqual(Object.keys(memo.at).sort(), ["a", "c", "d"]);
  // b comes back: new again, so top of working
  assert.equal(ids(L.calmOrder([S("b", "working", 70), S("c", "working", 50), S("a", "working", 45), S("d", "needs_you", 60)], memo, 1040)), "d,b,c,a");
  // a minute after the last re-sort the real times count again; needs you stays on top
  assert.equal(ids(L.calmOrder([S("a", "working", 80), S("b", "working", 70), S("c", "working", 50), S("d", "needs_you", 1)], memo, 1060)), "d,a,b,c");
});

test("sections: idle half an hour or ended goes to Archived, working and needs-you never", () => {
  assert.equal(L.section(S("x", "idle", 0), L.ARCHIVE_S), "archived");
  assert.equal(L.section(S("x", "idle", 1), L.ARCHIVE_S), "idle");
  assert.equal(L.section(S("x", "ended", 999), 1000), "archived");
  assert.equal(L.section(S("x", "working", 0), 99999), "working");
  assert.equal(L.section(S("x", "needs_you", 0), 99999), "needs_you");
  const old = S("o", "idle", 0);
  old.section = "archived";
  assert.equal(L.matches(old, "archived", {}, ""), true);
  assert.equal(L.matches(old, "idle", {}, ""), false);
  assert.equal(L.matches(S("e", "ended", 1), "archived", {}, ""), true); // no section yet: by group
});

test("plain names: task number and a short description, persona as a tag", () => {
  const relay = { id: "x", name: "relay-109-work", label: "Rei", relay: { task: "109", title: "Mission Control conversation view, proper rebuild" } };
  assert.equal(L.displayName(relay), "#109 Mission Control conversation view");
  assert.equal(L.personaTag(relay), "Rei");
  const ended = { id: "y", name: "relay-105-work", label: "Yuzu" };
  assert.equal(L.displayName(ended), "#105 Yuzu");
  assert.equal(L.personaTag(ended), "");
  const chat = { id: "z", label: "Mio", title: "Fix the WhatsApp chat so that replies arrive in order and nothing is lost" };
  const n = L.displayName(chat);
  assert.ok(n.length <= 45 && n.endsWith("…") && n.startsWith("Fix the WhatsApp chat"), n);
  assert.equal(L.personaTag(chat), "Mio");
  assert.equal(L.displayName({ id: "abcdef123456" }), "abcdef12");
  assert.equal(L.displayName({ id: "q", label: "Kai", name: "ejb-47" }), "Kai");
  assert.equal(L.personaTag({ id: "q", label: "Kai", name: "ejb-47" }), "");
  assert.equal(L.shortTitle("Relay boss WhatsApp chat bug hunt and fix, from Emerson"), "Relay boss WhatsApp chat bug hunt and fix");
  assert.equal(L.shortTitle("Fix: x"), "Fix: x");
  // paths become words (task 109); web addresses and A/B stay
  assert.equal(L.shortTitle("~/Forge/sessions/2026-10-08-ai-studio-new-models.md"), "ai studio new models");
  assert.equal(L.shortTitle("Read /home/ejb/Forge/apps/mission/WIP.md and carry on"), "Read WIP and carry on");
  assert.equal(L.shortTitle("Fix apps/mission/static/convos.js headers"), "Fix convos headers");
  assert.equal(L.shortTitle("(~/Forge/docs/) tidy"), "(docs) tidy");
  assert.equal(L.shortTitle("A/B testing of the hub"), "A/B testing of the hub");
  assert.equal(L.shortTitle("see https://example.com/a/b"), "see https://example.com/a/b");
});

test("a session that leaves stays a while, marked ended, and while open", () => {
  const memo = { last: {}, gone: {} };
  const none = new Set();
  const ids = (list) => list.map((s) => s.id + ":" + s.group).join(",");
  assert.equal(ids(L.linger([S("a", "working", 1), S("b", "idle", 1)], memo, 100, none, 180)), "a:working,b:idle");
  const got = L.linger([S("b", "idle", 1)], memo, 110, none, 180);
  assert.equal(ids(got), "b:idle,a:ended");
  assert.equal(got[1].gone, true);
  assert.equal(L.lingerDue(memo, 200, none, 180), false);
  // past the linger it goes, unless it is open
  assert.equal(L.lingerDue(memo, 300, new Set(["a"]), 180), false);
  assert.equal(ids(L.linger([S("b", "idle", 1)], memo, 300, new Set(["a"]), 180)), "b:idle,a:ended");
  assert.equal(L.lingerDue(memo, 300, none, 180), true);
  assert.equal(ids(L.linger([S("b", "idle", 1)], memo, 300, none, 180)), "b:idle");
  // one that comes back is live again, not a ghost
  L.linger([], memo, 400, none, 180);
  assert.equal(ids(L.linger([S("b", "working", 2)], memo, 410, none, 180)), "b:working");
  assert.deepEqual(memo.gone, {});
});

test("go to it: a session in no window opens its chat here", () => {
  assert.deepEqual(L.goResult({ ok: true, app: "claude" }), { chat: false, kind: "ok", text: "Opened in the Claude app" });
  assert.equal(L.goResult({ ok: true, tab: "1" }).text, "Brought its terminal tab forward");
  assert.equal(L.goResult({ ok: false, nowhere: true, reason: "x" }).chat, true);
  assert.deepEqual(L.goResult({ ok: false, reason: "busy" }), { chat: false, kind: "err", text: "busy" });
});

test("helper names: persona, crew name, ultracode label, then type", () => {
  assert.equal(L.helperName({ persona: "Aoi", type: "crew-worker" }), "Aoi");
  assert.equal(L.helperName({ type: "crew-worker", task: "x" }), "worker");
  assert.equal(L.helperName({ type: "workflow-subagent", task: "legs:landing" }), "legs:landing");
  assert.equal(L.helperName({}), "helper");
});
