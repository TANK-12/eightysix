// AI Studio start-up: the section tabs, then the first loads.
// A section can be opened by address too (#image, #edit, #video, #worlds,
// #library); the last one used comes back next time.
"use strict";
(function (AS) {
  const SECTIONS = ["image", "edit", "video", "worlds", "library"];
  const STORE = "ai-studio:section";
  const nav = AS.$("sectionNav");
  let libraryLoaded = false;

  AS.show = function (name) {
    if (!SECTIONS.includes(name)) name = "image";
    document.querySelectorAll("main > .section").forEach((s) => { s.hidden = s.dataset.section !== name; });
    nav.querySelectorAll("button").forEach((b) => {
      const on = b.dataset.section === name;
      b.classList.toggle("on", on);
      if (on) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    try { localStorage.setItem(STORE, name); } catch (e) { /* private window */ }
    if (location.hash !== "#" + name) history.replaceState(null, "", "#" + name);
    if (name === "library" && !libraryLoaded) { libraryLoaded = true; AS.library.load(); }
    AS.$("main").scrollTop = 0;
  };
  nav.addEventListener("click", (e) => {
    const b = e.target.closest("button[data-section]");
    if (b) AS.show(b.dataset.section);
  });
  window.addEventListener("hashchange", () => AS.show(location.hash.slice(1)));
  // a result made elsewhere refreshes the library the next time it is opened
  AS.on("library-changed", () => { if (AS.$("sec-library").hidden) libraryLoaded = false; });

  // Go buttons wait while another section's heavy job runs (core.js AS.heavy)
  function paintHeavy() {
    document.querySelectorAll("main form.form").forEach((form) => {
      const why = AS.heavy.reason(form);
      let line = form.querySelector(".busy-line");
      if (!line) {
        line = AS.el("p", { className: "busy-line", role: "status" });
        form.querySelector(".go").before(line);
      }
      line.textContent = why;
      form.querySelectorAll(".go").forEach((b) => {
        if (why) { b.disabled = true; b.dataset.heavy = "1"; }
        else if (b.dataset.heavy) { delete b.dataset.heavy; b.disabled = false; }
      });
    });
    const why = AS.heavy.reason(null);
    AS.$("modelsBusyLine").textContent = why ? why + " Switching models waits until then." : "";
    document.querySelectorAll('#modelsList button[data-act="activate"]').forEach((b) => {
      if (why) { b.disabled = true; b.title = why; }
    });
  }
  AS.on("heavy", paintHeavy);

  // The server's own report (GET /api/busy -> {busy: null | {kind, id,
  // detail}}) covers a job started in another window. Every 5 s while
  // shown; a failing server waits longer. GET /api/models carries it too.
  ForgeIdle.poll(async () => {
    try { AS.heavy.server((await AS.get("/api/busy")).busy); } catch (e) { return false; }
  }, 5000, { backoff: 2, maxMs: 30000, immediate: true });
  AS.on("models", paintHeavy);

  let first = location.hash.slice(1);
  if (!SECTIONS.includes(first)) { try { first = localStorage.getItem(STORE) || "image"; } catch (e) { first = "image"; } }
  AS.show(first);
  AS.models.load();
})(window.AS);
