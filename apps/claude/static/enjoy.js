/* The Enjoy layout of the Claude app (A15, with the roadmap tab A28).
 *
 * Same backend and conversations as the classic page (index.html), seen as
 * projects: a project is a conversation folder, a task is a conversation in
 * it. Views, chosen by the address's hash:
 *   #projects              every project, + new project, the loose tasks
 *   #project/<id>/<tab>    tasks. notes. workflows. of one project
 *   #task/<id>             the chat, with its plan and progress beside it
 *                          (read from Claude Code's ExitPlanMode and
 *                          TodoWrite calls, enjoy_logic.js)
 *   #now                   running / needs you, across every project
 *   #roadmap[/<brief>|<id>] the session briefs as constellations, and the
 *                          forge board's open notes; with a star, it opens
 *                          picked
 * Drawing a conversation, markdown and the API helpers are shared with the
 * classic page (claude_common.js). "classic layout ↗" switches back, and the
 * choice is remembered (localStorage claude.layout) so index.html sends you
 * to whichever you used last.
 */
const { api, post, el, markdown, readBase64, fileChip } = ClaudeCommon;
const L = EnjoyLogic;
const $ = (id) => document.getElementById(id);
const E = {
  listing: { projects: [], loose: [] }, profiles: [], profile: "", roadmap: null, when: "latest",
  looseAll: false, flowEdit: -1, note: "", task: null, poll: 0, skyTimer: 0,
};
const LAST = "claude.enjoy.last";
const PROFILE = "claude.enjoy.profile";
// the model, effort and permission level last picked in a task, which new
// tasks start with
const DEFAULTS = "claude.enjoy.defaults";
// short words for the permission levels; the backend's sentence is the tooltip
const MODE_WORDS = { dontAsk: "read & browse", plan: "plan only", acceptEdits: "edit files", auto: "auto", bypassPermissions: "anything" };
const KNOBS = ["e-t-model", "e-t-effort", "e-t-mode"];
const DRAG = "application/x-enjoy-task";

function toast(text) {
  const t = $("e-toast");
  t.textContent = text;
  t.hidden = false;
  requestAnimationFrame(() => t.classList.add("show"));
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    t.classList.remove("show");
    toast.timer = setTimeout(() => { t.hidden = true; }, 260);
  }, 3200);
}

function taskDefaults() {
  try { return JSON.parse(localStorage.getItem(DEFAULTS)) || {}; } catch (e) { return {}; }
}

// list rows and cards rise in one after another when a view opens (not on
// the 8-second refresh, which redraws the same lists)
function stagger(box) {
  if (!E.opening) return;
  [...box.children].forEach((c, i) => c.style.setProperty("--i", Math.min(i, 14)));
  box.classList.remove("e-stagger");
  void box.offsetWidth;
  box.classList.add("e-stagger");
}
ClaudeCommon.onStatus = toast;

const findProject = (pid) => E.listing.projects.find((p) => p.id === pid);
const allTasks = () => E.listing.projects.flatMap((p) => (p.tasks || []).map((t) => ({ ...t, project: p })))
  .concat(E.listing.loose.map((t) => ({ ...t, project: null })));
const stateClass = (s) => (s === "running" ? "running" : s === "needs you" ? "needs" : s === "new" ? "new" : "");

/* ---------------------------------------------------------------- data */

async function loadListing() {
  try {
    E.listing = await api("/api/projects");
  } catch (e) {
    toast("Could not load the projects: " + e.message);
    return;
  }
  drawRail();
}

async function loadProfiles() {
  try {
    const got = await api("/api/profiles");
    E.profiles = got.profiles || [];
    const saved = localStorage.getItem(PROFILE);
    E.profile = E.profiles.some((p) => p.name === saved) ? saved : got.active || "default";
  } catch (e) {
    E.profiles = [];
  }
  $("e-account").replaceChildren(...E.profiles.map((p) => {
    const o = el("option", "", p.name + (p.email ? ` · ${p.email}` : "") + (p.logged_in ? "" : " (signed out)"));
    o.value = p.name;
    return o;
  }));
  $("e-account").value = E.profile;
}

// the pickers' choices come from the backend (runner.MODELS, EFFORTS, MODES)
async function loadOptions() {
  try {
    E.options = await api("/api/options");
  } catch (e) {
    E.options = null;
  }
  const o = E.options || {};
  const fill = (id, entries, words) => $(id).replaceChildren(...Object.entries(entries || {}).map(([value, label]) => {
    const opt = el("option", "", value === "" ? "default" : (words && words[value]) || String(label).toLowerCase());
    opt.value = value;
    opt.title = label;
    return opt;
  }));
  fill("e-t-model", o.models);
  fill("e-t-effort", o.efforts);
  fill("e-t-mode", o.modes, MODE_WORDS);
  $("e-t-knobs").hidden = !o.models;
  $("e-t-effort").closest("label").hidden = !o.efforts;
  E.run = RunControls.create(o, saveRun);
  $("e-t-run").replaceChildren(E.run.root);
  if (E.task && E.task.meta) applyTaskMeta(E.task.meta, E.task.busy);
}

