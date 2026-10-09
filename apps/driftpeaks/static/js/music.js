/* Background music: the tracks /api/music lists, one after another, round and
   round. Browsers only let sound start after a key or click, so the game calls
   start() from its input handlers; volume 0 pauses it. While the page is
   out of sight (another app in front inside Forge, a background tab) it
   pauses too, and carries on from the same spot when the page is back. */

export function nextIndex(i, count) {
  return count ? (i + 1) % count : 0;
}

export function createMusic() {
  const el = new Audio();
  el.preload = "auto";
  let tracks = [];
  let at = 0;
  let volume = 0;
  let wanted = false;
  const away = () => document.hidden || (window.ForgeVisible ? ForgeVisible.on === false : false);

  const load = () => {
    if (!tracks.length) return;
    el.src = tracks[at].url;
  };
  const play = () => {
    if (!wanted || volume <= 0 || !tracks.length || away()) return el.pause();
    if (!el.src) load();
    el.play().catch(() => {});
  };
  el.addEventListener("ended", () => {
    at = nextIndex(at, tracks.length);
    load();
    play();
  });

  document.addEventListener("visibilitychange", play);
  document.addEventListener("forge-visible", play);

  fetch("api/music")
    .then((r) => r.json())
    .then((body) => {
      tracks = body.tracks || [];
      play();
    })
    .catch(() => {});

  return {
    element: el,
    start() {
      if (wanted && !el.paused) return;
      wanted = true;
      play();
    },
    setVolume(v) {
      volume = Math.max(0, Math.min(100, Number(v) || 0));
      el.volume = volume / 100;
      play();
    },
    get track() {
      return tracks[at] ? tracks[at].name : "";
    },
  };
}
