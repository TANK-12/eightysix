/* ==========================================================================
   Forge shared chrome control -- "Full screen" for every app.
   ==========================================================================

   Served by each app's own backend at /shared/forge_chrome.js (every
   web_app.py mounts ~/Forge/shared). One line in an app's index.html:

       <script src="/shared/forge_chrome.js"></script>

   ...and that app has a working full-screen control. Nothing else is needed:
   the script wires itself up on load, so a new app under apps/ gets this for
   free rather than copying a block of code.

   THREE LAYERS, and they are separate on purpose:

     1. The Forge sidebar. A page cannot touch it -- it lives in the hub shell,
        one document up -- so it is asked away by postMessage. The hub listens
        for {forge:"chrome", hidden:bool} and toggles `chromeless` on its body.
     2. The real Fullscreen API, so the app fills the window (and, standalone
        in a browser, fills the screen). The hub gives every workspace iframe
        `allowfullscreen`, so this is allowed from inside one.
     3. The GTK window itself. forge.py listens for WebKit's enter-fullscreen
        signal and fullscreens the window with it, which is what makes layer 2
        actually cover the screen rather than just the WebView.

   This used to live at the bottom of forge.js as `const ForgeChrome`, which is
   why Dossier's button did nothing: a top-level `const` in a classic script
   goes into the global LEXICAL scope, not onto `window`, so the app's
   `if (window.ForgeChrome)` guard was always false and the button was never
   wired. The assignment to window at the end of this file is not decoration.
   ========================================================================== */

