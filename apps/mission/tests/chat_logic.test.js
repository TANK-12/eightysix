const test = require("node:test");
const assert = require("node:assert");
const L = require("../static/chat_logic.js");

const MODELS = { "": "Claude Code's default", opus: "Opus", fable: "Fable", "claude-sonnet-5-5": "Sonnet 5.5", sonnet: "Sonnet (newest)", haiku: "Haiku" };
const EFFORTS = { "": "Default", low: "Low", medium: "Medium", high: "High", xhigh: "Extra high", max: "Max" };
const S = (id, group, last, extra = {}) => Object.assign({ id, group, last_active: last, label: id, cwd: "/x" }, extra);

test("chats in sections, needs you first, the given (calm) order kept inside (sweep)", () => {
  const groups = ["needs_you", "working", "idle", "ended"];
  const rank = { needs_you: 0, working: 1, idle: 2, archived: 3 };
  for (let n = 1; n < 400; n++) {
    const list = [];
    for (let i = 0; i < 1 + (n % 13); i++) {
      const g = groups[(i * 7 + n) % 4];
      list.push(S("s" + i, g, (i * 31 + n * 7) % 97, n % 3 ? { section: g === "ended" ? "archived" : (i + n) % 5 ? g : "archived" } : {}));
    }
    const secs = L.chatSections(list, "");
    assert.equal(secs.reduce((a, g) => a + g.items.length, 0), list.length);
    for (let i = 1; i < secs.length; i++) assert.ok(rank[secs[i - 1].section] < rank[secs[i].section], "sections out of order");
    for (const g of secs) {
      const pos = g.items.map((s) => list.indexOf(s));
      assert.deepEqual(pos, pos.slice().sort((a, b) => a - b), "the given order changed inside a section");
      for (const s of g.items) assert.equal(s.section || (s.group === "ended" ? "archived" : s.group), g.section);
    }
    assert.deepEqual(L.chatOrder(list, "").map((s) => s.id), secs.flatMap((g) => g.items.map((s) => s.id)));
  }
  assert.deepEqual(L.chatSections([S("a", "idle", 1, { section: "archived" }), S("b", "needs_you", 0)], "").map((g) => [g.section, g.label]), [["needs_you", "Needs you"], ["archived", "Archived"]]);
});

test("find narrows by name, folder or action", () => {
  const list = [S("Rin", "idle", 3, { action: "pytest" }), S("Kaito", "working", 5, { cwd: "/home/ejb/Forge" })];
  assert.deepEqual(L.chatOrder(list, "PYTEST").map((s) => s.id), ["Rin"]);
  assert.deepEqual(L.chatOrder(list, "forge").map((s) => s.id), ["Kaito"]);
  assert.equal(L.chatOrder(list, "zzz").length, 0);
});

test("next and previous wrap around", () => {
  const order = [S("a", "idle", 3), S("b", "idle", 2), S("c", "idle", 1)];
  assert.equal(L.neighbour(order, "a", 1), "b");
  assert.equal(L.neighbour(order, "c", 1), "a");
  assert.equal(L.neighbour(order, "a", -1), "c");
  assert.equal(L.neighbour(order, "gone", 1), "a");
  assert.equal(L.neighbour([], "a", 1), "");
});

test("a reply's route: Claude app, resume, or board note", () => {
  assert.equal(L.route(S("a", "working", 1), "c1").kind, "claude");
  assert.equal(L.route(S("a", "ended", 1), "").kind, "resume");
  assert.equal(L.route(S("a", "ended", 1), "").pick, true);
  assert.equal(L.route(S("a", "working", 1), "").kind, "board");
  assert.equal(L.route(S("a", "idle", 1), "").pick, false);
  assert.equal(L.route(null, "").kind, "none");
});

