/* Backup: Code (offline GitHub), Snapshots, Status, Help.
 *
 * Where you are lives in the URL hash (#tab=code&repo=Forge.git&view=files...),
 * so a reload lands on the same page. Every API error carries a `kind`; the
 * drive not being plugged in (no_drive) and root-owned folders (needs_admin)
 * get a friendly box instead of an error. */
"use strict";

const $ = (id) => document.getElementById(id);
// Hard-wrapped lines join their paragraph or list item (the shared renderer
// makes every line its own paragraph); code fences are left alone.
function unwrap(text) {
  const out = [];
  let fence = false;
  for (const line of text.split("\n")) {
    if (/^\s*```/.test(line)) { fence = !fence; out.push(line); continue; }
    const prev = out[out.length - 1];
    const block = !line.trim() || /^\s*([-*+]\s|\d+[.)]\s|#|\||>)/.test(line);
    if (!fence && !block && prev && prev.trim() && !/^\s*(#|\||```)/.test(prev)) {
      out[out.length - 1] = prev.replace(/\s+$/, "") + " " + line.trim();
    } else out.push(line);
  }
  return out.join("\n");
}

// Links to other files ([RESTORE.md](RESTORE.md)) keep just their words.
const md = (text) => window.ForgeConvo.markdown(unwrap(text).replace(/\[([^\]]+)\]\((?!https?:)[^)\s]+\)/g, "$1"));

// forge_convo marks web links with data-url and no href: open them here.
document.addEventListener("click", (e) => {
  const a = e.target.closest && e.target.closest("[data-url]");
  if (a) { e.preventDefault(); window.open(a.dataset.url, "_blank", "noopener"); }
});

async function api(path, opts = {}) {
  const res = await fetch(path, {
    ...opts,
    headers: { "X-Forge": "1", "Content-Type": "application/json", ...(opts.headers || {}) },
  });
  if (!res.ok) {
    let body = {};
    try { body = await res.json(); } catch (e) { body = { detail: res.statusText }; }
    const err = new Error(body.detail || res.statusText);
    err.kind = body.kind;
    throw err;
  }
  return res.json();
}

async function blobUrl(path) {
  const res = await fetch(path, { headers: { "X-Forge": "1" } });
  if (!res.ok) throw new Error(res.statusText);
  return URL.createObjectURL(await res.blob());
}

const qs = (o) => new URLSearchParams(Object.entries(o).filter(([, v]) => v !== undefined && v !== null)).toString();

/* h("div", {class: "x", onclick}, child, "text") */
function h(tag, attrs, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v === undefined || v === null || v === false) continue;
    if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
    else if (k === "class") n.className = v;
    else if (k === "html") n.innerHTML = v;
    else n.setAttribute(k, v === true ? "" : v);
  }
  for (const kid of kids.flat()) {
    if (kid === null || kid === undefined || kid === false) continue;
    n.append(kid instanceof Node ? kid : String(kid));
  }
  return n;
}

function fill(box, ...kids) { box.replaceChildren(...kids.flat().filter(Boolean)); }

function size(n) {
  if (n === null || n === undefined) return "";
  const u = ["B", "KB", "MB", "GB", "TB"];
  let i = 0;
  while (n >= 1000 && i < u.length - 1) { n /= 1000; i++; }
  return `${i ? n.toFixed(n < 10 ? 1 : 0) : n} ${u[i]}`;
}

function ago(iso) {
  if (!iso) return "";
  const t = new Date(iso.replace(" ", "T"));
  const s = (Date.now() - t.getTime()) / 1000;
  if (isNaN(s)) return "";
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 129600) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

function day(iso) {
  if (!iso) return "";
  return iso.replace("T", " ").slice(0, 16);
}

function snapLabel(name) {
  const m = name.match(/^(\d{4}-\d{2}-\d{2})_(\d{2})(\d{2})(\d{2})/);
  const when = m ? `${m[1]} ${m[2]}:${m[3]}` : name;
  return name.endsWith(".partial") ? `${when} (unfinished, still copying or stopped)` : when;
}

/* The friendly boxes. Returns true when it handled the error. */
function problem(box, err, retry) {
  if (err.kind === "no_drive") {
    fill(box, h("div", { class: "card notice" },
      h("div", { class: "big" }, "🔌"),
      h("h2", {}, /ejected/.test(err.message || "") ? "The drive is ejected" : "The backup drive is not plugged in"),
      h("p", {}, /ejected/.test(err.message || "") ? err.message
        : "Plug in the Toshiba drive (labels Rescue and Vault). Your backups and the offline code are on it. The Help tab works without it."),
      h("button", { class: "btn btn-primary", onclick: retry }, "Check again")));
    return true;
  }
  if (err.kind === "needs_admin") {
    fill(box, h("div", { class: "card notice" },
      h("div", { class: "big" }, "🔒"),
      h("h2", {}, "Needs admin"),
      h("p", {}, `${err.message}. Rescue keeps every file's owner, so system folders belong to root and this page cannot open them. Open them in a terminal with sudo (see Help, "Just one file or folder back").`),
      h("button", { class: "btn", onclick: retry }, "Back")));
    return true;
  }
  fill(box, h("div", { class: "card notice" },
    h("div", { class: "big" }, "⚠️"),
    h("h2", {}, "That did not work"),
    h("p", {}, err.message || String(err)),
    h("button", { class: "btn", onclick: retry }, "Try again")));
  return false;
}

