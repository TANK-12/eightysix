const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

let reader = null; // { key, label, pageUrls: [...], page: 0 }
let focusBeforeReader = null; // the row or tile that opened the reader
let opening = false; // one chapter or PDF opens at a time, however fast the clicks

// Load the shelves. Returns false when the server did not answer, so the
// retry poll below stretches its wait instead of hammering a dead server.
async function loadLibrary() {
  let data;
  try {
    const r = await fetch("/api/library");
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    data = await r.json();
  } catch (e) {
    $("libraryNote").textContent = "Can't reach InkForge's server. Retrying by itself…";
    return false;
  }
  $("libraryNote").textContent = data.komikku_error || "";
  renderMangaShelf(data.mangas || []);
  renderPdfShelf(data.pdfs || []);
  return true;
}

// Only runs while the library has not loaded yet (and rests while hidden):
// 3 s, then 6, 12, up to 30 s between tries; stops for good once loaded.
let libraryRetry = null;
async function loadLibraryUntilItWorks() {
  if (await loadLibrary()) return;
  if (libraryRetry) return;
  libraryRetry = ForgeIdle.poll(async () => {
    if (!(await loadLibrary())) return false;
    libraryRetry.stop();
    libraryRetry = null;
  }, 3000, { backoff: 2, maxMs: 30000 });
}

function renderMangaShelf(mangas) {
  $("mangaShelf").innerHTML = mangas.length
    ? mangas.map((m) => `
      <div class="tile" tabindex="0" data-manga="${esc(m.id)}">
        <div class="cover">📚</div>
        <div class="title" title="${esc(m.name)}">${esc(m.name)}</div>
        <div class="sub">${m.chapters.length} chapter(s)</div>
      </div>`).join("")
    : '<div class="muted">Nothing downloaded in Komikku yet.</div>';

  $("mangaShelf").querySelectorAll("[data-manga]").forEach((el) => {
    const manga = mangas.find((m) => String(m.id) === el.dataset.manga);
    onActivate(el, () => showChapters(manga));
  });
}

// Click or Enter/Space on a tile or row.
function onActivate(el, fn) {
  el.onclick = fn;
  // While the reader is open the row behind it must not re-open the chapter.
  el.onkeydown = (ev) => {
    if (reader) return;
    if (ev.key === "Enter" || ev.key === " ") { ev.preventDefault(); fn(); }
  };
}

function showChapters(manga) {
  $("chapterSection").hidden = false;
  $("chapterSeriesName").textContent = manga.name;
  $("chapterList").innerHTML = manga.chapters.length ? manga.chapters.map((c) => `
    <div class="chapRow" tabindex="0" data-chapter="${esc(c.id)}">
      <span>${esc(c.title || "Chapter " + c.num)}</span>
      <span class="muted">${c.pages} page(s)${c.last_page_read_index ? " · resume p." + (c.last_page_read_index + 1) : ""}</span>
    </div>`).join("") : '<div class="muted">No downloaded chapters.</div>';
  $("chapterList").querySelectorAll("[data-chapter]").forEach((el) => {
    const chapter = manga.chapters.find((c) => String(c.id) === el.dataset.chapter);
    onActivate(el, () => openKomikkuChapter(chapter, el));
  });
  $("chapterSection").scrollIntoView({ behavior: "smooth", block: "start" });
}

async function openKomikkuChapter(chapter, row) {
  if (opening) return;
  opening = true;
  row.classList.add("busy");
  try {
    let pages;
    try {
      const r = await fetch(`/api/komikku/chapter/${chapter.id}/pages`);
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).detail || `HTTP ${r.status}`);
      ({ pages } = await r.json());
    } catch (e) {
      ForgeDialog.alert(`Could not load that chapter: ${e.message}`);
      return;
    }
    if (!pages.length) { ForgeDialog.alert("That chapter has no pages on disk."); return; }
    const key = `komikku:${chapter.id}`;
    const saved = await fetchProgress(key);
    // No InkForge position yet: start where Komikku itself left off, as the
    // "resume p." hint in the chapter list promises.
    const start = saved === null ? chapter.last_page_read_index || 0 : saved;
    reader = {
      key,
      label: row.querySelector("span").textContent,
      pageUrls: pages.map((p) => `/api/komikku/page/${chapter.id}/${encodeURIComponent(p)}`),
      page: Math.max(0, Math.min(start, pages.length - 1)),
    };
    openReader();
  } finally {
    opening = false;
    row.classList.remove("busy");
  }
}

function renderPdfShelf(pdfs) {
  $("pdfShelf").innerHTML = pdfs.length
    ? pdfs.map((p) => `
      <div class="tile" tabindex="0" data-pdf="${esc(p.id)}">
        <div class="cover">📄</div>
        <div class="title" title="${esc(p.title)}">${esc(p.title)}</div>
        <div class="sub">${p.pages} page(s)</div>
      </div>`).join("")
    : '<div class="muted">No PDFs imported yet. Pick one above and press Import PDF.</div>';

  $("pdfShelf").querySelectorAll("[data-pdf]").forEach((el) => {
    const pdf = pdfs.find((p) => p.id === el.dataset.pdf);
    onActivate(el, () => openPdf(pdf));
  });
}