/* ---------------------------------------------------------------- rail */

function drawRail() {
  const g = L.groupNow(E.listing);
  $("e-now-badge").hidden = !g.needsYou.length;
  $("e-now-badge").textContent = g.needsYou.length;
  const here = location.hash;
  $("e-rail-projects").replaceChildren(...E.listing.projects.map((p) => {
    const a = el("a");
    a.href = `#project/${p.id}/tasks`;
    const hot = (p.counts || {})["needs you"] ? "needs" : (p.counts || {}).running ? "running" : "";
    const dot = el("i", "d e-dot " + hot);
    a.append(dot, el("span", "n", p.name));
    a.classList.toggle("on", here.startsWith(`#project/${p.id}`));
    dropZone(a, p.name, p.name);
    return a;
  }));
  document.querySelectorAll(".e-nav a").forEach((a) => a.classList.toggle("on", here.startsWith("#" + a.dataset.nav)));
}

/* ---------------------------------------------------------------- views */

function showView(name) {
  document.querySelectorAll(".e-view").forEach((v) => {
    const on = v.id === "v-" + name;
    if (on && v.hidden) {
      E.opening = true;
      setTimeout(() => { E.opening = false; }, 0);
      v.classList.remove("e-enter");
      void v.offsetWidth;
      v.classList.add("e-enter");
    }
    v.hidden = !on;
  });
  $("e-main").scrollTop = 0;
}

// the layout's full stop after a name, unless the name already ends a sentence
function withStop(name) {
  return /[.!?…]$/.test(String(name).trim()) ? String(name).trim() : `${String(name).trim()}.`;
}

async function route() {
  // a limits panel left open belongs to the task it was opened on
  if (E.run) E.run.root.querySelectorAll("details[open]").forEach((d) => d.removeAttribute("open"));
  const hash = location.hash.replace(/^#/, "") || localStorage.getItem(LAST) || "projects";
  const [view, a, b] = hash.split("/");
  if (!location.hash) history.replaceState(null, "", "#" + hash);
  try { localStorage.setItem(LAST, hash); } catch (e) { /* private mode */ }
  if (view !== "task") leaveTask();
  if (view !== "roadmap") clearInterval(E.skyTimer);
  drawRail();
  if (view === "project" && a) return showProject(a, b || "tasks");
  if (view === "task" && a) return showTask(a);
  if (view === "now") return showNow();
  if (view === "roadmap") return showRoadmap(a ? decodeURIComponent(hash.slice("roadmap/".length)) : "");
  return showProjects();
}

function taskRow(t, extra) {
  const li = el("li");
  li.append(el("i", "e-dot " + stateClass(t.state)), el("span", "t", t.title || "untitled task"));
  if (extra) li.appendChild(el("span", "w", extra));
  li.append(el("span", "w", t.state || ""), el("span", "w", L.ago(t.updated)), el("span", "go", "open ↗"));
  li.addEventListener("click", () => { location.hash = `#task/${t.id}`; });
  draggableTask(li, t);
  return li;
}

/* Filing tasks by dragging: a task row lifts, a project (card or rail entry)
 * takes it, and the loose tasks section takes it back out of any project. */
function draggableTask(li, t) {
  li.draggable = true;
  li.addEventListener("dragstart", (e) => {
    e.dataTransfer.setData(DRAG, t.id);
    e.dataTransfer.setData("text/plain", t.title || t.id);
    e.dataTransfer.effectAllowed = "move";
    li.classList.add("e-lifted");
    document.body.classList.add("e-dragging");
  });
  li.addEventListener("dragend", () => {
    li.classList.remove("e-lifted");
    document.body.classList.remove("e-dragging");
  });
}

function dropZone(node, folder, label) {
  node.classList.add("e-drop-zone");
  node.addEventListener("dragover", (e) => {
    if (![...e.dataTransfer.types].includes(DRAG)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    node.classList.add("e-drop-ok");
  });
  node.addEventListener("dragleave", (e) => {
    if (!node.contains(e.relatedTarget)) node.classList.remove("e-drop-ok");
  });
  node.addEventListener("drop", (e) => {
    node.classList.remove("e-drop-ok");
    const id = e.dataTransfer.getData(DRAG);
    if (!id) return;
    e.preventDefault();
    fileTask(id, folder, label);
  });
}

async function fileTask(id, folder, label) {
  const t = allTasks().find((x) => x.id === id);
  if (t && (t.project ? t.project.name : "") === folder) return;
  try {
    await post(`/api/conversations/${id}/settings`, { folder });
    await loadListing();
    route();
    toast(folder ? `filed into ${label}.` : "back in loose tasks.");
  } catch (e) {
    toast("Could not move it: " + e.message);
  }
}

function emptyRow(text) { return el("li", "e-empty-row", text); }

// projects.
function showProjects() {
  showView("projects");
  $("e-project-grid").replaceChildren(...E.listing.projects.map((p) => {
    const card = el("a", "e-card e-project");
    card.href = `#project/${p.id}/tasks`;
    const c = p.counts || {};
    const s = el("div", "s");
    const stat = (n, label, hot) => { const x = el("span", hot && n ? "hot" : ""); x.append(el("b", "", String(n)), " " + label); return x; };
    s.append(stat((p.tasks || []).length, "tasks"), stat(c.running || 0, "running", true), stat(c["needs you"] || 0, "need you", true));
    card.append(el("span", "n", withStop(p.name)), el("span", "c", p.cwd || "no working folder yet"), s);
    dropZone(card, p.name, p.name);
    return card;
  }));
  stagger($("e-project-grid"));
  if (!E.listing.projects.length) $("e-project-grid").appendChild(el("p", "e-muted", "no projects yet. make one below, or file conversations into a folder in the classic layout."));
  const loose = E.listing.loose;
  const shown = E.looseAll ? loose : loose.slice(0, 6);
  $("e-loose-list").replaceChildren(...(shown.length ? shown.map((t) => taskRow(t)) : [emptyRow("nothing loose. tidy.")]));
  stagger($("e-loose-list"));
  $("e-loose-more").hidden = E.looseAll || loose.length <= 6;
  $("e-loose-more").textContent = `+ ${loose.length - 6} more ↓`;
}

$("e-loose-more").addEventListener("click", () => { E.looseAll = true; showProjects(); });
$("e-new-project").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("e-np-status").textContent = "";
  try {
    const made = await post("/api/projects", { name: $("e-np-name").value.trim(), cwd: $("e-np-cwd").value.trim() });
    $("e-np-name").value = "";
    $("e-np-cwd").value = "";
    await loadListing();
    location.hash = `#project/${made.id}/tasks`;
  } catch (err) {
    $("e-np-status").textContent = err.message;
  }
});