function crumbs(root, path, go) {
  const parts = path ? path.split("/") : [];
  const out = [h("a", { onclick: () => go("") }, root)];
  parts.forEach((p, i) => {
    out.push(h("span", { class: "sep" }, "/"));
    const sub = parts.slice(0, i + 1).join("/");
    out.push(i === parts.length - 1 ? h("span", {}, p) : h("a", { onclick: () => go(sub) }, p));
  });
  return h("div", { class: "crumbs" }, out);
}

function codeView(text) {
  const lines = text.split("\n");
  if (lines.length > 1 && lines[lines.length - 1] === "") lines.pop();
  if (lines.length > 8000) return h("pre", { class: "code" }, text);
  const gutter = h("pre", { class: "code gutter" }, lines.map((_, i) => i + 1).join("\n"));
  const body = h("pre", { class: "code" }, lines.join("\n"));
  body.addEventListener("scroll", () => { gutter.scrollTop = body.scrollTop; });
  return h("div", { class: "code-wrap" }, gutter, body);
}

function diffView(text) {
  const pre = h("pre", { class: "diff" });
  for (const line of text.split("\n")) {
    let cls = null;
    if (line.startsWith("diff --git")) cls = "file";
    else if (line.startsWith("+++") || line.startsWith("---")) cls = "file";
    else if (line.startsWith("@@")) cls = "hunk";
    else if (line.startsWith("+")) cls = "add";
    else if (line.startsWith("-")) cls = "del";
    pre.append(cls ? h("span", { class: cls }, line) : line + "\n");
  }
  return pre;
}

/* ------------------------------------------------------------ state */

const TABS = ["code", "snapshots", "status", "help"];

const state = {
  tab: "code",
  repo: null, rev: null, view: "files", path: "", commit: null, hpath: "",
  area: "vault", set: null, snap: null, spath: "", file: null,
};

function saveHash() {
  const keys = state.tab === "code" ? ["repo", "rev", "view", "path", "commit", "hpath"]
    : state.tab === "snapshots" ? ["area", "set", "snap", "spath", "file"] : [];
  const o = { tab: state.tab };
  keys.forEach((k) => { if (state[k]) o[k] = state[k]; });
  history.replaceState(null, "", "#" + qs(o));
}

function loadHash() {
  const p = new URLSearchParams(location.hash.slice(1));
  for (const k of Object.keys(state)) if (p.has(k)) state[k] = p.get(k);
  if (!TABS.includes(state.tab)) state.tab = "code";
}

/* ------------------------------------------------------------ Code */

async function showCode() {
  saveHash();
  const box = h("div");
  fill($("code"), box);
  if (!state.repo) return repoList(box);
  try {
    await repoPage(box);
  } catch (err) {
    problem(box, err, () => { state.repo = null; showCode(); });
  }
}

async function repoList(box) {
  fill(box, h("p", { class: "muted" }, "Reading the mirrors…"));
  let data;
  try {
    data = await api("/api/repos");
  } catch (err) {
    return problem(box, err, showCode);
  }
  if (!data.repos.length) {
    return fill(box, h("div", { class: "card notice" }, h("div", { class: "big" }, "📭"),
      h("h2", {}, "No mirrors on the drive yet"),
      h("p", {}, "The Vault backup makes them (Forge, anime-codec-lab, eightysix). They appear after the first Vault run finishes.")));
  }
  fill(box,
    h("h2", {}, "Offline code"),
    h("p", { class: "muted" }, "Every branch and commit of each project, mirrored onto the Vault drive. Read-only."),
    h("div", { class: "repos" }, data.repos.map((r) => h("div", {
      class: "card repo",
      onclick: () => { Object.assign(state, { repo: r.name, rev: null, view: "files", path: "", commit: null, hpath: "" }); showCode(); },
    },
    h("div", { class: "title" }, r.label),
    h("div", { class: "sub" }, r.last_date
      ? `last commit ${ago(r.last_date)} · ${day(r.last_date)} · ${r.branches} branch${r.branches === 1 ? "" : "es"}`
      : r.error || "no commits yet"),
    r.last_subject ? h("div", { class: "msg" }, r.last_subject) : null))));
}

