/* Relay page: reads /api/state every 4 s and writes through the /api forms.
   All text from mail or sessions goes in through textContent (esc() for the
   few template strings), never as HTML. */

const $ = (id) => document.getElementById(id);
const openTails = new Set();
const openStates = new Set();
let last = null;
let formsFilled = false;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function ago(sec) {
  sec = Math.max(0, Math.round(sec));
  if (sec < 90) return sec + "s";
  if (sec < 5400) return Math.round(sec / 60) + "m";
  return Math.floor(sec / 3600) + "h" + String(Math.floor((sec % 3600) / 60)).padStart(2, "0") + "m";
}

async function api(path, body) {
  const res = await fetch("/api" + path, {
    method: body === undefined ? "GET" : "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await errText(res, "Request failed"));
  return res.json();
}

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

function button(label, onClick, cls = "btn") {
  const b = el("button", cls, label);
  b.type = "button";
  b.addEventListener("click", onClick);
  return b;
}

function renderHeader(s) {
  const boss = $("boss");
  if (s.boss_age === null) { boss.textContent = "boss not started"; boss.className = "pill bad"; }
  else if (s.boss_age > 300) { boss.textContent = "boss silent " + ago(s.boss_age); boss.className = "pill bad"; }
  else { boss.textContent = "boss ticking"; boss.className = "pill good"; }
  $("wait").textContent = s.wait_reason ? "waiting: " + s.wait_reason : "";
  $("pause").textContent = s.paused ? "Resume" : "Pause";
  $("pause").className = s.paused ? "btn btn-primary" : "btn";
  const box = $("meters");
  box.replaceChildren();
  for (const [name, m] of Object.entries(s.meters)) {
    const wrap = el("div", "meter");
    if (m.five === null || m.five === undefined) {
      wrap.textContent = name + ": no reading";
    } else {
      wrap.textContent = `${name}: 5h ${Math.round(m.five)}% · week ${Math.round(m.week || 0)}%`;
      const track = el("div", "track");
      // Two subscriptions: a full account just rests while another has room;
      // red only when no account can launch.
      const room = s.room || [];
      const resting = !room.includes(name);
      const look = !resting ? (m.five >= 70 ? " warn" : "") : room.length ? " rest" : " bad";
      const fill = el("div", "fill" + look);
      if (resting && room.length) wrap.append(" · resting");
      fill.style.width = Math.min(100, m.five) + "%";
      track.append(fill);
      wrap.append(track);
    }
    box.append(wrap);
  }
}

async function toggleTail(runId, holder) {
  if (openTails.has(runId)) { openTails.delete(runId); holder.replaceChildren(); return; }
  openTails.add(runId);
  await fillTail(runId, holder);
}

async function fillTail(runId, holder) {
  try {
    const data = await api(`/runs/${runId}/tail`);
    const pre = el("pre", "tail", data.lines.join("\n") || "(nothing yet)");
    holder.replaceChildren(pre);
    pre.scrollTop = pre.scrollHeight;
  } catch (e) { holder.textContent = e.message; }
}

// the name the Claude app, Crew Room and the Board show: "Mika (relay-59-work)"
function sessionText(x) {
  return x.session_label ? `${x.session_label} (${x.session_name})` : x.session_name;
}

function renderRunning(s) {
  const box = $("running");
  $("run-count").textContent = `(${s.running.length} of ${s.settings.max_sessions})`;
  box.replaceChildren();
  if (!s.running.length) { box.append(el("div", "empty", "Nothing running.")); return; }
  const tasks = Object.fromEntries(s.tasks.map((t) => [String(t.id), t]));
  for (const run of s.running) {
    const task = tasks[String(run.task)];
    const item = el("div", "item");
    const head = el("div", "head");
    // task number and a short description; the persona is the small tag
    const who = { name: run.session_name, label: run.session_label };
    const name = task
      ? ForgeSessionTitle.displayName({ ...who, relay: { task: task.id, title: task.title } })
      : `Planning goal ${run.goal}`;
    const title = el("span", "title", name);
    if (task) title.title = `#${task.id} ${task.title}`;
    head.append(title);
    head.append(el("span", "pill", `${run.kind} · ${run.account} · ${run.effort}`));
    const tag = task ? ForgeSessionTitle.personaTag({ ...who, relay: { task: task.id, title: task.title } }) : sessionText(run);
    if (tag) head.append(el("span", "muted", tag));
    const holder = el("div");
    head.append(button("Live", () => toggleTail(run.id, holder)));
    if (task) head.append(button("Stop", () => act(`/tasks/${task.id}/stop`), "btn btn-danger"));
    item.append(head);
    item.append(el("div", "meta",
      `${ago(run.age)} · ${Math.round(run.context_tokens / 1000)}k context · ${run.output_tokens} out · last: ${run.last_action || "starting"}`));
    item.append(holder);
    if (openTails.has(run.id)) fillTail(run.id, holder);
    box.append(item);
  }
}

const GROUPS = [
  ["Waiting on you", (t) => ["blocked", "parked"].includes(t.status)],
  ["Queued and running", (t) => ["queued", "running", "handing_over", "reviewing"].includes(t.status)],
  ["Finished", (t) => ["done", "stopped"].includes(t.status)],
];

function renderTasks(s) {
  const box = $("tasks");
  box.replaceChildren();
  if (!s.tasks.length) { box.append(el("div", "empty", "No tasks yet. Write one on the left or mail the Relay address.")); return; }
  for (const [label, test] of GROUPS) {
    let list = s.tasks.filter(test);
    if (label === "Finished") list = list.slice(-15).reverse();
    if (!list.length) continue;
    box.append(el("div", "group-title", label));
    for (const t of list) {
      const item = el("div", "item");
      const head = el("div", "head");
      head.append(el("span", "title", `#${t.id} ${t.title}`));
      const cls = { done: "good", blocked: "warn", parked: "bad", running: "good" }[t.status] || "";
      head.append(el("span", "pill " + cls, t.status + (t.priority === "important" ? " · important" : "")));
      if (["queued", "running", "handing_over", "reviewing"].includes(t.status)) head.append(button("Stop", () => act(`/tasks/${t.id}/stop`), "btn btn-danger"));
      if (["blocked", "parked", "stopped", "done"].includes(t.status)) head.append(button("Run again", () => act(`/tasks/${t.id}/retry`)));
      // which State boxes are open lives outside the list, which the 4 s
      // refresh rebuilds, or an open one shuts again within 4 s
      const details = el("div");
      const showState = () => details.replaceChildren(openStates.has(t.id) ? el("pre", "", t.state || "(empty)") : "");
      head.append(button("State", () => {
        if (!openStates.delete(t.id)) openStates.add(t.id);
        showState();
      }));
      showState();
      item.append(head);
      const bits = [];
      if (t.goal && t.goal !== "inbox") bits.push("goal " + t.goal);
      if (t.source) bits.push("from " + t.source);
      if (t.ran_on) bits.push(`${t.ran_on} · ${t.effort_used}`);
      if (t.attempts && t.attempts !== "0") bits.push(`${t.attempts} session(s)`);
      if (t.session_name) bits.push("last session " + sessionText(t));
      if (t.note) bits.push(t.note);
      item.append(el("div", "meta", bits.join(" · ")));
      item.append(details);
      box.append(item);
    }
  }
}

function renderGoals(s) {
  const box = $("goals");
  box.replaceChildren();
  const select = $("t-goal");
  const chosen = select.value;
  select.replaceChildren(el("option", "", "No goal"));
  select.firstChild.value = "";
  if (!s.goals.length) box.append(el("div", "empty", "No goals yet."));
  for (const g of s.goals) {
    if (g.status === "active") {
      const opt = el("option", "", g.title);
      opt.value = g.slug;
      select.append(opt);
    }
    const mine = s.tasks.filter((t) => t.goal === g.slug);
    const done = mine.filter((t) => t.status === "done").length;
    const item = el("div", "item");
    const head = el("div", "head");
    head.append(el("span", "title", g.title));
    head.append(el("span", "pill " + ({ done: "good", stuck: "bad", paused: "warn" }[g.status] || ""), g.status));
    if (g.status === "active") head.append(button("Pause", () => act(`/goals/${g.slug}/pause`)));
    else if (g.status !== "done") head.append(button("Resume", () => act(`/goals/${g.slug}/resume`)));
    if (g.status !== "done") head.append(button("Mark done", () => act(`/goals/${g.slug}/done`)));
    item.append(head);
    item.append(el("div", "meta", `${done} of ${mine.length} tasks done · check: ${g.check || "none"}${g.last_check ? " (last " + g.last_check + ")" : ""}`));
    box.append(item);
  }
  select.value = chosen;
}

function renderEvents(s) {
  const box = $("events");
  box.replaceChildren();
  for (const e of s.events) {
    const row = el("div");
    const when = new Date(e.at * 1000).toLocaleString([], { weekday: "short", hour: "2-digit", minute: "2-digit" });
    row.append(el("span", "muted", when + " "), el("span", "k", e.kind), document.createTextNode(e.text));
    box.append(row);
  }
}

function pair(range, number, value) {
  $(range).value = value; $(number).value = value;
  $(range).oninput = () => { $(number).value = $(range).value; };
  $(number).oninput = () => { $(range).value = $(number).value; };
}

function fillForms(s) {
  const st = s.settings;
  $("m-address").value = st.mail_address;
  $("m-senders").value = (st.allowed_senders || []).join(", ");
  $("m-report").value = st.report_to;
  $("m-digest").value = st.digest_time;
  $("m-enabled").checked = st.mail_enabled;
  pair("s-max", "s-max-n", st.max_sessions);
  pair("s-stall", "s-stall-n", st.stall_minutes);
  pair("s-review", "s-review-n", st.review_after_rounds);
  pair("s-every", "s-every-n", st.review_every_rounds);
  $("s-folder").value = st.default_folder;
  const acct = $("t-account");
  for (const name of Object.keys(s.meters)) {
    const opt = el("option", "", name);
    opt.value = name;
    acct.append(opt);
  }
  formsFilled = true;
}

function renderMailState(s) {
  const pill = $("mail-state");
  pill.textContent = s.mail_ready ? "on" : s.settings.mail_enabled ? "needs setup" : "off";
  pill.className = "pill " + (s.mail_ready ? "good" : s.settings.mail_enabled ? "warn" : "");
  $("m-pw-state").textContent = s.mail_password_set ? "(saved; paste a new one to replace it)" : "(not set)";
}

async function refresh() {
  try {
    const s = await api("/state");
    last = s;
    renderHeader(s);
    renderRunning(s);
    renderTasks(s);
    renderGoals(s);
    renderEvents(s);
    renderMailState(s);
    if (!formsFilled) fillForms(s);
  } catch (e) {
    $("boss").textContent = "page cannot reach the backend";
    $("boss").className = "pill bad";
  }
}

async function act(path, body = {}) {
  try {
    const r = await api(path, body);
    if (r.message) toast(r.message);
  } catch (e) { toast(e.message, "error"); }
  refresh();
}

$("pause").addEventListener("click", () => act(last && last.paused ? "/resume" : "/pause"));

// Files for the new request (Relay task 118): pasted, dropped on the box or
// picked; saved by /api/attach and named in the request by path.
let taskFiles = [];
function drawTaskFiles() {
  const box = $("t-files");
  box.replaceChildren(...taskFiles.map((f, i) => {
    const chip = el("span", "t-file", f.name);
    chip.append(button("×", () => { taskFiles.splice(i, 1); drawTaskFiles(); }, "t-unfile"));
    return chip;
  }));
}
let attach = null;
if (window.ForgeAttach) {
  attach = ForgeAttach.wire({
    box: $("t-text"),
    zone: $("t-text").closest(".card") || $("t-text"),
    picker: $("t-file"),
    upload: async (file) => api("/attach", { name: file.name || "pasted.png", data: await ForgeAttach.readBase64(file) }),
    pasteDesktop: () => api("/attach/paste-image", {}),
    onAdd: (saved) => { taskFiles.push(saved); drawTaskFiles(); },
    onError: (msg) => toast(msg, "error"),
  });
}

$("t-add").addEventListener("click", async () => {
  const button = $("t-add");
  // a double click would queue the task twice
  if (button.disabled) return;
  if (attach && attach.busy()) { toast("A file is still uploading; send again in a moment", "error"); return; }
  // a file that lands while the task is on its way stays for the next one
  const sent = taskFiles.slice();
  button.disabled = true;
  try {
    const r = await api("/tasks", {
      title: $("t-title").value, text: $("t-text").value, folder: $("t-folder").value,
      goal: $("t-goal").value, priority: $("t-priority").value,
      effort: $("t-effort").value, account: $("t-account").value,
      files: sent.map((f) => f.path),
    });
    $("t-title").value = ""; $("t-text").value = "";
    taskFiles = taskFiles.filter((f) => !sent.includes(f)); drawTaskFiles();
    toast(`Task ${r.task.id} queued`);
  } catch (e) { toast(e.message, "error"); }
  finally { button.disabled = false; }
  refresh();
});

$("g-add").addEventListener("click", async () => {
  try {
    const r = await api("/goals", {
      title: $("g-title").value, text: $("g-text").value, folder: $("g-folder").value,
      check: $("g-check").value, priority: $("g-priority").value,
    });
    for (const id of ["g-title", "g-text", "g-folder", "g-check"]) $(id).value = "";
    toast(`Goal ${r.goal.slug} added; planning starts on the next tick`);
  } catch (e) { toast(e.message, "error"); }
  refresh();
});

$("m-save").addEventListener("click", async () => {
  try {
    await api("/settings", { changes: {
      mail_address: $("m-address").value, allowed_senders: $("m-senders").value,
      report_to: $("m-report").value, digest_time: $("m-digest").value || "17:00",
      mail_enabled: $("m-enabled").checked,
    } });
    const pw = $("m-password").value.trim();
    if (pw) { await api("/mail/password", { password: pw }); $("m-password").value = ""; }
    toast("Mail settings saved");
  } catch (e) { toast(e.message, "error"); }
  refresh();
});

$("m-test").addEventListener("click", async () => {
  $("m-test").disabled = true;
  try { toast((await api("/mail/test", {})).message); } catch (e) { toast(e.message, "error"); }
  $("m-test").disabled = false;
});

$("s-save").addEventListener("click", async () => {
  try {
    await api("/settings", { changes: {
      max_sessions: $("s-max-n").value, stall_minutes: $("s-stall-n").value,
      review_after_rounds: $("s-review-n").value, review_every_rounds: $("s-every-n").value,
      default_folder: $("s-folder").value,
    } });
    toast("Settings saved");
  } catch (e) { toast(e.message, "error"); }
  refresh();
});

refresh();
setInterval(refresh, 4000);
