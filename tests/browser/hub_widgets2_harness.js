// Appended to a copy of the REAL hub/index.html by run.sh. S25 (2026-09-28),
// Emerson: "actually make the widgets that never got made". Checks the new
// kinds (weather, media player, calendar, disk, network, Jan, alarms,
// visualiser), the ⚙ options with colour and look, and the store hook the
// desktop uses. The weather service is stubbed: this runs offline.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  document.head.appendChild(document.createElement("style")).textContent = "* { transition: none !important; }";
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const asked = [];
  // the weather card starts from the time zone's city; this pins the zone
  let fakeTz = "Etc/UTC";
  const realOptions = Intl.DateTimeFormat.prototype.resolvedOptions;
  Intl.DateTimeFormat.prototype.resolvedOptions = function () { return Object.assign(realOptions.call(this), { timeZone: fakeTz }); };
  window.fetch = async (url) => {
    asked.push(String(url));
    const body = /geocoding/.test(url)
      ? { results: [{ name: "Leeds", country_code: "GB", latitude: 53.8, longitude: -1.55 }] }
      : { current: { time: "2026-09-28T10:00", temperature_2m: 21.4, apparent_temperature: 20, relative_humidity_2m: 55, weather_code: 2, wind_speed_10m: 12, is_day: 1 },
          hourly: { time: Array.from({ length: 48 }, (_, i) => `2026-09-28T${String(i % 24).padStart(2, "0")}:00`), temperature_2m: Array(48).fill(18), weather_code: Array(48).fill(61) },
          daily: { time: ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03"], weather_code: [2, 3, 61, 0, 1, 95],
            temperature_2m_max: [22, 19, 17, 20, 21, 18], temperature_2m_min: [12, 11, 10, 9, 12, 11], precipitation_probability_max: [5, 20, 80, 0, 10, 60] } };
    return { ok: true, status: 200, json: async () => body };
  };
  try {
    const W = window.ForgeWidgets;
    const kinds = ["weather", "player", "calendar", "disk", "network", "jan", "alarms", "visualiser"];
    T("the planned widgets exist, one define() each", kinds.every((k) => W.KINDS[k]), Object.keys(W.KINDS).join(","));
    // a memory store in place of localStorage: the desktop's hook
    let stored = null;
    W.store = { load: () => stored, save: (d) => { stored = JSON.parse(JSON.stringify(d)); } };
    W.starterPages = () => [{ name: "Desk", items: [{ kind: "clock", x: 0, y: 0, w: 3, h: 2 }] }];
    W.load();
    T("an empty store starts from the page's own starter", W.pages.length === 1 && W.pages[0].name === "Desk", W.pages.map((p) => p.name).join());
    W.render();
    W.addPage();
    kinds.forEach((k) => W.add(k));
    T("adding saves through the store", stored && stored.pages[1].items.length === kinds.length, stored && stored.pages[1].items.length);
    const card = (k) => document.querySelector(`#widgets .wg-${k}`);
    const broken = kinds.filter((k) => !card(k) || /could not start/.test(card(k).textContent));
    T("every new widget draws", broken.length === 0, broken.join(","));

    // numbers from forge.py's stats (shared/forge_sysinfo.py)
    window.forgeSetStats({ cpu: 30, mem: 50, battery: 90, charging: true, plugged: true,
      net: { down: 1500000, up: 2300, ifaces: ["wlan0"], wifi: "meloncherry" },
      disks: [{ mount: "/", name: "System", used: 61, free_gb: 82.6, total_gb: 246.7 }, { mount: "/run/media/ejb/AN3", name: "AN3", used: 95, free_gb: 12, total_gb: 256 }],
      jan: { running: true, loaded: ["qwen3.5-4b"] } });
    W.tick();
    T("Disks lists each drive with its free space", /System/.test(card("disk").textContent) && /82.6 GB free/.test(card("disk").textContent) && /AN3/.test(card("disk").textContent), card("disk").textContent.slice(0, 90));
    T("a nearly full drive shows red", !!card("disk").querySelector(".wg-meter.hot"));
    T("Network shows the speeds and the Wi-Fi", /1\.5 MB\/s/.test(card("network").textContent) && /2 KB\/s/.test(card("network").textContent) && /meloncherry/.test(card("network").textContent), card("network").textContent);
    T("Jan shows it runs and what is loaded", /running/.test(card("jan").textContent) && /qwen3\.5-4b/.test(card("jan").textContent), card("jan").textContent);

    // weather: asks for a place when the time zone names no city, then shows it
    T("Weather asks where (time zone UTC)", !!card("weather").querySelector(".wg-ask"));
    const wItem = W.pages[1].items.find((i) => i.kind === "weather");
    const ask = card("weather").querySelector(".wg-ask");
    ask.value = "Leeds";
    ask.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    T("Enter keeps the place", wItem.o && wItem.o.place === "Leeds");
    W.tick(); await wait(50); W.tick();
    T("then shows the temperature and the place", /21°C/.test(card("weather").textContent) && /Leeds, GB/.test(card("weather").textContent), card("weather").textContent.slice(0, 90));
    W.setOpt(wItem, "show", "days");
    W.tick(); await wait(10); W.tick();
    T("Shows: next days adds five days", card("weather").querySelectorAll(".wg-wx-cell").length === 5, card("weather").querySelectorAll(".wg-wx-cell").length);
    applyTheme({ weather_units: "f" });
    W.tick(); await wait(50); W.tick();
    T("Fahrenheit asks the service in Fahrenheit", asked.some((u) => /temperature_unit=fahrenheit/.test(u)) && /°F/.test(card("weather").textContent), card("weather").textContent.slice(0, 40));
    applyTheme({ weather_units: "c" });
    // S26: in Perth's time zone a new card shows Perth's weather straight away
    fakeTz = "Australia/Perth";
    const tzItem = W.add("weather");
    W.render(); W.tick(); await wait(50); W.tick();
    const tzCard = [...document.querySelectorAll("#widgets .wg-weather")].pop();
    T("a new Weather card starts from the time zone's city", !tzCard.querySelector(".wg-ask") && asked.some((u) => /geocoding.*name=Perth/.test(u))
      && /from the time zone/.test(tzCard.textContent), tzCard.textContent.slice(0, 80));
    W.remove(tzItem.id);
    fakeTz = "Etc/UTC";
    // S26: an added card takes the first gap, not the bottom of one column
    const back = W.page;
    W.addPage();
    const a = W.add("clock"), b = W.add("clock");
    T("Add fills the first gap that fits", a.x === 0 && a.y === 0 && b.x === a.w && b.y === 0, JSON.stringify([a, b]));
    W.removePage();
    W.go(back);

    // the media player
    NowPlaying.sysIn([{ bus: "org.mpris.MediaPlayer2.qbz", title: "Player song", artist: "A band", state: "playing", canNext: true, canPrev: true, current: 30, duration: 200, volume: 0.5 }]);
    W.tick();
    const seek = card("player").querySelector(".wg-seek input");
    T("Media player shows the song, a seek bar and the volume", /Player song/.test(card("player").textContent) && Number(seek.max) === 200
      && Number(card("player").querySelector(".wg-vol input").value) === 50, `${seek.max} ${card("player").querySelector(".wg-vol input").value}`);
    sent.length = 0;
    seek.value = 120; seek.dispatchEvent(new Event("change"));
    T("dragging the seek bar seeks the player", sent.some((m) => m.media && m.media.op === "seek" && m.media.value === 120), JSON.stringify(sent));
    card("player").querySelector('[title="Next"]').click();
    T("and Next goes to it", sent.some((m) => m.media && m.media.op === "next"));

    // calendar
    const cal = card("calendar"), cItem = W.pages[1].items.find((i) => i.kind === "calendar");
    T("Calendar shows this month with today marked", cal.querySelector(".wg-cal-day.today") && new RegExp(new Date().toLocaleDateString([], { month: "long" })).test(cal.textContent));
    const day = [...cal.querySelectorAll(".wg-cal-day")].find((b) => b.textContent === "3");
    day.click();
    const note = card("calendar").querySelector(".wg-ask");
    note.value = "Dentist"; note.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    T("a day gets a note, kept with the widget", Object.values(cItem.o.marks || {}).includes("Dentist") && !!card("calendar").querySelector(".wg-cal-day.marked"));

    // alarms and timers
    const aItem = W.pages[1].items.find((i) => i.kind === "alarms");
    W.Alarms.timer(aItem, 1);
    T("a timer shows its countdown", /0:5\d|1:00/.test(card("alarms").textContent), card("alarms").textContent.slice(0, 60));
    W.Alarms.check(new Date(Date.now() + 61000));
    T("when it runs out it rings", document.getElementById("wg-ring") && document.getElementById("wg-ring").classList.contains("on"));
    T("and the hub puts a note on screen, seen from inside apps too", /⏰/.test($("toast-text").textContent) && !$("toast").hidden, $("toast-text").textContent);
    T("the timer is gone once it rang", (W.opt(aItem, "timers") || []).length === 0);
    document.querySelector("#wg-ring .wg-btn.primary").click();
    T("Stop stops it", !document.getElementById("wg-ring").classList.contains("on"));
    const now = new Date(), hm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    const f = card("alarms").querySelector("form");
    f.querySelector('input[type="time"]').value = hm;
    f.querySelector('input[type="text"], input:not([type])').value = "Stretch";
    f.dispatchEvent(new Event("submit", { cancelable: true }));
    T("an alarm is added", (W.opt(aItem, "alarms") || []).some((a) => a.t === hm && a.label === "Stretch"));
    W.Alarms.check(now);
    T("it rings at its minute", document.getElementById("wg-ring").classList.contains("on") && /Stretch/.test(document.getElementById("wg-ring").textContent));
    W.Ring.stop();
    W.Alarms.check(now);
    T("only once that day", !document.getElementById("wg-ring").classList.contains("on"));

    // the visualiser card asks the hub's visualiser for levels
    Visual.demandAt = 0;
    await wait(200);
    T("the Visualiser card asks for levels while it shows", Visual.demanded(), Visual.style);
    T("it draws on its own canvas", !!card("visualiser").querySelector("canvas.wg-vis"));

    // ⚙ options: colour, look, what it shows
    W.edit(true);
    const cfg = card("disk").querySelector(".wg-cfg");
    T("each card has a ⚙ in edit mode", !!cfg);
    cfg.click();
    const opts = card("disk").querySelector(".wg-opts");
    T("⚙ opens its options: colour, look and its own", !!opts && opts.querySelectorAll(".wg-opt").length === 3, opts && opts.querySelectorAll(".wg-opt").length);
    const sel = [...opts.querySelectorAll("select")].find((x) => [...x.options].some((o) => o.value === "system"));
    sel.value = "system"; sel.dispatchEvent(new Event("change"));
    const dItem = W.pages[1].items.find((i) => i.kind === "disk");
    W.setOpt(dItem, "colour", "#ff66aa", true);
    W.setOpt(dItem, "look", "clear");
    W.edit(false);
    window.forgeSetStats(window.forgeLastStats);
    W.tick();
    T("Shows: only the system drive", !/AN3/.test(card("disk").textContent) && /System/.test(card("disk").textContent), card("disk").textContent.slice(0, 60));
    T("its own colour", card("disk").style.getPropertyValue("--accent") === "#ff66aa", card("disk").style.getPropertyValue("--accent"));
    T("see-through look", card("disk").dataset.look === "clear" && getComputedStyle(card("disk")).backgroundColor === "rgba(0, 0, 0, 0)", getComputedStyle(card("disk")).backgroundColor);
    const sItem = W.pages[1].items.find((i) => i.kind === "system");
    T("options survive a reload from the store", (() => { W.load(); return W.opt(W.pages[1].items.find((i) => i.kind === "disk"), "look") === "clear"; })());

    // notes keep their text in the layout now
    W.add("notes");
    const area = [...document.querySelectorAll("#widgets .wg-notes textarea")].pop();
    area.value = "milk"; area.dispatchEvent(new Event("input"));
    await wait(500);
    T("Notes save into the layout (so the desktop keeps its own)", JSON.stringify(stored).includes('"text":"milk"'));
  } catch (e) {
    T("the checks ran without an error", false, e && (e.message + " " + (e.stack || "").split("\n")[1]));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 600));
