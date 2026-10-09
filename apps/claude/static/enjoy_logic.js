/* The Enjoy layout's logic that needs no page, so node can test it
 * (tests/enjoy_logic.test.js):
 *
 *   planOf(events), planStep(plan, message)
 *       A task's plan and progress, read from Claude Code's own tool calls:
 *       the latest ExitPlanMode is the plan (markdown), the latest TodoWrite
 *       the todo list with its statuses (pending, in_progress, completed).
 *   groupNow(listing)
 *       /api/projects -> the tasks running now and the ones that need you,
 *       across every project and the loose tasks, newest first.
 *   layout(sessions, width)
 *       /api/roadmap's sessions -> one constellation per session: a cell on a
 *       grid and a star per ledger item, placed on a spiral with a jitter
 *       seeded by the session, so the sky looks the same every time; the
 *       lines join each star to the nearest one placed before it.
 *   ago(t, now)
 */
(function (root) {
  const emptyPlan = () => ({ plan: "", todos: [], done: 0, total: 0, now: "" });

  function planStep(plan, message) {
    const content = message && Array.isArray(message.content) ? message.content : [];
    let next = plan;
    for (const block of content) {
      if (!block || block.type !== "tool_use") continue;
      const input = block.input || {};
      if (block.name === "ExitPlanMode" && typeof input.plan === "string") {
        next = Object.assign({}, next, { plan: input.plan });
      } else if (block.name === "TodoWrite" && Array.isArray(input.todos)) {
        const todos = input.todos
          .filter((t) => t && typeof t === "object")
          .map((t) => ({
            content: String(t.content ?? ""),
            status: ["pending", "in_progress", "completed"].includes(t.status) ? t.status : "pending",
            activeForm: String(t.activeForm ?? t.content ?? ""),
          }));
        const working = todos.find((t) => t.status === "in_progress");
        next = Object.assign({}, next, {
          todos,
          total: todos.length,
          done: todos.filter((t) => t.status === "completed").length,
          now: working ? working.activeForm : "",
        });
      }
    }
    return next;
  }

  function planOf(events) {
    return (events || []).reduce(
      (plan, e) => (e && e.type === "assistant" ? planStep(plan, e.message) : plan),
      emptyPlan(),
    );
  }

  function groupNow(listing) {
    const running = [];
    const needsYou = [];
    const add = (task, project) => {
      const row = Object.assign({}, task, {
        project: project ? project.name : "",
        projectId: project ? project.id : "",
        title: task.title || "untitled task",
      });
      if (task.state === "running") running.push(row);
      else if (task.state === "needs you") needsYou.push(row);
    };
    ((listing && listing.projects) || []).forEach((p) => (p.tasks || []).forEach((t) => add(t, p)));
    ((listing && listing.loose) || []).forEach((t) => add(t, null));
    const newest = (a, b) => (b.updated || 0) - (a.updated || 0);
    return { running: running.sort(newest), needsYou: needsYou.sort(newest) };
  }

  // a small seeded random, so a session's stars keep their places
  function seeded(text) {
    let h = 2166136261;
    for (const ch of String(text)) h = Math.imul(h ^ ch.charCodeAt(0), 16777619);
    return () => {
      h = Math.imul(h ^ (h >>> 15), 2246822507);
      h = Math.imul(h ^ (h >>> 13), 3266489909);
      h ^= h >>> 16;
      return (h >>> 0) / 4294967296;
    };
  }

  function layout(sessions, width) {
    const cols = width >= 1100 ? 3 : width >= 640 ? 2 : 1;
    const w = width / cols;
    const h = Math.max(260, Math.min(360, w * 0.8));
    const groups = (sessions || []).map((s, i) => {
      const x = (i % cols) * w;
      const y = Math.floor(i / cols) * h;
      const cx = x + w / 2;
      const cy = y + h / 2 + 12; // room for the name above
      const items = s.items || [];
      const rand = seeded(`${s.date}|${s.slot}|${s.file || ""}`);
      const turn = rand() * Math.PI * 2;
      const reach = Math.min(w, h) / 2 - 34;
      const stars = items.map((item, k) => {
        // a sunflower spiral fills the disc evenly; the jitter keeps it from
        // looking like a pattern
        const r = reach * Math.sqrt((k + 0.6) / Math.max(items.length, 1));
        const a = turn + k * 2.39996;
        const jx = (rand() - 0.5) * 10;
        const jy = (rand() - 0.5) * 10;
        return {
          id: item.id,
          x: Math.round((cx + Math.cos(a) * r * 1.18 + jx) * 10) / 10,
          y: Math.round((cy + Math.sin(a) * r * 0.86 + jy) * 10) / 10,
          r: item.tag === "constraint" ? 2.2 : item.state === "done+checked" ? 4.2 : 3.4,
          item,
        };
      });
      // the lines: each star joins the nearest star placed before it, a tree
      // that reads as a constellation rather than a web of crossings
      const links = stars.slice(1).map((st, k) => {
        let best = 0;
        for (let j = 1; j <= k; j++) {
          if (Math.hypot(stars[j].x - st.x, stars[j].y - st.y) < Math.hypot(stars[best].x - st.x, stars[best].y - st.y)) best = j;
        }
        return [best, k + 1];
      });
      return { slot: s.slot, session: s, x, y, w, h, cx, cy, stars, links };
    });
    return { width, height: Math.ceil(groups.length / cols) * h, groups };
  }

  function ago(t, now) {
    const s = Math.max(0, (now ?? Date.now() / 1000) - (Number(t) || 0));
    if (s < 60) return "just now";
    if (s < 3600) return `${Math.floor(s / 60)} min ago`;
    if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
    const d = Math.floor(s / 86400);
    return d === 1 ? "yesterday" : `${d} days ago`;
  }

  const api = { planOf, planStep, emptyPlan, groupNow, layout, ago };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.EnjoyLogic = api;
})(typeof window !== "undefined" ? window : globalThis);
