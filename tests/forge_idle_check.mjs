// Node check of shared/forge_idle.js under a fake clock and a fake document.
// Run: node tests/forge_idle_check.mjs shared/forge_idle.js   (prints PASS/FAIL per case)
import fs from "fs";
import vm from "vm";

const SRC = fs.readFileSync(process.argv[2] || new URL("../shared/forge_idle.js", import.meta.url), "utf8");

function world() {
  const w = { now: 0, timers: [], seq: 0, evs: {} };
  const doc = {
    hidden: false,
    documentElement: { cls: new Set(), classList: { toggle(c, on) { on ? doc.documentElement.cls.add(c) : doc.documentElement.cls.delete(c); } } },
    head: { appendChild() {} },
    addEventListener(n, f) { (w.evs[n] ||= []).push(f); },
    createElement() { return {}; },
  };
  const ctx = {
    document: doc,
    Date: { now: () => w.now },
    setTimeout(f, ms) { const id = ++w.seq; w.timers.push({ id, at: w.now + (ms || 0), f }); return id; },
    clearTimeout(id) { w.timers = w.timers.filter((t) => t.id !== id); },
  };
  ctx.requestAnimationFrame = (f) => ctx.setTimeout(() => f(w.now), 16);
  ctx.cancelAnimationFrame = (id) => ctx.clearTimeout(id);
  ctx.window = ctx;
  ctx.ForgeVisible = { on: true };
  vm.createContext(ctx);
  vm.runInContext(SRC, ctx);
  w.doc = doc;
  w.I = ctx.ForgeIdle;
  w.fire = (n) => (w.evs[n] || []).forEach((f) => f());
  w.tab = (hidden) => { doc.hidden = hidden; w.fire("visibilitychange"); };
  w.hub = (on) => { ctx.ForgeVisible.on = on; w.fire("forge-visible"); };
  w.flush = async () => { for (let i = 0; i < 6; i++) await Promise.resolve(); };
  w.advance = async (ms) => {
    const end = w.now + ms;
    for (;;) {
      await w.flush();
      w.timers.sort((a, b) => a.at - b.at);
      const t = w.timers[0];
      if (!t || t.at > end) break;
      w.timers.shift();
      w.now = t.at;
      try { t.f(); } catch (e) { w.thrown = (w.thrown || 0) + 1; } // a browser reports these as uncaught
    }
    w.now = end;
    await w.flush();
  };
  return w;
}

const results = [];
async function check(name, fn) {
  try { const msg = await fn(); results.push([true, name, msg || ""]); }
  catch (e) { results.push([false, name, e.message]); }
}
function expect(cond, msg) { if (!cond) throw new Error(msg); }

await check("polls while shown, stops hidden, one run at once on return", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; }, 1000);
  await w.advance(10000); const vis = n;
  w.tab(true); await w.advance(20000); const hid = n - vis;
  expect(w.doc.documentElement.cls.has("forge-idle"), "forge-idle class not set while hidden");
  w.tab(false); await w.advance(1);
  expect(vis === 10 && hid === 0 && n - vis === 1, `visible ${vis} hidden ${hid} resume ${n - vis}`);
  return `visible 10s=${vis} hidden 20s=${hid} resume=1`;
});

await check("hub signal (ForgeVisible) pauses too; tab hidden + hub visible stays paused", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; }, 1000);
  await w.advance(3000); const a = n;
  w.hub(false); await w.advance(5000);
  expect(n === a, "ran while hub-hidden");
  w.tab(true); w.hub(true); await w.advance(5000);
  expect(n === a, "ran while tab hidden but hub visible");
  w.tab(false); await w.advance(1);
  expect(n === a + 1, "no run on return");
});

await check("1000 random flips leave one timer and the normal rate", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; }, 1000);
  w.I.poll(async () => { await null; }, 500);
  let r = 7; const rnd = () => ((r = (r * 1103515245 + 12345) % 2147483648) / 2147483648);
  for (let i = 0; i < 1000; i++) {
    if (rnd() < 0.5) w.tab(rnd() < 0.5); else w.hub(rnd() < 0.5);
    await w.advance(rnd() * 40);
  }
  w.tab(false); w.hub(true); await w.advance(50);
  expect(w.timers.length <= 2, `${w.timers.length} timers pending for 2 polls`);
  const a = n; await w.advance(10000);
  expect(n - a === 10, `rate after flips ${n - a} per 10 s`);
  return `timers=${w.timers.length} rate=${n - a}/10s`;
});