(function () {
  "use strict";

  const ForgeChrome = {
    hidden: false,

    /** Show a text size on this page only, until the hub's next theme
        (Settings previews its Text size slider while it is dragged). */
    previewTextSize(value) {
      applyTextSize((applyTextSize.latest = value));
    },
    _wired: false,
    _buttons: [],

    /** Hide or show the hub's sidebar AND take/leave real fullscreen.
        Every part is a harmless no-op outside the hub or outside a browser
        that allows it, so this is safe to call from anywhere. */
    set(hidden, { real = true } = {}) {
      this.hidden = !!hidden;

      // Layer 1: the hub sidebar. Inside the hub, the hub also fills the
      // window itself (`window`), in place of layer 2: element fullscreen
      // lifts the app's frame into WebKit's top layer over a black backdrop,
      // which hid the hub's wallpaper behind every glass app.
      const embedded = window.parent !== window;
      try {
        window.parent.postMessage(
          { forge: "chrome", hidden: this.hidden, window: real ? this.hidden : undefined },
          "*");
      } catch (e) {
        /* a stricter embedder; the layers below still apply */
      }
      document.body.classList.toggle("forge-fullscreen", this.hidden);

      // Layer 2: real fullscreen, standalone only. Only attempted on a user
      // gesture -- a rejected promise here is normal (no user activation)
      // and must not become an unhandled rejection.
      if (real && !embedded) {
        try {
          const d = document;
          if (this.hidden && !d.fullscreenElement) {
            const p = d.documentElement.requestFullscreen();
            if (p && p.catch) p.catch(() => {});
          } else if (!this.hidden && d.fullscreenElement) {
            const p = d.exitFullscreen();
            if (p && p.catch) p.catch(() => {});
          }
        } catch (e) {
          /* an engine without the Fullscreen API; layer 1 still worked */
        }
      }

      this._relabel();
      if (this._onChange) this._onChange(this.hidden);
      return this.hidden;
    },

    toggle(opts) { return this.set(!this.hidden, opts); },

    /** The hub left full screen on its own (Esc or F11 caught by the
        window): match it without asking the hub again. */
    _hubSays(hidden) {
      this.hidden = !!hidden;
      document.body.classList.toggle("forge-fullscreen", this.hidden);
      this._relabel();
      if (this._onChange) this._onChange(this.hidden);
    },

    _relabel() {
      const text = this.hidden ? "Exit full screen" : "Full screen";
      for (const el of this._buttons) {
        el.textContent = text;
        el.setAttribute("aria-pressed", this.hidden ? "true" : "false");
      }
    },

    /** Wire a button and a key. Pass `key: null` for no keyboard shortcut.
        Kept to the signature the apps already call, so existing
        `ForgeChrome.init({button: "go-fullscreen", key: "f"})` calls still
        mean what they meant. */
    init({ button = null, key = "f", onChange = null } = {}) {
      this._wired = true;
      if (onChange) this._onChange = onChange;

      if (button) {
        const el = typeof button === "string"
          ? document.getElementById(button) : button;
        if (el && this._buttons.indexOf(el) === -1) {
          this._buttons.push(el);
          el.addEventListener("click", () => this.toggle());
        }
      }

      if (key && !this._keyBound) {
        this._keyBound = true;
        window.addEventListener("keydown", (e) => {
          if (e.key === "Escape" && this.hidden) {
            e.preventDefault();
            this.set(false);
            return;
          }
          // Alt+key only: a bare "f" went full screen whenever it was typed
          // outside a text box. Inside Forge, forge.py takes Alt+F first.
          if (e.metaKey || e.ctrlKey || e.shiftKey || !e.altKey) return;
          if (e.key.toLowerCase() === key || e.code === "Key" + key.toUpperCase()) {
            e.preventDefault();
            this.toggle();
          }
        });
      }

      this._relabel();
      return this;
    },

    /** Ask the hub to close this app: go home, throw the page away, stop the
        backend. Emerson asked for it after opening a game by accident and
        finding it had started a language model behind his back -- hiding an
        app is not closing it. Outside the hub there is nothing to ask, so this
        is a no-op rather than an error. */
    close() {
      try {
        window.parent.postMessage({ forge: "close" }, "*");
      } catch (e) {
        /* standalone: nothing above us to hear it */
      }
    },

    /** The close control, put next to the full-screen one wherever that is:
        beside the app's own header button if it has one, or beside the
        injected floating button if it does not. Every app gets it without
        editing a line of its own markup. */
    _injectClose(next_to) {
      const el = document.createElement("button");
      el.id = "forge-close-app";
      el.className = "forge-chrome-btn forge-close-btn";
      el.type = "button";
      el.textContent = "Close app";
      el.title =
        "Close this app: stops its backend and anything it is running, and goes back to the home screen. It starts again next time you open it.";
      el.addEventListener("click", () => this.close());
      if (next_to && next_to.parentNode) {
        next_to.parentNode.insertBefore(el, next_to.nextSibling);
        // Sitting in an app's own header, it should look like that header's
        // buttons rather than like the floating one.
        el.classList.add("forge-close-inline");
      } else {
        document.body.appendChild(el);
      }
      this._closeButton = el;
      return el;
    },

    /** Inject a button for apps whose markup has no place for one. Apps that
        do have somewhere sensible put `id="go-fullscreen"` in their own
        header and this never runs. */
    _inject() {
      const el = document.createElement("button");
      el.id = "go-fullscreen";
      el.className = "forge-chrome-btn";
      el.type = "button";
      el.title = "Full screen: hides the Forge sidebar and fills the screen (Alt+F). Esc comes back.";
      document.body.appendChild(el);
      return el;
    },

    _style() {
      if (document.getElementById("forge-chrome-style")) return;
      const s = document.createElement("style");
      s.id = "forge-chrome-style";
      // Tokens come from shared/forge.css where the app loads it; the
      // fallbacks are for the apps that style themselves (ai-studio,
      // PixelForge), so the button is legible either way.
      s.textContent = `
.forge-chrome-btn {
  position: fixed; right: 12px; bottom: 12px; z-index: 2147483000;
  padding: 6px 12px; border-radius: 999px; cursor: pointer;
  font: 12px/1 -apple-system, "Segoe UI", Roboto, sans-serif;
  background: var(--panel-2, #1e222b); color: var(--muted, #8b93a3);
  border: 1px solid var(--border, #2a2f3a);
  opacity: .55; transition: opacity .15s, color .15s, border-color .15s;
}
.forge-chrome-btn:hover, .forge-chrome-btn:focus-visible {
  opacity: 1; color: var(--text, #e7e9ee); border-color: var(--accent, #6ea8fe);
}
/* The floating pair sit side by side; the close one goes to the left of
   full screen so the button under the cursor does not change meaning. */
.forge-close-btn { right: 108px; }
.forge-close-btn:hover, .forge-close-btn:focus-visible {
  color: var(--bad, #ff8080); border-color: var(--bad, #ff8080);
}
/* Inside an app's own header it is an ordinary button in the flow. */
.forge-close-inline { position: static; margin-left: 6px; opacity: .75; }`;
      document.head.appendChild(s);
    },

    /** Called automatically on load. Uses the app's own button if it has one
        (any element with id `go-fullscreen`, or `[data-forge-fullscreen]`),
        and injects a floating one otherwise. */
    mount() {
      if (this._mounted) return this;
      this._mounted = true;
      this._style();

      let el = document.getElementById("go-fullscreen")
        || document.querySelector("[data-forge-fullscreen]");
      const ownHeader = !!el;
      // Inside Forge the hub's bar carries Full screen and Close for every
      // app, so nothing floats over the app's own corner (it used to cover
      // the Board's Send button). Standalone, the floating pair stays.
      const inHub = window.parent !== window;
      if (!el && !inHub) el = this._inject();
      this.init({ button: el, key: "f" });
      if (!document.getElementById("forge-close-app") && (ownHeader || !inHub)) {
        this._injectClose(ownHeader ? el : null);
      }

      // Leaving fullscreen by Escape, F11 or the window manager must put the
      // sidebar back too -- otherwise the app is left with no chrome and no
      // obvious way to get it back. `real: false` because the browser has
      // already left; asking again would be a second, failing request.
      document.addEventListener("fullscreenchange", () => {
        if (!document.fullscreenElement && this.hidden) this.set(false, { real: false });
      });
      return this;
    },
  };

  // Text size lives in its own shared file, next to this one, because the hub
  // uses it too. Loaded the first time a theme asks for a size other than 1.
  const textSizeSrc = new URL("forge_textsize.js", (document.currentScript || {}).src || location.href).href;

  /* The frame-rate cap (B39, setting max_fps) is shared/forge_framecap.js,
     beside this file, so the hub uses the same one. Inside Forge it is loaded
     straight away and set from the hub's theme message; standalone nothing
     arrives, so it isn't loaded. */
  const FrameCap = {
    want: null,
    src: new URL("forge_framecap.js", (document.currentScript || {}).src || location.href).href,
    load() {
      if (window.parent === window || window.ForgeFrameCap) return;
      const tag = document.createElement("script");
      tag.src = this.src;
      tag.onload = () => { if (this.want !== null) window.ForgeFrameCap.set(this.want); };
      (document.head || document.documentElement).appendChild(tag);
    },
    set(value) {
      this.want = value;
      if (window.ForgeFrameCap) window.ForgeFrameCap.set(value);
    },
  };
  FrameCap.load();

  // Ctrl+Z / Ctrl+Shift+Z / Ctrl+Y in text boxes (shared/forge_undo.js):
  // WebKitGTK binds no key to undo, so every page that loads this one gets it.
  if (!document.getElementById("forge-undo-js")) {
    const u = document.createElement("script");
    u.id = "forge-undo-js";
    u.src = new URL("forge_undo.js", (document.currentScript || {}).src || location.href).href;
    (document.head || document.documentElement).appendChild(u);
  }

  // Inside the hub, every app reports what it plays to the bar's Now playing
  // and takes play/pause/seek/volume back (shared/forge_media.js).
  if (window.parent !== window && !document.getElementById("forge-media-js")) {
    const m = document.createElement("script");
    m.id = "forge-media-js";
    m.src = new URL("forge_media.js", (document.currentScript || {}).src || location.href).href;
    (document.head || document.documentElement).appendChild(m);
  }
  function applyTextSize(value) {
    const scale = Number(value) || 1;
    if (window.ForgeText) return window.ForgeText.apply(scale);
    if (scale === 1 || document.getElementById("forge-textsize-js")) return;
    const s = document.createElement("script");
    s.id = "forge-textsize-js";
    s.src = textSizeSrc;
    s.onload = () => window.ForgeText && window.ForgeText.apply(applyTextSize.latest);
    document.head.appendChild(s);
  }


  /* The hub's theme. Inside Forge the hub sends {forge:"theme", theme} once
     the app has loaded, and again whenever Settings changes it. Tokens are set
     inline on <html>, which beats any stylesheet's :root, so an app with its
     own palette is themed too. The page goes see-through and the hub draws the
     blurred wallpaper behind it; panels stay mostly solid so text stays
     readable. Only a message from the parent frame is accepted, and
     standalone nothing arrives, so nothing changes. */
  function applyTheme(t) {
    applyTextSize((applyTextSize.latest = t.text_scale));
    const html = document.documentElement;
    const glass = Math.max(0.2, Math.min(1, Number(t.glass) || 0.62));
    if (t.unify_accent && t.accent) {
      html.style.setProperty("--accent", t.accent);
      html.style.setProperty("--accent-2", t.accent_2 || t.accent);
      html.style.setProperty("--on-accent", t.on_accent || "#0b1220");
    }
    // Panel colours: tinted by the wallpaper when Settings says so, the
    // classic greys otherwise. Border and text come solid; the fills keep
    // the glass so the blurred wallpaper shows through.
    const s = t.surfaces || {};
    const rgba = (hex, fallback, alpha) => {
      const value = /^#[0-9a-f]{6}$/i.test(hex || "") ? hex : fallback;
      const n = parseInt(value.slice(1), 16);
      return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha.toFixed(2)})`;
    };
    html.style.setProperty("--bg", rgba(s.bg, "#0d0f13", glass));
    html.style.setProperty("--panel", rgba(s.panel, "#171a21", Math.min(1, 0.5 + glass * 0.45)));
    html.style.setProperty("--panel-2", rgba(s.panel_2, "#1e222b", Math.min(1, 0.6 + glass * 0.38)));
    for (const [token, key] of [["--border", "border"], ["--text", "text"], ["--muted", "muted"]]) {
      if (s[key]) html.style.setProperty(token, s[key]);
    }

    // Font and size, from Settings. "" / 1 leave the app exactly as it is.
    if (t.font_stack) {
      html.style.setProperty("--forge-font", t.font_stack);
      if (!document.getElementById("forge-font-style")) {
        const f = document.createElement("style");
        f.id = "forge-font-style";
        f.textContent = "html.forge-font body, html.forge-font button, html.forge-font input,"
          + " html.forge-font select, html.forge-font textarea { font-family: var(--forge-font); }";
        document.head.appendChild(f);
      }
    }
    html.classList.toggle("forge-font", !!t.font_stack);
    // App size is not applied here: forge.py zooms the whole window.
    // <html> and <body> both paint var(--bg); only one of them may, or the
    // glass is laid down twice and comes out nearly solid.
    html.style.background = "transparent";
    html.classList.add("forge-themed");
    // The hub's look (classic, material, brain...), for an app that wants to
    // match it: style against html[data-forge-look="material"].
    html.dataset.forgeLook = t.look || "classic";
    // Lighter effects (#225, setting lite_effects): the hub decides when
    // (always, or only on battery) and sends lite. Looping animations play
    // once and stop; the frosted blur goes flat.
    if (t.lite && !document.getElementById("forge-lite-css")) {
      const css = document.createElement("style");
      css.id = "forge-lite-css";
      css.textContent = "html.forge-lite *, html.forge-lite *::before, html.forge-lite *::after {"
        + " animation-iteration-count: 1 !important; backdrop-filter: none !important;"
        + " -webkit-backdrop-filter: none !important; }";
      document.head.appendChild(css);
    }
    html.classList.toggle("forge-lite", !!t.lite);
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window.parent || window.parent === window) return;
    const msg = event.data;
    if (msg && msg.forge === "theme" && msg.theme && typeof msg.theme === "object") {
      applyTheme(msg.theme);
      FrameCap.set(msg.theme.max_fps);
    }
  });

  // The hub telling us full screen ended without our button.
  window.addEventListener("message", (event) => {
    const msg = event.data;
    if (event.source === window.parent && msg && msg.forge === "chrome-state") {
      ForgeChrome._hubSays(msg.hidden);
    }
  });

  // The whole point of this file: a global the apps can actually see.
  window.ForgeChrome = ForgeChrome;

  /* Is this app the one on screen?
     The hub posts {forge:"visible", visible:bool} to every mounted app when
     the workspace changes or the window hides. ForgeVisible.on is that flag
     (true standalone, where there is no hub), and "forge-visible" fires on
     document with detail {visible}, so a page can pause a poll or an
     animation behind the home screen instead of running for nobody. */
  const ForgeVisible = {
    on: true,
    init() {
      addEventListener("message", (e) => {
        const m = e.data;
        if (!m || m.forge !== "visible") return;
        const next = !!m.visible;
        if (next === this.on) return;
        this.on = next;
        Rest.set(!next);
        document.dispatchEvent(new CustomEvent("forge-visible", { detail: { visible: next } }));
      });
    },
  };

  /* Off screen inside Forge, an app rests like a browser's background tab
     (B18): its CSS animations pause and its animation frames wait until it is
     back, when the held ones run together. Timers, network and media carry
     on. WebKit keeps an iframe that is merely invisible running at full
     rate, so without this every open game and effect drew for nobody.
     Standalone (no hub above) nothing is wrapped. */
  const Rest = {
    on: false, held: new Map(), next: 1e9, realRaf: null,
    install() {
      if (window.parent === window) return;
      const realRaf = window.requestAnimationFrame.bind(window);
      const realCancel = window.cancelAnimationFrame.bind(window);
      this.realRaf = realRaf;
      window.requestAnimationFrame = (cb) => {
        if (!Rest.on) return realRaf(cb);
        const id = Rest.next++;
        Rest.held.set(id, cb);
        return id;
      };
      window.cancelAnimationFrame = (id) => {
        if (!Rest.held.delete(id)) realCancel(id);
      };
      const style = document.createElement("style");
      style.textContent = "html.forge-resting *, html.forge-resting *::before, html.forge-resting *::after { animation-play-state: paused !important; }";
      (document.head || document.documentElement).appendChild(style);
    },
    set(resting) {
      if (!this.realRaf) return;
      this.on = resting;
      document.documentElement.classList.toggle("forge-resting", resting);
      if (resting || !this.held.size) return;
      const waiting = [...this.held.values()];
      this.held.clear();
      this.realRaf((t) => waiting.forEach((cb) => {
        try { cb(t); } catch (err) { setTimeout(() => { throw err; }); }
      }));
    },
  };
  Rest.install();
  ForgeVisible.init();
  window.ForgeVisible = ForgeVisible;

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => ForgeChrome.mount());
  } else {
    ForgeChrome.mount();
  }
})();
