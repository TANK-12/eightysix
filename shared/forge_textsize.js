/* Forge Text size: letters bigger or smaller without the boxes around them.

   Almost every Forge page sets its font sizes in px, so changing the root font
   size alone would do nothing. Instead every px font-size in the page's own
   stylesheets is rewritten once into calc(<px> * var(--forge-text, 1)), and
   the setting only ever changes that one variable. Sheets added later (a
   look, a lazily loaded panel) are caught by an observer. The root size is
   scaled too, for text that sets no size of its own and for rem-based pages.

   Used by the hub (script tag) and by every app through forge_chrome.js.
   ForgeText.apply(scale) is the whole interface. */
(function () {
  if (window.ForgeText) return;
  const done = new WeakSet();
  const PX = /^\s*-?[\d.]+px\s*$/;

  function scaleRules(rules) {
    for (const rule of rules) {
      if (rule.cssRules && rule.cssRules.length) {
        try { scaleRules(rule.cssRules); } catch (e) { /* unreadable nested block */ }
      }
      if (!rule.style || done.has(rule)) continue;
      const size = rule.style.getPropertyValue("font-size");
      if (!PX.test(size)) continue;
      done.add(rule);
      rule.style.setProperty(
        "font-size",
        `calc(${size.trim()} * var(--forge-text, 1))`,
        rule.style.getPropertyPriority("font-size"),
      );
    }
  }

  function sweep() {
    for (const sheet of document.styleSheets) {
      try { scaleRules(sheet.cssRules); } catch (e) { /* another origin's sheet */ }
    }
  }

  let watching = false;
  function watch() {
    if (watching) return;
    watching = true;
    new MutationObserver((changes) => {
      for (const change of changes) {
        for (const node of change.addedNodes) {
          if (node.nodeName === "STYLE") sweep();
          else if (node.nodeName === "LINK") node.addEventListener("load", sweep, { once: true });
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
    // A <link> swapped in place (the hub's look) fires load without being added.
    document.addEventListener("load", (e) => { if (e.target.nodeName === "LINK") sweep(); }, true);
  }

  function ensureRootRule() {
    if (document.getElementById("forge-text-root")) return;
    const s = document.createElement("style");
    s.id = "forge-text-root";
    s.textContent = "html { font-size: calc(100% * var(--forge-text, 1)); }";
    (document.head || document.documentElement).prepend(s);
  }

  window.ForgeText = {
    scale: 1,
    apply(value) {
      const scale = Math.min(2, Math.max(0.5, Number(value) || 1));
      // the same size again: the rules are already rewritten and watched, so
      // the walk over every stylesheet is skipped (the hub calls this on
      // every theme change)
      if (scale === this.scale && watching) return;
      this.scale = scale;
      document.documentElement.style.setProperty("--forge-text", String(scale));
      // At 1 nothing needs rewriting; once rewritten, 1 is simply identity.
      if (scale === 1 && !watching) return;
      ensureRootRule();
      sweep();
      watch();
    },
  };
})();
