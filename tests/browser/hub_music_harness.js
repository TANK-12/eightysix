// Appended to a copy of the REAL hub/index.html by run.sh. Checks the
// background music panel and the visualiser's system-audio source, with a
// fake forge.py message channel standing in for WebKit's: what the page asks
// for is recorded, and window.forgeMusic is fed what forge_music.py would
// push. Open with #shot to leave the panel up for a screenshot.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const music = () => sent.filter((m) => m.music).map((m) => m.music);
  const canvas = document.getElementById("visual");
  const inked = () => {
    const d = canvas.getContext("2d").getImageData(0, 0, canvas.width, canvas.height).data;
    let n = 0;
    for (let i = 3; i < d.length; i += 16) if (d[i] > 0) n++;
    return n;
  };

  try {
    applyTheme({
      animations: true, music: true, music_volume: 40, visualiser: "wave", visualiser_source: "system",
      music_tracks: [], music_note: "The music folder ~/Music/Forge does not exist yet",
    });
    selectWorkspace(null, { instant: true });
    await wait(50);
    T("system source chosen inside Forge", canvas.dataset.source === "system", canvas.dataset.source);
    T("the visualiser runs on the home screen", canvas.dataset.running === "1");
    T("it asks forge.py for levels", music().some((m) => m.op === "levels" && m.on === true && m.bars === 32),
      JSON.stringify(music()));
    forgeMusic({ type: "levels", v: Array.from({ length: 32 }, (_, i) => (i < 10 ? 0.9 : 0.3)) });
    // headless Chrome hardly runs animation frames, so draw a few directly,
    // each a frame's time after the last: the levels ease in by elapsed time
    // (ForgeVisual.follow), and back-to-back calls would leave the wave flat
    for (let k = 0; k < 8; k++) { cancelAnimationFrame(Visual.raf); Visual.at = performance.now() - 1000 / 60; Visual.frame(); }
    T("pushed levels draw the wave", inked() > 50, inked());
    const y = Array.from(Visual.wave).reduce((a, b) => Math.max(a, Math.abs(b - 128)), 0);
    T("the wave moves with the levels", y > 20, y);

    sent.length = 0;
    selectWorkspace("tool", { instant: true });
    await wait(50);
    T("opening an app stops the levels", music().some((m) => m.op === "levels" && m.on === false), JSON.stringify(music()));
    selectWorkspace(null, { instant: true });
    await wait(50);
    T("back home asks again", music().some((m) => m.op === "levels" && m.on === true));

    // the note button's panel
    const btn = document.getElementById("music-btn"), panel = document.getElementById("music-panel");
    T("the note button shows while music is on", !btn.hidden);
    T("its tooltip says why there is nothing", /does not exist/.test(btn.title), btn.title);
    sent.length = 0;
    btn.click();
    await wait(30);
    T("clicking it opens the panel", !panel.hidden);
    T("opening asks for a fresh track list", music().some((m) => m.op === "tracks"));
    T("the panel shows the folder note", /does not exist/.test(document.getElementById("music-note").textContent));
    T("skip is off with nothing to skip to", document.getElementById("music-skip").disabled);

    document.getElementById("music-url").value = "not a link";
    document.getElementById("music-add").requestSubmit();
    T("a non-link is refused in the page", /Paste a YouTube link/.test(document.getElementById("music-status").textContent));
    sent.length = 0;
    document.getElementById("music-url").value = "https://www.youtube.com/watch?v=xyz";
    document.getElementById("music-add").requestSubmit();
    T("a link is sent to forge.py", music().some((m) => m.op === "add" && m.url === "https://www.youtube.com/watch?v=xyz"));
    T("Add is disabled while saving", document.getElementById("music-go").disabled);
    forgeMusic({ type: "add-progress", frac: 0.42 });
    T("progress shows", /42%/.test(document.getElementById("music-status").textContent));
    const url = "file:///tmp/Chill%20mix%20%5Bxyz%5D.mp3";
    forgeMusic({ type: "add-done", file: url, note: "", tracks: [{ name: "Old song", url: "file:///tmp/old.mp3" }, { name: "Chill mix [xyz]", url }] });
    // checked at once: the fake file cannot load, and a file that will not
    // play rightly moves on to the next track a moment later
    T("the added track is loaded", Music.audio.src === url, Music.audio.src);
    T("the panel names it", /Chill mix/.test(document.getElementById("music-now").textContent));
    await wait(30);
    T("the note is gone once there is music", document.getElementById("music-note").hidden);
    T("done message", /Added/.test(document.getElementById("music-status").textContent));
    T("skip works with two tracks", !document.getElementById("music-skip").disabled);
    forgeMusic({ type: "add-error", error: "ERROR: Video unavailable" });
    T("an error shows in red", document.getElementById("music-status").dataset.kind === "err");

    // the small API zen mode uses
    Music.pause();
    T("Music.pause() pauses and is remembered", Music.paused && localStorage.getItem("forge.musicPaused") === "1");
    Music.play();
    T("Music.play() resumes", !Music.paused);
    T("Music.playing is a boolean", typeof Music.playing === "boolean");

    // no cava: fall back to the background music itself
    forgeMusic({ type: "levels-off", reason: "cava is not installed" });
    await wait(30);
    T("without cava the visualiser falls back to the music", canvas.dataset.source === "music", canvas.dataset.source);
    Visual.RETRY_MS = 60;
    await wait(150);
    T("a missing cava is not retried", canvas.dataset.source === "music", canvas.dataset.source);
    Visual.systemFailed = "";
    Visual.apply();
    forgeMusic({ type: "levels-off", reason: "cava stopped" });
    await wait(20);
    T("a cava that stopped falls back to the music for now", canvas.dataset.source === "music", canvas.dataset.source);
    await wait(150);
    T("a cava that stopped is tried again, so QBZ is heard again", canvas.dataset.source === "system", canvas.dataset.source);

    document.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    await wait(250); // it fades out now (S7, A25)
    T("a press elsewhere closes the panel", panel.hidden);
  } catch (e) {
    T("the harness ran without throwing", false, String(e && e.stack || e));
  }

  if (location.hash === "#shot") {
    document.getElementById("music-btn").click();
    return;
  }
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