// one project
function showProject(pid, tab) {
  const p = findProject(pid);
  if (!p) { toast("That project is gone"); location.hash = "#projects"; return; }
  showView("project");
  $("e-p-name").textContent = withStop(p.name);
  $("e-p-cwd").textContent = p.cwd || "no working folder: tasks start in your home folder";
  document.querySelectorAll(".e-tabs a").forEach((a) => {
    a.classList.toggle("on", a.dataset.tab === tab);
    a.href = `#project/${pid}/${a.dataset.tab}`;
  });
  ["tasks", "notes", "workflows"].forEach((t) => { $("e-p-" + t).hidden = t !== tab; });
  if (tab === "tasks") {
    const tasks = p.tasks || [];
    $("e-task-list").replaceChildren(...(tasks.length ? tasks.map((t) => taskRow(t)) : [emptyRow("no tasks yet. start one: say what you want in plain words.")]));
    stagger($("e-task-list"));
  } else if (tab === "notes") {
    loadNotes(p);
  } else {
    drawFlows(p);
  }
}

async function newTask(project, firstMessage, title) {
  try {
    // new tasks start with the model, effort and permission level last
    // picked in a task
    const d = taskDefaults();
    const start = { cwd: project ? project.cwd : "", profile: E.profile };
    ["model", "effort", "mode"].forEach((k) => { if (typeof d[k] === "string") start[k] = d[k]; });
    const meta = await post("/api/conversations", start);
    const settings = {};
    if (d.ultracode === true) settings.ultracode = true;
    if (d.limits && typeof d.limits === "object" && Object.keys(d.limits).length) settings.limits = d.limits;
    if (project) settings.folder = project.name;
    if (title) settings.title = title;
    if (Object.keys(settings).length) await post(`/api/conversations/${meta.id}/settings`, settings);
    await loadListing();
    location.hash = `#task/${meta.id}`;
    if (firstMessage) $("e-t-input").value = firstMessage;
    setTimeout(() => $("e-t-input").focus(), 60);
  } catch (e) {
    toast("Could not start a task: " + e.message);
  }
}
$("e-new-task").addEventListener("click", () => newTask(currentProject()));
function currentProject() {
  const m = location.hash.match(/^#project\/([^/]+)/);
  return m ? findProject(m[1]) : null;
}

// notes.
async function loadNotes(p) {
  let notes = [];
  try { notes = (await api(`/api/projects/${p.id}/notes`)).notes || []; } catch (e) { toast(e.message); }
  $("e-note-list").replaceChildren(...(notes.length ? notes.map((n) => {
    const li = el("li");
    li.append(el("span", "t", n.name), el("span", "w", L.ago(n.updated)));
    li.addEventListener("click", () => openNote(p, n.name));
    return li;
  }) : [emptyRow("no notes yet.")]));
  if (!$("e-note-form").hidden && E.note && !notes.some((n) => n.name === E.note)) $("e-note-form").hidden = true;
}

async function openNote(p, name) {
  E.note = name || "";
  $("e-note-form").hidden = false;
  $("e-note-name").value = name || "";
  $("e-note-text").value = "";
  $("e-note-delete").hidden = !name;
  $("e-note-status").textContent = "";
  if (name) {
    try { $("e-note-text").value = (await api(`/api/projects/${p.id}/notes/${encodeURIComponent(name)}`)).text || ""; } catch (e) { toast(e.message); }
  }
  $("e-note-preview").innerHTML = markdown($("e-note-text").value);
  (name ? $("e-note-text") : $("e-note-name")).focus();
}

$("e-new-note").addEventListener("click", () => { const p = currentProject(); if (p) openNote(p, ""); });
$("e-note-text").addEventListener("input", () => { $("e-note-preview").innerHTML = markdown($("e-note-text").value); });
$("e-note-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const p = currentProject();
  if (!p) return;
  try {
    const saved = await post(`/api/projects/${p.id}/notes`, { name: $("e-note-name").value.trim(), text: $("e-note-text").value });
    if (E.note && saved.name !== E.note) {
      await api(`/api/projects/${p.id}/notes/${encodeURIComponent(E.note)}`, { method: "DELETE" }).catch(() => {});
    }
    E.note = saved.name;
    $("e-note-delete").hidden = false;
    $("e-note-status").textContent = "saved ✓";
    loadNotes(p);
  } catch (err) {
    $("e-note-status").textContent = err.message;
  }
});
$("e-note-delete").addEventListener("click", async () => {
  const p = currentProject();
  if (!p || !E.note || !await ForgeDialog.confirm(`Delete the note "${E.note}"?`)) return;
  try {
    await api(`/api/projects/${p.id}/notes/${encodeURIComponent(E.note)}`, { method: "DELETE" });
    E.note = "";
    $("e-note-form").hidden = true;
    loadNotes(p);
  } catch (e) { toast(e.message); }
});