test("model cards keep the registry's models, default first, one on", () => {
  const cards = L.modelCards(MODELS, "claude-sonnet-5-5");
  assert.deepEqual(cards.map((c) => c.id), ["", "opus", "fable", "claude-sonnet-5-5", "sonnet", "haiku"]);
  assert.equal(cards.filter((c) => c.on).length, 1);
  assert.equal(cards.find((c) => c.on).family, "sonnet");
  assert.equal(cards[0].label, "Default");
  assert.ok(cards.every((c) => c.hue));
  // a model the looks do not know still gets a card
  const odd = L.modelCards({ "": "d", "claude-zeta-9": "Zeta 9" }, "");
  assert.equal(odd[1].family, "other");
  assert.equal(odd[0].on, true);
  // no "" in the registry: a Default card is added
  assert.equal(L.modelCards({ opus: "Opus" }, "")[0].id, "");
});

test("effort gauge lights up to the pick and keeps unknown levels", () => {
  const steps = L.effortSteps(EFFORTS, "high");
  assert.deepEqual(steps.map((s) => s.id), ["low", "medium", "high", "xhigh", "max"]);
  assert.deepEqual(steps.map((s) => s.lit), [true, true, true, false, false]);
  assert.equal(steps.filter((s) => s.on).length, 1);
  assert.deepEqual(L.effortSteps(EFFORTS, "").map((s) => s.lit), [false, false, false, false, false]);
  const more = L.effortSteps(Object.assign({ turbo: "Turbo" }, EFFORTS), "turbo");
  assert.equal(more[more.length - 1].id, "turbo");
  assert.ok(more.every((s) => s.lit));
});

test("the chip says model and effort in words", () => {
  assert.equal(L.chipText(MODELS, EFFORTS, "opus", "max"), "Opus · Max");
  assert.equal(L.chipText(MODELS, EFFORTS, "", ""), "Default model · Default effort");
  assert.equal(L.chipText(MODELS, EFFORTS, "claude-x", "xhigh"), "claude-x · Extra high");
});

test("ultrathink: next is one message, always stays, the word is not doubled", () => {
  assert.equal(L.withUltra("fix it", "next"), "ultrathink. fix it");
  assert.equal(L.withUltra("fix it", "always"), "ultrathink. fix it");
  assert.equal(L.withUltra("fix it", "off"), "fix it");
  assert.equal(L.withUltra("Ultrathink about this", "next"), "Ultrathink about this");
  assert.equal(L.afterSend("next"), "off");
  assert.equal(L.afterSend("always"), "always");
  assert.equal(L.afterSend("bogus"), "off");
  assert.equal(L.toggleUltra("off"), "next");
  assert.equal(L.toggleUltra("next"), "off");
  assert.equal(L.toggleUltra("always"), "off");
});

test("steps summary counts tools, names the running one, flags failures", () => {
  const run = [
    { name: "Bash", state: "done", brief: "ls" },
    { name: "Read", state: "done", brief: "a.py" },
    { name: "Bash", state: "done", brief: "pytest" },
    { name: "Thinking", state: "done", think: true },
    { name: "Edit", state: "running", brief: "b.py" },
  ];
  const s = L.stepsSummary(run);
  assert.equal(s.count, 4);
  assert.equal(s.label, "4 steps");
  assert.equal(s.state, "running");
  assert.equal(s.now, "Edit: b.py");
  assert.ok(s.names.startsWith("Bash ×2"), s.names);
  assert.ok(s.names.endsWith("a thought"), s.names);
  run[4].state = "failed";
  assert.equal(L.stepsSummary(run).state, "failed");
  assert.equal(L.stepsSummary(run).failed, 1);
  assert.equal(L.stepsSummary([{ name: "Thinking", think: true }]).label, "Thinking");
  const many = ["A", "B", "C", "D", "E", "F"].map((n) => ({ name: n, state: "done" }));
  assert.ok(L.stepsSummary(many).names.endsWith("+2 more"));
  assert.equal(L.stepsSummary([]).count, 0);
});

test("step names lose their icon", () => {
  assert.equal(L.stepName("⚙ Bash"), "Bash");
  assert.equal(L.stepName("🌐 Browser: open"), "Browser: open");
  assert.equal(L.stepName(""), "step");
});

