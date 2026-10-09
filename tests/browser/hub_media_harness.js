// Appended to a copy of the REAL hub/index.html by run.sh. Checks the bar's
// Now playing popup (S7 A9/A27/A30, finished by S10): media reported by an
// app's frame (shared/forge_media.js), desktop players from forge.py
// (shared/forge_mpris.py), the background music's volume past 100% and the
// music stepping aside while an app plays. The leveller is measured by
// hub_level_harness.js, which needs a real clock. Open with #shot to leave the popup up.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const media = () => sent.filter((m) => m.media).map((m) => m.media);
  const btn = $("music-btn"), panel = $("music-panel");
  const setRange = (el, v, type) => { el.value = v; el.dispatchEvent(new Event(type || "change", { bubbles: true })); };

  try {
    applyTheme({ animations: false, music: false, music_tracks: [], music_volume: 40, music_duck: true, music_level: true });
    selectWorkspace(null, { instant: true });
    await wait(30);
    T("nothing on and nothing playing: no music button", btn.hidden);

    // --- an app plays something -------------------------------------------------
    selectWorkspace("tool", { instant: true });
    await wait(50);
    const frame = parts.tool.inner.querySelector("iframe");
    const got = [];
    frame.contentWindow.addEventListener("message", (e) => got.push(e.data));
    const report = (extra) => window.dispatchEvent(new MessageEvent("message", {
      source: frame.contentWindow,
      data: Object.assign({ forge: "media", state: "playing", title: "Lofi mix", artist: "", artwork: "", kind: "video",
        current: 30, duration: 3600, volume: 1, canBoost: true, canNext: false, canPrev: true }, extra || {}),
    }));
    report();
    selectWorkspace(null, { instant: true });
    await wait(30);
    T("an app playing shows the button", !btn.hidden);
    T("the button lights up while something plays", btn.classList.contains("on"));
    T("its tooltip names what plays", /Lofi mix/.test(btn.title), btn.title);

    sent.length = 0;
    btn.click();
    await wait(30);
    T("the button opens Now playing", Popup.isOpen(panel));
    T("opening asks forge.py for the desktop's players", media().some((m) => m.op === "list"), JSON.stringify(media()));
    T("the app is the big one", !$("np-main").hidden && /Lofi mix/.test($("np-title").textContent), $("np-title").textContent);
    T("it names the app", /Tool/.test($("np-sub").textContent), $("np-sub").textContent);
    T("the background music part is hidden while music is off", $("music-section").hidden);

    $("np-toggle").click();
    await wait(30);
    T("play/pause goes to that app's frame", got.some((m) => m.forge === "media-cmd" && m.op === "toggle"), JSON.stringify(got));
    T("next is off when the app has no next", $("np-next").disabled);
    T("the time shows", $("np-len").textContent === "1:00:00", $("np-len").textContent);
    setRange($("np-seek"), 500);
    await wait(30);
    T("seeking half way sends half the length", got.some((m) => m.op === "seek" && Math.abs(m.time - 1800) < 1), JSON.stringify(got));
    T("app media from its own server can go to 200%", $("np-vol").max === "200", $("np-vol").max);
    setRange($("np-vol"), 150, "input");
    await wait(30);
    T("the volume goes as 0..2", got.some((m) => m.op === "volume" && Math.abs(m.volume - 1.5) < 1e-9), JSON.stringify(got));
    T("its number follows", $("np-vol-n").value === "150");
    report({ canBoost: false, title: "Stream" });
    await wait(20);
    T("media from elsewhere stops at 100%", $("np-vol").max === "100");
    T("the big one follows the new title", /Stream/.test($("np-title").textContent));

    $("np-go").click();
    await wait(30);
    T("Go to it brings up the app", current === "tool", current);
    T("and closes the popup", !Popup.isOpen(panel));
    selectWorkspace(null, { instant: true });

    // zen and background mode cover the apps: Go to it leaves them first
    Zen.toggle(true);
    Popup.open ? Popup.open(panel) : null;
    $("np-go").click();
    await wait(30);
    T("Go to it from zen leaves zen and brings up the app", !Zen.on && current === "tool", `${Zen.on} ${current}`);
    selectWorkspace(null, { instant: true });
    Ambient.toggle(true);
    $("np-go").click();
    await wait(30);
    T("Go to it from background mode leaves it and brings up the app", !Ambient.on && current === "tool", `${Ambient.on} ${current}`);
    selectWorkspace(null, { instant: true });

    // --- a player on the desktop ------------------------------------------------------
    const bus = "org.mpris.MediaPlayer2.firefox.instance_1_2";
    forgeMediaSys([{ bus, name: "Firefox", desktop: "firefox", state: "paused", title: "Song", artist: "Band", artwork: "",
      position: 10, duration: 200, volume: 0.8, canRaise: true, canNext: true, canPrev: true, canSeek: true }]);
    btn.click();
    await wait(30);
    const row = () => $("np-list").querySelector(`.np-row[data-id="${CSS.escape("sys:" + bus)}"]`);
    T("a paused desktop player is a row under what plays", !!row() && /Stream/.test($("np-title").textContent));
    T("the row names track, artist and player", row() && /Song/.test(row().textContent) && /Band/.test(row().textContent) && /Firefox/.test(row().textContent));
    sent.length = 0;
    row().querySelector(".np-row-toggle").click();
    await wait(20);
    T("its play/pause goes through forge.py", media().some((m) => m.op === "toggle" && m.bus === bus), JSON.stringify(media()));
    // B4: every row has its own volume and track controls
    const rv = () => row().querySelector(".np-row-vol input[type=range]");
    const rn = () => row().querySelector(".np-row-vol input[type=number]");
    T("the row has a volume slider and number at the player's volume", rv() && rn() && rv().value === "80" && rn().value === "80" && rv().max === "100",
      rv() ? `${rv().value} ${rn().value} max ${rv().max}` : "no slider");
    sent.length = 0;
    setRange(rv(), 40, "input");
    await wait(20);
    T("the row's volume goes to its player as 0..1", media().some((m) => m.op === "volume" && m.bus === bus && Math.abs(m.value - 0.4) < 1e-9), JSON.stringify(media()));
    T("the row's number follows", rn().value === "40");
    T("moving a row's volume leaves the big one alone", /Stream/.test($("np-title").textContent), $("np-title").textContent);
    rn().value = "65";
    rn().dispatchEvent(new Event("change", { bubbles: true }));
    await wait(20);
    T("typing a row's number sets its volume", media().some((m) => m.op === "volume" && m.bus === bus && Math.abs(m.value - 0.65) < 1e-9) && rv().value === "65");
    sent.length = 0;
    row().querySelector(".np-row-next").click();
    row().querySelector(".np-row-prev").click();
    await wait(20);
    T("the row's next and previous go to its player", media().some((m) => m.op === "next" && m.bus === bus) && media().some((m) => m.op === "prev" && m.bus === bus), JSON.stringify(media()));
    T("the big one is still the same", /Stream/.test($("np-title").textContent));
    row().querySelector(".np-row-meta").click();
    await wait(20);
    T("clicking its name makes it the big one", /Song/.test($("np-title").textContent), $("np-title").textContent);
    setRange($("np-seek"), 250);
    setRange($("np-vol"), 30, "input");
    await wait(20);
    T("seek goes in seconds", media().some((m) => m.op === "seek" && m.bus === bus && Math.abs(m.value - 50) < 1e-9), JSON.stringify(media()));
    T("desktop volume stops at 100%", $("np-vol").max === "100");
    T("volume goes as 0..1", media().some((m) => m.op === "volume" && m.bus === bus && Math.abs(m.value - 0.3) < 1e-9));
    $("np-go").click();
    await wait(20);
    T("Go to it raises the player", media().some((m) => m.op === "raise" && m.bus === bus));
    forgeMediaSys([]);
    await wait(20);
    T("a player that went away is dropped", !NowPlaying.sources["sys:" + bus]);

    // --- the app stops or closes ------------------------------------------------------------
    report({ state: "gone" });
    await wait(20);
    T("a page that goes away is dropped", !NowPlaying.sources["app:tool"]);
    report();
    await wait(20);
    closeWorkspace("tool");
    await wait(20);
    T("closing the app forgets its media", !NowPlaying.any());
    selectWorkspace("tool", { instant: true });
    await wait(50);
    const f1 = parts.tool.inner.querySelector("iframe");
    window.dispatchEvent(new MessageEvent("message", { source: f1.contentWindow,
      data: { forge: "media", state: "playing", title: "click", current: 0, duration: 1.2, volume: 1 } }));
    await wait(20);
    T("a short sound effect is not 'now playing'", !NowPlaying.any() && !NowPlaying.appPlaying());
    closeWorkspace("tool");
    selectWorkspace(null, { instant: true });
    btn.hidden = false;
    btn.click();
    await wait(30);
    T("an empty popup says so", !$("media-empty").hidden && $("np-main").hidden, $("media-empty").hidden);
    Popup.close(panel);

    // --- background music: past 100%, stepping aside --------------------------------------
    applyTheme({ music: true, music_tracks: [{ name: "A", url: "file:///tmp/a.mp3" }, { name: "B", url: "file:///tmp/b.mp3" }] });
    await wait(30);
    T("with music on its part shows", !$("music-section").hidden);
    T("the music slider goes to 200%", $("music-vol").max === "200", $("music-vol").max);
    sent.length = 0;
    setRange($("music-vol"), 150, "input");
    await wait(350);
    T("moving it sets the volume", theme.music_volume === 150, theme.music_volume);
    T("and saves it", sent.some((m) => m.settings && m.settings.music_volume === 150), JSON.stringify(sent));
    T("its number follows", $("music-vol-n").value === "150");
    const p = Music.volumeParts;
    T("routed through Web Audio: full element, gain carries the boost",
      JSON.stringify(p(150, true)) === '{"el":1,"gain":1.5}', JSON.stringify(p(150, true)));
    T("not routed: capped at 100%", JSON.stringify(p(150, false)) === '{"el":1,"gain":1}');
    T("not routed, under 100%", JSON.stringify(p(40, false)) === '{"el":0.4,"gain":1}');

    Music.paused = false;
    T("with nothing else playing the music wants to play", Music.wanted() === true);
    selectWorkspace("tool", { instant: true });
    await wait(50);
    const f2 = parts.tool.inner.querySelector("iframe");
    window.dispatchEvent(new MessageEvent("message", { source: f2.contentWindow,
      data: { forge: "media", state: "playing", title: "Clip", current: 1, duration: 240, volume: 1 } }));
    await wait(20);
    T("an app playing makes the music step aside", Music.wanted() === false);
    btn.click();
    await wait(30);
    T("and the music part says why it is quiet", !$("music-aside").hidden);
    Popup.close(panel);
    applyTheme({ music_duck: false });
    T("unless stepping aside is off", Music.wanted() === true);
    applyTheme({ music_duck: true });
    window.dispatchEvent(new MessageEvent("message", { source: f2.contentWindow,
      data: { forge: "media", state: "paused", title: "Clip", current: 1, duration: 240, volume: 1 } }));
    await wait(20);
    T("paused app media lets it back", Music.wanted() === true);
    closeWorkspace("tool");

    // --- a native view plays (YouTube in Media, behind another app) --------------
    selectWorkspace("tool", { instant: true });
    await wait(30);
    viewOwners.add("tool");
    sent.length = 0;
    NowPlaying.askViews();
    T("apps with views are asked what they play", sent.some((m) => m.view && m.view.op === "media" && !m.view.id), JSON.stringify(sent));
    window.forgeViewEvent({ event: "media", id: "media-youtube", owner: "tool", has: true, paused: false,
      title: "Lofi girl - YouTube", artist: "", current: 12, duration: 600, volume: 1, video: true });
    selectWorkspace(null, { instant: true });
    await wait(30);
    T("a view playing lights the button", btn.classList.contains("on") && /Lofi girl/.test(btn.title), btn.title);
    T("and the music steps aside for it", Music.wanted() === false);
    btn.click();
    await wait(30);
    const vid = NowPlaying.main();
    T("the popup shows the view's media big", vid && vid.id === "view:media-youtube" && $("np-title").textContent.includes("Lofi girl"), $("np-title").textContent);
    sent.length = 0;
    $("np-toggle").click();
    T("its pause goes to that view through forge.py", sent.some((m) => m.view && m.view.op === "media" && m.view.id === "media-youtube" && m.view.cmd === "toggle"), JSON.stringify(sent));
    T("and shows paused at once", NowPlaying.sources["view:media-youtube"].state === "paused");
    T("the music comes back while it is paused", Music.wanted() === true);
    window.forgeViewEvent({ event: "media", id: "media-youtube", owner: "tool", has: true, paused: false,
      title: "Lofi girl - YouTube", current: 13, duration: 600, volume: 1 });
    sent.length = 0;
    $("np-toggle").click();
    T("and a second press is play again, then pause", sent.some((m) => m.view && m.view.cmd === "toggle"));
    window.forgeViewEvent({ event: "media", id: "media-youtube", owner: "tool", has: false });
    T("a view with nothing to play leaves the list", !NowPlaying.sources["view:media-youtube"]);
    window.forgeViewEvent({ event: "media", id: "media-youtube", owner: "tool", has: true, paused: false, title: "x", duration: 600 });
    dropViews("tool");
    T("closing the app's views forgets their media", !NowPlaying.sources["view:media-youtube"]);
    Popup.close(panel);
    closeWorkspace("tool");

  } catch (e) {
    T("the harness ran without throwing", false, String(e && e.stack || e));
  }

  if (location.hash === "#shot") return;
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