async function repoPage(box) {
  const name = state.repo;
  const refs = await api(`/api/repos/${encodeURIComponent(name)}/refs`);
  const empty = !refs.branches.length && !refs.tags.length;
  const rev = empty ? null : state.rev || (refs.branches.some((b) => b.name === refs.head) ? refs.head : null)
    || (refs.branches[0] || refs.tags[0]).name;
  const pick = h("select", {
    onchange: (e) => {
      Object.assign(state, { rev: e.target.value, path: "", commit: null, hpath: "" });
      if (state.view === "commit") state.view = "history";
      if (state.view === "blob") state.view = "files";
      showCode();
    },
  },
    refs.branches.map((b) => h("option", { value: b.name, selected: b.name === rev }, `branch ${b.name}`)),
    refs.tags.map((t) => h("option", { value: t.name, selected: t.name === rev }, `tag ${t.name}`)));
  if (rev && ![...refs.branches, ...refs.tags].some((r) => r.name === rev)) {
    pick.prepend(h("option", { value: rev, selected: true }, `commit ${rev.slice(0, 10)}`));
  }
  const tabBtn = (v, label) => h("button", {
    class: "btn" + (state.view === v || (v === "history" && state.view === "commit") ? " on" : ""),
    onclick: () => {
      if (v === "files" && state.view === "blob") state.path = "";
      state.view = v; state.commit = null;
      showCode();
    },
  }, label);
  const body = h("div", {}, h("p", { class: "muted" }, "Loading…"));
  fill(box,
    h("div", { class: "toolbar" },
      h("button", { class: "btn", onclick: () => { state.repo = null; state.hpath = ""; showCode(); } }, "← All projects"),
      h("h2", { style: "margin:0" }, name.replace(/\.git$/, "").replaceAll("__", "/")),
      h("span", { class: "spacer" }),
      pick,
      h("div", { class: "seg" }, tabBtn("files", "Files"), tabBtn("history", "History"))),
    body);
  if (!rev) {
    return fill(body, h("div", { class: "card notice" }, h("div", { class: "big" }, "📭"),
      h("h2", {}, "No commits yet"), h("p", {}, "This mirror has no branches or tags, so there is nothing to show.")));
  }
  const base = `/api/repos/${encodeURIComponent(name)}`;
  if (state.view === "history") return historyView(body, base, rev);
  if (state.view === "commit" && state.commit) return commitView(body, base, state.commit);
  if (state.view === "blob") return blobView(body, base, rev, state.path);
  return treeView(body, base, rev, state.path);
}

async function treeView(box, base, rev, path) {
  const t = await api(`${base}/tree?${qs({ rev, path })}`);
  const go = (p) => { state.path = p; state.view = "files"; showCode(); };
  const rows = t.entries.map((e) => h("tr", {},
    h("td", {
      class: "name",
      onclick: () => {
        const full = t.path ? `${t.path}/${e.name}` : e.name;
        if (e.openable === false) return toast("This name has bytes that are not text, so it cannot be opened here.", "err");
        if (e.type === "dir") go(full);
        else if (e.type === "file") { state.path = full; state.view = "blob"; showCode(); }
      },
    }, h("span", { class: "ico" }, e.type === "dir" ? "📁" : e.type === "submodule" ? "📦" : e.link ? "🔗" : "📄"), e.name),
    h("td", { class: "num" }, e.type === "file" ? size(e.size) : "")));
  const readme = h("div");
  fill(box,
    h("div", { class: "toolbar" }, crumbs(state.repo.replace(/\.git$/, ""), t.path, go),
      h("span", { class: "spacer" }), h("span", { class: "muted" }, `at ${t.rev.slice(0, 10)}`)),
    h("div", { class: "card" }, rows.length ? h("table", { class: "files" }, h("tbody", {}, rows)) : h("p", { class: "muted" }, "Empty folder.")),
    readme);
  if (t.readme) {
    const rpath = t.path ? `${t.path}/${t.readme}` : t.readme;
    const b = await api(`${base}/blob?${qs({ rev: t.rev, path: rpath })}`);
    if (b.kind === "text") {
      fill(readme, h("div", { class: "card" }, h("h3", { style: "margin-top:0" }, `📖 ${t.readme}`),
        /\.(md|markdown)$/i.test(t.readme) ? h("div", { class: "md", html: md(b.text) }) : h("pre", { class: "code wrap" }, b.text)));
    }
  }
}

