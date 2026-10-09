// Contrast sweep (Relay task 57, 2026-10-07): finds text drawn in nearly the
// colour of what is behind it ("white on white", QUICKSTART item 2).
//
// forgeContrastSweep(root, opts) walks every visible element under root that
// draws text (a direct text node, or a form control's value), composites the
// background colours of it and its ancestors (gradients count as the average
// of their stops), and returns the ones whose WCAG contrast ratio is under
// opts.min (default 3). Where every layer is see-through, the text sits on
// the wallpaper; opts.base stands in for that (default a dark wallpaper), so
// only colours the CSS itself sets can fail. <option>s with no background of
// their own are measured against the popup the engine draws: white, unless
// color-scheme dark reaches them (the WebKitGTK case shared/forge.css notes).
(function () {
  function parse(c) {
    if (!c || c === "transparent") return null;
    let m = c.match(/^rgba?\(([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s,/]+/).filter(Boolean).map(Number);
      return { r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1 };
    }
    m = c.match(/^color\(srgb ([^)]+)\)$/);
    if (m) {
      const p = m[1].split(/[\s/]+/).filter(Boolean).map(Number);
      return { r: p[0] * 255, g: p[1] * 255, b: p[2] * 255, a: p.length > 3 ? p[3] : 1 };
    }
    return null;
  }
  function over(top, under) {
    const a = top.a + under.a * (1 - top.a);
    if (a <= 0) return { r: 0, g: 0, b: 0, a: 0 };
    const mix = (k) => (top[k] * top.a + under[k] * under.a * (1 - top.a)) / a;
    return { r: mix("r"), g: mix("g"), b: mix("b"), a };
  }
  function lum(c) {
    const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
    return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
  }
  function ratio(a, b) {
    const x = lum(a), y = lum(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }
  // the colours of a gradient layer, averaged into one
  function gradient(img) {
    const stops = (img.match(/(rgba?\([^)]+\)|color\(srgb [^)]+\))/g) || []).map(parse).filter(Boolean);
    if (!stops.length || !/gradient/.test(img)) return null;
    const n = stops.length, sum = { r: 0, g: 0, b: 0, a: 0 };
    stops.forEach((s) => { sum.r += s.r * s.a; sum.g += s.g * s.a; sum.b += s.b * s.a; sum.a += s.a; });
    if (!sum.a) return null;
    return { r: sum.r / sum.a, g: sum.g / sum.a, b: sum.b / sum.a, a: sum.a / n };
  }
  // opacity fades an element's whole group, its backing and its text alike
  function faded(e) {
    let o = 1;
    for (; e && e.nodeType === 1; e = e.parentElement) o *= Number(getComputedStyle(e).opacity);
    return o;
  }
  const fade = (c, o) => ({ r: c.r, g: c.g, b: c.b, a: c.a * o });
  function layers(el) {
    const out = [];
    // <body> and <html> paint under the wallpaper layers, so opts.base, the
    // wallpaper's stand-in, takes their place
    for (let e = el; e && e.nodeType === 1 && e !== document.body && e !== document.documentElement; e = e.parentElement) {
      // an absolutely placed ::before disc under the children (the widget
      // gauges' inner circle) is what their text really sits on
      const before = e === el ? null : getComputedStyle(e, "::before");
      if (before && before.content !== "none" && before.position === "absolute") {
        const d = parse(before.backgroundColor);
        if (d && d.a >= 0.9) { out.push(fade(d, faded(e))); break; }
        // a soft black radial pool (the hub's wallpaper text): its text sits
        // in the middle, so the first stop is what is behind it
        const m = /^radial-gradient/.test(before.backgroundImage) && before.backgroundImage.match(/(rgba?\([^)]+\)|color\(srgb [^)]+\))/);
        const peak = m && parse(m[1]);
        if (peak && peak.a > 0 && peak.r + peak.g + peak.b === 0) out.push(fade(peak, faded(e)));
      }
      const cs = getComputedStyle(e);
      const o = faded(e);
      const g = gradient(cs.backgroundImage || "");
      if (g) out.push(fade(g, o));
      const c = parse(cs.backgroundColor);
      if (c && c.a > 0) out.push(fade(c, o));
      if (out.length && out[out.length - 1].a >= 0.99) break;
    }
    return out;
  }
  function shown(el) {
    if (!el.getClientRects().length) return false;
    let o = 1;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.visibility === "hidden" || cs.display === "none") return false;
      o *= Number(cs.opacity);
    }
    return o > 0.05;
  }
  function where(el) {
    const bits = [];
    for (let e = el; e && e.nodeType === 1 && bits.length < 4; e = e.parentElement) {
      let s = e.tagName.toLowerCase();
      if (e.id) { bits.unshift(s + "#" + e.id); break; }
      if (e.classList.length) s += "." + [...e.classList].slice(0, 2).join(".");
      bits.unshift(s);
    }
    return bits.join(" > ");
  }
  function hex(c) {
    return "#" + [c.r, c.g, c.b].map((v) => Math.round(v).toString(16).padStart(2, "0")).join("");
  }
  window.forgeContrastSweep = function (root, opts) {
    opts = opts || {};
    const min = opts.min || 3;
    const base = parse(opts.base || "rgb(20, 22, 28)");
    const found = [];
    const all = [root, ...root.querySelectorAll("*")];
    for (const el of all) {
      const tag = el.tagName;
      if (/^(SCRIPT|STYLE|NOSCRIPT|TEMPLATE|SVG|CANVAS|IFRAME)$/.test(tag)) continue;
      const own = [...el.childNodes].some((n) => n.nodeType === 3 && n.textContent.trim());
      const control = /^(INPUT|TEXTAREA|SELECT)$/.test(tag) && el.type !== "range" && el.type !== "color"
        && el.type !== "checkbox" && el.type !== "radio" && el.type !== "hidden";
      const option = tag === "OPTION";
      if (!own && !control && !option) continue;
      if (!option && !shown(el)) continue;
      // WCAG leaves inactive controls out: a greyed-out button is meant to look off
      if (el.closest(":disabled")) continue;
      if (option && !shown(el.closest("select") || el)) continue;
      const cs = getComputedStyle(el);
      const fg = parse(cs.color);
      if (!fg || fg.a < 0.05) continue;
      let bg;
      if (option) {
        const own = parse(cs.backgroundColor);
        const popup = cs.colorScheme && /dark/.test(cs.colorScheme) ? parse("rgb(30, 30, 30)") : parse("rgb(255, 255, 255)");
        bg = own && own.a > 0 ? over(own, popup) : popup;
      } else {
        bg = base;
        layers(el).reverse().forEach((l) => { bg = over(l, bg); });
      }
      const text = over(fade(fg, option ? 1 : faded(el)), bg);
      const r = ratio(text, bg);
      if (r < min) {
        const words = (option || control ? el.value || el.textContent : [...el.childNodes].filter((n) => n.nodeType === 3).map((n) => n.textContent).join(" "))
          .trim().replace(/\s+/g, " ").slice(0, 40);
        found.push({ where: where(el), text: words, fg: hex(text), bg: hex(bg), ratio: Math.round(r * 100) / 100,
          shadow: cs.textShadow !== "none" });
      }
    }
    return found;
  };
  window.forgeContrastRatio = function (a, b) { return ratio(parse(a), parse(b)); };
})();
