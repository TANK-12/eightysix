/* Forge avatars: a live anime character on a page, as a Live2D model or a
 * generated puppet, playing the shared motion recipes, lip-syncing to speech
 * and following the mouse. Used by the Claude app's stage and its Avatar
 * Studio; any Forge app can use it (served at /shared/forge_avatar.js).
 *
 * Emerson asked for it on 2026-09-24 (see ~/.claude/self/PERSONALITY.md).
 * The Python half is shared/forge_avatars.py: it lists models, turns recipes
 * into Live2D .motion3.json files, and stores puppets.
 *
 *   const av = new ForgeAvatar(element, { base: "/shared/avatars" });
 *   await av.show({ kind: "live2d", id: "arch" }, { motions, recipes });
 *   av.react("thinking"); av.play("wink"); await av.speakBlob(wavBlob);
 */
(function () {
  "use strict";

  // Same ranges as forge_avatars.RANGES. Eyes rest open (1), all else at 0.
  const RANGES = {
    ParamAngleX: [-30, 30], ParamAngleY: [-30, 30], ParamAngleZ: [-30, 30],
    ParamBodyAngleX: [-10, 10], ParamBodyAngleY: [-10, 10], ParamBodyAngleZ: [-10, 10],
    ParamEyeBallX: [-1, 1], ParamEyeBallY: [-1, 1],
    ParamEyeLOpen: [0, 2], ParamEyeROpen: [0, 2], ParamEyeLSmile: [0, 1], ParamEyeRSmile: [0, 1],
    ParamMouthOpenY: [0, 1], ParamMouthForm: [-1, 1],
    ParamBrowLY: [-1, 1], ParamBrowRY: [-1, 1], ParamCheek: [0, 1], ParamBreath: [0, 1],
  };
  const REST = { ParamEyeLOpen: 1, ParamEyeROpen: 1 };
  const ALIASES = { ParamMouthOpenY: ["ParamA"], ParamCheek: ["PARAM_TERE"], ParamEyeLSmile: ["ParamEyeRSmile"] };

  // Expressions are offsets on the standard parameters, so they work on any
  // model that has them, and on puppets.
  const EXPRESSIONS = {
    neutral: {},
    happy: { ParamMouthForm: 1, ParamEyeLSmile: 0.5, ParamEyeRSmile: 0.5, ParamCheek: 0.3 },
    smug: { ParamMouthForm: 0.6, ParamEyeLOpen: -0.3, ParamEyeROpen: -0.3, ParamBrowLY: 0.2 },
    smirk: { ParamMouthForm: 0.7, ParamEyeLOpen: -0.25, ParamEyeROpen: -0.15 },
    think: { ParamEyeBallY: 0.6, ParamEyeBallX: 0.4, ParamMouthForm: -0.3, ParamBrowLY: 0.3 },
    embarrassed: { ParamCheek: 1, ParamMouthForm: -0.2, ParamEyeBallX: -0.5, ParamBrowLY: -0.3, ParamBrowRY: -0.3 },
    sad: { ParamBrowLY: -0.8, ParamBrowRY: -0.8, ParamMouthForm: -0.8, ParamEyeLOpen: -0.3, ParamEyeROpen: -0.3 },
    surprised: { ParamEyeLOpen: 0.3, ParamEyeROpen: 0.3, ParamBrowLY: 1, ParamBrowRY: 1, ParamMouthOpenY: 0.35 },
    sleepy: { ParamEyeLOpen: -0.6, ParamEyeROpen: -0.6, ParamAngleY: -6 },
  };
  const STATUS_FACE = { thinking: "think", tool: null, done: "happy", error: "embarrassed", idle: null, talking: null };

  const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
  const smooth = (x) => x * x * (3 - 2 * x);
  const pick = (list) => (list && list.length ? list[Math.floor(Math.random() * list.length)] : null);

  function envelope(kind, x) {
    x = clamp(x, 0, 1);
    if (kind === "bell") return Math.sin(Math.PI * x);
    if (kind === "in") return x;
    if (kind === "out") return 1 - x;
    return 1;
  }

  /* One curve's value at time t (seconds): the same maths as forge_avatars.sample. */
  function sampleCurve(curve, t, duration) {
    let value = 0;
    const keys = curve.keys || [];
    if (keys.length) {
      if (t <= keys[0][0]) value = keys[0][1];
      else if (t >= keys[keys.length - 1][0]) value = keys[keys.length - 1][1];
      else {
        for (let i = 0; i < keys.length - 1; i++) {
          const [t0, v0] = keys[i], [t1, v1] = keys[i + 1];
          if (t >= t0 && t <= t1) {
            const x = t1 === t0 ? 0 : smooth((t - t0) / (t1 - t0));
            value = v0 + (v1 - v0) * x;
            break;
          }
        }
      }
    }
    const w = curve.wave;
    if (w) {
      const raw = (w.offset || 0) + (w.amp || 0) * Math.sin(2 * Math.PI * (w.freq || 1) * t + (w.phase || 0));
      value += raw * envelope(curve.env || "none", duration ? t / duration : 0);
    }
    return value;
  }

  function snake(param) {
    const body = param.startsWith("Param") ? param.slice(5) : param;
    return "PARAM_" + body.replace(/(?!^)([A-Z])/g, "_$1").toUpperCase();
  }

  /* ------------------------------------------------------------ recipes */

  /** Plays recipes as standard-parameter values. Used for puppets. Live2D
   *  models play the same recipes as real motion files instead. */
  class RecipePlayer {
    constructor() { this.recipes = {}; this.active = []; }
    setRecipes(recipes) { this.recipes = recipes || {}; }
    play(name, opts = {}) {
      const recipe = typeof name === "string" ? this.recipes[name] : name;
      if (!recipe) return false;
      const loop = opts.loop ?? !!recipe.loop;
      if (!opts.layer) this.active = this.active.filter((m) => m.layer);
      this.active.push({ recipe, start: performance.now(), loop, speed: opts.speed || 1, intensity: opts.intensity ?? 1, layer: !!opts.layer });
      return true;
    }
    stop() { this.active = []; }
    busy() { return this.active.some((m) => !m.loop); }
    values(now) {
      const out = {};
      this.active = this.active.filter((m) => {
        const d = m.recipe.duration;
        let t = ((now - m.start) / 1000) * m.speed;
        if (t > d) { if (!m.loop) return false; t %= d; }
        for (const [param, curve] of Object.entries(m.recipe.curves)) {
          const rest = REST[param] || 0;
          const v = rest + (sampleCurve(curve, t, d) - rest) * m.intensity;
          out[param] = (out[param] ?? rest) + (v - rest);
        }
        return true;
      });
      return out;
    }
  }

  /* ------------------------------------------------------------ puppets */

  const SVGNS = "http://www.w3.org/2000/svg";

  function shade(hex, amount) {
    const n = parseInt(hex.slice(1), 16);
    const f = (c) => clamp(Math.round(c + (amount < 0 ? c : 255 - c) * amount), 0, 255);
    return "#" + [f(n >> 16), f((n >> 8) & 255), f(n & 255)].map((c) => c.toString(16).padStart(2, "0")).join("");
  }

  /** Draws a generated character as layered SVG and poses it each frame
   *  from standard parameters: head turn with parallax between the back hair,
   *  face, features and bangs, eye open and smile, iris follow, brows, mouth
   *  shape, blush, breathing. */
  class PuppetBackend {
    constructor(container) {
      this.container = container;
      this.svg = document.createElementNS(SVGNS, "svg");
      this.svg.setAttribute("viewBox", "0 0 300 400");
      this.svg.setAttribute("class", "forge-puppet");
      this.svg.style.width = "100%";
      this.svg.style.height = "100%";
      container.appendChild(this.svg);
      this.p = null;
      this.ids = new Set(Object.keys(RANGES));
    }
    destroy() { this.svg.remove(); }

    load(puppet) {
      this.p = puppet;
      const c = puppet.colours;
      const fw = puppet.face_width || 1;
      const hv = puppet.hair_volume || 1;
      const hair = c.hair, hairDark = shade(c.hair, -0.35), hairLight = shade(c.hair, 0.25);
      const skin = c.skin, skinShade = shade(c.skin, -0.12);
      const girl = puppet.body === "girl", boy = puppet.body === "boy";
      const shoulder = boy ? 92 : girl ? 74 : 82;
      const uid = "p" + Math.random().toString(36).slice(2, 8);

      const back = {
        short: `<ellipse cx="150" cy="150" rx="${88 * hv}" ry="${92 * hv}"/>`,
        messy: `<path d="M${150 - 92 * hv} 170 Q${150 - 110 * hv} 90 150 ${55 - 10 * hv} Q${150 + 110 * hv} 90 ${150 + 92 * hv} 170 L${150 + 80 * hv} 200 L${150 + 96 * hv} 215 L${150 + 60 * hv} 205 L150 190 L${150 - 60 * hv} 205 L${150 - 96 * hv} 215 L${150 - 80 * hv} 200Z"/>`,
        long: `<path d="M${150 - 90 * hv} 150 Q${150 - 100 * hv} 60 150 ${58 - 8 * hv} Q${150 + 100 * hv} 60 ${150 + 90 * hv} 150 L${150 + 100 * hv} 340 Q150 360 ${150 - 100 * hv} 340Z"/>`,
        bob: `<path d="M${150 - 92 * hv} 150 Q${150 - 100 * hv} 60 150 ${58 - 8 * hv} Q${150 + 100 * hv} 60 ${150 + 92 * hv} 150 L${150 + 92 * hv} 238 Q150 250 ${150 - 92 * hv} 238Z"/>`,
        spiky: `<path d="M${150 - 86 * hv} 185 L${150 - 118 * hv} 120 L${150 - 84 * hv} 110 L${150 - 100 * hv} 50 L${150 - 45 * hv} 72 L150 ${22 - 10 * hv} L${150 + 45 * hv} 72 L${150 + 100 * hv} 50 L${150 + 84 * hv} 110 L${150 + 118 * hv} 120 L${150 + 86 * hv} 185Z"/>`,
        twintails: `<ellipse cx="150" cy="148" rx="${88 * hv}" ry="${90 * hv}"/><path class="tail-l" d="M${150 - 80 * hv} 110 Q${150 - 150 * hv} 180 ${150 - 118 * hv} 330 Q${150 - 90 * hv} 250 ${150 - 70 * hv} 140Z"/><path class="tail-r" d="M${150 + 80 * hv} 110 Q${150 + 150 * hv} 180 ${150 + 118 * hv} 330 Q${150 + 90 * hv} 250 ${150 + 70 * hv} 140Z"/>`,
        ponytail: `<ellipse cx="150" cy="148" rx="${88 * hv}" ry="${90 * hv}"/><path class="tail-r" d="M${150 + 40 * hv} 80 Q${150 + 150 * hv} 100 ${150 + 110 * hv} 300 Q${150 + 95 * hv} 200 ${150 + 30 * hv} 110Z"/>`,
      }[puppet.hair_style] || "";

      const bangs = {
        straight: `<path d="M${150 - 80 * hv} 140 Q${150 - 84 * hv} 62 150 ${60 - 6 * hv} Q${150 + 84 * hv} 62 ${150 + 80 * hv} 140 L${150 + 62} 118 L${150 + 50} 138 L${150 + 30} 116 L${150 + 14} 136 L150 114 L${150 - 16} 136 L${150 - 32} 116 L${150 - 50} 138 L${150 - 62} 118Z"/>`,
        side: `<path d="M${150 - 82 * hv} 150 Q${150 - 86 * hv} 60 150 ${58 - 6 * hv} Q${150 + 86 * hv} 62 ${150 + 82 * hv} 140 Q${150 + 40} 100 ${150 - 20} 132 Q${150 - 50} 142 ${150 - 70} 170Z"/>`,
        split: `<path d="M${150 - 82 * hv} 160 Q${150 - 86 * hv} 60 150 ${58 - 6 * hv} Q${150 + 86 * hv} 60 ${150 + 82 * hv} 160 Q${150 + 60} 110 ${150 + 6} 92 L150 110 L${150 - 6} 92 Q${150 - 60} 110 ${150 - 82 * hv} 160Z"/>`,
        messy: `<path d="M${150 - 84 * hv} 150 Q${150 - 88 * hv} 58 150 ${56 - 6 * hv} Q${150 + 88 * hv} 58 ${150 + 84 * hv} 150 L${150 + 66} 112 L${150 + 58} 142 L${150 + 38} 108 L${150 + 22} 140 L${150 + 4} 104 L${150 - 12} 138 L${150 - 30} 106 L${150 - 44} 144 L${150 - 60} 110Z"/>`,
        none: `<path d="M${150 - 80 * hv} 110 Q${150 - 84 * hv} 58 150 ${56 - 6 * hv} Q${150 + 84 * hv} 58 ${150 + 80 * hv} 110 Q150 80 ${150 - 80 * hv} 110Z"/>`,
      }[puppet.bangs] || "";

      const outfitBody = `M${150 - shoulder} 400 L${150 - shoulder} 290 Q${150 - shoulder + 6} 252 ${150 - 26} 244 L${150 + 26} 244 Q${150 + shoulder - 6} 252 ${150 + shoulder} 290 L${150 + shoulder} 400Z`;
      const trim = c.outfit_trim, accent = c.accent;
      const outfitExtra = {
        hoodie: `<path d="M${150 - 40} 246 Q150 280 ${150 + 40} 246 Q150 262 ${150 - 40} 246Z" fill="${shade(c.outfit, -0.25)}"/><line x1="140" y1="262" x2="138" y2="300" stroke="${trim}" stroke-width="3" stroke-linecap="round"/><line x1="160" y1="262" x2="162" y2="300" stroke="${trim}" stroke-width="3" stroke-linecap="round"/>`,
        apron_hoodie: `<path d="M${150 - 40} 246 Q150 280 ${150 + 40} 246 Q150 262 ${150 - 40} 246Z" fill="${shade(c.outfit, -0.25)}"/><path d="M${150 - 44} 300 L${150 + 44} 300 L${150 + 50} 400 L${150 - 50} 400Z" fill="#6b4226" stroke="#3e2615" stroke-width="2"/><line x1="${150 - 40}" y1="300" x2="${150 - 30}" y2="248" stroke="#3e2615" stroke-width="4"/><line x1="${150 + 40}" y1="300" x2="${150 + 30}" y2="248" stroke="#3e2615" stroke-width="4"/><rect x="138" y="330" width="24" height="18" rx="3" fill="#57361f"/>`,
        uniform: `<path d="M${150 - 46} 246 L150 300 L${150 + 46} 246 L${150 + 60} 262 L150 318 L${150 - 60} 262Z" fill="${trim}"/><path d="M140 300 L150 312 L160 300 L166 322 L150 314 L134 322Z" fill="${accent}"/>`,
        jacket: `<path d="M${150 - 22} 244 L150 330 L${150 + 22} 244Z" fill="#f2f2f2"/><path d="M${150 - 26} 244 L${150 - 6} 330 L${150 - 30} 400 M${150 + 26} 244 L${150 + 6} 330 L${150 + 30} 400" stroke="${trim}" stroke-width="4" fill="none"/>`,
        dress: `<path d="M${150 - 34} 246 Q150 290 ${150 + 34} 246" fill="${skin}"/><path d="M${150 - 34} 246 Q150 290 ${150 + 34} 246" stroke="${trim}" stroke-width="3" fill="none"/>`,
        tank: `<path d="M${150 - 40} 244 Q150 300 ${150 + 40} 244" fill="${skin}"/><line x1="${150 - 44}" y1="250" x2="${150 - 38}" y2="290" stroke="${trim}" stroke-width="5"/><line x1="${150 + 44}" y1="250" x2="${150 + 38}" y2="290" stroke="${trim}" stroke-width="5"/>`,
        kimono: `<path d="M${150 - 30} 244 L${150 + 20} 330 M${150 + 30} 244 L${150 - 10} 300" stroke="${trim}" stroke-width="7" fill="none"/><rect x="${150 - shoulder}" y="330" width="${shoulder * 2}" height="22" fill="${accent}"/>`,
      }[puppet.outfit] || "";

      const eyeShape = puppet.eye_shape;
      const e = puppet.eye_size || 1;
      const eyeW = 15 * e, eyeH = (eyeShape === "sharp" ? 12 : eyeShape === "sleepy" ? 11 : 16) * e;
      const eye = (side) => {
        const cx = 150 + side * 30 * fw, cy = 160;
        const sparkle = eyeShape === "sparkly" ? `<circle cx="${cx + 4 * e}" cy="${cy + 6 * e}" r="${2 * e}" fill="#fff" opacity=".9"/><path d="M${cx - 6 * e} ${cy + 4 * e} l2 -4 l2 4 l-2 4Z" fill="#fff" opacity=".8"/>` : "";
        const wing = eyeShape === "sharp" ? `<path d="M${cx + side * eyeW} ${cy - eyeH * 0.5} l${side * 7} -5" stroke="#1d1420" stroke-width="3" stroke-linecap="round"/>` : "";
        return `<g class="eye" data-side="${side}" data-cx="${cx}" data-cy="${cy}">
          <g class="eye-open">
            <clipPath id="${uid}clip${side}"><ellipse cx="${cx}" cy="${cy}" rx="${eyeW}" ry="${eyeH}"/></clipPath>
            <ellipse cx="${cx}" cy="${cy}" rx="${eyeW}" ry="${eyeH}" fill="#fbfbff"/>
            <g clip-path="url(#${uid}clip${side})"><g class="iris">
              <ellipse cx="${cx}" cy="${cy + 1}" rx="${10.5 * e}" ry="${13.5 * e}" fill="url(#${uid}iris)"/>
              <ellipse cx="${cx}" cy="${cy + 2}" rx="${4.8 * e}" ry="${6.5 * e}" fill="#140c18"/>
              <circle cx="${cx - 4 * e}" cy="${cy - 5 * e}" r="${3.6 * e}" fill="#fff"/>${sparkle}
            </g></g>
            <path d="M${cx - eyeW - 2} ${cy - eyeH * 0.35} Q${cx} ${cy - eyeH - 6} ${cx + eyeW + 2} ${cy - eyeH * 0.35}" stroke="#1d1420" stroke-width="${eyeShape === "sleepy" ? 5 : 3.6}" fill="none" stroke-linecap="round"/>${wing}
          </g>
          <path class="eye-shut" d="M${cx - eyeW} ${cy + 2} Q${cx} ${cy - 10} ${cx + eyeW} ${cy + 2}" stroke="#1d1420" stroke-width="3.4" fill="none" stroke-linecap="round" opacity="0"/>
        </g>`;
      };
      const brow = (side) => {
        const cx = 150 + side * 30 * fw;
        return `<path class="brow" data-side="${side}" d="M${cx - 13} 132 Q${cx} 126 ${cx + 13} 132" stroke="${hairDark}" stroke-width="3.6" fill="none" stroke-linecap="round"/>`;
      };

      const acc = {
        headphones: `<path d="M${150 - 88 * hv} 150 Q150 ${10 - 10 * hv} ${150 + 88 * hv} 150" stroke="#2a2a33" stroke-width="9" fill="none"/><rect x="${150 - 100 * hv}" y="136" width="22" height="40" rx="9" fill="#2a2a33"/><rect x="${150 + 78 * hv}" y="136" width="22" height="40" rx="9" fill="#2a2a33"/><rect x="${150 - 96 * hv}" y="144" width="8" height="24" rx="3" fill="${accent}"/><rect x="${150 + 88 * hv}" y="144" width="8" height="24" rx="3" fill="${accent}"/>`,
        cat_ears: `<path d="M${150 - 70 * hv} 90 L${150 - 78 * hv} 20 L${150 - 30 * hv} 66Z" fill="${hair}"/><path d="M${150 - 66 * hv} 80 L${150 - 72 * hv} 36 L${150 - 42 * hv} 66Z" fill="#ffb3c7"/><path d="M${150 + 70 * hv} 90 L${150 + 78 * hv} 20 L${150 + 30 * hv} 66Z" fill="${hair}"/><path d="M${150 + 66 * hv} 80 L${150 + 72 * hv} 36 L${150 + 42 * hv} 66Z" fill="#ffb3c7"/>`,
        glasses: `<g stroke="#1d1d24" stroke-width="3" fill="rgba(200,230,255,.18)"><rect x="${150 - 30 * fw - 20}" y="145" width="40" height="30" rx="8"/><rect x="${150 + 30 * fw - 20}" y="145" width="40" height="30" rx="8"/><line x1="${150 - 30 * fw + 20}" y1="156" x2="${150 + 30 * fw - 20}" y2="156"/></g>`,
        ribbon: `<g transform="translate(${150 + 58 * hv} 70) rotate(20)"><path d="M0 0 L-26 -16 L-26 16Z M0 0 L26 -16 L26 16Z" fill="${accent}"/><circle r="6" fill="${shade(accent, -0.3)}"/></g>`,
        horns: `<path d="M${150 - 50 * hv} 70 Q${150 - 70 * hv} 20 ${150 - 90 * hv} 26 Q${150 - 66 * hv} 40 ${150 - 62 * hv} 80Z" fill="#2b2233"/><path d="M${150 + 50 * hv} 70 Q${150 + 70 * hv} 20 ${150 + 90 * hv} 26 Q${150 + 66 * hv} 40 ${150 + 62 * hv} 80Z" fill="#2b2233"/>`,
        halo: `<ellipse cx="150" cy="${30 - 10 * hv}" rx="44" ry="11" stroke="#ffe27a" stroke-width="5" fill="none" opacity=".9"/>`,
        anvil: "",
      }[puppet.accessory] || "";
      const anvil = puppet.accessory === "anvil" ? `<g class="familiar" transform="translate(250 250)"><path d="M-22 -8 L18 -8 Q30 -8 30 -2 L14 0 L10 10 L16 18 L-16 18 L-10 10 L-14 0 L-22 -2Z" fill="#4a4f5c" stroke="#23262e" stroke-width="2"/><circle cx="-4" cy="-2" r="2.5" fill="${accent}"/><circle cx="6" cy="-2" r="2.5" fill="${accent}"/></g>` : "";

      const soot = puppet.soot > 0 ? `<g opacity="${puppet.soot}" fill="#3a3a3a"><ellipse cx="${150 + 44 * fw}" cy="196" rx="9" ry="5" opacity=".55"/><ellipse cx="${150 + 52 * fw}" cy="200" rx="5" ry="3" opacity=".45"/></g>` : "";
      const streak = c.hair_streak && c.hair_streak !== c.hair ? `<path d="M${150 + 18} 60 Q${150 + 30} 100 ${150 + 22} 136 L${150 + 34} 116 Q${150 + 40} 90 ${150 + 28} 58Z" fill="${c.hair_streak}"/>` : "";

      this.svg.innerHTML = `
        <defs>
          <radialGradient id="${uid}iris" cx="50%" cy="35%" r="70%"><stop offset="0" stop-color="${shade(c.eyes, 0.35)}"/><stop offset=".6" stop-color="${c.eyes}"/><stop offset="1" stop-color="${shade(c.eyes, -0.5)}"/></radialGradient>
          <linearGradient id="${uid}hair" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="${hairLight}"/><stop offset=".5" stop-color="${hair}"/><stop offset="1" stop-color="${hairDark}"/></linearGradient>
        </defs>
        <g class="whole">
          <g class="body">
            <rect x="136" y="215" width="28" height="40" fill="${skinShade}"/>
            <path d="${outfitBody}" fill="${c.outfit}"/>${outfitExtra}
          </g>
          <g class="head">
            <g class="hair-back" fill="url(#${uid}hair)">${back}</g>
            <path class="face" d="M${150 - 66 * fw} 140 Q${150 - 68 * fw} 205 150 232 Q${150 + 68 * fw} 205 ${150 + 66 * fw} 140 Q${150 + 60 * fw} 76 150 74 Q${150 - 60 * fw} 76 ${150 - 66 * fw} 140Z" fill="${skin}"/>
            <g class="features">
              <ellipse class="blush" cx="${150 - 42 * fw}" cy="190" rx="14" ry="6" fill="#ff7f9f" opacity="0"/>
              <ellipse class="blush" cx="${150 + 42 * fw}" cy="190" rx="14" ry="6" fill="#ff7f9f" opacity="0"/>
              ${soot}${eye(-1)}${eye(1)}${brow(-1)}${brow(1)}
              <path class="nose" d="M150 184 l-2 5 l3 0" stroke="${skinShade}" stroke-width="1.8" fill="none"/>
              <path class="mouth" fill="#8c2f3c" stroke="#3a1a20" stroke-width="2.4" stroke-linejoin="round" stroke-linecap="round"/>
              <path class="fang" fill="#fff" opacity="${puppet.mouth_style === "fang" ? 1 : 0}"/>
            </g>
            <g class="hair-front" fill="url(#${uid}hair)">${bangs}${streak}</g>
            <g class="accessory">${acc}</g>
          </g>
          ${anvil}
        </g>`;
      const q = (s) => this.svg.querySelector(s);
      this.el = {
        whole: q(".whole"), body: q(".body"), head: q(".head"), back: q(".hair-back"), features: q(".features"),
        front: q(".hair-front"), acc: q(".accessory"), mouth: q(".mouth"), fang: q(".fang"),
        eyes: [...this.svg.querySelectorAll(".eye")], brows: [...this.svg.querySelectorAll(".brow")],
        blush: [...this.svg.querySelectorAll(".blush")], familiar: q(".familiar"),
        tails: [...this.svg.querySelectorAll(".tail-l,.tail-r")],
      };
    }

    apply(v, now) {
      if (!this.p) return;
      const ax = v.ParamAngleX, ay = v.ParamAngleY, az = v.ParamAngleZ + (this.p.head_tilt || 0);
      const bx = v.ParamBodyAngleX, bz = v.ParamBodyAngleZ, breath = v.ParamBreath;
      const E = this.el;
      E.whole.setAttribute("transform", `translate(0 ${-breath * 2.5})`);
      E.body.setAttribute("transform", `rotate(${bz * 0.8} 150 400) translate(${bx * 1.2} 0)`);
      E.head.setAttribute("transform", `translate(${ax * 0.9 + bx * 1.2} ${-ay * 0.5}) rotate(${az + bz * 0.8} 150 232)`);
      E.back.setAttribute("transform", `translate(${-ax * 0.35} ${ay * 0.25})`);
      E.features.setAttribute("transform", `translate(${ax * 0.55} ${-ay * 0.45})`);
      E.front.setAttribute("transform", `translate(${ax * 0.75} ${-ay * 0.55})`);
      E.acc.setAttribute("transform", `translate(${ax * 0.6} ${-ay * 0.4})`);
      E.tails.forEach((t, i) => t.setAttribute("transform", `rotate(${Math.sin(now / 700 + i) * 2 - az * 0.3 - ax * 0.1} 150 110)`));
      if (E.familiar) E.familiar.setAttribute("transform", `translate(${250 + Math.sin(now / 900) * 4} ${250 + Math.sin(now / 600) * 7}) rotate(${Math.sin(now / 800) * 6})`);

      const smile = Math.max(v.ParamEyeLSmile, v.ParamEyeRSmile || 0);
      E.eyes.forEach((g) => {
        const side = +g.dataset.side, cx = +g.dataset.cx, cy = +g.dataset.cy;
        const open = clamp(side < 0 ? v.ParamEyeLOpen : v.ParamEyeROpen, 0, 1.5);
        const shut = open < 0.18 || smile > 0.75;
        g.querySelector(".eye-open").setAttribute("transform", `translate(${cx} ${cy}) scale(1 ${shut ? 0.01 : Math.max(0.08, open)}) translate(${-cx} ${-cy})`);
        g.querySelector(".eye-open").setAttribute("opacity", shut ? 0 : 1);
        g.querySelector(".eye-shut").setAttribute("opacity", shut ? 1 : 0);
        g.querySelector(".iris").setAttribute("transform", `translate(${v.ParamEyeBallX * 5} ${-v.ParamEyeBallY * 4})`);
      });
      E.brows.forEach((b) => {
        const side = +b.dataset.side;
        const y = side < 0 ? v.ParamBrowLY : v.ParamBrowRY;
        const cx = 150 + side * 30 * (this.p.face_width || 1);
        b.setAttribute("transform", `translate(0 ${-y * 7}) rotate(${-side * y * -6} ${cx} 130)`);
      });
      const blush = clamp((this.p.blush || 0) * 0.45 + v.ParamCheek * 0.7, 0, 0.85);
      E.blush.forEach((b) => b.setAttribute("opacity", blush));

      // Mouth: form bends the corners, open drops the lower lip.
      const m = clamp(v.ParamMouthOpenY, 0, 1), f = clamp(v.ParamMouthForm, -1, 1);
      const style = this.p.mouth_style;
      const w = style === "grin" ? 15 : style === "small" ? 8 : 11;
      const x0 = 150 - w, x1 = 150 + w, y = 208;
      let d;
      if (m < 0.06) {
        d = style === "cat"
          ? `M${x0} ${y - f * 2} Q${150 - w / 2} ${y + 5 + f * 2} 150 ${y} Q${150 + w / 2} ${y + 5 + f * 2} ${x1} ${y - f * 2}`
          : `M${x0} ${y - f * 3} Q150 ${y + f * 7} ${x1} ${y - f * 3}`;
        E.mouth.setAttribute("fill", "none");
      } else {
        const open = 3 + m * 15;
        d = `M${x0} ${y - f * 3} Q150 ${y - 2 + f * 3} ${x1} ${y - f * 3} Q150 ${y + open + f * 4} ${x0} ${y - f * 3}Z`;
        E.mouth.setAttribute("fill", "#8c2f3c");
      }
      E.mouth.setAttribute("d", d);
      E.fang.setAttribute("d", `M${150 + w * 0.45} ${y - f * 3 + 1} l3 ${m < 0.06 ? 4 : 6} l3 ${m < 0.06 ? -4 : -6}Z`);
    }
  }

  /* ------------------------------------------------------------ Live2D */

  let libs = null;
  function loadScript(src) {
    return new Promise((resolve, reject) => {
      const s = document.createElement("script");
      s.src = src; s.onload = resolve; s.onerror = () => reject(new Error("Could not load " + src));
      document.head.appendChild(s);
    });
  }
  function loadLive2D(base) {
    if (!libs) {
      libs = (async () => {
        for (const f of ["live2dcubismcore.min.js", "live2d.min.js", "pixi.min.js", "index.min.js"]) await loadScript(`${base}/lib/${f}`);
        if (!window.PIXI || !PIXI.live2d) throw new Error("The Live2D viewer did not start");
      })();
    }
    return libs;
  }

  class Live2DBackend {
    constructor(container, base, frame) {
      this.container = container; this.base = base; this.frame = frame || 1;
      this.canvas = document.createElement("canvas");
      this.canvas.className = "forge-live2d";
      container.appendChild(this.canvas);
      this.overrides = {}; this.ids = new Set(); this.idOf = {};
    }
    destroy() {
      try { this.app && this.app.destroy(false, { children: true }); } catch (e) { /* already gone */ }
      this.canvas.remove();
    }
    resolve(param) {
      if (param in this.idOf) return this.idOf[param];
      // Cubism 2 hides its id list; its standard ids are the PARAM_* names.
      if (this.cubism === 2 && !this.ids.size) return (this.idOf[param] = snake(param));
      const found = [param, snake(param), ...(ALIASES[param] || [])].find((id) => this.ids.has(id)) || null;
      this.idOf[param] = found;
      return found;
    }
    async load(modelId, motions) {
      await loadLive2D(this.base);
      const models = window.__forgeAvatarModels || {};
      const url = models[modelId] ? `/shared/${models[modelId]}` : null;
      if (!url) throw new Error("Unknown model " + modelId);
      const settings = await (await fetch(url)).json();
      settings.url = url;
      this.forgeNames = Object.keys(motions || {});
      this.cubism = url.endsWith(".model3.json") ? 4 : 2;
      if (this.cubism === 4) {
        const refs = settings.FileReferences;
        refs.Motions = refs.Motions || {};
        refs.Motions.Forge = this.forgeNames.map((name) => ({ File: motions[name], Name: name, FadeInTime: 0.4, FadeOutTime: 0.5 }));
        if (!refs.Motions.Idle && motions && motions.idle_breathe) {
          refs.Motions.Idle = [{ File: motions.idle_breathe, Name: "idle_breathe" }];
        }
        this.own = Object.entries(refs.Motions).filter(([g]) => g !== "Forge").map(([g, items]) => [g, items.map((m) => m.Name || (m.File || "").split("/").pop().split(".")[0])]);
        this.faces = (refs.Expressions || []).map((e) => e.Name);
      } else {
        settings.motions = settings.motions || {};
        settings.motions.Forge = this.forgeNames.map((name) => ({ file: motions[name], fade_in: 400, fade_out: 500 }));
        if (!settings.motions.idle && motions && motions.idle_breathe) settings.motions.idle = [{ file: motions.idle_breathe }];
        this.own = Object.entries(settings.motions).filter(([g]) => g !== "Forge").map(([g, items]) => [g, items.map((m) => m.name || (m.file || "").split("/").pop().split(".")[0])]);
        this.faces = (settings.expressions || []).map((e) => e.name);
      }
      this.app = new PIXI.Application({ view: this.canvas, resizeTo: this.container, backgroundAlpha: 0, antialias: true, autoDensity: true, resolution: Math.min(2, window.devicePixelRatio || 1) });
      const model = await PIXI.live2d.Live2DModel.from(settings, { autoInteract: false });
      this.model = model;
      this.app.stage.addChild(model);
      const core = model.internalModel.coreModel;
      try { (core._model?.parameters?.ids || core.getModel?.().parameters.ids || []).forEach((id) => this.ids.add(id)); } catch (e) { /* ids unknown */ }
      if (this.cubism === 2) {
        this.set = (id, v) => core.setParamFloat(id, v);
        this.add = (id, v) => core.addToParamFloat(id, v);
        this.get = (id) => core.getParamFloat(id);
      } else {
        this.set = (id, v) => core.setParameterValueById(id, v);
        this.add = (id, v) => core.addParameterValueById(id, v);
        this.get = (id) => core.getParameterValueById(id);
      }
      this.fit();
      this.ro = new ResizeObserver(() => this.fit());
      this.ro.observe(this.container);
      // Apply lip sync, expressions and blinks just before the model draws.
      // This viewer does not emit "beforeModelUpdate", and values set here are
      // not saved into the next frame, so offsets never pile up.
      const draw = core.update.bind(core);
      core.update = () => { try { this.push(); } catch (e) { /* never block drawing */ } draw(); };
      return model;
    }
    fit() {
      if (!this.model) return;
      const w = this.container.clientWidth, h = this.container.clientHeight;
      const m = this.model;
      m.scale.set(1);
      // frame: how much of the model shows, from the top (1 = all of it).
      const s = Math.min(w / (m.width * Math.max(0.6, this.frame)), (h * 1.05) / (m.height * this.frame));
      m.scale.set(s);
      m.x = (w - m.width) / 2;
      m.y = this.frame < 1 ? h * 0.03 : h - m.height * 0.98;
    }
    push() {
      for (const [param, value] of Object.entries(this.overrides)) {
        const id = this.resolve(param);
        if (!id) continue;
        if (param === "ParamMouthOpenY" && value.abs) this.set(id, value.v);
        else if (value.v) this.add(id, value.v);
        else if (value.mul !== undefined) this.set(id, this.get(id) * value.mul);
      }
    }
    play(name) {
      const i = (this.forgeNames || []).indexOf(name);
      if (i < 0 || !this.model) return false;
      this.model.motion("Forge", i, 3);
      return true;
    }
    playOwn(group, index) { this.model && this.model.motion(group, index, 3); }
    /** The model's own motion by name, or a random one from a group of that name. */
    playOwnNamed(name) {
      if (!this.model) return false;
      const want = name.toLowerCase();
      for (const [group, names] of this.own || []) {
        const i = names.findIndex((n) => (n || "").toLowerCase() === want);
        if (i >= 0) { this.model.motion(group, i, 3); return true; }
      }
      const group = (this.own || []).find(([g]) => g.toLowerCase() === want);
      if (group && group[1].length) { this.model.motion(group[0], Math.floor(Math.random() * group[1].length), 3); return true; }
      return false;
    }
    /** The model's own expression with this name (any case); false when it has none. */
    face(name) {
      if (!this.model) return false;
      const real = (this.faces || []).find((f) => (f || "").toLowerCase() === (name || "").toLowerCase());
      try {
        if (real) { this.model.expression(real); return true; }
        const em = this.model.internalModel.motionManager.expressionManager;
        if (em && em.resetExpression) em.resetExpression();
      } catch (e) { /* the model has no expression manager */ }
      return false;
    }
    /** Hit area names under a page point (lower case), from the model's own HitAreas. */
    hits(x, y, zoom) {
      if (!this.model) return [];
      const r = this.canvas.getBoundingClientRect();
      try { return this.model.hitTest((x - r.left) / zoom, (y - r.top) / zoom).map((h) => String(h).toLowerCase()); } catch (e) { return []; }
    }
    focus(x, y) {
      if (!this.model) return;
      const r = this.canvas.getBoundingClientRect();
      const zoom = r.width / (this.canvas.clientWidth || r.width);
      this.model.focus((x - r.left) / zoom, (y - r.top) / zoom);
    }
  }

  /* ------------------------------------------------------------ the avatar */

  class ForgeAvatar {
    constructor(container, opts = {}) {
      this.container = container;
      this.base = opts.base || "/shared/avatars";
      this.frame = opts.frame || 1;
      this.player = new RecipePlayer();
      this.backend = null;
      this.expr = "neutral"; this.exprTarget = {}; this.exprNow = {};
      this.mouth = 0; this.talkUntil = 0; this.audioLevel = 0;
      this.blinkAt = performance.now() + 2000; this.blinkT = -1;
      this.look = { x: 0, y: 0 }; this.lookTarget = { x: 0, y: 0 };
      this.persona = null; this.lastIdle = performance.now();
      this.place = { x: 0, y: 0, zoom: 1 };
      this.onError = opts.onError || ((e) => console.warn(e));
      this._frame = this._frame.bind(this);
      this._move = (e) => this.lookAt(e.clientX, e.clientY);
      window.addEventListener("pointermove", this._move);
      requestAnimationFrame(this._frame);
    }

    destroy() {
      window.removeEventListener("pointermove", this._move);
      this.backend && this.backend.destroy();
      this.dead = true;
    }

    /** spec: {kind: "live2d"|"puppet", id} or {kind: "puppet", puppet}.
     *  data: {models, recipes, puppets, motions} from the app's API. */
    setFrame(frame) {
      this.frame = frame;
      if (this.backend && this.backend.fit) { this.backend.frame = frame; this.backend.fit(); }
    }

    async show(spec, data = {}, persona = null) {
      this.persona = persona;
      this.player.setRecipes(data.recipes || {});
      if (data.models) {
        window.__forgeAvatarModels = Object.fromEntries(data.models.map((m) => [m.id, m.url]));
      }
      if (this.backend) this.backend.destroy();
      this.backend = null;
      this.kind = spec.kind;
      if (spec.kind === "live2d") {
        const b = new Live2DBackend(this.container, this.base, this.frame);
        this.backend = b;
        try {
          await b.load(spec.id, data.motions || {});
        } catch (e) {
          b.destroy();
          this.backend = null;
          throw e;
        }
      } else {
        const puppet = spec.puppet || (data.puppets || []).find((p) => p.id === spec.id);
        if (!puppet) throw new Error("No puppet called " + spec.id);
        const b = new PuppetBackend(this.container);
        b.load(puppet);
        this.backend = b;
        this.player.play("idle_breathe", { loop: true, layer: true });
      }
      this.expression((persona && persona.expression) || "neutral");
      if (this.placePrefix !== undefined) this.interactive(this.placePrefix);
    }

    expression(name) {
      this.expr = EXPRESSIONS[name] ? name : "neutral";
      // A Live2D model's own expression of the same name wins over the offsets.
      const real = this.kind === "live2d" && this.backend && this.backend.face(name);
      this.exprTarget = real ? {} : EXPRESSIONS[this.expr];
    }

    /** Status from the app: idle, thinking, tool, talking, done, error. */
    react(status) {
      const reactions = (this.persona && this.persona.reactions) || {};
      const face = STATUS_FACE[status];
      this.expression(face || (this.persona && this.persona.expression) || "neutral");
      if (status === "talking" && this.player.busy()) return;
      this.playAny(reactions[status]);
      if (status === "done" || status === "error") {
        setTimeout(() => this.expression((this.persona && this.persona.expression) || "neutral"), 3500);
      }
    }

    play(name, opts = {}) {
      if (!this.backend) return false;
      // "own:Happy" is the model's own motion (or motion group) called Happy.
      if (name.startsWith("own:")) return this.kind === "live2d" && this.backend.playOwnNamed(name.slice(4));
      if (this.kind === "live2d") return this.backend.play(name);
      return this.player.play(name, opts);
    }

    playRecipe(recipe, opts = {}) {
      if (this.kind === "live2d") return false; // Live2D plays saved files; save it first
      return this.player.play(recipe, opts);
    }

    /** A chat reply's tag (happy, think, shy, sad, surprised, wink) as a
     *  face and a motion: the persona's own reaction lists first. */
    reactTag(tag) {
      const r = (this.persona && this.persona.reactions) || {};
      const plan = {
        happy: ["happy", r.done, ["own:happy", "laugh", "nod"]],
        think: ["think", r.thinking, ["own:thinking", "think_look_up", "tilt_curious"]],
        shy: ["embarrassed", r.head, ["own:shy", "shy_look_away", "peek"]],
        sad: ["sad", null, ["own:sad", "sigh"]],
        surprised: ["surprised", r.body, ["own:surprised", "surprised"]],
        wink: ["happy", null, ["own:wink", "wink"]],
      }[tag] || ["happy", null, ["nod"]];
      this.expression(plan[0]);
      // A mood-specific motion first, then the persona's list for that mood.
      this.playAny(plan[2]) || this.playAny(plan[1]);
      setTimeout(() => this.expression((this.persona && this.persona.expression) || "neutral"), 4000);
    }

    /** Reactions from a list, skipping ones this avatar cannot play. */
    playAny(names) {
      const list = [...(names || [])].sort(() => Math.random() - 0.5);
      return list.some((n) => this.play(n));
    }

    /** A click on the avatar at a page point: "head" or "body", from the
     *  model's HitAreas when it has them, else the top third is the head. */
    zoneAt(x, y) {
      if (this.kind === "live2d" && this.backend) {
        const hits = this.backend.hits(x, y, this.place.zoom);
        if (hits.some((h) => h.includes("head") || h.includes("face"))) return "head";
        if (hits.length) return "body";
      }
      const el = this.container.firstElementChild;
      const r = (el || this.container).getBoundingClientRect();
      if (x < r.left || x > r.right || y < r.top || y > r.bottom) return null;
      const top = this.kind === "live2d" && this.frame < 1 ? 0.5 : 0.35;
      return (y - r.top) / r.height < top ? "head" : "body";
    }

    /** Head tap: shy; body poke: surprised. A persona can set reactions.head
     *  and reactions.body; a model's own tap/flick groups are used when present. */
    poke(x, y) {
      const zone = this.zoneAt(x, y);
      if (!zone) return null;
      const reactions = (this.persona && this.persona.reactions) || {};
      const own = zone === "head" ? ["own:tap_head", "own:flick_head"] : ["own:tap_body", "own:tapbody"];
      const fallback = zone === "head" ? ["shy_look_away", "peek"] : ["surprised", "giggle"];
      this.expression(zone === "head" ? "embarrassed" : "surprised");
      this.playAny(reactions[zone]) || this.playAny(own) || this.playAny(fallback);
      setTimeout(() => this.expression((this.persona && this.persona.expression) || "neutral"), 2500);
      return zone;
    }

    /** Drag to move, wheel to zoom, click to poke. The place is kept in
     *  localStorage per page (prefix) and persona. */
    interactive(prefix) {
      this.placePrefix = prefix;
      const key = `${prefix}.${(this.persona && this.persona.id) || "none"}`;
      this.placeKey = key;
      this.place = { x: 0, y: 0, zoom: 1 };
      try { Object.assign(this.place, JSON.parse(localStorage.getItem("forge.avatar.place." + key) || "{}")); } catch (e) { /* none saved */ }
      this._applyPlace();
      if (this._wired) return;
      this._wired = true;
      const c = this.container;
      let down = null;
      c.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        down = { x: e.clientX, y: e.clientY, px: this.place.x, py: this.place.y, moved: false };
        c.setPointerCapture(e.pointerId);
      });
      c.addEventListener("pointermove", (e) => {
        if (!down) return;
        const dx = e.clientX - down.x, dy = e.clientY - down.y;
        if (!down.moved && Math.hypot(dx, dy) < 5) return;
        down.moved = true;
        this.place.x = down.px + dx; this.place.y = down.py + dy;
        this._applyPlace();
      });
      c.addEventListener("pointerup", (e) => {
        if (!down) return;
        const d = down; down = null;
        if (d.moved) this._savePlace(); else this.poke(e.clientX, e.clientY);
      });
      c.addEventListener("wheel", (e) => {
        e.preventDefault();
        this.place.zoom = clamp(this.place.zoom * (e.deltaY < 0 ? 1.1 : 1 / 1.1), 0.4, 3);
        this._applyPlace(); this._savePlace();
      }, { passive: false });
    }

    resetPlace() { this.place = { x: 0, y: 0, zoom: 1 }; this._applyPlace(); this._savePlace(); }

    _applyPlace() {
      const el = this.container.firstElementChild;
      if (!el || !this.place) return;
      el.style.transformOrigin = "50% 40%";
      el.style.transform = `translate(${this.place.x}px, ${this.place.y}px) scale(${this.place.zoom})`;
    }

    _savePlace() {
      try { localStorage.setItem("forge.avatar.place." + this.placeKey, JSON.stringify(this.place)); } catch (e) { /* not kept */ }
    }

    lookAt(x, y) {
      const r = this.container.getBoundingClientRect();
      if (!r.width) return;
      const cx = r.left + r.width / 2, cy = r.top + r.height * 0.35;
      this.lookTarget = { x: clamp((x - cx) / (r.width * 0.9), -1, 1), y: clamp((cy - y) / (r.height * 0.9), -1, 1) };
      if (this.kind === "live2d" && this.backend) this.backend.focus(x, y);
    }

    /** Lip movement while text streams in, when nothing is being spoken. */
    talkPulse(ms = 350) { this.talkUntil = Math.max(this.talkUntil, performance.now() + ms); }

    async speakBlob(blob) {
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      try {
        this.actx = this.actx || new AudioContext();
        const src = this.actx.createMediaElementSource(audio);
        const an = this.actx.createAnalyser();
        an.fftSize = 512;
        src.connect(an); an.connect(this.actx.destination);
        this.analyser = an;
        this.buf = new Float32Array(an.fftSize);
      } catch (e) { this.analyser = null; }
      this.speaking = audio;
      await audio.play();
      await new Promise((resolve) => { audio.onended = resolve; audio.onerror = resolve; });
      this.speaking = null; this.analyser = null;
      URL.revokeObjectURL(url);
    }

    stopSpeaking() { if (this.speaking) { this.speaking.pause(); this.speaking.onended && this.speaking.onended(); } }

    _mouthNow(now) {
      if (this.analyser) {
        this.analyser.getFloatTimeDomainData(this.buf);
        let sum = 0;
        for (const s of this.buf) sum += s * s;
        const level = clamp(Math.sqrt(sum / this.buf.length) * 7, 0, 1);
        this.audioLevel += (level - this.audioLevel) * 0.5;
        return this.audioLevel;
      }
      if (now < this.talkUntil) return 0.25 + 0.35 * Math.abs(Math.sin(now / 55)) * Math.abs(Math.sin(now / 131));
      return 0;
    }

    _frame(now) {
      if (this.dead) return;
      requestAnimationFrame(this._frame);
      if (!this.backend) return;
      // Ease the gaze and the expression.
      this.look.x += (this.lookTarget.x - this.look.x) * 0.08;
      this.look.y += (this.lookTarget.y - this.look.y) * 0.08;
      for (const k of new Set([...Object.keys(this.exprNow), ...Object.keys(this.exprTarget)])) {
        const t = this.exprTarget[k] || 0;
        this.exprNow[k] = (this.exprNow[k] || 0) + (t - (this.exprNow[k] || 0)) * 0.08;
      }
      // Blinks every 2 to 6 seconds.
      let blink = 1;
      if (now > this.blinkAt) { this.blinkT = now; this.blinkAt = now + 2000 + Math.random() * 4000; }
      if (this.blinkT > 0) {
        const x = (now - this.blinkT) / 160;
        if (x < 1) blink = Math.abs(1 - 2 * x); else this.blinkT = -1;
      }
      const target = this._mouthNow(now);
      this.mouth += (target - this.mouth) * 0.45;

      // Idle fidgets every 15 to 30 seconds.
      if (!this.speaking && now > this.talkUntil && now - this.lastIdle > 15000 + Math.random() * 15000 && !this.player.busy()) {
        this.lastIdle = now;
        const idle = pick(this.persona && this.persona.reactions && this.persona.reactions.idle);
        if (idle && idle !== "idle_breathe") this.play(idle);
      }

      if (this.kind === "puppet") {
        const v = {};
        for (const k of Object.keys(RANGES)) v[k] = REST[k] || 0;
        const motion = this.player.values(now);
        for (const [k, val] of Object.entries(motion)) v[k] = val;
        for (const [k, val] of Object.entries(this.exprNow)) v[k] = (v[k] ?? 0) + val;
        v.ParamAngleX += this.look.x * 22; v.ParamAngleY += this.look.y * 14;
        v.ParamEyeBallX += this.look.x * 0.9; v.ParamEyeBallY += this.look.y * 0.8;
        v.ParamBodyAngleX += this.look.x * 3;
        v.ParamEyeLOpen *= blink; v.ParamEyeROpen *= blink;
        v.ParamMouthOpenY = Math.max(v.ParamMouthOpenY, this.mouth);
        for (const [k, [lo, hi]] of Object.entries(RANGES)) v[k] = clamp(v[k], lo, hi);
        this.backend.apply(v, now);
      } else {
        const o = {};
        for (const [k, val] of Object.entries(this.exprNow)) if (Math.abs(val) > 0.01) o[k] = { v: val };
        o.ParamMouthOpenY = this.mouth > 0.02 ? { v: this.mouth, abs: true } : { v: 0 };
        if (blink < 1 && !this.backend.model?.internalModel?.eyeBlink) {
          o.ParamEyeLOpen = { mul: blink }; o.ParamEyeROpen = { mul: blink };
        }
        this.backend.overrides = o;
      }
    }
  }

  ForgeAvatar.EXPRESSIONS = EXPRESSIONS;
  ForgeAvatar.RecipePlayer = RecipePlayer;
  ForgeAvatar.sampleCurve = sampleCurve;
  window.ForgeAvatar = ForgeAvatar;
})();
