/* Sample crew for the Crew Room.
 *
 * Adds a clearly labelled sample session, crew helpers of every type, a crew
 * board and a Jan model on top of the live data, so every kind of character
 * can be seen without starting a crew or loading a model. Turned on by the
 * "Add a sample crew" setting or ?demo in the address; never on by default.
 */
(function (global) {
  "use strict";

  function apply(data, nowMs) {
    const out = JSON.parse(JSON.stringify(data || {}));
    out.sessions = out.sessions || [];
    out.helpers = out.helpers || [];
    out.crews = out.crews || [];
    out.jan = out.jan || { running: false, models: [] };
    const t = nowMs / 1000;
    const beat = Math.floor(t / 20) % 4;

    const commander = {
      id: "sample-commander", pid: 0, name: "sample-commander", status: "busy", busy: true,
      kind: "sample", cwd: "~/Forge/apps/crewroom", place: "crewroom", started_at: 1, updated_at: t,
      model: "claude-opus-5", family: "opus", effort: "high",
      action: ["planning the crew", "editing app.js", "running tests", "reading worker notes"][beat],
      actions: [
        { tool: "Read", text: "reading PLAN-crew-room.md" },
        { tool: "Agent", text: "sending out a helper" },
        { tool: "Edit", text: "editing app.js" },
      ],
      tokens: { turns: 12, avg_context: 84000, last_context: 91000, avg_output: 2100 },
      sample: true,
    };
    const idler = Object.assign({}, commander, {
      id: "sample-idle", name: "sample-idle", status: "idle", busy: false, model: "claude-sonnet-5",
      family: "sonnet", effort: "medium", action: "taking a break", started_at: 2,
    });
    out.sessions.push(commander, idler);

    const helper = (id, type, family, effort, task, state, action) => ({
      id, parent: commander.id, parent_name: commander.name, type, crew: type.startsWith("crew-"),
      task, state, model: "claude-" + family + "-5", family, effort, action,
      actions: [{ tool: "Bash", text: action }], tokens: { turns: 4, avg_context: 30000, last_context: 32000, avg_output: 900 },
      idle_seconds: state === "done" ? 120 : 3, sample: true,
    });
    out.helpers.push(
      helper("sample-light", "crew-light", "haiku", null, "Fill room data files", "working", "writing office.json"),
      helper("sample-worker", "crew-worker", "sonnet", "medium", "Speech bubbles", "working", "running tests"),
      helper("sample-deep", "crew-deep", "opus", "high", "Path finding", beat % 2 ? "done" : "working", "thinking"),
    );

    out.crews.push({
      name: "sample", commander: commander.name, goal: "build the crew room",
      members: [{ name: commander.name, role: "commander" }],
      tasks: [
        { id: 1, title: "room data", owner: "light-1", status: "done", files: [] },
        { id: 2, title: "speech bubbles", owner: "worker-1", status: "taken", files: [] },
        { id: 3, title: "path finding", owner: "deep-1", status: beat % 2 ? "done" : "taken", files: [] },
        { id: 4, title: "jan glow", owner: null, status: "open", files: [] },
      ],
      claims: [
        { path: "static/app.js", owner: commander.name },
        { path: "static/room.css", owner: commander.name },
      ],
      log: [],
    });

    const cpu = 20 + 70 * Math.abs(Math.sin(t / 9));
    out.jan.running = true;
    out.jan.models = (out.jan.models || []).concat([
      { id: "jan-sample", pid: -1, name: "Qwen3_5-9B-Q4_K_M (sample)", short: "Qwen3.5 9B", cpu: Math.round(cpu), share: Math.round(cpu / 8), rss_mb: 5400, sample: true },
    ]);
    out.sample = true;
    return out;
  }

  global.CrewRoomDemo = { apply };
})(window);
