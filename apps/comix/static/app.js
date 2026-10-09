/* Comix page: library, group choice, queue, reader, settings. */

const HOME = "https://comix.to/";
let STATE = null;
let settingsFilled = false;
let openSeries = null;
const checking = new Set();  // series ids with a "check for new chapters" running

async function api(path, opts = {}) {
  const init = { ...opts };
  if (opts.body !== undefined) {
    init.method = opts.method || "POST";
    init.headers = { "Content-Type": "application/json" };
    init.body = JSON.stringify(opts.body);
  }
  let r;
  try { r = await fetch(path, init); }
  catch { throw new Error("Comix isn't answering. Try again in a moment."); }
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(data.detail || `${r.status} ${r.statusText}`);
  return data;
}

function el(tag, attrs = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== undefined && v !== null && v !== false) e.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) if (kid !== null && kid !== undefined) e.append(kid);
  return e;
}

function say(msg, kind) {
  if (typeof toast === "function" && document.getElementById("toast")) toast(msg, kind);
  else console.info(msg);
}

function chapterName(c) {
  return `Ch. ${Number(c.number).toString()}`;
}

/* --- state poll ------------------------------------------------------------- */

/* While the backend is away: a calm bar, the poll stretches out (ForgeIdle
   backoff), and the first answer brings everything back by itself. */
let offline = false;
function setOffline(off) {
  if (off === offline) return;
  offline = off;
  document.getElementById("conn").hidden = !off;
  if (!off) {
    loadSeries();
    if (document.querySelector('.panel.active[data-panel="queue"]')) loadQueue();
  }
}

async function refreshState() {
  try { STATE = await api("/api/state"); } catch (e) {
    if (e instanceof TypeError) setOffline(true);  // no answer at all, not a refusal
    return false;
  }
  setOffline(false);
  const login = STATE.login.comix || { cookies: 0 };
  const bar = document.getElementById("login-bar");
  bar.classList.toggle("ok", login.cookies > 0);
  document.getElementById("login-text").textContent = login.cookies > 0
    ? `Using your comix.to login from the Forge Browser (${login.cookies} cookies).`
    : "Not logged in yet. Log in on comix.to in the Forge Browser once, and Comix will use that login.";
  document.getElementById("login-btn").textContent = login.cookies > 0 ? "Open comix.to" : "Log in on comix.to";

  const c = STATE.counts;
  const waiting = (c.queued || 0) + (c.running || 0) + (c.partial || 0);
  document.getElementById("queue-badge").textContent = waiting ? String(waiting) : "";
  document.getElementById("counts").textContent =
    `${c.done || 0} saved · ${waiting} waiting · ${c.failed || 0} failed · ${STATE.free_gb} GB free`;
  document.getElementById("pause-btn").textContent = STATE.paused ? "Resume" : "Pause";
  const now = document.getElementById("now");
  now.replaceChildren(...(STATE.current.length
    ? STATE.current.map(cur => el("div", { class: "now-item" },
        el("strong", {}, cur.name), ` — page ${cur.page || 1} of ${cur.total}`,
        el("div", { class: "bar" }, el("span", { style: `width:${Math.round(100 * (cur.page || 0) / cur.total)}%` }))))
    : [el("div", { class: "muted" }, STATE.paused ? "Paused." : "Nothing downloading right now.")]));
  document.getElementById("log").textContent = STATE.log.join("\n");
  document.getElementById("free").textContent = `${STATE.free_gb} GB free on that disk`;
  if (!settingsFilled) fillSettings();
}

/* --- login ------------------------------------------------------------------ */

document.getElementById("login-btn").addEventListener("click", async () => {
  window.parent.postMessage({ forge: "open", role: "browser" }, "*");
  try {
    await api("/api/login/open", { body: { url: HOME } });
    say("Opened comix.to in the Forge Browser. Log in there, then come back and press \"I've logged in\".");
  } catch (e) { say(`Could not open comix.to: ${e.message}`, "err"); }
});
document.getElementById("login-check").addEventListener("click", refreshState);