async function blobView(box, base, rev, path) {
  const b = await api(`${base}/blob?${qs({ rev, path })}`);
  const parent = path.split("/").slice(0, -1).join("/");
  const head = h("div", { class: "toolbar" },
    crumbs(state.repo.replace(/\.git$/, ""), path, (p) => { state.path = p; state.view = "files"; showCode(); }),
    h("span", { class: "spacer" }),
    h("span", { class: "muted" }, `${size(b.size)} at ${b.rev.slice(0, 10)}`),
    h("button", { class: "btn", onclick: () => { state.view = "history"; state.hpath = path; showCode(); } }, "History of this file"),
    h("button", { class: "btn", onclick: () => { state.path = parent; state.view = "files"; showCode(); } }, "← Folder"));
  let view;
  if (b.kind === "image") {
    view = h("img", { class: "view-img", alt: path });
    blobUrl(`${base}/raw?${qs({ rev: b.rev, path })}`).then((u) => { view.src = u; }).catch(() => {});
  } else if (b.kind === "binary") {
    view = h("p", { class: "muted" }, `A binary file (${size(b.size)}); nothing to show as text.`);
  } else if (/\.(md|markdown)$/i.test(path)) {
    view = h("div", { class: "md" , html: md(b.text) });
  } else {
    view = codeView(b.text);
  }
  fill(box, head, b.truncated ? h("p", { class: "badge" }, "Only the first 1 MB is shown.") : null, h("div", { class: "card" }, view));
}

async function historyView(box, base, rev, skip = 0, list = null) {
  const path = state.hpath;
  const data = await api(`${base}/log?${qs({ rev, skip, path })}`);
  if (!list) {
    list = h("div", { class: "commits" });
    fill(box,
      h("p", { class: "muted" }, `${data.total} commit${data.total === 1 ? "" : "s"}${path ? ` touching ${path}` : ""} on ${rev}`,
        path ? h("button", { class: "btn", style: "margin-left:12px", onclick: () => { state.hpath = ""; showCode(); } }, "All files") : null),
      h("div", { class: "card" }, list));
  }
  list.querySelector(".more")?.remove();
  for (const c of data.commits) {
    list.append(h("div", { class: "c", onclick: () => { state.view = "commit"; state.commit = c.sha; showCode(); } },
      h("span", { class: "sha" }, c.short),
      h("span", { class: "s" }, c.subject),
      h("span", { class: "meta" }, `${c.author} · ${day(c.date)} (${ago(c.date)})`)));
  }
  const shown = skip + data.commits.length;
  if (shown < data.total) {
    list.append(h("div", { class: "more", style: "padding:12px 6px" },
      h("button", { class: "btn", onclick: () => historyView(box, base, rev, shown, list) }, `Show more (${data.total - shown} older)`)));
  }
}

async function commitView(box, base, sha) {
  const c = await api(`${base}/commit/${encodeURIComponent(sha)}`);
  const [subject, ...rest] = c.message.split("\n");
  fill(box,
    h("div", { class: "toolbar" },
      h("button", { class: "btn", onclick: () => { state.view = "history"; state.commit = null; showCode(); } }, "← History"),
      h("span", { class: "spacer" }),
      h("button", { class: "btn btn-primary", onclick: () => { state.rev = c.sha; state.view = "files"; state.path = ""; showCode(); } }, "Browse files at this commit")),
    h("div", { class: "card" },
      h("h2", {}, subject),
      rest.join("\n").trim() ? h("div", { class: "message" }, rest.join("\n").trim()) : null,
      h("p", { class: "muted" }, h("span", { class: "sha" }, c.sha.slice(0, 12)), ` · ${c.author} · ${day(c.date)} (${ago(c.date)})`,
        c.parents.length ? ` · parent ` : " · first commit",
        c.parents.map((p) => h("a", { class: "sha", style: "cursor:pointer;margin-right:8px", onclick: () => { state.commit = p; showCode(); } }, p.slice(0, 10)))),
      h("table", {}, h("tbody", {}, c.files.map((f) => h("tr", {},
        h("td", {}, f.name),
        h("td", { class: "stat-add" }, f.added === "-" ? "binary" : `+${f.added}`),
        h("td", { class: "stat-del" }, f.removed === "-" ? "" : `−${f.removed}`)))))),
    c.truncated ? h("p", { class: "badge" }, "The diff is long; only the first part is shown.") : null,
    c.diff ? diffView(c.diff) : h("p", { class: "muted" }, "No file changes in this commit."));
}

/* ------------------------------------------------------------ Snapshots */

let snapSets = null;
let snapLoad = 0;  // only the newest snapshot request may draw