// workflows.
function drawFlows(p) {
  const flows = p.workflows || [];
  $("e-flow-list").replaceChildren(...(flows.length ? flows.map((f, i) => {
    const li = el("li");
    const run = el("button", "e-btn e-primary", "run ↗");
    const edit = el("button", "e-btn e-quiet", "edit");
    const del = el("button", "e-btn e-quiet", "×");
    del.title = "Delete this workflow";
    li.append(el("span", "t", f.name), el("span", "e-steps", `${f.steps.length} step${f.steps.length === 1 ? "" : "s"}`), edit, del, run);
    run.addEventListener("click", async (e) => {
      e.stopPropagation();
      try {
        const meta = await post(`/api/projects/${p.id}/workflows/${i}/run`);
        await loadListing();
        location.hash = `#task/${meta.id}`;
      } catch (err) { toast("Could not run it: " + err.message); }
    });
    edit.addEventListener("click", (e) => { e.stopPropagation(); editFlow(f, i); });
    li.addEventListener("click", () => editFlow(f, i));
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      if (!await ForgeDialog.confirm(`Delete the workflow "${f.name}"?`)) return;
      await saveFlows(p, flows.filter((_, k) => k !== i));
    });
    return li;
  }) : [emptyRow("no workflows yet. save the steps you repeat.")]));
  if (E.flowEdit >= flows.length) editFlow(null, -1);
}

function editFlow(flow, index) {
  E.flowEdit = index;
  $("e-flow-title").textContent = flow ? `edit ${flow.name}.` : "+ new workflow";
  $("e-flow-name").value = flow ? flow.name : "";
  $("e-flow-steps").value = flow ? flow.steps.join("\n") : "";
  $("e-flow-cancel").hidden = !flow;
  $("e-flow-status").textContent = "";
  if (flow) $("e-flow-name").focus();
}

async function saveFlows(p, flows) {
  try {
    await post(`/api/projects/${p.id}`, { workflows: flows });
    await loadListing();
    drawFlows(findProject(p.id) || p);
    return true;
  } catch (e) {
    $("e-flow-status").textContent = e.message;
    return false;
  }
}

$("e-flow-cancel").addEventListener("click", () => editFlow(null, -1));
$("e-flow-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const p = currentProject();
  if (!p) return;
  const flow = { name: $("e-flow-name").value.trim(), steps: $("e-flow-steps").value.split("\n").map((s) => s.trim()).filter(Boolean) };
  const flows = (p.workflows || []).slice();
  if (E.flowEdit >= 0) flows[E.flowEdit] = flow; else flows.push(flow);
  if (await saveFlows(p, flows)) { editFlow(null, -1); $("e-flow-status").textContent = "saved ✓"; }
});

// running / needs you.
function showNow() {
  showView("now");
  const g = L.groupNow(E.listing);
  $("e-now-needs").replaceChildren(...(g.needsYou.length ? g.needsYou.map((t) => taskRow(t, t.project || "loose")) : [emptyRow("nothing waiting on you. enjoy.")]));
  $("e-now-running").replaceChildren(...(g.running.length ? g.running.map((t) => taskRow(t, t.project || "loose")) : [emptyRow("nothing running right now.")]));
  stagger($("e-now-needs"));
  stagger($("e-now-running"));
}

/* ---------------------------------------------------------------- a task */

function leaveTask() {
  E.poll++;
  E.task = null;
}

const taskHooks = {
  scroll(view, force) {
    if (view.bulk || !E.task || E.task.view !== view) return;
    const log = $("e-t-log");
    if (force || log.scrollHeight - log.scrollTop - log.clientHeight < 160) log.scrollTop = log.scrollHeight;
  },
  shown() { $("e-t-empty").hidden = true; },
  assistant(message) {
    if (!E.task) return;
    E.task.plan = L.planStep(E.task.plan, message);
    E.task.planDirty = true;
  },
  browserTool() { window.parent.postMessage({ forge: "open", role: "browser" }, "*"); },
};