/* A job the backend no longer knows (it restarted) is an error, not a result. */
function track(job, every, onDone, onError) {
  return pollJob(job, { every,
    onDone: (j) => (j && j.status === "done" ? onDone(j) : onError(j && j.detail ? `${j.detail} (Comix restarted?)` : "the job was lost")),
    onError });
}

/* Run fn with the button disabled, so a double click sends one request. */
async function busy(btn, fn) {
  if (btn.disabled) return;
  btn.disabled = true;
  try { await fn(); }
  catch (e) { say(e.message, "err"); }
  finally { btn.disabled = false; }
}

/* --- look up a series and choose its groups --------------------------------- */

document.getElementById("lookup-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const url = document.getElementById("lookup-url").value.trim();
  if (!url) return;
  const status = document.getElementById("lookup-status");
  const btn = document.getElementById("lookup-btn");
  btn.disabled = true;
  status.textContent = "Reading the chapter list (every page of it)… this takes a little while.";
  document.getElementById("choose").hidden = true;
  try {
    const { job } = await api("/api/lookup", { body: { url } });
    track(job, 1500,
      (j) => {
        btn.disabled = false;
        const info = j.result;
        status.textContent = `${info.title}: ${info.numbers} chapters, ${info.group_counts.length} scanlation group(s).`;
        showChoice(document.getElementById("choose"), info.group_counts, "ranked", [], async (mode, groups) => {
          const s = await api("/api/series", { body: { job, mode, groups } });
          say(`Added ${s.title}.`);
          document.getElementById("choose").hidden = true;
          status.textContent = "";
          document.getElementById("lookup-url").value = "";
          loadSeries();
        }, "Add and download");
      },
      (e) => { btn.disabled = false; status.textContent = `Could not read that series: ${e}`; });
  } catch (e) { btn.disabled = false; status.textContent = e.message; }
});

/* The group chooser: one group, a ranked list with fallback, or everything. */
function showChoice(box, groupCounts, mode, groups, onApply, applyLabel) {
  const order = groups.length ? [...groups, ...groupCounts.map(g => g.group).filter(g => !groups.includes(g))]
                              : groupCounts.map(g => g.group);
  const count = Object.fromEntries(groupCounts.map(g => [g.group, g.chapters]));
  let picked = mode === "pending" ? "ranked" : mode;

  const modes = el("div", { class: "modes" },
    ...[["one", "One group only"], ["ranked", "Best group per chapter"], ["all", "Every group's version"]].map(([m, label]) =>
      el("label", { class: "mode-opt" },
        el("input", { type: "radio", name: "gm", value: m, checked: m === picked,
                      onchange: () => { picked = m; draw(); } }), " ", label)));
  const hint = el("p", { class: "muted small" });
  const list = el("ol", { class: "group-rank" });

  function draw() {
    hint.textContent = {
      one: "Only the group at the top. Chapters it never did are skipped.",
      ranked: "For each chapter, the highest group in this list that has it. Chapters none of them did come from whoever did. Use the arrows to rank.",
      all: "Every group's copy of every chapter. Uses the most disk.",
    }[picked];
    list.hidden = picked === "all";
    list.replaceChildren(...order.map((g, i) => el("li", {},
      el("span", { class: "g-name" }, g || "(no group named)"),
      el("span", { class: "muted small" }, ` ${count[g] || 0} ch`),
      el("span", { class: "spacer" }),
      el("button", { class: "btn mini", type: "button", disabled: i === 0,
                     onclick: () => { [order[i - 1], order[i]] = [order[i], order[i - 1]]; draw(); } }, "▲"),
      el("button", { class: "btn mini", type: "button", disabled: i === order.length - 1,
                     onclick: () => { [order[i + 1], order[i]] = [order[i], order[i + 1]]; draw(); } }, "▼"))));
  }
  draw();
  const go = el("button", { class: "btn btn-primary", type: "button", onclick: async () => {
    if (go.disabled) return;
    go.disabled = true;
    try { await onApply(picked, picked === "all" ? [] : [...order]); }
    catch (e) { say(e.message, "err"); }
    go.disabled = false;
  } }, applyLabel);
  box.replaceChildren(modes, hint, list, go);
  box.hidden = false;
}