async function openPdf(pdf) {
  if (opening || !pdf.pages) return;
  opening = true;
  try {
    const key = `pdf:${pdf.id}`;
    const start = (await fetchProgress(key)) || 0;
    reader = {
      key,
      label: pdf.title,
      pageUrls: Array.from({ length: pdf.pages }, (_, i) => `/api/pdf/${pdf.id}/page/${i}`),
      page: Math.max(0, Math.min(start, pdf.pages - 1)),
    };
    openReader();
  } finally {
    opening = false;
  }
}

// The saved page, or null when InkForge has none for this item.
async function fetchProgress(key) {
  try {
    const r = await fetch(`/api/progress/${encodeURIComponent(key)}`);
    const d = await r.json();
    if (d.saved === false) return null;
    return Number.isInteger(d.page) ? d.page : null;
  } catch (e) {
    return null;
  }
}

let saveTimer = null;
function saveProgress() {
  if (!reader) return;
  clearTimeout(saveTimer);
  const { key, page } = reader;
  saveTimer = setTimeout(() => {
    fetch(`/api/progress/${encodeURIComponent(key)}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ page }),
    }).catch(() => {});
  }, 300);
}

function openReader() {
  focusBeforeReader = document.activeElement;
  focusBeforeReader?.blur?.();
  $("reader").classList.add("open");
  document.body.style.overflow = "hidden";
  requestAnimationFrame(() => $("reader").classList.add("shown"));
  renderPage();
}

function closeReader() {
  saveProgress();
  $("reader").classList.remove("open", "shown");
  document.body.style.overflow = "";
  $("readerImg").removeAttribute("src");
  $("readerMsg").textContent = "";
  reader = null;
  if (focusBeforeReader?.isConnected) focusBeforeReader.focus({ preventScroll: true });
  focusBeforeReader = null;
}

function renderPage() {
  if (!reader) return;
  const img = $("readerImg");
  img.classList.add("loading");
  $("readerMsg").textContent = "";
  img.src = reader.pageUrls[reader.page];
  $("readerStage").scrollTop = 0;
  $("readerLabel").textContent = reader.label;
  $("pageIndicator").textContent = `${reader.page + 1} / ${reader.pageUrls.length}`;
  // Fetch the next page ahead so turning to it is instant.
  if (reader.page + 1 < reader.pageUrls.length) new Image().src = reader.pageUrls[reader.page + 1];
  saveProgress();
}

// Until the Fit button is used, a tall strip page (webtoon style) opens fit
// to width, where it can be scrolled, instead of as a thin sliver.
let fitChosen = false;
function setFitWidth(on) {
  $("readerStage").classList.toggle("fitWidth", on);
  $("fitToggle").textContent = on ? "Fit page" : "Fit width";
}

$("readerImg").onload = () => {
  const img = $("readerImg");
  img.classList.remove("loading");
  if (!fitChosen && img.naturalWidth) setFitWidth(img.naturalHeight > 2.5 * img.naturalWidth);
};
$("readerImg").onerror = () => {
  if (!reader || !$("readerImg").getAttribute("src")) return;
  $("readerImg").classList.remove("loading");
  $("readerMsg").textContent = "This page could not be loaded.";
};

function nextPage() {
  if (!reader || reader.page >= reader.pageUrls.length - 1) return;
  reader.page += 1;
  renderPage();
}

function prevPage() {
  if (!reader || reader.page <= 0) return;
  reader.page -= 1;
  renderPage();
}

$("readerClose").onclick = closeReader;
$("nextPage").onclick = nextPage;
$("prevPage").onclick = prevPage;
$("fitToggle").onclick = () => {
  fitChosen = true;
  setFitWidth(!$("readerStage").classList.contains("fitWidth"));
};
// Click the left third of the page to go back, anywhere else to go on.
$("readerStage").onclick = (ev) => {
  const box = $("readerStage").getBoundingClientRect();
  if (ev.clientX - box.left < box.width / 3) prevPage();
  else nextPage();
};

document.addEventListener("keydown", (ev) => {
  if (!reader) return;
  if (ev.key === "ArrowRight") nextPage();
  else if (ev.key === "ArrowLeft") prevPage();
  else if (ev.key === "Escape") closeReader();
});

let importing = false;
$("importForm").onsubmit = async (ev) => {
  ev.preventDefault();
  if (importing) return;
  $("importErr").textContent = "";
  const file = $("pdfFile").files[0];
  if (!file) { $("importErr").textContent = "Pick a PDF first."; return; }
  importing = true;
  const btn = $("importForm").querySelector("button");
  btn.disabled = true;
  btn.textContent = "Importing…";
  try {
    const body = new FormData();
    body.append("file", file);
    const r = await fetch("/api/pdf/import", { method: "POST", body });
    if (!r.ok) {
      const detail = (await r.json().catch(() => ({}))).detail;
      $("importErr").textContent = typeof detail === "string" ? detail : "Import failed.";
      return;
    }
    $("pdfFile").value = "";
    await loadLibraryUntilItWorks();
  } catch (e) {
    $("importErr").textContent = "Import failed: the server did not answer.";
  } finally {
    importing = false;
    btn.disabled = false;
    btn.textContent = "Import PDF";
  }
};

loadLibraryUntilItWorks();