await check("slow async job never overlaps, hidden mid-run schedules nothing", async () => {
  const w = world(); let live = 0, max = 0, n = 0;
  const job = () => new Promise((res) => { live++; n++; max = Math.max(max, live); w.window_setTimeout(() => { live--; res(); }, 2500); });
  w.window_setTimeout = (f, ms) => { const id = ++w.seq; w.timers.push({ id, at: w.now + ms, f, job: true }); };
  w.I.poll(job, 1000, { immediate: true });
  await w.advance(1000);
  w.tab(true); w.tab(false); w.tab(true); w.tab(false); // flips while in flight
  await w.advance(9000);
  expect(max === 1, `overlap: ${max} runs at once`);
  w.tab(true); await w.advance(2000); // hidden while a run is in flight
  const m = n; await w.advance(20000);
  expect(n === m, `ran ${n - m} times while hidden`);
  return `runs=${n} max concurrent=${max}`;
});

await check("stop() during a run ends it for good", async () => {
  const w = world(); let n = 0, done;
  const h = w.I.poll(() => { n++; return new Promise((r) => (done = r)); }, 1000, { immediate: true });
  await w.advance(10); h.stop(); done(); await w.advance(10000);
  w.tab(true); w.tab(false); await w.advance(5000);
  expect(n === 1, `ran ${n} times after stop`);
});

await check("a throwing job keeps polling", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; throw new Error("boom"); }, 1000);
  await w.advance(5000);
  expect(n === 5, `ran ${n}`);
});

await check("hiddenMs keeps a slow tick while hidden", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; }, 1000, { hiddenMs: 5000 });
  w.tab(true); await w.advance(20000);
  expect(n === 4, `hidden ticks ${n}`);
});

await check("backoff stretches on false up to maxMs and resets on success", async () => {
  const w = world(); const at = []; let fail = true;
  w.I.poll(() => { at.push(w.now); return fail ? false : true; }, 1000, { backoff: 2, maxMs: 4000 });
  await w.advance(15000);
  const gaps = at.slice(1).map((t, i) => t - at[i]);
  expect(gaps.join() === "2000,4000,4000,4000", `gaps ${gaps.join()}`);
  fail = false; await w.advance(4000); const k = at.length; await w.advance(3000);
  expect(at.length - k === 3, `after success ${at.length - k} runs in 3 s`);
});

await check("brief hide keeps the schedule (no extra run, no delay)", async () => {
  const w = world(); const at = [];
  w.I.poll(() => { at.push(w.now); }, 1000);
  await w.advance(1000); // run at 1000
  await w.advance(400); w.tab(true); await w.advance(100); w.tab(false);
  await w.advance(1000);
  expect(at.join() === "1000,2000", `runs at ${at.join()}`);
});

await check("now() runs at once and resets the wait", async () => {
  const w = world(); const at = [];
  const h = w.I.poll(() => { at.push(w.now); }, 1000);
  await w.advance(300); h.now(); await w.advance(1000);
  expect(at.join() === "300,1300", `runs at ${at.join()}`);
});

await check("loop pauses hidden, resumes shown, ends on false", async () => {
  const w = world(); let f = 0;
  w.I.loop(() => { f++; return f < 100; });
  await w.advance(160); const a = f;
  w.hub(false); await w.advance(1000);
  expect(f === a, "frames while hidden");
  w.hub(true); await w.advance(5000);
  expect(f === 100, `loop did not end at 100 (${f})`);
  return `frames ${a} in 160 ms`;
});

await check("a job that never settles does not end the poll", async () => {
  const w = world(); let n = 0;
  w.I.poll(() => { n++; return n === 1 ? new Promise(() => {}) : null; }, 1000);
  await w.advance(1000 + 30000 + 5000);
  expect(n >= 5, `only ${n} runs after a stuck one`);
  return `runs=${n} in 36 s, first stuck`;
});

await check("a throwing loop frame keeps the loop going", async () => {
  const w = world(); let f = 0;
  w.I.loop(() => { f++; if (f === 3) throw new Error("frame"); });
  await w.advance(500);
  expect(f > 10 && w.thrown === 1, `loop died at ${f}, reported ${w.thrown}`);
});

let bad = 0;
for (const [ok, name, msg] of results) { if (!ok) bad++; console.log(`${ok ? "PASS" : "FAIL"} ${name}${msg ? "  (" + msg + ")" : ""}`); }
console.log(bad ? `${bad} FAILED of ${results.length}` : `all ${results.length} passed`);
process.exit(bad ? 1 : 0);
