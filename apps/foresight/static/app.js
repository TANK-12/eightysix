/* Foresight frontend.
 *
 * The page draws whatever the backend's registries report — tiers, signal
 * sources, analysers — and names none of them itself. Adding a source or a
 * tier needs no change here.
 *
 * The one thing this page insists on: every answer shows which tier produced
 * it and whether a model was involved. A rules answer must never be mistaken
 * for a model's, or the point of having a rules tier is lost.
 */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(path, options) {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!r.ok) {
    let detail = r.statusText;
    try { detail = (await r.json()).detail || detail; } catch (e) {}
    throw new Error(detail);
  }
  return r.json();
}

const state = { status: null, tier: "rules", findings: [], sweepPoll: null, bootPoll: null };

/* ---------------------------------------------------------------- views */

function showView(name) {
  document.querySelectorAll(".view").forEach((v) =>
    v.classList.toggle("on", v.id === "view-" + name));
  document.querySelectorAll(".views button").forEach((b) =>
    b.classList.toggle("on", b.dataset.view === name));
  const target = "#/" + name;
  if (location.hash !== target) history.replaceState(null, "", target);
  if (name === "findings") loadFindings();
  if (name === "plans") loadPlans();
  if (name === "watch") loadWatchlist();
}

function routeFromHash() {
  const view = (location.hash || "").replace("#/", "");
  showView(["ask", "findings", "plans", "watch", "about"].includes(view) ? view : "ask");
}
window.addEventListener("hashchange", routeFromHash);
document.querySelectorAll(".views button").forEach((b) =>
  b.addEventListener("click", () => showView(b.dataset.view)));

/* ----------------------------------------------------------- fullscreen */
/* Three separate things, which is why F11 alone was never enough: the Forge
   sidebar is hidden by a postMessage to the hub, the page takes real
   fullscreen, and forge.py fullscreens the GTK window behind it. All of that
   lives in shared/forge_chrome.js now, which wires the `go-fullscreen` button
   and the `f` key by itself the moment it loads -- there is nothing to do
   here. F11 is handled by the window in forge.py, not by the page. */

/* ----------------------------------------------------------------- boot */

/* If the server is not up yet, boot keeps trying on a stretching wait (it
   rests while hidden) instead of leaving the page dead until a reload. */
async function boot() {
  if (!state.sweepPoll) {
    state.sweepPoll = ForgeIdle.poll(pollSweep, 8000, { backoff: 2, maxMs: 30000, immediate: true });
  }
  try {
    state.status = await api("/api/status");
  } catch (e) {
    $("pill-jan").textContent = "backend unreachable";
    $("pill-jan").className = "pill bad";
    if (!state.bootPoll) {
      state.bootPoll = ForgeIdle.poll(boot, 4000, { backoff: 2, maxMs: 30000 });
    }
    return false;
  }
  if (state.bootPoll) { state.bootPoll.stop(); state.bootPoll = null; }
  const s = state.status;

  $("pill-store").textContent =
    (s.storage.on_usb ? "AN3 · " : "local disk · ") + s.storage.free_gb + " GB free";
  $("pill-store").className = "pill " + (s.storage.on_usb ? "ok" : "");
  $("pill-store").title = s.storage.detail + "\n" + s.storage.path;

  $("pill-dossier").textContent = s.dossier.available
    ? `Dossier · ${s.dossier.subjects} subjects`
    : "Dossier unreachable";
  $("pill-dossier").className = "pill " + (s.dossier.available ? "ok" : "bad");
  $("pill-dossier").title = s.dossier.detail;

  renderJanPill(s.jan);
  renderTiers(s.tiers);
  renderSources(s.sources);
  renderAnalysers(s.analysers);
  $("storage-detail").textContent =
    `${s.storage.detail}\nEverything Foresight stores — signal series, findings, `
    + `chats — lives at ${s.storage.path}, beside Dossier's library rather than `
    + `inside it. Nothing here ever writes into Dossier's data.`;

  routeFromHash();
  return true;
}

function renderJanPill(jan) {
  const pill = $("pill-jan");
  if (!jan.jan) {
    pill.textContent = "Jan offline · rules tier still works";
    pill.className = "pill";
    pill.title = jan.detail || "";
    return;
  }
  const think = jan.tiers.think || {};
  pill.textContent = think.model ? `Jan · think: ${think.model}` : "Jan";
  pill.className = "pill " + (think.is_ideal ? "ok" : "");
  pill.title = Object.entries(jan.tiers)
    .map(([t, v]) => `${t}: ${(v && v.model) || "none"}${v && !v.is_ideal ? ` (ideal ${v.ideal})` : ""}`)
    .join("\n");
}

