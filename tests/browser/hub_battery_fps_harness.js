// Appended to a copy of the REAL hub/index.html by run.sh. Emerson #199
// (2026-09-27): "i want forge to use less power somehow". On battery the
// frame cap drops to battery_fps; plugged in, max_fps applies again, and
// every open app hears the new cap.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  try {
    let sent = 0;
    window.sendTheme = () => { sent++; };
    const ws = document.querySelector(".workspace");
    ws.appendChild(document.createElement("iframe"));
    const frames = ws.querySelectorAll("iframe").length;
    const stats = (s) => window.forgeSetStats(Object.assign({ cpu: 5, mem: 40 }, s));
    applyTheme({ max_fps: 60, battery_fps: 30 });
    stats({ battery: 80, charging: true, plugged: true });
    T("plugged in, the cap is max_fps", ForgeFrameCap.fps === 60, ForgeFrameCap.fps);
    sent = 0; // applyTheme sends too
    stats({ battery: 80, charging: false, plugged: false });
    T("unplugged, the cap drops to battery_fps", ForgeFrameCap.fps === 30, ForgeFrameCap.fps);
    T("and open apps are sent it", sent === frames && appTheme().max_fps === 30, `${sent} sends to ${frames} frames, apps get ${appTheme().max_fps}`);
    stats({ battery: 79, charging: false, plugged: false });
    T("a stats tick with no change sends nothing", sent === frames, `${sent} sends`);
    stats({ battery: 79, charging: false, plugged: true });
    T("held at a charge limit but on the wall counts as plugged in", ForgeFrameCap.fps === 60 && sent === 2 * frames, ForgeFrameCap.fps);
    applyTheme({ max_fps: 20 });
    stats({ battery: 70, charging: false, plugged: false });
    T("a lower plugged-in cap still wins on battery", ForgeFrameCap.fps === 20, ForgeFrameCap.fps);
    applyTheme({ max_fps: 60, battery_fps: 45 });
    T("changing battery_fps applies at once", ForgeFrameCap.fps === 45, ForgeFrameCap.fps);
    stats({ battery: 70, charging: false });
    T("stats without a plugged reading fall back to charging", ForgeFrameCap.fps === 45, ForgeFrameCap.fps);
    stats({ battery: null, charging: null, plugged: null });
    T("a machine with no battery is never on battery", ForgeFrameCap.fps === 60, ForgeFrameCap.fps);

    // #225 Lighter effects: full by default, on battery, or always
    const lite = () => document.documentElement.classList.contains("forge-lite");
    const probe = document.body.appendChild(document.createElement("div"));
    probe.style.cssText = "animation: pulse 1s linear infinite; backdrop-filter: blur(8px)";
    applyTheme({ lite_effects: "full", animations: true });
    stats({ battery: 60, charging: false, plugged: false });
    T("Full keeps every effect on battery", !lite() && appTheme().lite === false
      && getComputedStyle(probe).animationIterationCount === "infinite",
      `${lite()} ${appTheme().lite} ${getComputedStyle(probe).animationIterationCount}`);
    applyTheme({ lite_effects: "battery" });
    T("On battery lightens while unplugged", lite() && appTheme().lite === true
      && getComputedStyle(probe).animationIterationCount === "1" && getComputedStyle(probe).backdropFilter === "none",
      getComputedStyle(probe).animationIterationCount + " " + getComputedStyle(probe).backdropFilter);
    sent = 0;
    stats({ battery: 60, charging: true, plugged: true });
    T("and goes back to full on the charger, telling the apps", !lite() && appTheme().lite === false && sent === frames);
    applyTheme({ lite_effects: "always" });
    T("Always lightens on the charger too", lite() && appTheme().lite === true);
    applyTheme({ lite_effects: "full" });
  } catch (e) {
    T("the checks ran", false, String(e && e.stack || e));
  }
  let pre = document.getElementById("results");
  if (!pre) { pre = document.createElement("pre"); pre.id = "results"; document.body.appendChild(pre); }
  pre.textContent = out.join("\n");
}, 400));
