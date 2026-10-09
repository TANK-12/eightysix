/*
 * Schema-driven form controls.
 *
 * Every effect, emitter and scene describes its own parameters, and this turns
 * one of those descriptions into a control. Doing it in one place is what lets
 * a new effect appear in the editor with working controls without anyone
 * touching the UI -- and it is why every "strength" slider in the app looks and
 * behaves the same.
 *
 * Numeric parameters get a slider *and* a number box, wired to each other: drag
 * for feel, type for a value you already know. Directions get a dial you can
 * see at a glance.
 */
(function (global) {
  "use strict";

  function el(tag, cls, html) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (html !== undefined) n.innerHTML = html;
    return n;
  }

  // Filled in from /api/modulation-sources at boot; until then the "~" button
  // simply doesn't appear, so the controls still work.
  let MOD_SOURCES = [];
  let MOD_SHAPES = ["sine", "ramp", "pulse", "wander"];
  function setModulationSources(sources, shapes) {
    MOD_SOURCES = sources || [];
    if (shapes && shapes.length) MOD_SHAPES = shapes;
  }
  const isModulated = (v) => v && typeof v === "object" && "base" in v;
  const baseOf = (v) => (isModulated(v) ? v.base : v);

  function decimalsFor(step) {
    const s = String(step ?? 1);
    return s.includes(".") ? s.split(".")[1].length : 0;
  }

  // A slider and a number box showing the same value, either one driving it.
  function numericPair(spec, value, onChange) {
    const min = spec.min ?? 0;
    const max = spec.max ?? 1;
    const step = spec.step ?? (spec.type === "int" ? 1 : 0.01);
    const dp = decimalsFor(step);

    const wrap = el("div", "ctl-pair");
    const slider = el("input");
    slider.type = "range";
    slider.min = min;
    slider.max = max;
    slider.step = step;
    slider.value = value;
    const box = el("input", "ctl-num");
    box.type = "number";
    box.min = min;
    box.max = max;
    box.step = step;
    box.value = Number(value).toFixed(dp);

    const commit = (raw, live) => {
      let v = parseFloat(raw);
      if (!isFinite(v)) return;
      v = Math.min(max, Math.max(min, v));
      if (spec.type === "int") v = Math.round(v);
      slider.value = v;
      if (document.activeElement !== box) box.value = v.toFixed(dp);
      onChange(v, live);
    };
    // dragging streams live updates; letting go commits
    slider.addEventListener("input", () => commit(slider.value, true));
    slider.addEventListener("change", () => commit(slider.value, false));
    box.addEventListener("change", () => commit(box.value, false));

    wrap.appendChild(slider);
    wrap.appendChild(box);
    if (spec.unit) wrap.appendChild(el("span", "ctl-unit", spec.unit));
    return wrap;
  }

  // A direction, as a dial you can read without parsing a number.
  function angleControl(spec, value, onChange) {
    const wrap = el("div", "ctl-pair");
    const dial = el("div", "ctl-dial");
    const needle = el("i");
    dial.appendChild(needle);
    const slider = el("input");
    slider.type = "range";
    slider.min = 0;
    slider.max = 359;
    slider.step = 1;
    slider.value = value;
    const box = el("input", "ctl-num");
    box.type = "number";
    box.min = 0;
    box.max = 359;
    box.value = Math.round(value);

    const paint = (v) => {
      // screen y grows downward, so negate to make 90 point up
      needle.style.transform = `rotate(${-v}deg)`;
    };
    const commit = (raw, live) => {
      let v = parseFloat(raw);
      if (!isFinite(v)) return;
      v = ((Math.round(v) % 360) + 360) % 360;
      slider.value = v;
      if (document.activeElement !== box) box.value = v;
      paint(v);
      onChange(v, live);
    };
    slider.addEventListener("input", () => commit(slider.value, true));
    slider.addEventListener("change", () => commit(slider.value, false));
    box.addEventListener("change", () => commit(box.value, false));
    paint(value);

    wrap.appendChild(dial);
    wrap.appendChild(slider);
    wrap.appendChild(box);
    return wrap;
  }

  /* A parameter can be tied to something that moves instead of holding a fixed
   * number. This is the row that appears under the slider when you press "~":
   * pick a source, how far it should swing, and how fast. */
  function modulationRow(spec, current, onChange) {
    const row = el("div", "ctl-mod");
    const mod = isModulated(current)
      ? { ...current }
      : { base: current ?? spec.default, mod: "lfo", amount: 0, period: 20, shape: "sine" };

    const src = el("select");
    for (const s of MOD_SOURCES) {
      const o = el("option", null, s.label);
      o.value = s.id;
      if (s.id === mod.mod) o.selected = true;
      src.appendChild(o);
    }
    const span = (spec.max ?? 1) - (spec.min ?? 0);
    const amount = el("input");
    amount.type = "range";
    amount.min = -span / 2;
    amount.max = span / 2;
    amount.step = (spec.step ?? 0.01);
    amount.value = mod.amount ?? 0;
    const amountBox = el("input", "ctl-num");
    amountBox.type = "number";
    amountBox.step = spec.step ?? 0.01;
    amountBox.value = Number(mod.amount ?? 0).toFixed(decimalsFor(spec.step ?? 0.01));

    const period = el("input", "ctl-num");
    period.type = "number";
    period.min = 1;
    period.max = 600;
    period.step = 1;
    period.value = mod.period ?? 20;
    const shape = el("select");
    for (const sh of MOD_SHAPES) {
      const o = el("option", null, sh);
      o.value = sh;
      if (sh === mod.shape) o.selected = true;
      shape.appendChild(o);
    }

    const note = el("div", "ctl-help");
    const push = (live) => {
      mod.mod = src.value;
      mod.amount = parseFloat(amount.value) || 0;
      mod.period = parseFloat(period.value) || 20;
      mod.shape = shape.value;
      const meta = MOD_SOURCES.find((s) => s.id === mod.mod);
      const lfo = mod.mod === "lfo";
      period.hidden = !lfo;
      shape.hidden = !lfo;
      note.textContent = meta
        ? meta.help + (meta.needs_live ? " Needs this shot set to live." : "")
        : "";
      onChange(mod.amount === 0 ? mod.base : { ...mod }, live);
    };
    amount.addEventListener("input", () => {
      amountBox.value = Number(amount.value).toFixed(decimalsFor(spec.step ?? 0.01));
      push(true);
    });
    amount.addEventListener("change", () => push(false));
    amountBox.addEventListener("change", () => {
      amount.value = amountBox.value;
      push(false);
    });
    for (const c of [src, period, shape]) c.addEventListener("change", () => push(false));

    row.appendChild(el("span", "ctl-modlabel", "moves with"));
    row.appendChild(src);
    row.appendChild(amount);
    row.appendChild(amountBox);
    row.appendChild(period);
    row.appendChild(shape);
    const wrap = el("div");
    wrap.appendChild(row);
    wrap.appendChild(note);
    push(false);
    return wrap;
  }

  /**
   * One labelled control for one parameter.
   * onChange(value, isLive) -- isLive is true while a slider is being dragged,
   * so callers can throttle expensive work until it settles.
   */
  function buildField(spec, value, onChange) {
    const raw = value === undefined || value === null ? spec.default : value;
    const v = baseOf(raw);
    const field = el("div", "ctl");
    const label = el("label", null, spec.label || spec.key);
    field.appendChild(label);

    const t = spec.type;
    const canModulate =
      MOD_SOURCES.length && (t === "range" || t === "int" || t === "angle");
    let modBox = null;
    let currentBase = v;
    if (canModulate) {
      const tog = el("button", "ctl-modtoggle", "~");
      tog.title = "Make this move on its own";
      tog.onclick = () => {
        if (modBox) {
          modBox.remove();
          modBox = null;
          tog.classList.remove("on");
          onChange(currentBase, false);
        } else {
          tog.classList.add("on");
          modBox = modulationRow(spec, isModulated(raw) ? raw : currentBase, onChange);
          field.appendChild(modBox);
        }
      };
      label.appendChild(tog);
      if (isModulated(raw)) {
        tog.classList.add("on");
        setTimeout(() => {
          modBox = modulationRow(spec, raw, onChange);
          field.appendChild(modBox);
        }, 0);
      }
    }
    const emit = (val, live) => {
      currentBase = val;
      if (modBox) {
        // keep the base in step while a modulation is attached
        const cur = isModulated(raw) ? raw : {};
        onChange({ ...cur, base: val }, live);
      } else {
        onChange(val, live);
      }
    };
    if (t === "range" || t === "int" || (t === "float" && spec.min !== undefined)) {
      field.insertBefore(numericPair(spec, v, emit), modBox);
    } else if (t === "angle") {
      field.insertBefore(angleControl(spec, v, emit), modBox);
    } else if (t === "bool") {
      const cb = el("input");
      cb.type = "checkbox";
      cb.checked = !!v;
      cb.addEventListener("change", () => onChange(cb.checked, false));
      const row = el("div", "ctl-pair");
      row.appendChild(cb);
      field.appendChild(row);
    } else if (t === "select") {
      const sel = el("select");
      for (const o of spec.options || []) {
        const opt = el("option", null, String(o));
        opt.value = o;
        if (String(o) === String(v)) opt.selected = true;
        sel.appendChild(opt);
      }
      sel.addEventListener("change", () => onChange(sel.value, false));
      field.appendChild(sel);
    } else if (t === "color") {
      const row = el("div", "ctl-pair");
      const c = el("input");
      c.type = "color";
      c.value = v || "#ffffff";
      const hex = el("input", "ctl-num ctl-hex");
      hex.type = "text";
      hex.value = c.value;
      c.addEventListener("input", () => {
        hex.value = c.value;
        onChange(c.value, true);
      });
      c.addEventListener("change", () => onChange(c.value, false));
      hex.addEventListener("change", () => {
        if (/^#[0-9a-fA-F]{6}$/.test(hex.value)) {
          c.value = hex.value;
          onChange(hex.value, false);
        }
      });
      row.appendChild(c);
      row.appendChild(hex);
      field.appendChild(row);
    } else {
      const inp = el("input");
      inp.type = "text";
      inp.value = v ?? "";
      if (t === "path") inp.placeholder = "/path/to/frames or sprite.gif";
      inp.addEventListener("change", () => onChange(inp.value, false));
      field.appendChild(inp);
    }

    if (spec.help) field.appendChild(el("div", "ctl-help", spec.help));
    return field;
  }

  /** A whole schema at once. `values` is the saved dict; `onChange(key, v, live)`. */
  function buildForm(schema, values, onChange) {
    const box = el("div", "ctl-grid");
    for (const spec of schema || []) {
      box.appendChild(
        buildField(spec, (values || {})[spec.key], (v, live) =>
          onChange(spec.key, v, live)
        )
      );
    }
    return box;
  }

  global.Controls = {
    buildField,
    buildForm,
    el,
    setModulationSources,
    isModulated,
    baseOf,
  };
})(window);