async function showTask(cid) {
  if (E.task && E.task.id === cid) { showView("task"); return; }
  leaveTask();
  showView("task");
  const task = { id: cid, view: ClaudeCommon.newView(cid), plan: L.emptyPlan(), planDirty: true, files: [], meta: null, busy: false };
  E.task = task;
  const poll = E.poll;
  $("e-t-empty").hidden = false;
  $("e-t-log").replaceChildren($("e-t-empty"), task.view.box);
  $("e-t-input").value = "";
  drawChips();
  const known = allTasks().find((t) => t.id === cid);
  $("e-t-back").href = known && known.project ? `#project/${known.project.id}/tasks` : "#projects";
  $("e-t-back").textContent = known && known.project ? `← ${known.project.name}` : "← projects";
  try {
    const body = await api(`/api/conversations/${cid}/events?after=-1`);
    if (poll !== E.poll) return;
    task.view.bulk = true;
    try { body.events.forEach((ev) => ClaudeCommon.draw(ev, task.view, taskHooks)); } finally { task.view.bulk = false; }
    if (body.events.length) task.view.seq = body.events[body.events.length - 1].seq;
    task.view.boot = body.boot;
    applyTaskMeta(body.meta, body.busy);
    taskHooks.scroll(task.view, true);
  } catch (e) {
    toast("Could not open the task: " + e.message);
    return;
  }
  // opening it is seeing it: the pill and the badges follow at once
  post(`/api/conversations/${cid}/seen`).then(loadListing)
    .then(() => { if (E.task === task) applyTaskMeta(task.meta, task.busy); }).catch(() => {});
  followTask(poll);
}

async function followTask(poll) {
  while (poll === E.poll && E.task) {
    const task = E.task;
    try {
      const body = await api(`/api/conversations/${task.id}/events?after=${task.view.seq}&wait=25&boot=${task.view.boot || ""}`);
      if (poll !== E.poll) return;
      if (body.reset) {
        // the backend restarted: event numbers start again; open it afresh
        leaveTask();
        showTask(task.id);
        return;
      }
      body.events.forEach((ev) => ClaudeCommon.draw(ev, task.view, taskHooks));
      if (body.events.length) task.view.seq = body.events[body.events.length - 1].seq;
      const was = task.busy;
      applyTaskMeta(body.meta, body.busy);
      if (was !== body.busy) {
        loadListing();
        if (!body.busy) post(`/api/conversations/${task.id}/seen`).catch(() => {});
      }
    } catch (e) {
      if (poll !== E.poll) return;
      $("e-t-status").textContent = "lost the backend for a moment; trying again…";
      await new Promise((r) => setTimeout(r, 3000));
    }
  }
}

function applyTaskMeta(meta, busy) {
  const task = E.task;
  if (!task || !meta) return;
  task.meta = meta;
  task.busy = busy;
  if (document.activeElement !== $("e-t-title")) $("e-t-title").value = meta.title || "";
  const known = allTasks().find((t) => t.id === task.id);
  const state = busy ? "running" : known ? known.state : "quiet";
  $("e-t-state").textContent = busy ? "running…" : state === "needs you" ? "needs you" : state;
  $("e-t-state").className = "e-pill " + stateClass(busy ? "running" : state);
  $("e-t-stop").hidden = !busy;
  $("e-t-status").textContent = busy ? "claude is working. anything you send now joins this turn." : "";
  if (E.run && !E.knobsBusy) E.run.apply(meta);
  KNOBS.forEach((id) => {
    const pick = $(id);
    if (document.activeElement === pick || E.knobsBusy) return;
    pick.value = meta[pick.dataset.key] || "";
    if (pick.selectedIndex < 0 && pick.options.length) pick.selectedIndex = 0;
  });
  const cost = meta.cost_usd ? `$${Number(meta.cost_usd).toFixed(2)} at API list prices (not billed)` : "";
  const rows = [["folder", meta.cwd], ["account", meta.profile || "default"], ["model", meta.model || "claude code's default"], ["worth", cost]];
  $("e-t-meta").replaceChildren(...rows.filter((r) => r[1]).flatMap(([k, v]) => [el("dt", "", k), el("dd", "", v)]));
  if (task.planDirty) drawPlan(task.plan);
  task.planDirty = false;
}

function drawPlan(plan) {
  $("e-t-progress").hidden = !plan.total;
  $("e-t-bar").style.width = plan.total ? `${Math.round((plan.done / plan.total) * 100)}%` : "0";
  $("e-t-count").textContent = `${plan.done} of ${plan.total} done`;
  $("e-t-now").textContent = plan.now ? plan.now.toLowerCase() + "…" : plan.total && plan.done === plan.total ? "all done ✓" : "";
  $("e-t-todos").replaceChildren(...plan.todos.map((t) => el("li", t.status, t.content)));
  $("e-t-plan-box").hidden = !plan.plan;
  $("e-t-plan").innerHTML = plan.plan ? markdown(plan.plan) : "";
  if (plan.plan && !plan.total) $("e-t-plan-box").open = true;
  $("e-t-noplan").hidden = !!(plan.total || plan.plan);
}

