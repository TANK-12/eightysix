/* The Docs section (docs.html): every doc from doc_sources.json as a folder
 * tree, newest first, with a read-only view. "Recent" holds the newest 20
 * from every folder. #<path> opens a doc, so a link can point straight at it.
 */
(() => {
const { api, el, markdown } = window.ClaudeCommon;
const $ = (id) => document.getElementById(id);
const RECENT = 20;
let listing = { folders: [], docs: [] };
let current = null;

function guess(doc) {
  return doc.dated_by === "modified" ? "no date in the name or header; this is when the file last changed" : `dated by its ${doc.dated_by}`;
}

function docButton(doc) {
  const b = el("button", "d-doc");
  b.type = "button";
  b.dataset.path = doc.path;
  b.title = `${doc.summary || doc.name}\n${doc.path}`;
  b.appendChild(el("span", "d-title", doc.title));
  b.appendChild(el("span", `d-date${doc.dated_by === "modified" ? " guess" : ""}`, `${doc.date} · ${doc.name}`));
  b.onclick = () => open(doc.path);
  return b;
}

function folderNode(name, node, open) {
  const box = el("details", "d-folder");
  box.open = open;
  const head = el("summary", "", name);
  head.appendChild(el("span", "d-n", String(node.count)));
  box.appendChild(head);
  for (const [sub, child] of node.subs) box.appendChild(folderNode(sub, child, false));
  for (const doc of node.docs) box.appendChild(docButton(doc));
  return box;
}

function buildTree() {
  const root = new Map();
  for (const doc of listing.docs) {
    let level = root;
    let node = null;
    for (const part of doc.folder) {
      if (!level.has(part)) level.set(part, { subs: new Map(), docs: [], count: 0 });
      node = level.get(part);
      node.count += 1;
      level = node.subs;
    }
    if (node) node.docs.push(doc);
  }
  return root;
}

function drawTree(searching) {
  const tree = $("tree");
  tree.replaceChildren();
  const recent = { subs: new Map(), docs: listing.docs.slice(0, RECENT), count: Math.min(RECENT, listing.docs.length) };
  tree.appendChild(folderNode(searching ? "Found" : "Recent", recent, true));
  const root = buildTree();
  const order = [...listing.folders, ...[...root.keys()].filter((k) => !listing.folders.includes(k))];
  for (const name of order) if (root.has(name)) tree.appendChild(folderNode(name, root.get(name), searching));
  $("count").textContent = `${listing.docs.length} docs`;
  mark();
}

function mark() {
  for (const b of document.querySelectorAll(".d-doc")) b.classList.toggle("on", b.dataset.path === current);
}

async function copy(text) {
  try { await navigator.clipboard.writeText(text); return; } catch (e) {}
  const t = el("textarea");
  t.value = text;
  document.body.appendChild(t);
  t.select();
  document.execCommand("copy");
  t.remove();
}

async function open(path) {
  current = path;
  mark();
  if (location.hash.slice(1) !== encodeURIComponent(path)) history.replaceState(null, "", `#${encodeURIComponent(path)}`);
  const view = $("view");
  let doc;
  try {
    doc = await api(`/api/docs/read?path=${encodeURIComponent(path)}`);
  } catch (e) {
    view.replaceChildren(el("p", "muted", `Could not read it: ${e.message}`));
    return;
  }
  const meta = el("div", "d-meta");
  const date = el("span", "", `📅 ${doc.date}`);
  date.title = guess(doc);
  meta.append(date, el("span", "", `changed ${doc.updated}`), el("span", "", doc.folder.join(" / ")));
  const where = el("code", "", doc.path);
  const copyBtn = el("button", "btn small-btn", "Copy path");
  copyBtn.type = "button";
  copyBtn.title = "Paste it into a Claude message and Claude can read the doc";
  copyBtn.onclick = async () => { await copy(doc.path); copyBtn.textContent = "Copied"; setTimeout(() => (copyBtn.textContent = "Copy path"), 1200); };
  meta.append(where, copyBtn);
  const body = el("div", "d-body");
  if (doc.name.toLowerCase().endsWith(".md")) body.innerHTML = markdown(window.DocsText.unwrap(doc.text));
  else body.appendChild(el("pre", "", doc.text));
  view.replaceChildren(meta, body);
  view.scrollTop = 0;
}

async function load() {
  const q = $("search").value.trim();
  listing = await api(`/api/docs${q ? `?q=${encodeURIComponent(q)}` : ""}`);
  $("lib-path") && ($("lib-path").textContent = listing.library);
  drawTree(Boolean(q));
}

$("search").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
$("search").addEventListener("search", () => { if (!$("search").value) load(); });
$("refresh").onclick = load;
try { if (localStorage.getItem("claude.layout") === "enjoy") $("back").href = "enjoy.html"; } catch (e) {}
load().then(() => {
  const wanted = decodeURIComponent(location.hash.slice(1));
  if (wanted) open(wanted);
});
})();
