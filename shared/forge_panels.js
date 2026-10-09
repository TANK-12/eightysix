// ForgePanels: an app's blocks as cards on a board that the user arranges.
//
// Mark each block with data-panel="<id>" data-title="<Title>" inside one
// container, then call
//
//   ForgePanels.mount(container, { key: "ai-studio", defaults: {
//     settings: { x: 0, y: 0, w: 0.3, h: 1 }, ... } });
//
// Each block is wrapped in a card with a title bar (drag to move, double-click
// to fill the board and back) and a corner grip (drag to resize). Positions are
// fractions of the container, so a layout survives the window changing size,
// and they are kept per app in localStorage. Below `stackBelow` pixels wide the
// cards stack in one scrolling column instead, so a small window never crams.
// mount() returns { reset(), layout() }.
(function () {
  "use strict";
  const STORE = "forge-panels:";
  const MIN_W = 220; // px, smallest card
  const MIN_H = 120;
  const SNAP = 0.005; // fractions snap to half a percent

  const CSS = `
  .fp-board { position: relative; overflow: hidden; }
  .fp-card { position: absolute; display: flex; flex-direction: column; min-width: 0;
    background: var(--panel, #171a21); border: 1px solid var(--border, #2a2f3a);
    border-radius: 12px; overflow: hidden; box-shadow: 0 6px 24px rgba(0,0,0,.25); }
  .fp-bar { flex: none; display: flex; align-items: center; gap: 8px; padding: 6px 12px;
    font-size: 12px; color: var(--muted, #8b93a3); background: var(--panel-2, #1e222b);
    border-bottom: 1px solid var(--border, #2a2f3a); cursor: grab; user-select: none;
    touch-action: none; }
  .fp-bar::before { content: "⠿"; opacity: .6; }
  .fp-card.fp-moving .fp-bar { cursor: grabbing; }
  .fp-body { flex: 1; min-height: 0; overflow: auto; }
  .fp-grip { position: absolute; right: 0; bottom: 0; width: 16px; height: 16px;
    cursor: nwse-resize; touch-action: none;
    background: linear-gradient(135deg, transparent 50%, var(--muted, #8b93a3) 50%, transparent 62%,
      transparent 70%, var(--muted, #8b93a3) 70%, transparent 82%); opacity: .5; }
  .fp-grip:hover { opacity: 1; }
  .fp-board.fp-stacked { overflow-y: auto; display: flex; flex-direction: column; gap: 12px; }
  /* Stacked: one full-width column; the saved size (inline styles) waits for a wide board. */
  .fp-stacked .fp-card { position: static; flex: none; width: auto !important;
    height: auto !important; }
  .fp-stacked .fp-bar { cursor: default; }
  .fp-stacked .fp-grip { display: none; }`;

  function injectCss() {
    if (document.getElementById("fp-css")) return;
    const style = document.createElement("style");
    style.id = "fp-css";
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  const clamp = (v, lo, hi) => Math.min(Math.max(v, lo), hi);
  const snap = (v) => Math.round(v / SNAP) * SNAP;

  function load(key) {
    try {
      return JSON.parse(localStorage.getItem(STORE + key) || "null");
    } catch (e) {
      return null;
    }
  }

  function save(key, layout) {
    try {
      localStorage.setItem(STORE + key, JSON.stringify(layout));
    } catch (e) {}
  }

  // Keep a rect inside the board and at least the minimum size.
  function fit(r, board) {
    const W = Math.max(board.clientWidth, 1);
    const H = Math.max(board.clientHeight, 1);
    const w = clamp(r.w, Math.min(MIN_W / W, 1), 1);
    const h = clamp(r.h, Math.min(MIN_H / H, 1), 1);
    return {
      x: clamp(r.x, 0, 1 - w),
      y: clamp(r.y, 0, 1 - h),
      w,
      h,
      z: r.z || 1,
    };
  }

  function mount(board, opts) {
    injectCss();
    const key = opts.key;
    const defaults = opts.defaults || {};
    const stackBelow = opts.stackBelow ?? 760;
    const cards = {};
    let layout = {};
    let top = 1;

    board.classList.add("fp-board");
    for (const el of Array.from(board.querySelectorAll(":scope > [data-panel]"))) {
      const id = el.dataset.panel;
      const card = document.createElement("section");
      card.className = "fp-card";
      card.dataset.card = id;
      const bar = document.createElement("div");
      bar.className = "fp-bar";
      bar.textContent = el.dataset.title || id;
      bar.title = "Drag to move, double-click to fill the board";
      const grip = document.createElement("div");
      grip.className = "fp-grip";
      grip.title = "Drag to resize";
      board.insertBefore(card, el);
      el.classList.add("fp-body");
      card.append(bar, el, grip);
      cards[id] = card;
      drag(bar, id, false);
      drag(grip, id, true);
      bar.addEventListener("dblclick", () => toggleFill(id));
      card.addEventListener("pointerdown", () => raise(id));
    }

    function stacked() {
      return board.classList.contains("fp-stacked");
    }

    function apply(id) {
      const r = layout[id];
      const s = cards[id].style;
      s.left = r.x * 100 + "%";
      s.top = r.y * 100 + "%";
      s.width = r.w * 100 + "%";
      s.height = r.h * 100 + "%";
      s.zIndex = r.z;
    }

    function applyAll() {
      for (const id in cards) apply(id);
    }

    function start(saved) {
      layout = {};
      for (const id in cards) {
        const r = (saved && saved[id]) || defaults[id] || { x: 0, y: 0, w: 0.5, h: 0.5 };
        layout[id] = fit(r, board);
        top = Math.max(top, layout[id].z);
      }
      applyAll();
    }

    function raise(id) {
      const z = layout[id].z;
      if (stacked() || Object.keys(layout).every((k) => k === id || layout[k].z < z)) return;
      layout[id].z = ++top;
      apply(id);
      save(key, layout);
    }

    function toggleFill(id) {
      if (stacked()) return;
      const r = layout[id];
      if (r.before) {
        layout[id] = fit({ ...r.before, z: r.z }, board);
      } else {
        layout[id] = { x: 0, y: 0, w: 1, h: 1, z: r.z, before: { x: r.x, y: r.y, w: r.w, h: r.h } };
      }
      apply(id);
      save(key, layout);
    }

    function drag(handle, id, resize) {
      handle.addEventListener("pointerdown", (e) => {
        if (stacked() || e.button !== 0) return;
        e.preventDefault();
        e.stopPropagation();
        raise(id);
        const r0 = { ...layout[id] };
        delete r0.before;
        const W = board.clientWidth;
        const H = board.clientHeight;
        const x0 = e.clientX;
        const y0 = e.clientY;
        const card = cards[id];
        card.classList.add("fp-moving");
        try {
          handle.setPointerCapture(e.pointerId);
        } catch (err) {}
        const move = (ev) => {
          const dx = (ev.clientX - x0) / W;
          const dy = (ev.clientY - y0) / H;
          const r = resize
            ? { ...r0, w: snap(r0.w + dx), h: snap(r0.h + dy) }
            : { ...r0, x: snap(r0.x + dx), y: snap(r0.y + dy) };
          if (resize) {
            r.w = Math.min(r.w, 1 - r0.x);
            r.h = Math.min(r.h, 1 - r0.y);
          }
          layout[id] = fit(r, board);
          apply(id);
        };
        const up = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", up);
          handle.removeEventListener("pointercancel", up);
          card.classList.remove("fp-moving");
          save(key, layout);
        };
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", up);
        handle.addEventListener("pointercancel", up);
      });
    }

    function checkWidth() {
      board.classList.toggle("fp-stacked", board.clientWidth < stackBelow);
    }

    start(load(key));
    checkWidth();
    if (window.ResizeObserver) new ResizeObserver(checkWidth).observe(board);
    else window.addEventListener("resize", checkWidth);

    return {
      reset() {
        try {
          localStorage.removeItem(STORE + key);
        } catch (e) {}
        top = 1;
        start(null);
      },
      layout: () => JSON.parse(JSON.stringify(layout)),
    };
  }

  window.ForgePanels = { mount };
})();
