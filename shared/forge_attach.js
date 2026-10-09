/* ForgeAttach: paste, drop and an attach button for a Forge message box
   (Relay task 118). The page's backend saves each file (shared/forge_attach.py)
   and the message carries the paths, so a Claude session can open them.

   ForgeAttach.wire({
     box,          the textarea: a paste with files attaches them
     zone,         where files may be dropped (default: box)
     picker,       an <input type="file" multiple> (the attach button's)
     upload,       async (file) => {name, path, bytes}: send one file
     pasteDesktop, async () => {name, path, bytes}: the backend reads the
                   desktop clipboard (WebKitGTK hands a copied screenshot to
                   the page only as a type, never as a file)
     onAdd,        (saved) => void: one file is saved
     onError,      (message) => void
     refuse,       () => message or "": why the box takes no files right now
                   (a paste then goes in as text, a drop shows the message)
     maxBytes,     a bigger file is refused before it is read (default 50 MB,
                   the backends' limit)
   }) -> {add, busy}: busy() is true while a file is still uploading, so a
   send can wait for it instead of going without it
   ForgeAttach.readBase64(file) -> Promise<string>
   ForgeAttach.pasted(clipboardData) -> {files, desktop}: what a paste holds */
(function (root) {
  "use strict";

  function readBase64(file) {
    return new Promise((ok, bad) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result).split(",")[1] || "");
      r.onerror = () => bad(r.error || new Error("Could not read the file"));
      r.readAsDataURL(file);
    });
  }

  // A paste's files; `desktop` when it says it holds an image but gives no
  // file and no text (WebKitGTK and a copied screenshot).
  function pasted(dt) {
    if (!dt) return { files: [], desktop: false };
    const files = [...(dt.files || [])];
    if (!files.length) {
      for (const it of [...(dt.items || [])]) {
        const f = it.kind === "file" && it.getAsFile();
        if (f) files.push(f);
      }
    }
    const types = [...(dt.types || [])];
    // copied text that also carries a picture (spreadsheet cells, a web
    // page) pastes as text, the way a text box always did
    if (types.includes("text/plain")) return { files: [], desktop: false };
    // WebKitGTK sometimes names no type at all for a copied screenshot
    const desktop = !files.length &&
      (!types.length || types.some((t) => String(t).startsWith("image/")));
    return { files, desktop };
  }

  const hasFiles = (e) => !!e.dataTransfer && [...(e.dataTransfer.types || [])].includes("Files");

  function wire(o) {
    const zone = o.zone || o.box;
    const fail = o.onError || (() => {});
    const refuse = o.refuse || (() => "");
    const maxBytes = o.maxBytes || 50 * 1024 * 1024;
    let pending = 0;
    async function track(job) {
      pending++;
      try { return await job(); } finally { pending--; }
    }
    async function add(list) {
      const why = refuse();
      if (why) { if (list.length) fail(why); return; }
      await track(async () => {
        for (const file of list) {
          const name = file.name || "the file";
          if (file.size > maxBytes) { fail(`${name} is too big to attach (over ${Math.round(maxBytes / 1048576)} MB)`); continue; }
          try { o.onAdd(await o.upload(file)); }
          catch (e) { fail(`Could not attach ${name}: ${e.message}`); }
        }
      });
    }
    if (o.box) {
      o.box.addEventListener("paste", (e) => {
        if (refuse()) return;
        const got = pasted(e.clipboardData);
        if (got.files.length) { e.preventDefault(); add(got.files); return; }
        if (got.desktop && o.pasteDesktop) {
          e.preventDefault();
          track(o.pasteDesktop).then(o.onAdd).catch((err) => fail(`Could not paste the picture: ${err.message}`));
        }
      });
    }
    if (zone) {
      zone.addEventListener("dragover", (e) => { if (!hasFiles(e)) return; e.preventDefault(); zone.classList.add("fa-drop"); });
      zone.addEventListener("dragleave", (e) => { if (!zone.contains(e.relatedTarget)) zone.classList.remove("fa-drop"); });
      zone.addEventListener("drop", (e) => {
        zone.classList.remove("fa-drop");
        if (!hasFiles(e)) return;
        e.preventDefault();
        add([...e.dataTransfer.files]);
      });
    }
    if (o.picker) o.picker.addEventListener("change", () => { add([...o.picker.files]); o.picker.value = ""; });
    return { add, busy: () => pending > 0 };
  }

  const api = { wire, readBase64, pasted };
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ForgeAttach = api;
})(typeof window !== "undefined" ? window : globalThis);
