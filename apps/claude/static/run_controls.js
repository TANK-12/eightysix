/* How a conversation runs, shared by both layouts: the Normal / Ultracode
 * switch and the agent limits fold. Everything is drawn from /api/options:
 * options.agent_limits is runner.AGENT_LIMITS (one entry per limit: env, kind
 * int|choice, min/max or choices, default, label, help), so a new limit needs
 * no change here. Empty = Claude Code's own default.
 *
 *   const ctl = RunControls.create(options, save)   save(changes) -> Promise
 *   host.append(ctl.root); ctl.apply(meta)          redraw from a meta
 */
(() => {
function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
}

function create(options, save) {
  const limits = (options && options.agent_limits) || {};
  const unsupported = ((options && options.ultracode) || {}).unsupported_models || [];
  const root = el("span", "run-ctl");
  let meta = {};

  // Normal / Ultracode
  const seg = el("span", "run-seg");
  seg.setAttribute("role", "group");
  seg.setAttribute("aria-label", "How Claude works");
  const normal = el("button", "", "Normal");
  const ultra = el("button", "", "Ultracode");
  normal.type = ultra.type = "button";
  normal.title = "Claude works on its own, starting helpers only when it decides to";
  const ultraTitle = "Ultracode: Claude plans the work as a dynamic workflow and runs helpers for it, at any effort. Uses more of your limit. Applies from the next message.";
  ultra.title = ultraTitle;
  seg.append(normal, ultra);
  const ultraNote = el("span", "run-note");
  async function setUltra(on) {
    if (!!meta.ultracode === on) return;
    seg.classList.add("saving");
    try { await save({ ultracode: on }); } finally { seg.classList.remove("saving"); }
  }
  normal.addEventListener("click", () => setUltra(false));
  ultra.addEventListener("click", () => setUltra(true));

  // the limits fold
  const fold = el("details", "run-fold");
  const summary = el("summary", "", "Limits");
  summary.title = "Limits on the helpers (subagents) this conversation may start";
  const panel = el("div", "run-panel");
  // In the classic header's settings row an absolute panel can run off the
  // window: pin it to the window under its button instead, and close it when
  // the row scrolls or the window resizes.
  fold.addEventListener("toggle", () => {
    const row = fold.closest(".head-controls");
    if (!fold.open || !row) return;
    const r = summary.getBoundingClientRect();
    panel.style.position = "fixed";
    panel.style.top = `${Math.round(r.bottom + 6)}px`;
    panel.style.left = `${Math.round(Math.max(8, Math.min(r.left, innerWidth - panel.offsetWidth - 8)))}px`;
    const shut = () => { fold.open = false; };
    row.addEventListener("scroll", shut, { once: true });
    addEventListener("resize", shut, { once: true });
  });
  const head = el("p", "run-head", "Limits on helpers for this conversation. Empty is Claude Code's default; changes apply from the next message.");
  panel.append(head);
  const rows = {};
  Object.entries(limits).forEach(([key, spec]) => {
    const row = el("div", "run-row");
    const label = el("label", "run-label", spec.label);
    label.title = spec.help || "";
    row.append(label);
    const put = (value) => save({ limits: { [key]: value } });
    if (spec.kind === "int") {
      const slider = el("input");
      slider.type = "range";
      slider.min = spec.min; slider.max = spec.max; slider.step = 1;
      const num = el("input", "run-num");
      num.type = "number";
      num.min = spec.min; num.max = spec.max; num.step = 1;
      num.placeholder = "auto";
      num.title = `Empty: Claude Code's default (${spec.default || "its own"})`;
      const id = "run-" + key;
      num.id = id; label.htmlFor = id;
      slider.setAttribute("aria-label", spec.label);
      slider.addEventListener("input", () => { num.value = slider.value; row.classList.add("set"); });
      slider.addEventListener("change", () => put(Number(slider.value)));
      num.addEventListener("change", () => put(num.value.trim() === "" ? "" : Number(num.value)));
      const clear = el("button", "run-clear", "×");
      clear.type = "button";
      clear.title = "Back to Claude Code's default";
      clear.addEventListener("click", () => put(""));
      row.append(slider, num, clear);
      rows[key] = (value) => {
        const set = value !== undefined && value !== null && value !== "";
        row.classList.toggle("set", set);
        if (document.activeElement !== num) num.value = set ? value : "";
        if (document.activeElement !== slider) {
          const fallback = Number(spec.default);
          slider.value = set ? value : (Number.isFinite(fallback) ? fallback : spec.min);
        }
      };
    } else {
      const pick = el("select");
      const none = el("option", "", `default (${spec.default || "Claude Code's"})`);
      none.value = "";
      pick.append(none, ...Object.entries(spec.choices || {}).map(([value, text]) => {
        const opt = el("option", "", text);
        opt.value = value;
        return opt;
      }));
      pick.setAttribute("aria-label", spec.label);
      pick.addEventListener("change", () => put(pick.value));
      row.append(pick);
      rows[key] = (value) => {
        row.classList.toggle("set", !!value);
        if (document.activeElement !== pick) pick.value = value || "";
      };
    }
    const fallback = spec.kind === "int" && /^\d+$/.test(String(spec.default || "")) ? `; default ${spec.default}` : "";
    if (spec.help) row.append(el("p", "run-help", spec.help + fallback));
    panel.append(row);
  });
  fold.append(summary, panel);
  fold.hidden = !Object.keys(limits).length;
  // one open fold at a time; a click elsewhere or Esc closes it
  document.addEventListener("pointerdown", (e) => { if (fold.open && !fold.contains(e.target)) fold.open = false; });
  fold.addEventListener("keydown", (e) => { if (e.key === "Escape") { fold.open = false; summary.focus(); } });

  root.append(seg, fold, ultraNote);
  if (!options || !options.ultracode) seg.hidden = true; // an older backend

  function apply(m) {
    meta = m || {};
    const on = !!meta.ultracode;
    const cannot = unsupported.includes(meta.model || "");
    normal.setAttribute("aria-pressed", String(!on));
    ultra.setAttribute("aria-pressed", String(on));
    ultra.disabled = cannot && !on;
    root.classList.toggle("ultra", on);
    const st = meta.ultracode_state;
    let note = "", warn = false;
    if (on && cannot) { note = "this model has no ultracode"; warn = true; }
    else if (on && st && !st.active) { note = st.available ? "ultracode did not start" : "ultracode is not available here"; warn = true; }
    else if (on && st && st.active) note = "";
    else if (on) note = "from the next message";
    ultraNote.textContent = note;
    ultraNote.classList.toggle("warn", warn);
    ultra.title = cannot ? "This model cannot run ultracode; pick Opus, Fable or Sonnet" : ultraTitle;
    const set = meta.limits || {};
    let count = 0;
    Object.entries(rows).forEach(([key, draw]) => { draw(set[key]); if (set[key] !== undefined && set[key] !== "") count += 1; });
    summary.textContent = count ? `Limits · ${count}` : "Limits";
    fold.classList.toggle("set", count > 0);
  }
  return { root, apply };
}

window.RunControls = { create };
})();