async function showSnapshots(reloadSets = true) {
  const box = $("snap");
  const mine = ++snapLoad;
  document.querySelectorAll("#snap-area .btn").forEach((b) => b.classList.toggle("on", b.dataset.area === state.area));
  if (reloadSets || !snapSets) {
    fill(box, h("p", { class: "muted" }, "Reading the drive…"));
    try {
      const sets = (await api(`/api/snap/sets?${qs({ area: state.area })}`)).sets;
      if (mine !== snapLoad) return;
      snapSets = sets;
    } catch (err) {
      if (mine !== snapLoad) return;
      fill($("snap-set")); fill($("snap-date"));
      return problem(box, err, () => showSnapshots());
    }
  }
  if (!snapSets.some((s) => s.name === state.set)) state.set = snapSets[0] && snapSets[0].name;
  const set = snapSets.find((s) => s.name === state.set);
  fill($("snap-set"), snapSets.map((s) => h("option", { value: s.name, selected: s.name === state.set }, s.needs_admin ? `${s.name} (needs admin)` : `${s.name} (${s.snapshots.length})`)));
  const snaps = set ? set.snapshots : [];
  if (!snaps.some((s) => s.name === state.snap)) {
    const done = snaps.find((s) => !s.partial);
    state.snap = (done || snaps[0] || {}).name || null;
    state.spath = ""; state.file = null;
  }
  fill($("snap-date"), snaps.map((s) => h("option", { value: s.name, selected: s.name === state.snap }, snapLabel(s.name))));
  saveHash();
  if (set && set.needs_admin) {
    return problem(box, { kind: "needs_admin", message: `The ${set.name} folder on the drive needs admin to read.` }, () => showSnapshots());
  }
  if (!state.snap) {
    return fill(box, h("div", { class: "card notice" }, h("div", { class: "big" }, "📭"),
      h("h2", {}, "No snapshots of this set yet"), h("p", {}, "They appear after its first backup run.")));
  }
  try {
    if (state.file) await snapFile(box, mine);
    else await snapFolder(box, mine);
  } catch (err) {
    if (mine !== snapLoad) return;
    if (!state.file && err.kind === "bad_input" && /is not a folder/.test(err.message)) {
      // a link that led to a file: show the file instead
      state.file = state.spath;
      state.spath = state.spath.split("/").slice(0, -1).join("/");
      return showSnapshots(false);
    }
    problem(box, err, () => {
      if (state.file) state.file = null;
      else state.spath = state.spath.split("/").slice(0, -1).join("/");
      showSnapshots(false);
    });
  }
}

const snapQ = (path) => qs({ area: state.area, set: state.set, snap: state.snap, path });

function snapCrumbs(path) {
  return crumbs(`${state.set} · ${snapLabel(state.snap).split(" (")[0]}`, path, (p) => { state.spath = p; state.file = null; showSnapshots(false); });
}

/* A relative link inside the snapshot (bin -> usr/bin) opens its target in the
   same snapshot; an absolute one would point at the laptop, so it does not. */
function linkTarget(dir, target) {
  if (!target || target.startsWith("/")) return null;
  const parts = dir ? dir.split("/") : [];
  for (const p of target.split("/")) {
    if (!p || p === ".") continue;
    if (p === "..") { if (!parts.length) return null; parts.pop(); } else parts.push(p);
  }
  return parts.join("/");
}

function snapRow(d, e) {
  const full = d.path ? `${d.path}/${e.name}` : e.name;
  const locked = !e.readable;
  return h("tr", { class: locked ? "locked" : "" },
    h("td", {
      class: "name",
      onclick: () => {
        if (e.openable === false) return toast("This name has bytes that are not text, so it cannot be opened here. Copy its folder back instead.", "err");
        if (e.type === "link") {
          const to = linkTarget(d.path, e.target);
          if (to !== null) { state.spath = to; state.file = null; showSnapshots(false); }
          return;
        }
        if (locked || e.type === "other") return;
        if (e.type === "dir") { state.spath = full; state.file = null; }
        else state.file = full;
        showSnapshots(false);
      },
    },
    h("span", { class: "ico" }, e.type === "dir" ? "📁" : e.type === "link" ? "🔗" : e.type === "other" ? "⚙️" : "📄"),
    e.name,
    e.type === "link" ? h("span", { class: "muted" }, `  → ${e.target}`) : null,
    locked ? h("span", { class: "badge" }, "needs admin") : null),
    h("td", { class: "num" }, size(e.size)),
    h("td", { class: "when" }, e.mtime));
}

