/* The plain name of a session, the same on every page (Emerson, 2026-10-08):
   the task number and a short plain description, so a list reads as what each
   session is doing. A Relay session: "#109 Mission Control conversation
   view"; another: its chat title, cut short; neither: its persona or board
   name. The persona (s.label) then rides along as a small tag (personaTag).
   Loaded by pages as a plain script (window.ForgeSessionTitle) and by node
   --test as a CommonJS module. A session is {id, name, label, title, relay:
   {task, title}}; name "relay-109-work" alone also marks a Relay run. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ForgeSessionTitle = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  /* A file path says its last part in words (task 109): "~/Forge/sessions/
     2026-10-08-ai-studio-new-models.md" -> "ai studio new models". A path
     starts a word with "/", "~/" or "./", or has two slashes or more; web
     addresses and "A/B" stay as they are. */
  const PATH = /(^|[\s("'])((?:~|\.{1,2})?\/[\w.@+-]+(?:\/[\w.@+-]+)*\/?|[\w.@+-]+(?:\/[\w.@+-]+){2,}\/?)/g;
  function pathWords(path) {
    const last = path.replace(/\/+$/, "").split("/").pop() || path;
    const words = last.replace(/\.[A-Za-z0-9]{1,5}$/, "").replace(/^\d{4}-\d{2}-\d{2}[-_ ]?/, "").replace(/[-_]+/g, " ").trim();
    return words || last;
  }
  function shortTitle(text, max = 44) {
    let t = String(text || "").replace(/\s+/g, " ").trim().replace(PATH, (m, pre, path) => pre + pathWords(path));
    const cut = t.search(/[:;,(]| - | — /);
    if (cut >= 12) t = t.slice(0, cut).trim();
    if (t.length <= max) return t;
    const sp = t.lastIndexOf(" ", max - 1);
    return t.slice(0, sp > max / 2 ? sp : max - 1).replace(/[\s,.;:-]+$/, "") + "…";
  }
  function relayTask(s) {
    if (s.relay && s.relay.task) return { task: String(s.relay.task), title: s.relay.title || "" };
    const m = /^relay-(\d+)-/.exec(s.name || "");
    return m ? { task: m[1], title: "" } : null;
  }
  function displayName(s) {
    const r = relayTask(s);
    const title = shortTitle((r && r.title) || s.title || "");
    if (r) return "#" + r.task + " " + (title || s.label || s.name || "Relay task");
    return title || s.label || s.name || String(s.id || "").slice(0, 8);
  }
  function personaTag(s) {
    const tag = s.label || s.name || "";
    return tag && !displayName(s).endsWith(tag) ? tag : "";
  }
  return { shortTitle, relayTask, displayName, personaTag };
});
