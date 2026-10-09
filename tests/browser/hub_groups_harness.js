// Appended to a copy of the REAL hub/index.html by run.sh, with
// hub_groups_status.js beside it as status.js. Checks the Pixel games tab:
// one tile per group, a chooser inside it, member apps still opening as their
// own windows, and an app naming a group that does not exist keeping its tile.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const visible = (el) => !!el && getComputedStyle(el).display !== "none";
  const names = (nodes) => nodes.map((n) => n.querySelector(".name").textContent).join(",");

  try {
    const tiles = [...document.querySelectorAll("#tiles .tile")].filter(visible);
    T("home shows one tile for the group and none for its games",
      names(tiles) === "Tool,Pixel games,Stray", names(tiles));
    const dock = [...document.querySelectorAll("#dock .dock-item[data-app]")].filter(visible)
      .map((d) => d.dataset.app).join(",");
    T("the dock has one icon for the group", dock === "tool,group:pixel-games,stray", dock);
    const gTile = tiles.find((t) => t.dataset.key === "group:pixel-games");
    const gDock = document.querySelector('#dock .dock-item[data-app="group:pixel-games"]');
    T("the group's tile and dock show its drawn icon (shared/forge_icons.js)",
      !!(gTile && gTile.querySelector(".icon svg.forge-glyph") && gDock && gDock.querySelector("svg.forge-glyph")),
      gTile ? gTile.querySelector(".icon").innerHTML.slice(0, 40) : "no tile");
    // The bar shows an app's icon only once it is opened; the row itself
    // skips the grouped games (one icon for the group).
    const numbers = [...document.querySelectorAll("#workspaces .ws:not(.grouped)")]
      .map((n) => n.dataset.key).join(",");
    T("the bar skips the grouped games", numbers === "tool,group:pixel-games,stray", numbers);
    T("no icon shows in the bar before anything is opened",
      [...document.querySelectorAll("#workspaces .ws")].filter(visible).length === 0);

    window.forgeKey("2");
    T("Ctrl+2 opens the group", current === "group:pixel-games", String(current));
    const litNow = [...document.querySelectorAll("#workspaces .ws")].filter(visible).map((n) => n.dataset.key).join(",");
    T("the opened group's icon shows in the bar", litNow === "group:pixel-games", litNow);
    T("the title bar names the group",
      document.getElementById("title").textContent.includes("Pixel games"));
    T("a chooser, not an app, so no automatic full screen",
      !document.body.classList.contains("immersive"));
    const cards = [...document.querySelectorAll('.workspace[data-workspace="group:pixel-games"] .choice')];
    T("the chooser lists every game in the group", names(cards) === "Ember,Town", names(cards));
    T("a card shows whether its game is running",
      cards[0].classList.contains("up") && !cards[1].classList.contains("up"));

    cards[0].click();
    await wait(60);
    T("picking a game opens that game's own window",
      current === "ember"
      && document.querySelector('.workspace[data-workspace="ember"]').classList.contains("active"),
      String(current));
    T("the game keeps its own full screen", document.body.classList.contains("immersive"));
    const lit = document.querySelector("#workspaces .ws.active");
    T("the group's icon stays lit inside one of its games",
      lit && lit.dataset.key === "group:pixel-games", lit && lit.dataset.key);

    window.forgeKey("next");
    T("Ctrl+Tab steps on to the next tile, not the other game",
      current === "stray", String(current));
    selectWorkspace("town", { instant: true });
    T("a game still opens by its own name, so #app= links keep working",
      current === "town", String(current));

    selectWorkspace(null, { instant: true });
    T("searching a game's name finds the group tile",
      filterTiles("town") === "group:pixel-games", String(filterTiles("town")));
    T("searching the group's own words finds it too",
      filterTiles("pixel") === "group:pixel-games", String(filterTiles("pixel")));
    filterTiles("");

    forgeSetStatus({ town: Object.assign({}, status.town, { state: "up", available: true }) });
    selectWorkspace("group:pixel-games", { instant: true });
    const after = [...document.querySelectorAll('.workspace[data-workspace="group:pixel-games"] .choice')];
    T("a game coming up shows on its card", after[1].classList.contains("up"));
  } catch (e) {
    T("the harness ran without throwing", false, String((e && e.stack) || e));
  }

  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