/* ----------------------------------------------------------------- ask */

function renderTiers(tiers) {
  const pick = $("tier-pick");
  pick.innerHTML = "";
  const help = $("tier-help");
  help.innerHTML = "";
  tiers.forEach((tier) => {
    const b = el("button", tier.uses_model ? "" : "norobot");
    if (tier.name === state.tier) b.classList.add("on");
    b.append(el("span", "lbl", tier.label));
    b.append(el("span", "sub", tier.uses_model ? "uses a model" : "no model"));
    b.addEventListener("click", () => {
      state.tier = tier.name;
      renderTiers(tiers);
    });
    pick.appendChild(b);

    const line = el("div", "solver");
    line.append(el("b", null, tier.label + (tier.uses_model ? "" : " — no model")));
    line.append(document.createTextNode(tier.description));
    help.appendChild(line);

    if (!tier.uses_model && tier.solvers.length) {
      const list = $("solver-list");
      list.innerHTML = "";
      tier.solvers.forEach((s) => {
        const row = el("div", "solver");
        row.append(el("b", null, s.label));
        row.append(document.createTextNode(s.description));
        list.appendChild(row);
      });
    }
  });
}

function renderAnswer(question, answer) {
  const card = el("div", "card answer");
  card.appendChild(el("div", "question", question));

  const who = el("span", "who " + (answer.used_model ? "model" : "rules"));
  who.textContent = answer.used_model
    ? `${answer.tier} · ${answer.model || "model"} · ${answer.seconds}s`
    : `${answer.tier} · no model used`;
  card.appendChild(who);

  const text = el("pre", "text");
  text.textContent = answer.text;
  card.appendChild(text);

  // The thinking is the point of the think tier, so it is kept and shown -
  // folded away, because it is long.
  if (answer.reasoning) {
    const details = el("details", "thinking");
    details.appendChild(el("summary", null,
      `its thinking (${answer.reasoning.length.toLocaleString()} characters)`));
    const pre = el("pre");
    pre.textContent = answer.reasoning;
    details.appendChild(pre);
    card.appendChild(details);
  }

  const answers = $("ask-answers");
  answers.insertBefore(card, answers.firstChild);
}

async function ask() {
  const question = $("ask-box").value.trim();
  if (!question) return;
  const button = $("ask-go");
  const note = $("ask-note");
  button.disabled = true;
  const usesModel = (state.status.tiers.find((t) => t.name === state.tier) || {}).uses_model;
  note.textContent = usesModel
    ? "thinking — the think tier is allowed to take minutes…"
    : "computing…";
  try {
    const answer = await api("/api/ask", {
      method: "POST",
      body: JSON.stringify({
        question,
        tier: state.tier,
        prefer_rules: $("prefer-rules").checked,
      }),
    });
    renderAnswer(question, answer);
    $("ask-box").value = "";
    note.textContent = "";
  } catch (e) {
    note.textContent = e.message;
  }
  button.disabled = false;
}
$("ask-go").addEventListener("click", ask);
$("ask-box").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) ask();
});

/* ------------------------------------------------------------- findings */

function sparkline(points) {
  if (!points || points.length < 2) return null;
  const values = points.map((p) => Number(p.value) || 0);
  const min = Math.min(...values), max = Math.max(...values);
  const span = max - min || 1;
  const step = 100 / (values.length - 1);
  const coords = values.map((v, i) =>
    `${(i * step).toFixed(2)},${(28 - ((v - min) / span) * 26).toFixed(2)}`);
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "spark");
  svg.setAttribute("viewBox", "0 0 100 30");
  svg.setAttribute("preserveAspectRatio", "none");
  const line = document.createElementNS(ns, "polyline");
  line.setAttribute("points", coords.join(" "));
  svg.appendChild(line);
  const dot = document.createElementNS(ns, "circle");
  dot.setAttribute("class", "last");
  dot.setAttribute("cx", coords[coords.length - 1].split(",")[0]);
  dot.setAttribute("cy", coords[coords.length - 1].split(",")[1]);
  dot.setAttribute("r", "1.6");
  svg.appendChild(dot);
  return svg;
}

