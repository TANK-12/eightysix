// Appended to a copy of the REAL hub/index.html by run.sh, after
// window.TEST_PAIRS (forge_theme.POWER_PAIRS). Emerson 2026-09-27: "more lod
// and frame rate options on battery and off battery". Unplugged, every
// battery twin applies: the frame cap, fewer particles, and the values sent
// to forge.py for scrolling and the Browser's video.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const posted = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => posted.push(JSON.parse(m)) } } };
  const power = () => posted.filter((m) => m.power).map((m) => m.power);
  try {
    const stats = (s) => window.forgeSetStats(Object.assign({ cpu: 5, mem: 40, battery: 70 }, s));
    stats({ charging: true, plugged: true });
    applyTheme({
      power_pairs: TEST_PAIRS, max_fps: 60, battery_fps: 30, particle_amount: 2, battery_particles: 0.5,
      video_fps: 60, battery_video_fps: 30, video_height: "2160", battery_video_height: "720",
      smooth_scroll: true, battery_smooth_scroll: false,
    });
    let last = power().pop() || {};
    T("plugged in: full frame rate and particles", ForgeFrameCap.fps === 60 && Particles.look().particle_amount === 2,
      `${ForgeFrameCap.fps} ${Particles.look().particle_amount}`);
    T("forge.py hears the plugged-in values", last.video_fps === 60 && last.video_height === "2160" && last.smooth_scroll === true,
      JSON.stringify(last));
    stats({ charging: false, plugged: false });
    last = power().pop() || {};
    T("unplugged: the battery frame cap", ForgeFrameCap.fps === 30, ForgeFrameCap.fps);
    T("unplugged: half the particles", Particles.look().particle_amount === 1, Particles.look().particle_amount);
    T("forge.py hears the battery video and scrolling values",
      last.video_fps === 30 && last.video_height === "720" && last.smooth_scroll === false, JSON.stringify(last));
    T("apps are told they are on battery", appTheme().on_battery === true && appTheme().max_fps === 30);
    const count = power().length;
    stats({ battery: 69, charging: false, plugged: false });
    T("a stats tick with nothing new sends forge.py nothing", power().length === count, `${power().length} vs ${count}`);
    applyTheme({ battery_particles: 0 });
    T("0% on battery turns the particles off", Particles.look().particle_amount === 0, Particles.look().particle_amount);
    stats({ charging: true, plugged: true });
    last = power().pop() || {};
    T("back on the charger it all returns", ForgeFrameCap.fps === 60 && Particles.look().particle_amount === 2
      && last.smooth_scroll === true && appTheme().on_battery === false, JSON.stringify(last));
  } catch (e) {
    T("the checks ran", false, String(e && e.stack || e));
  }
  let pre = document.getElementById("results");
  if (!pre) { pre = document.createElement("pre"); pre.id = "results"; document.body.appendChild(pre); }
  pre.textContent = out.join("\n");
}, 500));