async function snapFolder(box, mine) {
  const d = await api(`/api/snap/list?${snapQ(state.spath)}`);
  if (mine !== snapLoad) return;
  const result = h("div");
  const partial = state.snap.endsWith(".partial");
  const tbody = h("tbody", {}, d.entries.map((e) => snapRow(d, e)));
  const more = h("div");
  const moreBtn = (shown) => fill(more, h("p", {},
    h("button", { class: "btn", onclick: async () => {
      fill(more, h("p", { class: "muted" }, "Loading…"));
      try {
        const next = await api(`/api/snap/list?${snapQ(state.spath)}&offset=${shown}`);
        next.entries.forEach((e) => tbody.append(snapRow(next, e)));
        const now = shown + next.entries.length;
        if (next.more) moreBtn(now); else fill(more);
      } catch (err) {
        fill(more, h("p", { class: "result-needs_admin" }, err.message));
      }
    } }, `Show more (${d.total - shown} more of ${d.total})`)));
  if (d.more) moreBtn(d.entries.length);
  fill(box,
    partial ? h("p", { class: "badge" }, "This snapshot is unfinished: it is still being copied, or the copy stopped. Pick a date without (unfinished) for a complete one.") : null,
    h("div", { class: "toolbar" }, snapCrumbs(d.path), h("span", { class: "spacer" }),
      d.path ? h("button", { class: "btn", onclick: () => compareInto(result, d.path) }, "Compare folder with laptop") : null,
      d.path ? h("button", { class: "btn btn-primary", onclick: () => restoreInto(result, d.path) }, "Copy this folder back") : null),
    d.live ? h("p", { class: "muted" }, `On the laptop this is ${d.live}`) : null,
    result,
    h("div", { class: "card" },
      d.total ? h("table", { class: "files" }, h("thead", {}, h("tr", {}, h("th", {}, "Name"), h("th", { style: "text-align:right" }, "Size"), h("th", {}, "Changed"))), tbody)
        : h("p", { class: "muted" }, "Empty folder."),
      more));
}

async function snapFile(box, mine) {
  const path = state.file;
  const f = await api(`/api/snap/file?${snapQ(path)}`);
  if (mine !== snapLoad) return;
  const result = h("div");
  let view;
  if (f.kind === "image") {
    view = h("img", { class: "view-img", alt: path });
    blobUrl(`/api/snap/raw?${snapQ(path)}`).then((u) => { view.src = u; }).catch(() => {});
  } else if (f.kind === "binary") {
    view = h("p", { class: "muted" }, `A binary file (${size(f.size)}); nothing to show as text. You can still copy it back.`);
  } else if (f.kind === "link") {
    view = h("p", {}, `A link to ${f.target}`);
  } else {
    view = codeView(f.text);
  }
  fill(box,
    h("div", { class: "toolbar" }, snapCrumbs(path), h("span", { class: "spacer" }), h("span", { class: "muted" }, size(f.size)),
      h("button", { class: "btn", onclick: () => { state.file = null; showSnapshots(false); } }, "← Folder")),
    h("div", { class: "toolbar" },
      f.live ? h("button", { class: "btn", onclick: () => compareInto(result, path) }, "Compare with the laptop") : null,
      h("button", { class: "btn btn-primary", onclick: () => restoreInto(result, path) }, "Copy back to ~/Restored"),
      f.live ? h("span", { class: "muted" }, `On the laptop: ${f.live}`) : null),
    result,
    f.truncated ? h("p", { class: "badge" }, "Only the first 1 MB is shown.") : null,
    h("div", { class: "card" }, view));
}

async function compareInto(box, path) {
  fill(box, h("div", { class: "card" }, h("p", { class: "muted" }, "Comparing…")));
  try {
    const c = await api(`/api/snap/compare?${snapQ(path)}`);
    const kids = [h("div", { class: `result-${c.state}` }, c.say), h("p", { class: "muted" }, `Laptop copy: ${c.live}`)];
    if (c.only_snapshot) {
      const list = (title, names) => names.length ? [h("h3", {}, `${title} (${names.length})`), h("p", {}, names.join(", "))] : [];
      kids.push(...list("Only in the snapshot", c.only_snapshot), ...list("Only on the laptop", c.only_laptop), ...list("Different size", c.changed));
    } else if (c.diff) {
      kids.push(diffView(c.diff));
    } else if (c.state === "different") {
      kids.push(h("p", { class: "muted" }, `Not text, so no line-by-line view. Snapshot ${size(c.snap_size)}, laptop ${size(c.live_size)}.`));
    }
    fill(box, h("div", { class: "card" }, kids));
  } catch (err) {
    fill(box, h("div", { class: "card" }, h("p", { class: "result-needs_admin" }, err.message)));
  }
}

