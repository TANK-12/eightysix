// node --test tests/  (run by tests/test_enjoy_js.py inside pytest too)
// The Enjoy layout's page-free logic: plans and progress read from a
// conversation's events, the running / needs you view, and the roadmap's
// star layout (A15, A28).
const test = require("node:test");
const assert = require("node:assert");
const L = require("../static/enjoy_logic.js");

const tool = (name, input, id = "m1") => ({
  type: "assistant",
  message: { id, content: [{ type: "tool_use", id: "t" + Math.random(), name, input }] },
});

test("the latest TodoWrite is the progress, the latest ExitPlanMode the plan", () => {
  const events = [
    { type: "forge_user", text: "go" },
    tool("TodoWrite", { todos: [{ content: "a", status: "pending", activeForm: "doing a" }] }),
    tool("ExitPlanMode", { plan: "## Plan\n\n1. a" }),
    { type: "assistant", message: { id: "m2", content: [{ type: "text", text: "working" }] } },
    tool("TodoWrite", {
      todos: [
        { content: "a", status: "completed", activeForm: "doing a" },
        { content: "b", status: "in_progress", activeForm: "doing b" },
        { content: "c", status: "pending", activeForm: "doing c" },
      ],
    }),
  ];
  const p = L.planOf(events);
  assert.strictEqual(p.plan, "## Plan\n\n1. a");
  assert.deepStrictEqual(p.todos.map((t) => t.status), ["completed", "in_progress", "pending"]);
  assert.strictEqual(p.done, 1);
  assert.strictEqual(p.total, 3);
  assert.strictEqual(p.now, "doing b");
});

test("no plan yet is an empty plan, not an error", () => {
  const p = L.planOf([{ type: "result" }, { type: "assistant", message: {} }, { type: "assistant" }]);
  assert.deepStrictEqual(p, { plan: "", todos: [], done: 0, total: 0, now: "" });
});

test("bad todo input is skipped", () => {
  const p = L.planOf([tool("TodoWrite", { todos: "nope" }), tool("TodoWrite", { todos: [null, { content: 3 }] })]);
  assert.strictEqual(p.total, 1);
  assert.strictEqual(p.todos[0].content, "3");
  assert.strictEqual(p.todos[0].status, "pending");
});

test("planStep folds one message in, for events that arrive live", () => {
  let p = L.planOf([]);
  p = L.planStep(p, tool("ExitPlanMode", { plan: "x" }).message);
  assert.strictEqual(p.plan, "x");
});

test("running and needs you across projects and loose tasks", () => {
  const listing = {
    projects: [
      { id: "p1", name: "Cosmos", tasks: [
        { id: "a", title: "stars", state: "running", updated: 5 },
        { id: "b", title: "moons", state: "needs you", updated: 9 },
        { id: "c", title: "old", state: "quiet", updated: 1 },
      ] },
      { id: "p2", name: "Forge", tasks: [{ id: "d", title: "hub", state: "needs you", updated: 3 }] },
    ],
    loose: [{ id: "e", title: "", state: "running", updated: 7 }],
  };
  const g = L.groupNow(listing);
  assert.deepStrictEqual(g.running.map((t) => t.id), ["e", "a"]);
  assert.deepStrictEqual(g.needsYou.map((t) => t.id), ["b", "d"]);
  assert.strictEqual(g.needsYou[0].project, "Cosmos");
  assert.strictEqual(g.running[0].project, "");
  assert.strictEqual(g.running[0].title, "untitled task");
});

test("the star layout is stable, inside its cell and one star per item", () => {
  const sessions = [
    { slot: "S7", date: "2026-09-26", items: Array.from({ length: 28 }, (_, i) => ({ id: "A" + (i + 1), state: "not done" })) },
    { slot: "S8", date: "2026-09-26", items: [{ id: "A1", state: "done+checked" }] },
    { slot: "", date: "2026-09-25", items: [] },
  ];
  const a = L.layout(sessions, 900);
  const b = L.layout(sessions, 900);
  assert.deepStrictEqual(a, b);
  assert.strictEqual(a.groups.length, 3);
  assert.strictEqual(a.groups[0].stars.length, 28);
  for (const g of a.groups) {
    for (const s of g.stars) {
      assert.ok(s.x > g.x && s.x < g.x + g.w && s.y > g.y && s.y < g.y + g.h, `${g.slot} ${s.x},${s.y}`);
    }
  }
  assert.ok(a.height > 0 && a.width === 900);
});

test("stars do not sit on top of each other", () => {
  const items = Array.from({ length: 30 }, (_, i) => ({ id: "A" + i, state: "not done" }));
  const g = L.layout([{ slot: "S1", date: "d", items }], 600).groups[0];
  let closest = Infinity;
  g.stars.forEach((s, i) => g.stars.slice(i + 1).forEach((t) => { closest = Math.min(closest, Math.hypot(s.x - t.x, s.y - t.y)); }));
  assert.ok(closest > 8, String(closest));
});

test("a constellation's lines are a tree to each star's nearest earlier star", () => {
  const items = Array.from({ length: 28 }, (_, i) => ({ id: "A" + i, state: "not done" }));
  const g = L.layout([{ slot: "S7", date: "d", items }], 900).groups[0];
  assert.strictEqual(g.links.length, 27);
  g.links.forEach(([a, b], k) => {
    assert.strictEqual(b, k + 1);
    assert.ok(a < b);
    const d = (i, j) => Math.hypot(g.stars[i].x - g.stars[j].x, g.stars[i].y - g.stars[j].y);
    for (let j = 0; j < b; j++) assert.ok(d(a, b) <= d(j, b) + 1e-9);
  });
  assert.deepStrictEqual(L.layout([{ slot: "S1", date: "d", items: [{ id: "A1" }] }], 900).groups[0].links, []);
});

test("ago reads like a person", () => {
  const now = 1_000_000;
  assert.strictEqual(L.ago(now - 20, now), "just now");
  assert.strictEqual(L.ago(now - 120, now), "2 min ago");
  assert.strictEqual(L.ago(now - 7200, now), "2 h ago");
  assert.strictEqual(L.ago(now - 3 * 86400, now), "3 days ago");
});
