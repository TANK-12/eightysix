// Library: everything made so far, searchable, with a viewer, delete, and
// a picker other sections use to choose a starting picture.
"use strict";
(function (AS) {
  const $ = AS.$, el = AS.el;
  const gallery = $("gallery"), search = $("search");
  const kind = AS.chips($("libKind"), () => load());
  let seq = 0, retry = null, shownKey = "";

  function line(box, text) {
    box.replaceChildren(el("div", { className: "empty-state" }, text));
  }

  async function load() {
    const mine = ++seq;
    const params = new URLSearchParams({ q: search.value, kind: kind.value });
    let rows;
    try {
      const res = await fetch(`/api/library?${params}`);
      if (res.status >= 400 && res.status < 500) {
        // this search can never work (say, far too long): say so, no retry
        const msg = await AS.errorText(res, "That search can't be run");
        if (mine !== seq) return true;
        shownKey = "";
        line(gallery, msg);
        return true;
      }
      if (!res.ok) throw new Error(await AS.errorText(res, "The library didn't answer"));
      rows = await res.json();
    } catch (e) {
      if (mine !== seq) return true; // a newer search took over
      shownKey = "";
      line(gallery, AS.failText(e) + " Trying again by itself...");
      // retry with a growing wait (2 s up to 30 s), resting while hidden
      if (!retry) {
        retry = ForgeIdle.poll(async () => {
          const ok = await load();
          if (ok && retry) { retry.stop(); retry = null; }
          return ok;
        }, 2000, { backoff: 2, maxMs: 30000 });
      }
      return false;
    }
    if (mine !== seq) return true; // an older answer arriving late
    const k = JSON.stringify(rows);
    if (k === shownKey) return true; // same list: keep the thumbs, no flicker
    shownKey = k;
    if (!rows.length) {
      line(gallery, search.value.trim() || kind.value ? "Nothing found." : "Nothing here yet. Make something and it shows up here.");
      return true;
    }
    gallery.replaceChildren(...rows.map(thumb));
    return true;
  }

  function thumb(row) {
    const isVideo = row.kind === "video";
    // the small thumbnail when the server has one (videos: their first frame)
    const media = el("div", { className: "media" },
      row.missing ? el("div", { className: "gone" }, "The file is gone")
        : row.thumb_url ? AS.media(row.thumb_url, "image", { lazy: true })
        : isVideo ? AS.media(row.url, "video", { muted: true, controls: false })
        : AS.media(row.url, "image", { lazy: true }));
    const box = el("div", { className: "thumb", tabIndex: 0, title: row.prompt || "", onclick: () => view(row),
      onkeydown: (e) => { if (e.key === "Enter") view(row); } },
      media,
      isVideo ? el("span", { className: "kind" }, "Video") : null,
      el("button", { type: "button", className: "del", title: "Delete", ariaLabel: "Delete",
        onclick: (e) => { e.stopPropagation(); remove(row, box); } }, "×"),
      el("div", { className: "caption" }, row.prompt || "(no words)"),
    );
    return box;
  }

  async function remove(row, box) {
    if (!(await ForgeDialog.confirm("Delete this for good?", { ok: "Delete", cancel: "Keep it" }))) return false;
    try {
      const res = await fetch(`/api/library/${encodeURIComponent(row.id)}`, { method: "DELETE" });
      if (!res.ok && res.status !== 404) throw new Error(await AS.errorText(res, "Couldn't delete that"));
      if (box) box.remove();
      shownKey = "";
      return true;
    } catch (e) {
      ForgeDialog.alert(AS.failText(e));
      return false;
    }
  }

  // ---- viewer ----
  const viewer = $("viewer");
  function view(row) {
    $("viewerMedia").replaceChildren(row.missing
      ? el("p", { className: "hint" }, "The file for this one is gone from the outputs folder. You can delete the entry.")
      : AS.media(row.url, row.kind, { play: true }));
    $("viewerPrompt").textContent = row.prompt || "";
    const close = () => closeViewer();
    $("viewerActions").replaceChildren(
      ...(row.missing ? [] : AS.resultActions({ id: row.id, url: row.url, kind: row.kind })).map((b) => {
        if (b.tagName === "BUTTON") b.addEventListener("click", close);
        return b;
      }),
      el("button", { type: "button", className: "btn btn-danger", onclick: async () => {
        if (await remove(row, null)) { closeViewer(); load(); }
      } }, "Delete"),
    );
    viewer.hidden = false;
  }
  function closeViewer() {
    viewer.hidden = true;
    $("viewerMedia").replaceChildren(); // stops a playing video
  }
  $("viewerClose").addEventListener("click", closeViewer);
  viewer.addEventListener("mousedown", (e) => { if (e.target === viewer) closeViewer(); });

  // ---- picker: choose a picture from the library ----
  const pickModal = $("pickModal"), pickGallery = $("pickGallery");
  let pickDone = null;
  function endPick(item) {
    pickModal.hidden = true;
    pickGallery.replaceChildren();
    if (pickDone) { pickDone(item); pickDone = null; }
  }
  $("pickClose").addEventListener("click", () => endPick(null));
  pickModal.addEventListener("mousedown", (e) => { if (e.target === pickModal) endPick(null); });
  async function pick() {
    if (pickDone) endPick(null);
    pickModal.hidden = false;
    line(pickGallery, "Loading your pictures...");
    const promise = new Promise((done) => { pickDone = done; });
    try {
      const rows = await AS.get("/api/library?" + new URLSearchParams({ q: "", kind: "image" }), "The library didn't answer");
      if (pickModal.hidden) return promise;
      if (!rows.length) line(pickGallery, "No pictures yet. Make one first, or choose a file instead.");
      else pickGallery.replaceChildren(...rows.filter((row) => !row.missing).map((row) => el("div", { className: "thumb", tabIndex: 0, title: row.prompt || "",
        onclick: () => endPick(row), onkeydown: (e) => { if (e.key === "Enter") endPick(row); } },
        el("div", { className: "media" }, AS.media(row.thumb_url || row.url, "image", { lazy: true })),
        el("div", { className: "caption" }, row.prompt || "(no words)"))));
    } catch (e) {
      line(pickGallery, AS.failText(e));
    }
    return promise;
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || document.querySelector(".forge-dialog-back")) return;
    if (!pickModal.hidden) endPick(null);
    else if (!viewer.hidden) closeViewer();
  });

  let debounce = 0;
  search.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(load, 200); });
  AS.on("library-changed", () => { shownKey = ""; if (!$("sec-library").hidden) load(); });

  AS.library = { load, pick };
})(window.AS);
