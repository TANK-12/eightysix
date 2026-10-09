// Appended to a copy of the REAL desktop/particles.html by run.sh. S18
// (2026-09-27), Emerson: "the extension for the particles in desktop should
// also have settings". Settings > Desktop particles sits over the home
// screen's settings: its own kind ("same" follows the home screen), amount
// and frame rate, with the Speed page's cap still on top.
addEventListener("load", () => setTimeout(() => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  try {
    // this copy's hub/theme.js: home snow at 2x, desktop "same" at 0.5x, 20 fps
    T("'Same as the home screen' shows the home screen's kind", Particles.look().particles === "snow", Particles.look().particles);
    T("the desktop's own amount, not the home screen's", Particles.look().particle_amount === 0.5, Particles.look().particle_amount);
    T("fewer dots at the lower amount", Particles.dots.length === Math.round(Particles.KINDS.snow.count * 0.5),
      `${Particles.dots.length} vs ${Particles.KINDS.snow.count}`);
    T("its own frame rate", ForgeFrameCap.fps === 20, ForgeFrameCap.fps);
    window.forgeTheme(Object.assign({}, window.FORGE_THEME, { desktop_particle_kind: "rain", max_fps: 10, desktop_particle_fps: 30 }));
    T("a kind of its own", Particles.look().particles === "rain", Particles.look().particles);
    T("the Speed page's lower cap wins", ForgeFrameCap.fps === 10, ForgeFrameCap.fps);
    window.forgeTheme({ particles: "soft", desktop_particles: true });
    T("with no desktop settings saved yet: home kind and amount, 30 fps",
      Particles.look().particles === "soft" && ForgeFrameCap.fps === 30, `${Particles.look().particles} ${ForgeFrameCap.fps}`);
    // S21: a wallpaper's own pick, only an Off setting stops them, new kinds
    window.forgeTheme({ particles: "auto", ambience: "snow", wallpaper_particles: "lanterns", desktop_particles: true });
    T("a wallpaper's own pick beats Match the wallpaper", Particles.level === "lanterns", Particles.level);
    window.forgeTheme({ particles: "rain", wallpaper_particles: "glitter", desktop_particles: true });
    T("and beats a set kind", Particles.level === "glitter", Particles.level);
    window.forgeTheme({ particles: "off", wallpaper_particles: "glitter", desktop_particles: true });
    T("the Off setting still turns them all off", Particles.level === "off", Particles.level);
    window.forgeTheme({ particles: "auto", ambience: "snow", wallpaper_particles: "off", desktop_particles: true });
    T("a wallpaper set to Off has none", Particles.level === "off", Particles.level);
    window.forgeTheme({ particles: "auto", ambience: "snow", wallpaper_particles: "", desktop_particles: true });
    T("no pick: Match the wallpaper", Particles.level === "snow", Particles.level);
    for (const kind of ["glitter", "lanterns"]) {
      window.forgeTheme({ particles: kind, wall_light: 0.2, desktop_particles: true });
      const c = Particles.ctx;
      c.clearRect(0, 0, innerWidth, innerHeight);
      Particles.drawn = 0;
      for (let f = 0; f < 3; f++) Particles[Particles.KINDS[kind].draw](c, f * 16, innerWidth, innerHeight, { x: -1, y: -1 }, "#8ab4ff");
      const px = c.getImageData(0, 0, innerWidth, innerHeight).data;
      let on = 0;
      for (let i = 3; i < px.length; i += 4 * 31) if (px[i] > 0) on++;
      T(`${kind} draws`, Particles.dots.length > 0 && on > 20, `${Particles.dots.length} dots, ${on} lit`);
    }
    window.forgeTheme({ particles: "soft", wall_light: 0.8, desktop_particles: true });
    const cb = Particles.ctx;
    Particles.blend(cb);
    T("on a bright picture the glows are painted over it, not added", Particles.bright && cb.globalCompositeOperation === "source-over", cb.globalCompositeOperation);
    window.forgeTheme({ particles: "soft", wall_light: 0.3, desktop_particles: true });
    Particles.blend(cb);
    T("on a dark one they add light", !Particles.bright && cb.globalCompositeOperation === "lighter", cb.globalCompositeOperation);
    Particles.dots.forEach((d) => { d.vx = 1; d.vy = 0; d.x = 100; });
    Particles.kick(1);
    Particles.frame(performance.now() + 5000);
    T("a beat's kick moves every particle further", Particles.surge > 0.5 && Particles.surge < 1 && Particles.dots[0].x > 103, `${Particles.surge} ${Particles.dots[0].x}`);
    // #199: particles.py adds on_battery; the battery cap then applies too
    window.forgeTheme({ desktop_particles: true, desktop_particle_fps: 30, battery_fps: 12, on_battery: true });
    T("on battery the battery cap applies", ForgeFrameCap.fps === 12, ForgeFrameCap.fps);
    window.forgeTheme({ desktop_particles: true, desktop_particle_fps: 30, battery_fps: 12, on_battery: false });
    T("plugged in it does not", ForgeFrameCap.fps === 30, ForgeFrameCap.fps);
  } catch (e) {
    T("the checks ran without an error", false, e && e.stack);
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 300));