function drawChips() {
  const task = E.task;
  const files = task ? task.files : [];
  $("e-t-chips").replaceChildren(...files.map((f, i) => {
    const chip = fileChip(task.id, f.name);
    const x = el("button", "", "×");
    x.title = "Remove";
    x.addEventListener("click", () => { task.files.splice(i, 1); drawChips(); });
    chip.appendChild(x);
    return chip;
  }));
}

async function sendTask() {
  const task = E.task;
  const text = $("e-t-input").value;
  // one send at a time: a double click or a held Enter must not send twice
  if (!task || task.sending || (!text.trim() && !task.files.length)) return;
  task.sending = true;
  $("e-t-send").disabled = true;
  const files = task.files;
  $("e-t-input").value = "";
  task.files = [];
  drawChips();
  autosize();
  try {
    await post(`/api/conversations/${task.id}/send`, { text, files: files.map((f) => f.name) });
    applyTaskMeta(task.meta, true);
  } catch (e) {
    // put it back so nothing typed is lost (unless a new message was started)
    if (E.task === task && !$("e-t-input").value) {
      $("e-t-input").value = text;
      task.files = files;
      drawChips();
      autosize();
    }
    $("e-t-status").textContent = "not sent: " + e.message;
  } finally {
    task.sending = false;
    $("e-t-send").disabled = false;
  }
}

async function attach(fileList) {
  const task = E.task;
  if (!task) return;
  for (const file of fileList) {
    try {
      task.files.push(await post(`/api/conversations/${task.id}/files`, { name: file.name || "pasted.png", data: await readBase64(file) }));
      drawChips();
    } catch (e) {
      toast(`Could not attach ${file.name}: ${e.message}`);
    }
  }
}

function autosize() {
  const t = $("e-t-input");
  t.style.height = "auto";
  t.style.height = `${Math.min(220, t.scrollHeight)}px`;
}

function knobNote(text) {
  const n = $("e-t-knob-note");
  n.textContent = text;
  n.classList.add("show");
  clearTimeout(knobNote.timer);
  knobNote.timer = setTimeout(() => n.classList.remove("show"), 2600);
}

document.querySelectorAll("#e-t-knobs select").forEach((pick) => pick.addEventListener("change", async () => {
  const task = E.task;
  if (!task) return;
  const key = pick.dataset.key;
  const value = pick.value; // read now: a reply to another picker may redraw it
  const knob = pick.closest(".e-knob");
  E.knobsBusy = (E.knobsBusy || 0) + 1;
  try {
    const meta = await post(`/api/conversations/${task.id}/settings`, { [key]: value });
    if (E.task === task) task.meta = meta;
    const d = taskDefaults();
    d[key] = value;
    try { localStorage.setItem(DEFAULTS, JSON.stringify(d)); } catch (e) { /* private mode */ }
    knobNote(task.busy ? "saved. it applies from your next message." : "saved. new tasks start like this too.");
    knob.classList.remove("e-saved");
    void knob.offsetWidth;
    knob.classList.add("e-saved");
  } catch (e) {
    toast("Could not change it: " + e.message);
  }
  // redraw only from the last reply, which has every change in it
  E.knobsBusy -= 1;
  if (!E.knobsBusy && E.task === task) applyTaskMeta(task.meta, task.busy);
}));

// the Normal / Ultracode switch and the limits fold (run_controls.js)
async function saveRun(changes) {
  const task = E.task;
  if (!task) return;
  E.knobsBusy = (E.knobsBusy || 0) + 1;
  try {
    const meta = await post(`/api/conversations/${task.id}/settings`, changes);
    if (E.task === task) task.meta = meta;
    const d = taskDefaults();
    if ("ultracode" in changes) d.ultracode = !!meta.ultracode;
    if ("limits" in changes) d.limits = meta.limits || {};
    try { localStorage.setItem(DEFAULTS, JSON.stringify(d)); } catch (e) { /* private mode */ }
    knobNote(task.busy ? "saved. it applies from your next message." : "saved. new tasks start like this too.");
  } catch (e) {
    toast("Could not change it: " + e.message);
  }
  E.knobsBusy -= 1;
  if (!E.knobsBusy && E.task === task) applyTaskMeta(task.meta, task.busy);
}

// files dropped on the chat attach to the next message, like paste and ↑
const hasFiles = (e) => [...((e.dataTransfer && e.dataTransfer.types) || [])].includes("Files");
$("e-t-chat").addEventListener("dragover", (e) => {
  if (!hasFiles(e) || !E.task) return;
  e.preventDefault();
  e.dataTransfer.dropEffect = "copy";
  $("e-t-chat").classList.add("e-drop-files");
});
$("e-t-chat").addEventListener("dragleave", (e) => {
  if (!$("e-t-chat").contains(e.relatedTarget)) $("e-t-chat").classList.remove("e-drop-files");
});
$("e-t-chat").addEventListener("drop", (e) => {
  $("e-t-chat").classList.remove("e-drop-files");
  if (!hasFiles(e) || !E.task) return;
  e.preventDefault();
  attach([...e.dataTransfer.files]);
});
dropZone($("e-loose"), "", "loose tasks");

