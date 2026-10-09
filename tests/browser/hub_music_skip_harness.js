// Appended to a copy of the REAL hub/index.html by run.sh. S14 (2026-09-27):
// Emerson: "when i skip the background music song it makes a honk noise",
// and "make it so that i can open the background music folder".
//
// The honk: the leveller (a compressor with automatic make-up gain) sits at
// full boost during the gap between songs, so the new song's first
// milliseconds went through it loud before its attack caught up. The fix is
// a fade stage in front of the leveller (Music.chain's `fade`) that ramps the
// new song in (Music.ramp). Measured in an OfflineAudioContext through the
// real chain: the first 60 ms after a loud song starts must not be louder
// than the song settles at.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(typeof m === "string" ? JSON.parse(m) : m) } } };
  try {
    const rate = 44100, onset = 0.5;
    // half a second of silence, then a loud tone: what the chain hears on a skip
    const render = async (fadeIn) => {
      const ctx = new OfflineAudioContext(1, rate * 1.6, rate);
      const chain = Music.chain(ctx);
      chain.set(35, true);
      const buf = ctx.createBuffer(1, rate * 1.6, rate);
      const d = buf.getChannelData(0);
      for (let i = Math.floor(onset * rate); i < d.length; i++) d[i] = 0.9 * Math.sin(2 * Math.PI * 220 * i / rate);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(chain.input);
      chain.output.connect(ctx.destination);
      if (fadeIn) Music.ramp(chain.fade.gain, 0, 1, onset, Music.FADE_IN);
      src.start(0);
      const r = (await ctx.startRendering()).getChannelData(0);
      const peak = (a, b) => { let m = 0; for (let i = Math.floor(a * rate); i < b * rate; i++) m = Math.max(m, Math.abs(r[i])); return m; };
      return { first: peak(onset, onset + 0.06), steady: peak(1.2, 1.5) };
    };
    T("the chain has a fade stage in front of the leveller", !!(Music.chain(new OfflineAudioContext(1, rate, rate)).fade));
    const cut = await render(false);
    T("without the fade, the start of a song overshoots (the honk)", cut.first > cut.steady * 1.1,
      `first 60 ms ${cut.first.toFixed(3)} vs settled ${cut.steady.toFixed(3)}`);
    const faded = await render(true);
    T("with the fade in, the start is no louder than the settled song", faded.first <= faded.steady * 1.02,
      `first 60 ms ${faded.first.toFixed(3)} vs settled ${faded.steady.toFixed(3)}`);
    T("the settled level is the same either way", Math.abs(faded.steady - cut.steady) < 0.02,
      `${faded.steady.toFixed(3)} vs ${cut.steady.toFixed(3)}`);
    T("fades are short", Music.FADE_OUT <= 0.25 && Music.FADE_IN <= 0.6, `${Music.FADE_OUT} s out, ${Music.FADE_IN} s in`);

    // Open folder: ask forge.py for the full path, then open it in Files
    T("the music panel has an Open folder button", !!$("music-folder"));
    const opened = [];
    const realOpen = openWithHash;
    openWithHash = (key, hash) => opened.push([key, hash]);
    const hadFiles = order.find((k) => (status[k] || {}).role === "files");
    if (hadFiles) status[hadFiles].role = "files-hidden";
    $("music-folder").click();
    T("pressing it asks forge.py for the folder", sent.some((m) => m && m.music && m.music.op === "folder"),
      JSON.stringify(sent.slice(-1)));
    window.forgeMusic({ type: "folder", path: "/home/me/Music" });
    T("without a Files app it says so instead of doing nothing",
      opened.length === 0 && /Files/.test($("music-status").textContent), $("music-status").textContent);
    if (hadFiles) status[hadFiles].role = "files";
    const filesKey = hadFiles || "files-test";
    if (!hadFiles) { status[filesKey] = { role: "files", label: "Files", url: "http://127.0.0.1:1/" }; order.push(filesKey); }
    window.forgeMusic({ type: "folder", path: "/home/me/Music/Forge & Co" });
    T("with one, the answer opens that folder in Files", opened.length === 1 && opened[0][0] === filesKey
      && new URLSearchParams(opened[0][1]).get("path") === "/home/me/Music/Forge & Co", JSON.stringify(opened));
    if (!hadFiles) { delete status[filesKey]; order.splice(order.indexOf(filesKey), 1); }
    openWithHash = realOpen;
  } catch (e) {
    T("music skip harness ran", false, String(e && e.message) + " " + String(e && e.stack || e));
  }
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
