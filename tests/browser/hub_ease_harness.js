// Appended to a copy of the REAL hub/index.html by run.sh (2026-09-29).
// Easing off for GPU load and a flat battery, Alt+V at full rate, the Alt+V
// keys surviving a stray focus, the visuals popup surviving a dropdown, and
// the real-depth 2.5D renderer (shared/forge_depth.js).
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  document.head.appendChild(document.createElement("style")).textContent = "* { transition: none !important; }";
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  const press = (key, opts = {}) => {
    const e = new KeyboardEvent("keydown", Object.assign({ key, bubbles: true, cancelable: true }, opts));
    (document.activeElement || document.body).dispatchEvent(e);
    return e;
  };
  const stats = (o) => window.forgeSetStats(Object.assign({ cpu: 5, mem: 30, plugged: true, battery: 80, charging: true }, o));
  try {
    const rows = await (await fetch("fx_rows.json")).json();
    applyTheme({ visuals_popup: rows, animations: true, visualiser: "bars", ambient_visualiser: "keep", particles: "snow",
      visualiser_shown: true, particles_shown: true, visualiser_source: "system", fx_hud: true, gpu_ease: true, gpu_ease_note: true,
      max_fps: 60, particle_fps: 30, particle_amount: 1, battery_fps: 30, battery_particle_fps: 20, battery_particles: 0.5,
      battery_visualiser: false, battery_saver: 20, pulse_full_fps: true,
      power_pairs: { max_fps: ["battery_fps", "min"], particle_fps: ["battery_particle_fps", "min"], particle_amount: ["battery_particles", "scale"] } });
    stats({ gpu: { level: 0, by: "" } });
    T("to start: visualiser on, no cap", Visual.style === "bars" && ForgeFrameCap.fps === 60, `${Visual.style} ${ForgeFrameCap.fps}`);

    // --- the GPU ladder
    stats({ gpu: { level: 1, by: "Blender" } });
    T("level 1: the visualiser goes off", Visual.style === "off", Visual.style);
    T("and says why at the top", /Blender uses the GPU: visualiser off/.test($("fx-hud").textContent), $("fx-hud").textContent);
    T("the particles stay whole at level 1", powerTheme.particle_amount === 1 && Particles.level === "snow");
    stats({ gpu: { level: 2, by: "Blender" } });
    T("level 2: half the particles", powerTheme.particle_amount === 0.5, String(powerTheme.particle_amount));
    stats({ gpu: { level: 3, by: "Blender" } });
    T("level 3: everything at 25 fps", ForgeFrameCap.fps === 25 && powerTheme.particle_fps === 25, `${ForgeFrameCap.fps} ${powerTheme.particle_fps}`);

    // --- Alt+V: full rate whatever the load
    window.forgeKey("pulse");
    T("Alt+V runs at the screen's rate under load", ForgeFrameCap.fps === 60 && powerTheme.particle_fps === 60, `${ForgeFrameCap.fps} ${powerTheme.particle_fps}`);
    T("Alt+V shows the whole key list, wrapped", $("fx-hud").classList.contains("long") && /beat effects/.test($("fx-hud").textContent));

    // --- the keys survive a stray focus
    $("search").focus();
    T("(the search box holds the focus)", document.activeElement === $("search"));
    const before = theme.visualiser;
    press("ArrowRight");
    T("an arrow still changes the visualiser with the search box focused", theme.visualiser !== before, `${before} -> ${theme.visualiser}`);
    T("and the search box let go", document.activeElement !== $("search"));
    press("x");
    T("a key Alt+V does not use does not send the focus to the search box", document.activeElement !== $("search"));
    const again = theme.visualiser;
    press("ArrowRight");
    T("the arrows keep working after it", theme.visualiser !== again, `${again} -> ${theme.visualiser}`);
    const effect = Fx.effects()[0].key, was = Fx.value(effect);
    press("1");
    T("and the numbers", Fx.value(effect) !== was, `${effect}: ${was} -> ${Fx.value(effect)}`);
    press("h");
    T("H brings the key list back", $("fx-hud").classList.contains("show") && $("fx-hud").classList.contains("long"));

    // --- Alt+M's popup
    window.forgeKey("visualiser-toggle");
    await wait(50);
    T("Alt+M opens the visuals popup", Popup.isOpen($("fx-panel")));
    const sel = $("fx-list").querySelector("select");
    sel.focus();
    dispatchEvent(new Event("blur"));
    await wait(250);
    T("a dropdown opening (the window loses focus) keeps the popup open", Popup.isOpen($("fx-panel")));
    window.forgeKey("visualiser-toggle");
    await wait(250);
    T("Alt+M again closes it", !Popup.isOpen($("fx-panel")));
    T("and the focus left the closed popup", !$("fx-panel").contains(document.activeElement));
    const third = theme.visualiser;
    press("ArrowLeft");
    T("the arrows work after the popup", theme.visualiser !== third, `${third} -> ${theme.visualiser}`);
    dispatchEvent(new Event("blur"));
    window.forgeKey("pulse");
    T("leaving Alt+V goes back to the eased 25 fps", ForgeFrameCap.fps === 25, String(ForgeFrameCap.fps));
    window.forgeKey("ambient");

    // --- back down, the switch, the battery
    stats({ gpu: { level: 0, by: "" } });
    T("load gone: all back", ForgeFrameCap.fps === 60 && powerTheme.particle_amount === 1, `${ForgeFrameCap.fps}`);
    applyTheme({ gpu_ease: false });
    stats({ gpu: { level: 3, by: "Jan" } });
    T("Ease off switched off: no change under load", ForgeFrameCap.fps === 60, String(ForgeFrameCap.fps));
    applyTheme({ gpu_ease: true });
    stats({ gpu: { level: 0 }, plugged: false, charging: false, battery: 80 });
    T("unplugged: 30 fps, particles 20 fps and half, no visualiser",
      ForgeFrameCap.fps === 30 && powerTheme.particle_fps === 20 && powerTheme.particle_amount === 0.5 && Visual.style === "off",
      `${ForgeFrameCap.fps} ${powerTheme.particle_fps} ${powerTheme.particle_amount} ${Visual.style}`);
    stats({ gpu: { level: 0 }, plugged: false, charging: false, battery: 12 });
    T("under the low-battery mark: 25 fps", ForgeFrameCap.fps === 25, String(ForgeFrameCap.fps));
    stats({ gpu: { level: 0 }, plugged: true, battery: 80 });

    // --- real depth
    const pic = (draw) => { const c = document.createElement("canvas"); c.width = 64; c.height = 36; draw(c.getContext("2d")); return c.toDataURL("image/png"); };
    const image = pic((x) => { for (let i = 0; i < 64; i += 8) { x.fillStyle = i % 16 ? "#e04" : "#04e"; x.fillRect(i, 0, 8, 36); } });
    const depth = pic((x) => { const g = x.createLinearGradient(0, 0, 64, 0); g.addColorStop(0, "#000"); g.addColorStop(1, "#fff"); x.fillStyle = g; x.fillRect(0, 0, 64, 36); });
    applyTheme({ wall_3d: true, wall_3d_mode: "depth", wall_3d_depth: 3, wall_3d_drift: false, wallpaper: image, wallpaper_depth: depth, wallpaper_fg: "", wallpaper_bg: "" });
    await wait(400);
    if (!ForgeDepth.gl) {
      T("no WebGL here: 2.5D keeps the two-layer look", !document.body.classList.contains("wall-depth"));
    } else {
      T("real depth is drawing", Depth3D.on && ForgeDepth.ready && document.body.classList.contains("wall-depth"));
      // The whole middle row: a 16 px strip sits inside one wide stripe of
      // the test picture, so a real shift could leave it unchanged.
      const gl = ForgeDepth.gl, w = ForgeDepth.canvas.width, px = new Uint8Array(4 * w);
      const row = (ox) => { ForgeDepth.draw(ox, 0); gl.readPixels(0, Math.floor(ForgeDepth.canvas.height / 2), w, 1, gl.RGBA, gl.UNSIGNED_BYTE, px); return Array.from(px).join(","); };
      const a = row(0), b = row(1);
      T("moving the view bends the picture", a !== b, `${a.slice(0, 40)} | ${b.slice(0, 40)} | ${ForgeDepth.canvas.width}x${ForgeDepth.canvas.height} err ${gl.getError()}`);
      applyTheme({ wall_3d_mode: "layers" });
      T("Two layers turns the renderer off", !Depth3D.on && !document.body.classList.contains("wall-depth"));
    }
  } catch (err) {
    T("harness ran without throwing", false, String(err && err.stack || err));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = out.join("\n");
  document.body.appendChild(pre);
}, 300));