$("e-t-send").addEventListener("click", sendTask);
$("e-t-stop").addEventListener("click", () => { if (E.task) post(`/api/conversations/${E.task.id}/stop`).catch((e) => toast(e.message)); });
$("e-t-input").addEventListener("keydown", (e) => {
  if (e.isComposing) return;
  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendTask(); }
});
$("e-t-input").addEventListener("input", autosize);
$("e-t-file").addEventListener("change", (e) => { attach([...e.target.files]); e.target.value = ""; });
// the same paste rules as the classic page: files and images attach; a paste
// that brings no text has the backend read the desktop clipboard (WebKitGTK
// does not always hand a copied screenshot to the page)
$("e-t-input").addEventListener("paste", (e) => {
  const dt = e.clipboardData;
  const images = dt ? [...dt.files] : [];
  if (!images.length && dt) [...dt.items].forEach((item) => { const f = item.kind === "file" && item.getAsFile(); if (f) images.push(f); });
  if (images.length) { e.preventDefault(); attach(images); return; }
  const types = dt ? [...dt.types] : [];
  if (types.includes("text/plain")) return;
  if (types.some((t) => t.startsWith("image/"))) e.preventDefault();
  const task = E.task;
  if (task) post(`/api/conversations/${task.id}/paste-image`).then((f) => { task.files.push(f); drawChips(); }).catch(() => {});
});
$("e-t-title").addEventListener("change", async () => {
  if (!E.task) return;
  try { await post(`/api/conversations/${E.task.id}/settings`, { title: $("e-t-title").value.trim() }); loadListing(); } catch (e) { toast(e.message); }
});
$("e-t-log").addEventListener("click", async (e) => {
  const link = e.target.closest("a[data-url]");
  if (!link) return;
  e.preventDefault();
  try {
    window.parent.postMessage({ forge: "open", role: "browser" }, "*");
    const answer = await post("/api/open-link", { url: link.dataset.url });
    if (!answer.ok) toast(answer.error || "The Browser did not open it");
  } catch (err) { toast(err.message); }
});

/* ---------------------------------------------------------------- roadmap */

const STAR = { "done+checked": "lit", "done not checked": "dim", "in progress": "prog", blocked: "block" };
const SAY = { "done+checked": "done and checked", "done not checked": "done, not checked yet", "in progress": "in progress",
  blocked: "blocked: waiting on something", "not done": "not done yet", moved: "handed on" };
const SVG = "http://www.w3.org/2000/svg";
const svg = (tag, attrs, text) => {
  const n = document.createElementNS(SVG, tag);
  Object.entries(attrs || {}).forEach(([k, v]) => n.setAttribute(k, v));
  if (text !== undefined) n.textContent = text;
  return n;
};

// #roadmap/<brief file>|<id> opens with that star picked
async function showRoadmap(star) {
  showView("roadmap");
  await loadRoadmap();
  const node = star && [...document.querySelectorAll("#e-sky .star")].find((n) => n.dataset.key === star);
  if (node) node.dispatchEvent(new MouseEvent("click"));
  clearInterval(E.skyTimer);
  E.skyTimer = setInterval(() => { if (ForgeIdle.shown()) loadRoadmap(); }, 30000);
}

async function loadRoadmap() {
  try {
    E.roadmap = await api("/api/roadmap");
  } catch (e) {
    toast("Could not read the roadmap: " + e.message);
    return;
  }
  drawSky();
  drawNotes();
}

function skySessions() {
  const all = ((E.roadmap && E.roadmap.sessions) || []).filter((s) => s.items.length);
  if (E.when === "all") return all;
  const latest = all.reduce((d, s) => (s.date > d ? s.date : d), "");
  return all.filter((s) => s.date === latest);
}

