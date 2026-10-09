/* Real-depth 2.5D wallpaper (Emerson, 2026-09-29: "make the 2.5d way cooler
   ... more layers or even actually be 3d").

   One WebGL canvas inside the hub's #wall draws the picture bent by its depth
   map (shared/forge_layers.py's <key>-depth.png, light = near). For every
   pixel the shader walks a short ray through the depth map, near to far, and
   shows the first surface the ray meets. Nearer parts slide further than far
   ones and cover what is behind them, as in a 3D photo, so the picture has as
   many layers as it has depths instead of two.

   The cut-out (when forge_layers found a subject) stays as its own layer on
   top, with the particles between it and this canvas. The view pivots on the
   subject's own depth, so the cut-out and the picture never slide apart: the
   world swings round the character.

   It draws only while something moves (the pointer, the slow drift, the beat)
   and stops asking for frames once the view has settled. Its frames go
   through requestAnimationFrame, so Forge's frame-rate cap and its rest while
   hidden apply. Without WebGL, or when the picture cannot be read into it,
   mount() or load() fails and the hub keeps the two-layer look.

   API: mount(parent) -> bool, load(image, depth, cutout) -> Promise,
   set({ strength, drift }), point(x, y) with -1..1, beat(k), stop(). */
(function (root) {
  const VS = "attribute vec2 p; varying vec2 uv;"
    + "void main() { uv = vec2(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5); gl_Position = vec4(p, 0.0, 1.0); }";
  // off: how far the view has moved, in picture widths; fit: the part of the
  // picture on screen (cover fit, less the margin the movement needs)
  const FS = `precision mediump float;
varying vec2 uv;
uniform sampler2D img;
uniform sampler2D dep;
uniform vec2 off;
uniform vec4 fit;
uniform float focus;
uniform float steps;
const int STEPS = 16;
float depthAt(vec2 s) { return texture2D(dep, s).r; }
void main() {
  vec2 t = uv * fit.xy + fit.zw;
  float pz = 1.0;
  vec2 ps = t - off * (pz - focus);
  float pd = depthAt(ps);
  vec2 hit = ps;
  if (pd < pz) {
    for (int i = 1; i <= STEPS; i++) {
      if (float(i) > steps) break;
      float z = 1.0 - float(i) / steps;
      vec2 s = t - off * (z - focus);
      float d = depthAt(s);
      if (d >= z) {
        float a = pd - pz, b = d - z;
        float w = a / (a - b);
        hit = t - off * (mix(pz, z, w) - focus);
        break;
      }
      pz = z; pd = d; hit = s;
    }
  }
  gl_FragColor = texture2D(img, clamp(hit, vec2(0.001), vec2(0.999)));
}`;
  const MAX_SHIFT = 0.022; // picture widths per step of 2.5D depth
  // The slow drift alone moves the nearest layer under a pixel a frame at 24
  // frames a second, and every frame is a full-screen ray walk (task 56); the
  // pointer and the beat still draw at the full rate.
  // v2 (2026-10-07, Emerson: "a bit too heavy on the GPU"): 20 a second for
  // the drift, a ray walk of 10 steps while only drifting (16 while the
  // pointer or the beat moves it, 8 on the reduced tier), and the canvas
  // drawn at 3/4 of the screen (1/2 reduced) and stretched: the picture is
  // soft, and that is about half the pixels.
  const DRIFT_FPS = 20;
  const STEPS_MOVING = 16, STEPS_DRIFT = 10, STEPS_REDUCED = 8;
  const RES = { full: 0.75, reduced: 0.5 };
  // the shared power tier (shared/forge_power.js, v2 2026-10-07): reduced
  // drifts at half that rate, paused draws nothing until it changes
  // set({ tier }) from the host, else the page theme's power_tier
  let tierName = "";
  const tier = () => String(tierName || (typeof window === "object" && window.FORGE_THEME && window.FORGE_THEME.power_tier) || "full").split(":")[0].trim();

  const D = {
    canvas: null, gl: null, prog: null, u: {}, tex: {}, size: [1, 1], ready: false, focus: 0.5,
    strength: 1, drift: () => false, x: 0, y: 0, tx: 0, ty: 0, k: 0, raf: 0, timer: 0, t0: 0, token: 0,
    // s: the strength shown, eased toward the setting; behind an open app
    // (body.in-app) toward 0, so the picture goes back to a plain cover fit
    // instead of the zoom the movement margin needs, then it stops drawing
    s: 1, away: false,

    mount(parent) {
      if (this.gl) {
        if (this.canvas.parentNode !== parent) parent.appendChild(this.canvas);
        this.canvas.hidden = false;
        return true;
      }
      const c = document.createElement("canvas");
      c.className = "depth";
      const gl = c.getContext("webgl", { alpha: false, antialias: false, premultipliedAlpha: false, powerPreference: "low-power" });
      if (!gl) return false;
      const sh = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null;
      };
      const vs = sh(gl.VERTEX_SHADER, VS), fs = sh(gl.FRAGMENT_SHADER, FS);
      if (!vs || !fs) return false;
      const prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return false;
      gl.useProgram(prog);
      const buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
      const at = gl.getAttribLocation(prog, "p");
      gl.enableVertexAttribArray(at);
      gl.vertexAttribPointer(at, 2, gl.FLOAT, false, 0, 0);
      for (const n of ["img", "dep", "off", "fit", "focus", "steps"]) this.u[n] = gl.getUniformLocation(prog, n);
      gl.uniform1i(this.u.img, 0);
      gl.uniform1i(this.u.dep, 1);
      c.addEventListener("webglcontextlost", (e) => { e.preventDefault(); this.ready = false; });
      document.addEventListener("forge-power", () => this.wake());
      // an app opened or closed in the hub: ease the depth out or back in
      const watch = () => {
        const away = document.body.classList.contains("in-app");
        if (away !== this.away) { this.away = away; this.wake(); }
      };
      new MutationObserver(watch).observe(document.body, { attributes: true, attributeFilter: ["class"] });
      watch();
      this.canvas = c;
      this.gl = gl;
      this.prog = prog;
      parent.appendChild(c);
      return true;
    },

    picture(url) {
      return new Promise((ok, bad) => {
        const im = new Image();
        im.decoding = "async";
        im.onload = () => ok(im);
        im.onerror = () => bad(new Error(`could not load ${url}`));
        im.src = url;
      });
    },
    upload(unit, im) {
      const gl = this.gl;
      const tex = this.tex[unit] || gl.createTexture();
      this.tex[unit] = tex;
      gl.activeTexture(gl.TEXTURE0 + unit);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGB, gl.RGB, gl.UNSIGNED_BYTE, im); // throws on a picture it may not read
    },
    // the depth the view pivots on: the cut-out's own (its alpha-weighted mean
    // depth), or a third of the way in for a landscape with no subject
    pivot(depthIm, cutIm) {
      if (!cutIm) return 0.35;
      const n = 96, c = document.createElement("canvas");
      c.width = c.height = n;
      const x = c.getContext("2d", { willReadFrequently: true });
      x.drawImage(depthIm, 0, 0, n, n);
      const d = x.getImageData(0, 0, n, n).data;
      x.clearRect(0, 0, n, n);
      x.drawImage(cutIm, 0, 0, n, n);
      const a = x.getImageData(0, 0, n, n).data;
      let sum = 0, weight = 0;
      for (let i = 0; i < d.length; i += 4) { sum += (d[i] / 255) * a[i + 3]; weight += a[i + 3]; }
      return weight > 0 ? sum / weight : 0.35;
    },
    async load(image, depth, cutout) {
      const token = ++this.token;
      this.ready = false;
      const [im, dm, cut] = await Promise.all([this.picture(image), this.picture(depth), cutout ? this.picture(cutout).catch(() => null) : null]);
      if (token !== this.token || !this.gl) return false;
      this.upload(0, im);
      this.upload(1, dm);
      this.size = [im.naturalWidth || 1, im.naturalHeight || 1];
      this.focus = this.pivot(dm, cut);
      this.ready = true;
      this.wake();
      return true;
    },

    set(o) {
      if ("strength" in o) {
        this.strength = Math.max(0, Number(o.strength) || 0);
        if (!this.ready) this.s = this.strength;
      }
      if ("tier" in o) tierName = ["full", "reduced", "paused"].includes(o.tier) ? o.tier : "";
      if ("drift" in o) this.drift = typeof o.drift === "function" ? o.drift : () => !!o.drift;
      this.wake();
    },
    point(x, y) { this.tx = x; this.ty = y; this.wake(); },
    beat(k) { this.k = Math.max(this.k, Number(k) || 0); if (this.k > 0.01) this.wake(); },
    stop() {
      cancelAnimationFrame(this.raf);
      clearTimeout(this.timer);
      this.raf = this.timer = 0;
      this.token++;
      this.ready = false;
      if (this.canvas) this.canvas.hidden = true;
    },
    wake() {
      if (this.raf || !this.ready || tier() === "paused") return;
      clearTimeout(this.timer);
      this.timer = 0;
      this.raf = requestAnimationFrame((t) => this.frame(t));
    },

    frame(t) {
      this.raf = 0;
      if (!this.ready || !this.gl || tier() === "paused") return;
      const goal = this.away ? 0 : this.strength;
      this.s += (goal - this.s) * 0.12;
      if (Math.abs(goal - this.s) < 0.003) this.s = goal;
      const drifting = !this.away && this.strength > 0 && this.drift();
      this.x += (this.tx - this.x) * 0.1;
      this.y += (this.ty - this.y) * 0.1;
      this.k *= 0.88;
      let ox = this.x, oy = this.y;
      if (drifting) {
        const s = (t || 0) / 1000;
        ox += Math.sin(s * 0.21) * 0.55 + Math.sin(s * 0.047) * 0.25;
        oy += Math.cos(s * 0.17) * 0.35;
      }
      const settled = Math.abs(this.tx - this.x) < 0.002 && Math.abs(this.ty - this.y) < 0.002 && this.k < 0.01 && this.s === goal;
      this.draw(ox, oy, settled && drifting ? STEPS_DRIFT : STEPS_MOVING);
      if (!settled) this.raf = requestAnimationFrame((n) => this.frame(n));
      else if (drifting) {
        this.timer = setTimeout(() => {
          this.timer = 0;
          this.raf = requestAnimationFrame((n) => this.frame(n));
        }, 1000 / (tier() === "reduced" ? DRIFT_FPS / 2 : DRIFT_FPS) - 4);
      }
    },
    draw(ox, oy, steps = STEPS_MOVING) {
      const gl = this.gl, c = this.canvas, reduced = tier() === "reduced";
      // a share of the screen's pixels, never above 1920 across: the canvas
      // is stretched to the screen by its CSS size
      const scale = Math.min(reduced ? RES.reduced : RES.full, 1920 / Math.max(1, c.clientWidth));
      const w = Math.max(1, Math.round(c.clientWidth * scale)), h = Math.max(1, Math.round(c.clientHeight * scale));
      if (c.width !== w || c.height !== h) { c.width = w; c.height = h; }
      gl.viewport(0, 0, w, h);
      const shift = MAX_SHIFT * this.s * (1 + this.k * 0.8);
      // cover fit, then leave the margin the shift needs so no edge shows
      const [iw, ih] = this.size;
      const cover = Math.max(w / iw, h / ih);
      const margin = 1 - Math.min(0.3, shift * 2.2);
      const fx = (w / (iw * cover)) * margin, fy = (h / (ih * cover)) * margin;
      gl.uniform4f(this.u.fit, fx, fy, (1 - fx) / 2, (1 - fy) / 2);
      gl.uniform2f(this.u.off, -ox * shift, -oy * shift * (iw / ih));
      gl.uniform1f(this.u.focus, this.focus);
      gl.uniform1f(this.u.steps, reduced ? Math.min(steps, STEPS_REDUCED) : steps);
      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    },
  };
  if (typeof module === "object" && module.exports) module.exports = D;
  else root.ForgeDepth = D;
})(this);