test("text size stays in range", () => {
  assert.equal(L.clampSize(19), 19);
  assert.equal(L.clampSize(3), L.SIZE.min);
  assert.equal(L.clampSize(99), L.SIZE.max);
  assert.equal(L.clampSize("22.4"), 22);
  assert.equal(L.clampSize("x"), L.SIZE.start);
});

/* ---- the WhatsApp mirror (Emerson's note 1295) ---- */
test("WhatsApp marks: bold, italic, struck, code, links, line breaks", () => {
  assert.strictEqual(L.waText("*big* news"), "<b>big</b> news");
  assert.strictEqual(L.waText("an _odd_ ~old~ one"), "an <i>odd</i> <s>old</s> one");
  assert.strictEqual(L.waText("run `ls -l` now"), "run <code>ls -l</code> now");
  assert.strictEqual(L.waText("one\ntwo"), "one<br>two");
  assert.strictEqual(L.waText("see https://x.org/a?b=1&c=2."), 'see <a href="https://x.org/a?b=1&amp;c=2" target="_blank" rel="noopener">https://x.org/a?b=1&amp;c=2</a>.');
  assert.match(L.waText("```\na *b*\n```"), /^<code class="wa-mono">a \*b\*<\/code>$/);
});

test("WhatsApp marks leave ordinary text alone", () => {
  for (const s of ["snake_case_name", "5 * 3 * 2", "a*b*c", "file_one and file_two", "~/Forge/apps", "it's 5_000", "half *open", "``` never closed"]) {
    assert.strictEqual(L.waText(s), s.replace(/&/g, "&amp;").replace(/'/g, "&#39;"), s);
  }
});

test("WhatsApp text is escaped, so a line cannot add markup (sweep)", () => {
  const bits = ["<img src=x onerror=alert(1)>", '"', "'", "&", "*", "_", "~", "`", "```", "\n", "https://a.b/<x>", "<script>", " ", "word"];
  for (let i = 0; i < 3000; i++) {
    let s = "";
    for (let k = (i % 7) + 1; k > 0; k--) s += bits[(i * 31 + k * 17) % bits.length];
    const out = L.waText(s);
    const tags = out.match(/<\/?([a-z]+)/g) || [];
    for (const t of tags) assert.ok(/^<\/?(b|i|s|code|a|br)$/.test(t), `${JSON.stringify(s)} -> ${out}`);
    assert.ok(!/<[a-z]+[^>]*\son\w+=/i.test(out), out);
  }
});

test("WhatsApp lines: who speaks, runs, days and the read mark", () => {
  assert.deepStrictEqual(["Emerson", "Relay", "Boss", "Jan", "Local", "Someone"].map(L.waWho), ["me", "relay", "boss", "jan", "local", "relay"]);
  const M = (at, who, extra = {}) => Object.assign({ key: at + who, at, who, me: who === "Emerson", text: "t", new: false }, extra);
  const THU = new Date(2026, 9, 8, 12, 0); // Thursday 8 October 2026, noon
  const rows = L.waRuns([M("Wed 23:58", "Relay"), M("Wed 23:59", "Relay"), M("Thu 00:01", "Relay"), M("Thu 09:00", "Emerson"), M("Thu 09:01", "Emerson", { new: true }), M("Thu 09:02", "Boss")], THU);
  assert.deepStrictEqual(rows.map((r) => r.first), [true, false, true, true, false, true]);
  assert.deepStrictEqual(rows.map((r) => r.day), ["Yesterday", "", "Today", "", "", ""]);
  assert.deepStrictEqual(rows.map((r) => r.time), ["23:58", "23:59", "00:01", "09:00", "09:01", "09:02"]);
  assert.deepStrictEqual(rows.map((r) => r.mark), ["", "", "", "", "sent", ""]);
  assert.deepStrictEqual(L.waRuns([M("Thu 09:00", "Emerson"), M("Thu 09:01", "Relay")], THU).map((r) => r.mark), ["read", ""]);
  assert.deepStrictEqual(L.waRuns([M("", "Relay", { at: "" })], THU).map((r) => [r.day, r.time, r.first]), [["", "", true]]);
  assert.deepStrictEqual(L.waRuns(null, THU), []);
});

test("WhatsApp day chips know the week: a line from last week is not today", () => {
  const M = (at, who = "Relay") => ({ key: at + who, at, who, me: who === "Emerson", text: "t", new: false });
  const THU = new Date(2026, 9, 8, 12, 0);
  const day = (list) => L.waRuns(list.map((a) => M(a)), THU).map((r) => r.day);
  // a week wraps on the same weekday when the time goes back
  assert.deepStrictEqual(day(["Thu 18:00", "Thu 09:00"]), ["Thursday 1 Oct", "Today"]);
  // weekdays walk back one by one: Mon this week, then Fri (6 days back, a weekday name like WhatsApp) and Thu last week
  assert.deepStrictEqual(day(["Thu 10:00", "Fri 10:00", "Mon 10:00", "Wed 10:00", "Thu 10:00"]), ["Thursday 1 Oct", "Friday", "Monday", "Yesterday", "Today"]);
  // a newest line later in the day than now is last week's
  assert.deepStrictEqual(day(["Thu 23:50"]), ["Thursday 1 Oct"]);
  // across the year's end (Friday 1 January 2027): a week back from yesterday
  assert.deepStrictEqual(L.waRuns([M("Thu 10:00"), M("Thu 09:00")], new Date(2027, 0, 1, 12, 0)).map((r) => r.day), ["Thursday 24 Dec", "Yesterday"]);
});

test("twin model cards say how they differ", () => {
  const cards = L.modelCards(MODELS, "");
  const blurb = (id) => cards.find((c) => c.id === id).blurb;
  assert.ok(blurb("claude-sonnet-5-5").startsWith("Stays on Sonnet 5.5."), blurb("claude-sonnet-5-5"));
  assert.ok(blurb("sonnet").startsWith("Always the newest one."), blurb("sonnet"));
  assert.notEqual(blurb("sonnet"), blurb("claude-sonnet-5-5"));
  assert.equal(blurb("opus"), L.FAMILIES.opus.blurb);
});

test("text size box: nothing usable keeps the size, numbers are clamped", () => {
  assert.deepStrictEqual(["", " ", "-", "-3", "0", "abc", "1e3", "12px"].map(L.sizeFrom), [null, null, null, null, null, null, null, null]);
  assert.deepStrictEqual(["8", "14", "20", "20.6", "99"].map(L.sizeFrom), [14, 14, 20, 21, 28]);
});

test("turn ends in words, no dollars", () => {
  assert.deepStrictEqual([0, 400, 1000, 59400, 61000, 1070500, 3600000, 5000000, NaN].map(L.tookWords), ["", "", "took 1 s", "took 59 s", "took 1 min", "took 18 min", "took 1 h", "took 1 h 23 min", ""]);
});

test("asides are short words on the way; sending lines match with spaces squashed", () => {
  assert.equal(L.isAside("Let me check the tests."), true);
  assert.equal(L.isAside("   "), false);
  assert.equal(L.isAside("x".repeat(L.ASIDE_MAX)), true);
  assert.equal(L.isAside("x".repeat(L.ASIDE_MAX + 1)), false);
  assert.equal(L.sameLine("one\n\n\ntwo  three", "Thu 10:00 one\n\ntwo three"), true);
  assert.equal(L.sameLine("", "anything"), false);
  assert.equal(L.sameLine("hello there", "goodbye"), false);
});

test("a message with files reads as the session gets it, and its sending line still matches", () => {
  assert.equal(L.withFiles(" look ", []), "look");
  assert.equal(L.withFiles("look", ["/a/b.png", "", "/a/c.pdf"]), "look\n\nAttached files:\n- /a/b.png\n- /a/c.pdf");
  assert.equal(L.withFiles("", ["/a/b.png"]), "Attached files:\n- /a/b.png");
  const sent = L.withFiles("", ["/home/ejb/.local/share/forge/mission/attachments/2026-10-08/pasted.png"]);
  assert.equal(L.sameLine(sent, "From Mission Control: " + sent), true);
});