function renderFindings(findings) {
  const list = $("findings-list");
  list.innerHTML = "";
  $("findings-count").textContent = findings.length
    ? `${findings.length} findings`
    : "";
  if (!findings.length) {
    list.appendChild(el("div", "empty",
      "Nothing has broken out of its baseline. Gather some signals first — "
      + "a series needs about ten readings before it has a normal to depart from."));
    return;
  }
  findings.forEach((f) => {
    const rising = /up sharply/.test(f.headline);
    const card = el("div", "finding " + (rising ? "rising" : "falling"));
    const head = el("div", "head");
    head.appendChild(el("b", null, f.headline));
    head.appendChild(el("span", "tag", f.source));
    head.appendChild(el("span", "tag norobot", "no model"));
    card.appendChild(head);
    card.appendChild(el("div", "detail", f.detail));
    const spark = sparkline(f.evidence);
    if (spark) card.appendChild(spark);
    list.appendChild(card);
  });
}

async function loadFindings() {
  try {
    const payload = await api("/api/findings");
    state.findings = payload.findings;
    renderFindings(payload.findings);
  } catch (e) {
    $("findings-list").innerHTML = "";
    $("findings-list").appendChild(el("div", "empty", e.message));
  }
}
$("findings-refresh").addEventListener("click", loadFindings);

/* -------------------------------------------------------------- signals */

async function loadWatchlist() {
  try {
    const payload = await api("/api/watchlist?limit=60");
    const list = $("watchlist");
    list.innerHTML = "";
    if (!payload.subjects.length) {
      list.appendChild(el("div", "muted small",
        "Dossier's library is not reachable — is the AN3 drive plugged in?"));
      return;
    }
    payload.subjects.forEach((s, i) => {
      const row = el("div", "watchrow");
      row.append(el("span", null, `${i + 1}. ${s.name}`));
      row.append(el("span", "muted small", s.entity_type));
      list.appendChild(row);
    });
  } catch (e) {}
}

/* The sweep's progress, read every 8 s while the page is shown and every
   1.5 s while a sweep runs. Hidden, it rests; while the server does not
   answer, the wait stretches to 30 s and the page says so. */
let sweepFast = 0;
async function pollSweep() {
  let payload;
  try { payload = await api("/api/sweep"); } catch (e) {
    $("sweep-summary").textContent = "Foresight's server is not answering; trying again shortly";
    return false;
  }
  const pill = $("pill-sweep");
  pill.hidden = !payload.running;
  if (payload.running) {
    pill.className = "pill busy";
    pill.textContent = `sweeping ${payload.done}/${payload.total}`;
  }
  const pct = payload.total ? (payload.done / payload.total) * 100 : 0;
  $("sweep-bar").style.width = pct.toFixed(1) + "%";
  $("sweep-summary").textContent = payload.running
    ? `sweeping — ${payload.done} of ${payload.total} done`
    : (payload.last ? `last swept ${payload.last.replace("T", " ").replace("+00:00", "")}` : "idle");
  $("sweep-log").textContent = (payload.log || []).join("\n") || "nothing running";
  clearTimeout(sweepFast);
  if (payload.running) {
    sweepFast = setTimeout(() => { if (ForgeIdle.shown()) state.sweepPoll.now(); }, 1500);
  }
  return true;
}

$("sweep-go").addEventListener("click", async () => {
  const button = $("sweep-go");
  button.disabled = true;
  try {
    await api("/api/sweep", {
      method: "POST",
      body: JSON.stringify({
        limit: Number($("sweep-limit").value),
        days: Number($("sweep-days").value),
      }),
    });
    state.sweepPoll.now();
  } catch (e) { ForgeDialog.alert(e.message); }
  button.disabled = false;
});

$("sweep-history").addEventListener("click", async () => {
  const button = $("sweep-history");
  button.disabled = true;
  try {
    const r = await api("/api/sweep", {
      method: "POST",
      body: JSON.stringify({ history: true, limit: Number($("sweep-limit").value) }),
    });
    $("sweep-summary").textContent = `getting five years for ${r.subjects} subjects…`;
    state.sweepPoll.now();
  } catch (e) { ForgeDialog.alert(e.message); }
  button.disabled = false;
});

/* -------------------------------------------------------------- sources */

function renderSources(sources) {
  const list = $("source-list");
  list.innerHTML = "";
  sources.forEach((s) => {
    const row = el("div", "sourcerow");
    const head = el("div", "row");
    head.append(el("b", null, s.label));
    head.append(el("span", "tag", s.kind));
    head.append(el("span", "tag", s.unit));
    if (s.needs_credentials) head.append(el("span", "tag", "needs credentials"));
    row.appendChild(head);
    row.appendChild(el("div", "small muted", s.description));
    row.appendChild(el("div", "caveat", "Caveat: " + s.caveat));
    list.appendChild(row);
  });
}

