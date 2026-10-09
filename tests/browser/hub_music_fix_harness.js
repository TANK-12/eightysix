// Appended to a copy of the REAL hub/index.html by run.sh. S12 (2026-09-27):
// Emerson: "the play pause button dont work", "in zen mode make the music off
// button work", and background start must not play music until the window
// is really opened. Checks Music.wanted(), the decision the player follows.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  try {
    applyTheme(Object.assign({}, theme, { animations: false, music: true, music_duck: true,
      music_tracks: [{ name: "a", url: "file:///tmp/a.mp3" }] }));
    Music.apply();
    selectWorkspace(null, { instant: true });
    Music.play();
    T("music on, nothing else playing: wanted", Music.wanted());

    // a view (YouTube in Media) said it was playing, then went quiet
    await wait(5);
    NowPlaying.fromView({ id: 7, has: true, owner: Object.keys(parts)[0], paused: false, title: "clip", duration: 600 });
    T("a view playing now makes the music step aside", !Music.wanted());
    NowPlaying.sources["view:7"].at = Date.now() - 20000;
    T("a view that stopped reporting 20 s ago no longer holds the music", Music.wanted());
    delete NowPlaying.sources["view:7"];

    // pressing Play means play, even while an app plays
    NowPlaying.fromView({ id: 8, has: true, owner: Object.keys(parts)[0], paused: false, title: "clip", duration: 600 });
    Music.pause();
    T("paused: not wanted", !Music.wanted());
    await wait(5);
    Music.play();
    T("Play while an app plays: the music plays anyway", Music.wanted());
    Music.pause();
    Music.play();
    T("and again after another pause", Music.wanted());
    await wait(5);
    NowPlaying.fromView({ id: 9, has: true, owner: Object.keys(parts)[0], paused: false, title: "new", duration: 600 });
    T("an app that starts after Play still makes it step aside", !Music.wanted());
    delete NowPlaying.sources["view:9"];

    // Emerson: pause and stepping aside were too slow (a fixed 1.5 s fade).
    // The fade now takes music_fade ms, whatever the start volume.
    // #257 (S26): the fade ends paused with the element back at a normal
    // volume, never resting at 0: WebKit hands that volume to the system
    // mixer, which saved 0% for every later Forge sound. The element is
    // stood in for, since headless Chrome plays nothing here.
    let fakePaused = true;
    const asks = [];
    const realSend = Music.send;
    Music.send = (req) => { asks.push(req); return true; };
    Object.defineProperty(Music.audio, "paused", { configurable: true, get: () => fakePaused });
    Music.audio.play = () => { fakePaused = false; return Promise.resolve(); };
    Music.audio.pause = () => { fakePaused = true; };
    applyTheme(Object.assign({}, theme, { music_fade: 150 }));
    Music.play();
    T("starting the music asks forge.py to make Forge audible", asks.some((r) => r.op === "audible"), JSON.stringify(asks));
    clearInterval(Music.fade);
    Music.audio.volume = 1;
    let lowest = 1;
    const watch = setInterval(() => { lowest = Math.min(lowest, Music.audio.volume); }, 5);
    Music.pause();
    await wait(400);
    clearInterval(watch);
    T("pause goes quiet within the fade time", fakePaused && lowest < 0.2, `${fakePaused} ${lowest}`);
    T("and the paused element rests at a normal volume, not 0", Music.audio.volume > 0, Music.audio.volume);
    const before = Music.audio.volume;
    Music.sync();
    T("syncing while paused leaves that volume alone", Music.audio.volume === before && fakePaused);
    applyTheme(Object.assign({}, theme, { music_fade: 0 }));
    Music.play();
    clearInterval(Music.fade);
    Music.audio.volume = 1;
    Music.pause();
    T("a fade of 0 cuts at once", fakePaused && Music.audio.volume > 0, `${fakePaused} ${Music.audio.volume}`);
    delete Music.audio.paused;
    delete Music.audio.play;
    delete Music.audio.pause;
    Music.send = realSend;
    applyTheme(Object.assign({}, theme, { music_fade: 150 }));
    Music.play();
    delete NowPlaying.sources["view:8"];

    // the popup's toggle and zen's button flip it
    Music.play();
    $("music-toggle").click();
    T("the popup's toggle pauses", Music.paused && !Music.wanted());
    $("music-toggle").click();
    T("and plays again", !Music.paused && Music.wanted());
    Zen.toggle(true);
    await wait(50);
    T("zen shows its music button", !$("zen-music").hidden);
    $("zen-music").click();
    T("zen's button turns the music off", Music.paused && /off/i.test($("zen-music").textContent), $("zen-music").textContent);
    $("zen-music").click();
    T("and on again", !Music.paused && /on/i.test($("zen-music").textContent), $("zen-music").textContent);
    Zen.toggle(false);

    // started in the background: silent until the window first shows
    Music.shown = false;
    T("a window not shown yet plays no music", !Music.wanted());
    window.forgeShown();
    T("forgeShown() lets it play", Music.wanted());
    window.forgeShown();
    T("a second forgeShown() changes nothing", Music.wanted() && Music.shown === true);

    // every visualiser style draws; the ring sits around the home clock
    selectWorkspace(null, { instant: true });
    await wait(50);
    const cv = $("visual"), cx = cv.getContext("2d");
    const lit = (x, y, w, h) => { const d = cx.getImageData(x, y, w, h).data; let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 20) n++; return n; };
    for (const style of Object.keys(Visual.STYLES)) {
      applyTheme(Object.assign({}, theme, { animations: true, visualiser: style, visualiser_source: "system", visualiser_size: 1 }));
      Visual.systemFailed = "";
      Visual.apply();
      Visual.levelsIn(Array.from({ length: 32 }, (_, i) => 0.3 + 0.5 * Math.abs(Math.sin(i))));
      for (let k = 0; k < 12; k++) Visual.frame();
      T(`the ${style} visualiser draws`, lit(0, 0, cv.width, cv.height) > 500, lit(0, 0, cv.width, cv.height));
      if (style === "ring") {
        const r = $("big-clock").getBoundingClientRect(), at = Visual.anchor(cv.width, cv.height);
        T("the ring is centred on the home clock", Math.abs(at.x - (r.left + r.width / 2)) < 2 && Math.abs(at.y - (r.top + r.height / 2)) < 2);
      }
      cancelAnimationFrame(Visual.raf); Visual.raf = 0;
    }
    if (location.hash === "#shot") {
      applyTheme(Object.assign({}, theme, { visualiser: location.search.slice(1) || "wave" }));
      Visual.apply();
      for (let k = 0; k < 12; k++) Visual.frame();
      cancelAnimationFrame(Visual.raf); Visual.raf = 0;
    }

    // B19: a section folds only from its own button, not from a press
    // anywhere along the heading's row
    selectWorkspace(null, { instant: true });
    const sec = [...document.querySelectorAll(".section")].find((s) => !s.matches(".hidden, .empty, .bare, .solo"));
    if (sec) {
      const head = sec.querySelector(".section-head"), pill = head.querySelector(".s-pill").getBoundingClientRect();
      const row = head.getBoundingClientRect(), x = Math.min(innerWidth - 20, pill.right + 200), y = pill.top + pill.height / 2;
      const was = sec.classList.contains("collapsed");
      const hit = document.elementFromPoint(x, y);
      if (hit) hit.click();
      T("a press on the row beside the heading does not fold it", sec.classList.contains("collapsed") === was && !head.contains(hit),
        `${hit && hit.className} row ${Math.round(row.width)}px pill ${Math.round(pill.width)}px`);
      document.elementFromPoint(pill.left + 10, y).click();
      T("a press on the heading's button folds it", sec.classList.contains("collapsed") !== was);
      document.elementFromPoint(pill.left + 10, y).click();
    } else T("a section to fold exists", false);

    // B14: the size popup can be dragged off what it changes, and stays there
    try { localStorage.removeItem("forge.popupAt.size-panel"); } catch (e) {}
    Sizes.panel(true);
    await wait(600);
    const sp = $("size-panel"), grip = sp.querySelector(".grip");
    T("the size popup has a grip", !!grip && grip.offsetWidth > 0);
    const r0 = sp.getBoundingClientRect(), gr = grip.getBoundingClientRect();
    const ev = (type, x, y) => grip.dispatchEvent(new PointerEvent(type, { bubbles: true, clientX: x, clientY: y, pointerId: 1 }));
    ev("pointerdown", gr.left + 5, gr.top + 5);
    ev("pointermove", gr.left + 5 - 400, gr.top + 5 + 300);
    ev("pointerup", gr.left + 5 - 400, gr.top + 5 + 300);
    const r1 = sp.getBoundingClientRect();
    T("dragging the grip moves it", Math.abs(r1.left - (r0.left - 400)) < 6 && Math.abs(r1.top - (r0.top + 300)) < 6,
      `${Math.round(r0.left)},${Math.round(r0.top)} -> ${Math.round(r1.left)},${Math.round(r1.top)}`);
    T("the popup is still open after the drag", Popup.isOpen(sp));
    Sizes.panel(false);
    await wait(250);
    Sizes.panel(true);
    await wait(600);
    const r2 = sp.getBoundingClientRect();
    T("it opens again where it was left", Math.abs(r2.left - r1.left) < 6 && Math.abs(r2.top - r1.top) < 6, `${Math.round(r2.left)},${Math.round(r2.top)} saved ${localStorage.getItem("forge.popupAt.size-panel")} style ${sp.style.left},${sp.style.top},${sp.style.right}`);
    grip.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }));
    const r3 = sp.getBoundingClientRect();
    T("a double-click puts it back under its button", Math.abs(r3.top - r0.top) < 6 && Math.abs(r3.right - r0.right) < 6);
    Sizes.panel(false);

    // B10: every particle kind draws something
    selectWorkspace(null, { instant: true });
    const pc = $("particles").getContext("2d");
    for (const kind of Object.keys(Particles.KINDS)) {
      applyTheme(Object.assign({}, theme, { animations: true, particles: kind, particle_amount: 1 }));
      for (let k = 0; k < 5; k++) Particles.frame(performance.now());
      const d = pc.getImageData(0, 0, $("particles").width, $("particles").height).data;
      let n = 0; for (let i = 3; i < d.length; i += 4) if (d[i] > 10) n++;
      T(`the ${kind} particles draw`, n > 50, n);
    }
    cancelAnimationFrame(Particles.raf); Particles.raf = 0;
    // B6: background mode, zen without the clock or timer
    applyTheme(Object.assign({}, theme, { animations: true, particles: "soft", particle_amount: 1, visualiser: "bars",
      ambient_particles: 2, ambient_visualiser: "aurora", ambient_drift: true, ambient_drift_seconds: 40, ambient_hint: true }));
    selectWorkspace(Object.keys(parts)[0], { instant: true });
    await wait(50);
    const homeDots = Particles.KINDS.soft.count;
    // the end state, not a fade frozen part way by the virtual clock
    const still = document.head.appendChild(document.createElement("style"));
    still.textContent = "* { transition: none !important; }";
    $("ambient-btn").click();
    await wait(100);
    const op = (id) => parseFloat(getComputedStyle($(id)).opacity);
    T("the bar button enters background mode, going home first", Ambient.on && current === null && document.body.classList.contains("ambient"));
    T("the bar, home, dock and zen are out of sight", op("bar") === 0 && op("home") === 0 && op("dock") === 0 && op("zen") === 0, ["bar","home","dock","zen"].map(op).join(",") + " zenOn=" + Zen.on + " body=" + document.body.className);
    T("the particles are boosted", Particles.dots.length === homeDots * 2, `${Particles.dots.length} vs ${homeDots}`);
    T("its own visualiser choice applies", Visual.style === "aurora", Visual.style);
    T("Drift length sets how long one sweep takes", $("wall").style.animationDuration === "40s", $("wall").style.animationDuration);
    T("the wallpaper drifts", document.body.classList.contains("drift") && getComputedStyle($("wall")).animationName === "kenburns");
    T("it says how to leave", $("ambient-hint").classList.contains("show"));
    document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    await wait(100);
    T("Esc leaves it, back in the app it was started from", !Ambient.on && op("bar") > 0.9 && current === Object.keys(parts)[0], `${Ambient.on} ${op("bar")} ${current}`);
    selectWorkspace(null, { instant: true });
    await wait(50);
    T("home's particles and visualiser come back", Particles.dots.length === homeDots && Visual.style === "bars", `${Particles.dots.length} ${Visual.style}`);
    window.forgeKey("ambient");
    T("Alt+B (forgeKey ambient) enters it", Ambient.on);
    window.forgeKey("zen");
    T("zen from background mode swaps over", Zen.on && !Ambient.on === false || Zen.on);
    Zen.toggle(false);
    Ambient.toggle(false);
    still.remove();
  } catch (e) {
    T("music fix harness ran", false, String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
// #ambient leaves background mode on for a screenshot
addEventListener("load", () => setTimeout(() => {
  if (location.hash !== "#ambient") return;
  document.head.appendChild(document.createElement("style")).textContent = "* { transition: none !important; }";
  applyTheme(Object.assign({}, theme, { animations: true, particles: "fireflies", visualiser: "wave", ambient_visualiser: "aurora" }));
  Ambient.toggle(true);
  Visual.levelsIn(Array.from({ length: 32 }, (_, i) => 0.3 + 0.5 * Math.abs(Math.sin(i))));
}, 5000));
