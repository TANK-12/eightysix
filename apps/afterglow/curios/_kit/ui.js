/* Tiny DOM helpers so every curio's controls look and behave alike.
 * The classes are styled by the shell (static/app.css). Anything built with
 * {adv: true} gets class "adv" and hides in Simple mode.
 */

/** el("div", {class: "x", text: "hi", on: {click}, style: {}}, ...children) */
export function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key === "text") node.textContent = value;
    else if (key === "on") for (const [ev, fn] of Object.entries(value)) node.addEventListener(ev, fn);
    else if (key === "style") Object.assign(node.style, value);
    else if (key === "dataset") Object.assign(node.dataset, value);
    else if (key in node && typeof value !== "string") node[key] = value;
    else node.setAttribute(key, value === true ? "" : value);
  }
  for (const child of children.flat()) {
    if (child === null || child === undefined || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function cls(base, { adv, kind } = {}) {
  return [base, kind, adv ? "adv" : ""].filter(Boolean).join(" ");
}

/** A button. kind: "primary" or "ghost". */
export function button(label, onclick, opts = {}) {
  return el("button", {
    type: "button",
    class: cls("ag-btn", opts),
    title: opts.title,
    text: label,
    on: { click: onclick },
  });
}

function decimals(step) {
  const s = String(step);
  return s.includes(".") ? s.length - s.indexOf(".") - 1 : 0;
}

/** A range slider paired with a number field; both stay in step.
 *  oninput(value) runs on every change from either one. */
export function slider({ label, min, max, step = 1, value, oninput, adv, title }) {
  const range = el("input", { type: "range", min, max, step, value });
  const num = el("input", { type: "number", class: "ag-num", min, max, step, value });
  const places = decimals(step);
  const clamp = (v) => Math.min(max, Math.max(min, v));
  const tidy = (v) => Number(clamp(v).toFixed(places));
  let current = tidy(Number(value));
  const apply = (v, silent) => {
    if (!Number.isFinite(v)) return;
    current = tidy(v);
    range.value = String(current);
    if (document.activeElement !== num) num.value = String(current);
    if (!silent && oninput) oninput(current);
  };
  range.addEventListener("input", () => {
    apply(Number(range.value));
    num.value = String(current);
  });
  num.addEventListener("input", () => {
    if (num.value.trim() !== "") apply(Number(num.value));
  });
  num.addEventListener("change", () => {
    num.value = String(current);
  });
  const node = el(
    "label",
    { class: cls("ag-slider", { adv }), title },
    el("span", { class: "ag-slider-label", text: label }),
    range,
    num,
  );
  return { el: node, get: () => current, set: (v, { silent = true } = {}) => apply(Number(v), silent) };
}

/** A row of mutually exclusive buttons. options: strings or {value, label, title}. */
export function seg(options, value, onchange, opts = {}) {
  const items = options.map((o) => (typeof o === "object" ? o : { value: o, label: String(o) }));
  let current = value;
  const node = el("div", { class: cls("ag-seg", opts), role: "group", title: opts.title });
  const buttons = items.map((o) =>
    el("button", {
      type: "button",
      text: o.label,
      title: o.title,
      dataset: { value: String(o.value) },
      on: { click: () => set(o.value, false) },
    }),
  );
  node.append(...buttons);
  function set(v, silent = true) {
    current = v;
    buttons.forEach((b, i) => b.classList.toggle("on", items[i].value === v));
    if (!silent && onchange) onchange(v);
  }
  set(value);
  return { el: node, get: () => current, set: (v) => set(v, true) };
}

/** A labelled on/off switch. */
export function toggle(label, value, onchange, opts = {}) {
  const box = el("input", { type: "checkbox", checked: !!value });
  box.addEventListener("change", () => onchange && onchange(box.checked));
  const node = el("label", { class: cls("ag-toggle", opts), title: opts.title }, box, el("span", { text: label }));
  return { el: node, get: () => box.checked, set: (v) => (box.checked = !!v) };
}

/** A frosted panel with a heading; append controls to .body. */
export function panel(title, opts = {}) {
  const body = el("div", { class: "ag-panel-body" });
  const node = el(
    "section",
    { class: cls("ag-panel", { adv: opts.adv, kind: opts.cls }) },
    title ? el("h3", { text: title }) : null,
    body,
  );
  return { el: node, body };
}