async function restoreInto(box, path) {
  const where = `~/Restored/${state.snap.replace(/\.partial$/, "")}/${state.set}/${path}`;
  if (!confirm(`Copy ${path} to ${where}?\n\nIt goes to a new place; nothing on the laptop or the drive is changed or deleted.`)) return;
  fill(box, h("div", { class: "card" }, h("p", { class: "muted" }, "Copying…")));
  try {
    let job = await api("/api/snap/restore", { method: "POST", body: JSON.stringify({ area: state.area, set: state.set, snap: state.snap, path }) });
    while (job.state === "copying") {
      fill(box, h("div", { class: "card" }, h("p", {}, `Copying… ${job.files} files, ${size(job.bytes)}`)));
      await new Promise((r) => setTimeout(r, 700));
      job = await api(`/api/jobs/${job.id}`);
    }
    if (job.state === "failed") throw new Error(job.error || "the copy failed");
    fill(box, h("div", { class: "card" },
      h("div", { class: "result-same" }, `Copied ${job.files} file${job.files === 1 ? "" : "s"} (${size(job.bytes)})`),
      h("p", {}, `It is in ${job.dest}`),
      job.skipped.length ? h("div", {},
        h("p", { class: "badge" }, `${job.skipped.length} item(s) could not be copied:`),
        h("pre", { class: "code wrap" }, job.skipped.slice(0, 30).map((s) => `${s.path}: ${s.why}`).join("\n"))) : null));
    toast("Copied back to ~/Restored", "ok");
  } catch (err) {
    fill(box, h("div", { class: "card" }, h("p", { class: "result-needs_admin" }, err.message)));
  }
}

/* ------------------------------------------------------------ Status */

let progressTimer = null;
let progressGen = 0;  // a newer watch makes older ones stop

async function showStatus() {
  saveHash();
  const box = $("status");
  let st;
  try {
    st = await api("/api/status");
  } catch (err) {
    return problem(box, err, showStatus);
  }
  updatePill(st);
  const run = h("div");
  const btn = (area, label) => h("button", {
    class: "btn" + (area === "all" ? " btn-primary" : ""), disabled: st.running || !st.plugged,
    onclick: () => backupNow(area),
  }, label);
  const kids = [];
  if (!st.plugged) {
    kids.push(h("div", { class: "card notice" }, h("div", { class: "big" }, "🔌"),
      h("h2", {}, "The backup drive is not plugged in"),
      h("p", {}, "Backups wait until it is: plugging it in starts whatever is due by itself."),
      h("button", { class: "btn btn-primary", onclick: showStatus }, "Check again")));
  }
  kids.push(h("div", { class: "card" },
    h("div", { class: "big-line" }, st.running ? "⏳ A backup is running" : st.plugged ? "✅ Drive plugged in, no backup running" : "Drive not plugged in"),
    h("div", { class: "buttons" },
      btn("all", "Back up everything now"), btn("rescue", "Rescue now"), btn("vault", "Vault now"),
      h("span", { class: "spacer", style: "flex:1" }),
      h("button", { class: "btn btn-danger", disabled: st.running || !st.plugged, onclick: ejectDrive }, "Eject drive")),
    run));
  const areas = h("div", { class: "areas" });
  for (const a of st.areas) {
    const card = h("div", { class: "card" }, h("h2", {}, a.label), h("p", { class: "muted" }, a.about));
    if (!a.plugged) {
      card.append(h("p", {}, "Not plugged in."));
    } else {
      const pct = a.total_gb ? Math.round((100 * a.used_gb) / a.total_gb) : 0;
      card.append(
        h("div", {}, `${a.free_gb} GB free of ${a.total_gb} GB `,
          a.due === null ? h("span", { class: "pill" }, "due: needs admin to tell")
            : h("span", { class: "pill " + (a.due ? "warn" : "good") }, a.due ? "backup due" : "up to date")),
        h("div", { class: "bar" }, h("div", { style: `width:${pct}%` })),
        h("p", { class: "muted" }, `Runs every ${a.every_hours} h when the drive is in, keeps the newest ${a.keep}.`),
        h("table", {},
          h("thead", {}, h("tr", {}, h("th", {}, "Set"), h("th", {}, "Snapshots"), h("th", {}, "Newest"), h("th", {}, "Age"), h("th", {}, "Due"))),
          h("tbody", {}, a.sets.map((s) => h("tr", {},
            h("td", {}, s.name),
            h("td", {}, s.needs_admin ? "needs admin" : String(s.count), s.unfinished.length ? h("span", { class: "badge" }, `${s.unfinished.length} unfinished`) : null),
            h("td", {}, s.newest ? snapLabel(s.newest) : "none yet"),
            h("td", {}, s.age_hours === null ? "" : s.age_hours < 48 ? `${s.age_hours} h` : `${Math.round(s.age_hours / 24)} days`),
            h("td", {}, s.due === null || s.due === undefined ? "" : s.due ? "due" : "no"))))));
      if (a.mirrors) card.append(h("p", {}, `Git mirrors: ${a.mirrors.length ? a.mirrors.map((m) => m.replace(/\.git$/, "")).join(", ") : "none yet"}`));
      if (a.last_run) {
        const r = a.last_run;
        const sets = Object.entries(r.sets || {}).map(([n, v]) => `${n} ${v.ok ? "ok" : "failed"}`).join(", ");
        const gits = Object.entries(r.git || {}).map(([p, ok]) => `${p.split("/").pop()} ${ok ? "ok" : "failed"}`).join(", ");
        card.append(...[h("h3", {}, "Last run"),
          h("p", {}, r.skipped ? `Skipped (${r.skipped}) at ${day(r.started)}`
            : `${r.ok ? "✅ Finished" : "⚠️ Had a problem"} · started ${day(r.started)} (${ago(r.started)}) · took ${Math.round((r.seconds || 0) / 60)} min`),
          sets ? h("p", { class: "muted" }, sets) : null,
          gits ? h("p", { class: "muted" }, `Git mirrors: ${gits}`) : null].filter(Boolean));
      }
    }
    areas.append(card);
  }
  kids.push(areas);
  fill(box, kids);
  watchProgress(run, st.running);
}