/* --- series list and detail -------------------------------------------------- */

let seriesAll = [];
async function loadSeries() {
  const box = document.getElementById("series-list");
  let series;
  try { series = await api("/api/series"); } catch (e) {
    // Keep cards already drawn; a first load that fails says so calmly.
    if (!box.querySelector(".series-card")) {
      box.replaceChildren(el("p", { class: "muted" }, "Could not load your series. ",
        el("button", { class: "btn mini", type: "button", onclick: loadSeries }, "Try again")));
    }
    return;
  }
  seriesAll = series;
  drawSeries();
  fillReadSeries(series);
}

function drawSeries() {
  const box = document.getElementById("series-list");
  const filter = document.getElementById("series-filter").value.trim().toLowerCase();
  const series = filter ? seriesAll.filter(s => s.title.toLowerCase().includes(filter)) : seriesAll;
  if (!seriesAll.length) {
    box.replaceChildren(el("p", { class: "muted" }, "No series yet. Paste a series link above, or sync your library."));
  } else if (!series.length) {
    box.replaceChildren(el("p", { class: "muted" }, "No series match that filter."));
  } else {
    box.replaceChildren(...series.map(s => el("div", {
      class: "series-card" + (s.group_mode === "pending" ? " pending" : "") + (openSeries === s.id ? " open" : ""),
      onclick: () => showSeries(s.id),
    },
      el("div", { class: "s-title" }, s.title),
      el("div", { class: "muted small" }, s.group_mode === "pending" && !s.wanted
        ? `${s.listed} chapter rows · pick groups to start`
        : `${s.done || 0} of ${s.wanted || 0} saved` + (s.group_mode === "pending" ? " · groups not picked yet" : "")),
      el("div", { class: "bar" }, el("span", { style: `width:${s.wanted ? Math.round(100 * (s.done || 0) / s.wanted) : 0}%` })))));
  }
}
document.getElementById("series-filter").addEventListener("input", drawSeries);

const STATE_LABEL = { skipped: "not chosen", queued: "waiting", running: "downloading", partial: "missing pages, will retry",
                      failed: "failed", done: "saved" };

let seriesSeq = 0;
async function showSeries(sid) {
  openSeries = sid;
  const seq = ++seriesSeq;
  let s;
  try { s = await api(`/api/series/${sid}`); } catch (e) {
    if (seq === seriesSeq) say(`Could not open that series: ${e.message}`, "err");
    return;
  }
  if (seq !== seriesSeq) return;  // another series was clicked meanwhile
  const box = document.getElementById("series-detail");
  const chooser = el("div", { class: "choose" });
  showChoice(chooser, s.group_counts, s.group_mode, s.groups, async (mode, groups) => {
    const r = await api(`/api/series/${sid}/choice`, { body: { mode, groups } });
    say(`${r.queued} chapter(s) queued for ${s.title}.`);
    showSeries(sid); loadSeries();
  }, s.group_mode === "pending" ? "Start downloading" : "Apply group choice");

  const rows = s.chapters.map(c => el("tr", { class: "st-" + c.state },
    el("td", {}, chapterName(c)),
    el("td", {}, c.grp || "—"),
    el("td", {}, STATE_LABEL[c.state] + (c.pages_total && c.state !== "done" && c.state !== "skipped" ? ` (${c.pages_ok}/${c.pages_total})` : "")),
    el("td", {},
      c.state === "done"
        ? el("button", { class: "btn mini", type: "button", onclick: () => readChapter(c.id, s.id) }, "Read")
        : el("button", { class: "btn mini", type: "button",
                         onclick: (ev) => busy(ev.currentTarget, async () => { await api(`/api/chapters/${c.id}/want`, { body: { wanted: c.state === "skipped" } }); showSeries(sid); }) },
             c.state === "skipped" ? "Get" : "Skip"))));

  box.replaceChildren(
    el("div", { class: "detail-head" },
      el("h3", {}, s.title),
      el("span", { class: "spacer" }),
      el("a", { href: s.url, target: "_blank", class: "btn mini" }, "On comix.to"),
      el("button", { class: "btn mini", type: "button", disabled: checking.has(sid), onclick: (ev) => {
        const btn = ev.currentTarget;
        if (checking.has(sid)) return;  // a redrawn detail must not start a second check
        busy(btn, async () => {
          checking.add(sid);
          try {
            const { job } = await api(`/api/series/${sid}/refresh`, { body: {} });
            say("Checking for new chapters…");
            btn.disabled = true;  // stays off until the check ends, so one check runs at a time
            await new Promise((done) => track(job, 1500,
              (j) => { checking.delete(sid); say(`${j.result.new} new chapter row(s).`); showSeries(sid); loadSeries(); done(); },
              (e) => { checking.delete(sid); say(e, "err"); done(); }));
          } finally { checking.delete(sid); }
        });
      } }, "Check for new chapters"),
      el("button", { class: "btn mini btn-danger", type: "button", onclick: (ev) => busy(ev.currentTarget, async () => {
        if (!await ForgeDialog.confirm(`Forget ${s.title}? Downloaded files stay on disk.`)) return;
        await api(`/api/series/${sid}`, { method: "DELETE" });
        box.hidden = true; openSeries = null; loadSeries();
      }) }, "Remove")),
    el("h4", {}, "Scanlation groups"),
    chooser,
    el("h4", {}, "Chapters"),
    el("table", { class: "chapters" }, el("tbody", {}, rows)));
  box.hidden = false;
  box.scrollIntoView({ behavior: "smooth", block: "start" });
}

