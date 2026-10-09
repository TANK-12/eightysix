/* Settings > Speed and detail for the Browser app's real web pages. forge.py
   injects this, after shared/forge_framecap.js, at the start of every page and
   frame (forge_views.power_script), and calls ForgeWebCap.set() again when the
   values change or the charger is plugged in or pulled out.

   - max_fps: the frame-rate cap, through ForgeFrameCap, as in Forge's apps.
   - video_fps, video_height: a site asks the browser which video formats it
     can play (MediaSource.isTypeSupported, canPlayType) before it picks one;
     YouTube names each format's size and frame rate in that question. Formats
     above the caps are answered "no", so the player takes a lighter one (the
     approach of the h264ify extensions). A question with no size or rate in it
     is left alone. It applies from the next video the page loads. */
(() => {
  if (window.ForgeWebCap) return;
  const caps = { fps: 60, height: 2160 };
  const grab = (type, name) => {
    const m = new RegExp(`${name}\\s*=\\s*"?(\\d+(?:\\.\\d+)?)`).exec(type);
    return m ? Number(m[1]) : null;
  };
  // 29.97 passes a 30 cap and 59.94 does not.
  function allowed(type) {
    const t = String(type || "");
    const fps = grab(t, "framerate");
    if (fps !== null && fps > caps.fps + 0.5) return false;
    const w = grab(t, "width"), h = grab(t, "height");
    const side = w !== null && h !== null ? Math.min(w, h) : h;
    return !(side !== null && side > caps.height);
  }
  ["MediaSource", "ManagedMediaSource", "WebKitMediaSource"].forEach((name) => {
    const MS = window[name];
    if (!MS || typeof MS.isTypeSupported !== "function") return;
    const real = MS.isTypeSupported.bind(MS);
    MS.isTypeSupported = (type) => allowed(type) && real(type);
  });
  const proto = typeof HTMLMediaElement === "function" && HTMLMediaElement.prototype;
  if (proto && typeof proto.canPlayType === "function") {
    const real = proto.canPlayType;
    proto.canPlayType = function (type) { return allowed(type) ? real.call(this, type) : ""; };
  }
  window.ForgeWebCap = {
    allowed,
    set(v) {
      v = v || {};
      caps.fps = Number(v.video_fps) || 60;
      caps.height = Number(v.video_height) || 2160;
      if (window.ForgeFrameCap) window.ForgeFrameCap.set(v.max_fps);
    },
  };
})();