function renderAnalysers(analysers) {
  const list = $("analyser-list");
  list.innerHTML = "";
  analysers.forEach((a) => {
    const row = el("div", "solver");
    const title = el("b");
    title.textContent = a.label;
    row.appendChild(title);
    row.append(document.createTextNode(a.description));
    if (!a.uses_model) row.append(el("span", "tag norobot", "no model"));
    list.appendChild(row);
  });
}

boot();


/* ---------------------------------------------------------------- plans */
/*
 * A scenario is branches of the future, each carrying dated, falsifiable
 * indicators. The page never decides what a tier is or what an outcome means —
 * both come from the backend, so adding a tier or an outcome needs no edit
 * here.
 */

const OUTCOME_LABEL = {
  pending: "not due yet",
  met: "happened",
  missed: "did not happen",
  unscorable: "cannot be marked",
};

async function loadPlans() {
  fillPlanTiers();
  fillPlanNames();
  let data;
  try {
    data = await api("/api/plans");
  } catch (e) {
    $("plan-list").innerHTML = "";
    $("plan-list").appendChild(el("div", "empty", e.message));
    return;
  }
  renderRecord(data.record);
  renderScenarios(data.scenarios);
}

function fillPlanTiers() {
  const select = $("plan-tier");
  if (select.options.length || !state.status || !state.status.tiers) return;
  state.status.tiers.forEach((tier) => {
    const option = document.createElement("option");
    option.value = tier.name;
    option.textContent = tier.uses_model ? tier.label : tier.label + " (no model)";
    select.appendChild(option);
  });
}

async function fillPlanNames() {
  const list = $("plan-names");
  if (list.options.length) return;
  try {
    const rows = await api("/api/watchlist");
    (rows.subjects || rows || []).forEach((row) => {
      const option = document.createElement("option");
      option.value = row.slug;
      option.label = row.name;
      option.textContent = row.name;
      list.appendChild(option);
    });
  } catch (e) { /* the picker is a convenience; typing a slug still works */ }
}

/* 1841160000000 is not a claim anyone can check at a glance. */
function prettyNumber(value) {
  const n = Number(value);
  if (!isFinite(n)) return String(value);
  const size = Math.abs(n);
  for (const [unit, suffix] of [[1e12, "tn"], [1e9, "bn"], [1e6, "m"], [1e3, "k"]]) {
    if (size >= unit) return (n / unit).toFixed(size / unit >= 100 ? 0 : 2) + suffix;
  }
  return size >= 10 ? n.toFixed(2) : n.toPrecision(3);
}

/* What backtesting against stored history taught. Drawn apart from the live
 * ledger on purpose: being marked against the past is not being marked against
 * a future nobody had seen. */
function renderLessons(lessons) {
  const box = $("plan-lessons");
  box.innerHTML = "";
  if (!lessons || !lessons.series) {
    box.appendChild(el("div", "muted",
      "Nothing learned yet. Sweep some subjects, then learn from their history."));
    return;
  }
  const line = (label, value) => {
    const row = el("div", "ledger-row");
    row.appendChild(el("span", "k", label));
    row.appendChild(el("span", "v", String(value)));
    box.appendChild(row);
  };
  line("subjects", lessons.subjects);
  line("series backtested", lessons.series);
  line("straight-line claims held",
    `${lessons.hits} of ${lessons.claims}`
    + (lessons.hit_rate === null || lessons.hit_rate === undefined
      ? "" : ` (${Math.round(lessons.hit_rate * 100)}%)`));
  line("a line beat no change", lessons.trend_wins);
  line("no change beat a line", lessons.persistence_wins);
}