document.getElementById("sync-btn").addEventListener("click", (ev) => {
  const btn = ev.currentTarget;
  busy(btn, async () => {
    const { job } = await api("/api/library/sync", { body: {} });
    say("Reading your comix.to library. Each new series gets its chapter list read, so this takes a while.");
    btn.disabled = true;  // one sync at a time: off until this one ends
    await new Promise((done) => track(job, 3000,
      (j) => { say(`Library: ${j.result.found} series found, ${j.result.added} new, ${j.result.relisted} waiting for groups listed again. Pick their groups to start.`); loadSeries(); done(); },
      (e) => { say(e, "err"); done(); }));
  });
});

/* --- queue ------------------------------------------------------------------ */

async function loadQueue() {
  const box = document.getElementById("queue-list");
  let q;
  try { q = await api("/api/queue"); } catch (e) {
    if (!box.querySelector(".q-row")) box.replaceChildren(el("p", { class: "muted" }, "Could not load the queue. It comes back by itself."));
    return false;
  }
  if (!q.length) { box.replaceChildren(el("p", { class: "muted" }, "The queue is empty.")); return; }
  box.replaceChildren(...q.map(c => el("div", { class: "q-row st-" + c.state },
    el("span", { class: "q-name" }, `${c.series_title} · ${chapterName(c)}`),
    el("span", { class: "muted small" }, c.grp || ""),
    el("span", { class: "spacer" }),
    el("span", { class: "small" }, STATE_LABEL[c.state] + (c.pages_total ? ` ${c.pages_ok}/${c.pages_total}` : "")),
    c.error ? el("span", { class: "muted small err", title: c.error }, " ⚠") : null)));
}

document.getElementById("pause-btn").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  await api("/api/queue/pause", { body: { paused: !(STATE && STATE.paused) } });
  await refreshState();
}));
document.getElementById("retry-btn").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  const r = await api("/api/queue/retry", { body: {} });
  say(`${r.requeued} chapter(s) back in the queue.`);
  await loadQueue();
}));

/* --- reader ------------------------------------------------------------------ */

let readSeries = [];
let reading = null;

function fillReadSeries(series) {
  readSeries = series.filter(s => (s.done || 0) > 0);
  const sel = document.getElementById("read-series");
  const keep = sel.value;
  sel.replaceChildren(el("option", { value: "" }, readSeries.length ? "Series…" : "Nothing downloaded yet"),
    ...readSeries.map(s => el("option", { value: s.id }, s.title)));
  if (keep) sel.value = keep;
}