function updatePill(st) {
  const pill = $("drive-pill");
  pill.className = "pill " + (st.running ? "warn" : st.plugged ? "good" : "bad");
  pill.textContent = st.running ? "backup running" : st.plugged ? "drive plugged in" : "drive not plugged in";
}

async function watchProgress(box, running, gen = ++progressGen) {
  clearTimeout(progressTimer);
  let p;
  try {
    p = await api("/api/progress");
  } catch (err) {
    if (gen === progressGen && state.tab === "status") progressTimer = setTimeout(() => watchProgress(box, running, gen), 5000);
    return;
  }
  if (gen !== progressGen) return;
  const units = p.units.filter((u) => u.running).map((u) => u.Id.replace(".service", ""));
  const used = Object.entries(p.used_gb).map(([a, gb]) => `${a} ${gb} GB used`).join(" · ");
  fill(box,
    h("h3", {}, p.running ? `Running: ${units.join(", ")}` : "Recent backup log"),
    p.running ? h("p", { class: "muted" }, `${used}. This page updates by itself every 3 seconds.`) : null,
    h("div", { class: "logbox big" }, p.journal.join("\n") || "Nothing in the log yet."));
  const log = box.querySelector(".logbox");
  log.scrollTop = log.scrollHeight;  // the newest lines are at the bottom
  if (p.running && state.tab === "status") {
    const hidden = window.ForgeVisible && !window.ForgeVisible.on;
    progressTimer = setTimeout(() => watchProgress(box, true, gen), hidden ? 15000 : 3000);
  } else if (running && !p.running) {
    showStatus();
  }
}

async function backupNow(area) {
  const what = { all: "everything (Rescue, then Vault)", rescue: "the whole laptop (Rescue)", vault: "the work folders and git mirrors (Vault)" }[area];
  if (!confirm(`Back up ${what} now?\n\nIt runs in the background at low priority; Rescue can take an hour. You can close this page.`)) return;
  try {
    const r = await api("/api/backup", { method: "POST", body: JSON.stringify({ area }) });
    toast(`Started ${r.unit}`, "ok");
  } catch (err) {
    toast(err.message, "err");
  }
  setTimeout(showStatus, 800);
}

async function ejectDrive() {
  if (!confirm("Eject the backup drive? Both parts are unmounted and the drive powers down, so it can be unplugged.")) return;
  try {
    const r = await api("/api/eject", { method: "POST" });
    toast(r.message, "ok");
  } catch (err) {
    toast(err.message, "err");
  }
  setTimeout(showStatus, 1500);
}

/* ------------------------------------------------------------ Help */

async function showHelp() {
  saveHash();
  const box = $("help");
  try {
    const docs = await api("/api/help");
    fill(box,
      docs.RESTORE ? h("div", { class: "card md", html: md(docs.RESTORE) }) : null,
      docs.README ? h("div", { class: "card md", html: md(docs.README) }) : null);
  } catch (err) {
    problem(box, err, showHelp);
  }
}

/* ------------------------------------------------------------ wiring */

const shows = { code: showCode, snapshots: () => showSnapshots(), status: showStatus, help: showHelp };
const selectTab = initTabs((name) => {
  state.tab = name;
  if (name !== "status") { clearTimeout(progressTimer); progressGen++; }
  shows[name]();
});

document.querySelectorAll("#snap-area .btn").forEach((b) => b.addEventListener("click", () => {
  if (state.area === b.dataset.area) return;
  Object.assign(state, { area: b.dataset.area, set: null, snap: null, spath: "", file: null });
  showSnapshots();
}));
$("snap-set").addEventListener("change", (e) => { Object.assign(state, { set: e.target.value, snap: null, spath: "", file: null }); showSnapshots(false); });
$("snap-date").addEventListener("change", (e) => { state.snap = e.target.value; state.file = null; showSnapshots(false); });

loadHash();
selectTab(state.tab);
api("/api/status").then(updatePill).catch(() => {});