function renderRecord(record) {
  const box = $("plan-record");
  box.innerHTML = "";
  renderLessons((record || {}).backtest);
  const totals = (record || {}).totals || {};
  if (!totals.scenarios) {
    box.appendChild(el("div", "muted", "Nothing forecast yet."));
    return;
  }
  const line = (label, value) => {
    const row = el("div", "ledger-row");
    row.appendChild(el("span", "k", label));
    row.appendChild(el("span", "v", String(value)));
    box.appendChild(row);
  };
  line("scenarios", totals.scenarios);
  line("indicators settled", totals.settled);
  line("happened", totals.met);
  line("did not happen", totals.missed);
  line("not due yet", totals.pending);
  if (totals.unscorable) line("cannot be marked", totals.unscorable);
  line(
    "hit rate",
    totals.accuracy === null || totals.accuracy === undefined
      ? "— nothing has come due"
      : Math.round(totals.accuracy * 100) + "%"
  );
  Object.entries((record || {}).by_tier || {}).forEach(([tier, line2]) => {
    if (!line2.settled) return;
    box.appendChild(el("div", "small muted",
      `${tier}: ${line2.met}/${line2.settled} (${Math.round(line2.accuracy * 100)}%)`));
  });
}

function renderScenarios(scenarios) {
  const list = $("plan-list");
  list.innerHTML = "";
  if (!scenarios || !scenarios.length) {
    list.appendChild(el("div", "empty",
      "No scenarios yet. Pick a subject that has signals stored and write one."));
    return;
  }
  scenarios.forEach((scenario) => {
    const card = el("div", "card scenario");
    const head = el("div", "head");
    head.appendChild(el("b", null, scenario.title));
    head.appendChild(el("span", "tag", scenario.tier));
    if (!scenario.model) head.appendChild(el("span", "tag norobot", "no model"));
    else head.appendChild(el("span", "tag", scenario.model));
    card.appendChild(head);
    card.appendChild(el("div", "basis", `${scenario.created} — ${scenario.basis}`));

    (scenario.branches || []).forEach((branch) => {
      const box = el("div", "finding branch");
      const bh = el("div", "head");
      bh.appendChild(el("b", null, branch.name));
      if (branch.likelihood) bh.appendChild(el("span", "tag", branch.likelihood));
      box.appendChild(bh);
      if (branch.narrative) box.appendChild(el("div", "detail", branch.narrative));
      (branch.indicators || []).forEach((ind) => {
        const row = el("div", "indicator " + ind.outcome);
        row.appendChild(el("span", "outcome", OUTCOME_LABEL[ind.outcome] || ind.outcome));
        let claim = `${ind.series} ${ind.direction} ${prettyNumber(ind.threshold)}`
          + ` by ${ind.by_date}`;
        if (ind.observed !== null && ind.observed !== undefined) {
          claim += ` — it was ${prettyNumber(ind.observed)}`;
        }
        row.appendChild(el("span", "claim", claim));
        if (ind.note) row.appendChild(el("span", "means", ind.note));
        box.appendChild(row);
      });
      card.appendChild(box);
    });

    const actions = el("div", "row");
    actions.style.marginTop = "10px";
    const mark = el("button", "ghost", "Mark what is due");
    mark.addEventListener("click", async () => {
      mark.disabled = true;
      try { await api(`/api/plans/${scenario.id}/score`, { method: "POST" }); await loadPlans(); }
      catch (e) { toast(e.message, "bad"); }
      finally { mark.disabled = false; }
    });
    const drop = el("button", "ghost", "Delete");
    drop.addEventListener("click", async () => {
      try { await api(`/api/plans/${scenario.id}`, { method: "DELETE" }); await loadPlans(); }
      catch (e) { toast(e.message, "bad"); }
    });
    actions.append(mark, drop);
    card.appendChild(actions);
    list.appendChild(card);
  });
}

$("plan-make").addEventListener("click", async () => {
  const slug = $("plan-subject").value.trim();
  if (!slug) return;
  const button = $("plan-make");
  button.disabled = true;
  $("plan-note").textContent = "Working it out…";
  try {
    await api("/api/plans", {
      method: "POST",
      body: JSON.stringify({ slug, tier: $("plan-tier").value }),
    });
    $("plan-note").textContent = "";
    await loadPlans();
  } catch (e) {
    $("plan-note").textContent = e.message;
  } finally {
    button.disabled = false;
  }
});

$("plan-score").addEventListener("click", async () => {
  const button = $("plan-score");
  button.disabled = true;
  try { await api("/api/plans/score", { method: "POST" }); await loadPlans(); }
  catch (e) { toast(e.message, "bad"); }
  finally { button.disabled = false; }
});

$("plan-learn").addEventListener("click", async () => {
  const button = $("plan-learn");
  button.disabled = true;
  try { await api("/api/plans/learn", { method: "POST", body: "{}" }); await loadPlans(); }
  catch (e) { toast(e.message, "bad"); }
  finally { button.disabled = false; }
});