function drawSky() {
  const sky = $("e-sky");
  const width = Math.max(320, Math.round(sky.parentElement.clientWidth || 900));
  const lay = L.layout(skySessions(), width);
  const height = Math.max(lay.height, 280);
  sky.setAttribute("viewBox", `0 0 ${width} ${height}`);
  sky.style.height = height + "px";
  sky.replaceChildren();
  const defs = svg("defs");
  const glow = svg("filter", { id: "e-glow", x: "-200%", y: "-200%", width: "500%", height: "500%" });
  glow.append(svg("feGaussianBlur", { stdDeviation: "2.6", result: "b" }));
  const merge = svg("feMerge");
  merge.append(svg("feMergeNode", { in: "b" }), svg("feMergeNode", { in: "SourceGraphic" }));
  glow.append(merge);
  defs.append(glow);
  sky.append(defs);
  // dust: faint background stars, the same every time
  let seed = 7;
  const rnd = () => { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
  for (let i = 0; i < Math.round((width * height) / 5200); i++) {
    sky.append(svg("circle", { class: "dust", cx: (rnd() * width).toFixed(1), cy: (rnd() * height).toFixed(1),
      r: (rnd() * 0.9 + 0.2).toFixed(2), opacity: (rnd() * 0.5 + 0.12).toFixed(2) }));
  }
  if (!lay.groups.length) {
    sky.append(svg("text", { class: "sub", x: width / 2, y: height / 2, "text-anchor": "middle" }, "no session briefs with asks yet."));
    return;
  }
  for (const g of lay.groups) {
    const s = g.session;
    const name = (s.name || s.topic || s.file).toLowerCase().replace(/[.\s]+$/, "") + ".";
    sky.append(svg("text", { class: "name", x: g.x + 22, y: g.y + 30 }, name));
    sky.append(svg("text", { class: "sub", x: g.x + 22, y: g.y + 48 },
      `${s.slot || "session"} · ${s.date} · ${s.counts.done} of ${s.counts.total} lit`));
    // the constellation's lines (enjoy_logic.js); lit where both ends are done
    for (const [i, j] of g.links) {
      const a = g.stars[i], b = g.stars[j];
      const lit = STAR[a.item.state] === "lit" && STAR[b.item.state] === "lit";
      sky.append(svg("line", { class: "link" + (lit ? " lit" : ""), x1: a.x, y1: a.y, x2: b.x, y2: b.y }));
    }
    for (const st of g.stars) {
      const cls = st.item.tag === "constraint" ? "constraint" : STAR[st.item.state] || "off";
      const c = svg("circle", { class: `star ${cls}`, cx: st.x, cy: st.y, r: st.r, tabindex: "0",
        "data-key": `${s.file}|${st.id}` });
      c.append(svg("title", {}, `${st.id}: ${st.item.quote || st.item.meaning}`));
      c.addEventListener("click", () => pickStar(s, st.item, c));
      c.addEventListener("keydown", (e) => { if (e.key === "Enter") pickStar(s, st.item, c); });
      sky.append(c);
    }
  }
}

function pickStar(session, item, node) {
  document.querySelectorAll("#e-sky .star.picked").forEach((n) => n.classList.remove("picked"));
  node.classList.add("picked");
  const card = $("e-star");
  const close = el("button", "x", "×");
  close.title = "Close";
  close.addEventListener("click", () => { card.hidden = true; node.classList.remove("picked"); });
  const who = session.name ? `${session.name} (${session.slot})` : session.slot || session.topic;
  const st = el("span", "st", SAY[item.state] || item.state);
  st.style.color = { lit: "#ffd36e", dim: "#d6c79a", prog: "#9ecbff", block: "#ff8f7a" }[STAR[item.state]] || "#8d98bd";
  const parts = [close, el("div", "k", `${item.id} · ${who}${item.label ? " · " + item.label : ""}`)];
  if (item.quote) parts.push(el("div", "k", "emerson said"), el("q", "", item.quote));
  if (item.meaning) parts.push(el("div", "k", "which means"), el("div", "", item.meaning));
  parts.push(el("div", "k", "state"), st);
  if (item.moved_to) parts.push(el("div", "k", "handed to"), el("div", "", item.moved_to));
  if (item.note) parts.push(el("div", "k", "latest word"), el("div", "", item.note.length > 700 ? item.note.slice(0, 700) + "…" : item.note));
  parts.push(el("div", "k", "brief"), el("div", "e-mono", session.file));
  card.replaceChildren(...parts);
  card.hidden = false;
}

function drawNotes() {
  const notes = (E.roadmap && E.roadmap.notes) || [];
  $("e-notes").replaceChildren(...(notes.length ? notes.map((n) => {
    const li = el("li");
    li.append(el("span", "who", `${n.from} → ${n.to || "everyone"}`), el("span", "t", n.text), el("span", "w", L.ago(n.t)));
    return li;
  }) : [emptyRow("the board is quiet.")]));
}

document.querySelectorAll(".e-filters [data-when]").forEach((b) => b.addEventListener("click", () => {
  E.when = b.dataset.when;
  document.querySelectorAll(".e-filters [data-when]").forEach((x) => x.classList.toggle("on", x === b));
  $("e-star").hidden = true;
  drawSky();
}));
addEventListener("resize", () => {
  clearTimeout(drawSky.timer);
  drawSky.timer = setTimeout(() => { if (!$("v-roadmap").hidden && E.roadmap) drawSky(); }, 150);
});

/* ---------------------------------------------------------------- wiring */

$("e-account").addEventListener("change", (e) => {
  E.profile = e.target.value;
  try { localStorage.setItem(PROFILE, E.profile); } catch (err) { /* private mode */ }
});
$("e-classic").addEventListener("click", () => {
  try { localStorage.setItem("claude.layout", "classic"); } catch (e) { /* private mode */ }
});
try { localStorage.setItem("claude.layout", "enjoy"); } catch (e) { /* private mode */ }
addEventListener("hashchange", route);
// task states change as work finishes elsewhere; the list is small and local
setInterval(() => {
  if (!ForgeIdle.shown()) return;
  loadListing().then(() => {
    const view = (location.hash.match(/^#(\w+)/) || [])[1];
    if (view === "now") showNow();
    else if (view === "projects") showProjects();
  });
}, 8000);

(async () => {
  await Promise.all([loadListing(), loadProfiles()]);
  loadOptions();
  route();
})();