async function fillReadChapters(sid, selected) {
  const s = await api(`/api/series/${sid}`);
  const done = s.chapters.filter(c => c.state === "done");
  const sel = document.getElementById("read-chapter");
  sel.replaceChildren(...done.map(c => el("option", { value: c.id }, `${chapterName(c)} (${c.grp || "—"})`)));
  if (selected) sel.value = selected;
  return done;
}

document.getElementById("read-series").addEventListener("change", async (ev) => {
  if (!ev.target.value) return;
  let done;
  try { done = await fillReadChapters(ev.target.value); } catch (e) { say(e.message, "err"); return; }
  if (done.length) readChapter(done[0].id, ev.target.value, true);
});
document.getElementById("read-chapter").addEventListener("change", (ev) => readChapter(Number(ev.target.value), null, true));
document.getElementById("read-prev").addEventListener("click", () => reading && reading.prev && readChapter(reading.prev, null, true));
document.getElementById("read-next").addEventListener("click", () => reading && reading.next && readChapter(reading.next, null, true));

let readSeq = 0;
async function readChapter(cid, sid, stay) {
  if (!stay) selectTab("read");
  const seq = ++readSeq;  // quick Next clicks: only the last chapter asked for is drawn
  let got;
  try { got = await api(`/api/read/${cid}`); } catch (e) {
    if (seq === readSeq) say(`Could not open that chapter: ${e.message}`, "err");
    return;
  }
  if (seq !== readSeq) return;
  reading = got;
  const seriesId = sid || reading.chapter.series_id;
  document.getElementById("read-series").value = seriesId;
  try { await fillReadChapters(seriesId, cid); } catch { /* the chapter list is a nicety */ }
  if (seq !== readSeq) return;
  const pages = document.getElementById("pages");
  pages.replaceChildren(...Array.from({ length: reading.pages }, (_, i) =>
    el("img", { src: `/api/read/${cid}/${i + 1}`, loading: "lazy", alt: `page ${i + 1}` })));
  document.getElementById("read-prev").disabled = !reading.prev;
  document.getElementById("read-next").disabled = !reading.next;
  pages.scrollTop = 0;
  window.scrollTo(0, 0);
}

/* --- settings ------------------------------------------------------------------ */

function fillSettings() {
  const s = STATE.settings;
  document.getElementById("set-dir").value = s.download_dir;
  document.getElementById("set-library").value = s.library_url;
  document.getElementById("numbers").replaceChildren(...STATE.numbers.map(n => {
    const range = el("input", { type: "range", min: n.min, max: n.max, value: s[n.key], id: `r-${n.key}` });
    const num = el("input", { type: "number", min: n.min, max: n.max, value: s[n.key], id: `n-${n.key}`, class: "num" });
    range.addEventListener("input", () => { num.value = range.value; });
    num.addEventListener("input", () => { range.value = num.value; });
    return el("div", { class: "field" }, el("label", { for: `n-${n.key}` }, n.label), el("div", { class: "pair" }, range, num));
  }));
  ForgeMode.init(s.advanced_mode);
  settingsFilled = true;
}

document.getElementById("save-settings").addEventListener("click", (ev) => busy(ev.currentTarget, async () => {
  const values = {
    download_dir: document.getElementById("set-dir").value,
    library_url: document.getElementById("set-library").value,
    advanced_mode: ForgeMode.on,
  };
  for (const n of STATE.numbers) values[n.key] = Number(document.getElementById(`n-${n.key}`).value);
  await api("/api/settings", { body: { values } });
  say("Settings saved.");
  settingsFilled = false;
  await refreshState();
}));

/* --- start ------------------------------------------------------------------------ */

const selectTab = initTabs((name) => {
  if (name === "queue") loadQueue();
  if (name === "library") loadSeries();
});

document.getElementById("conn-retry").addEventListener("click", () => poller.now());

refreshState();
loadSeries();
// Every 3 s while shown; a failed check stretches the wait (6, 12, 24, 30 s).
const poller = ForgeIdle.poll(async () => {
  if ((await refreshState()) === false) return false;
  if (document.querySelector('.panel.active[data-panel="queue"]')) await loadQueue();
}, 3000, { backoff: 2, maxMs: 30000 });
