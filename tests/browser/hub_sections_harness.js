// Appended to a copy of the REAL hub/index.html by run.sh, with
// hub_sections_status.js beside it as status.js. Checks the organised home
// screen: sections in their order, filter chips, search across sections,
// collapsing, the recent row, the bar numbering only opened apps, and the
// particle kinds.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const visible = (el) => !!el && getComputedStyle(el).display !== "none";
  const heads = () => [...document.querySelectorAll("#tiles .section")].filter(visible)
    .map((s) => s.querySelector(".s-label").textContent).join(",");
  const inSection = (id) => [...document.querySelectorAll(`.section[data-section="${id}"] .tile`)]
    .filter(visible).map((t) => t.dataset.key).join(",");

  try {
    T("sections show in their order, Other last, an empty one hidden", heads() === "Create,Play,Other", heads());
    T("apps sit under their section in app order", inSection("create") === "novel,paint", inSection("create"));
    T("a group sits under the group's section", inSection("play") === "group:pixel", inSection("play"));
    T("an app naming no real section lands in Other", inSection("other") === "stray", inSection("other"));
    const count = document.querySelector('.section[data-section="create"] .s-count').textContent;
    T("a heading counts its tiles", count === "2", count);
    const chips = [...document.querySelectorAll("#chips .fchip")].map((c) => c.textContent).join(",");
    T("a chip per section with apps, plus All", chips === "All,CCreate,GPlay,Other", chips);

    document.querySelectorAll("#chips .fchip")[2].click();
    T("a chip shows only its section", heads() === "Play", heads());
    T("the chip is remembered", localStorage.getItem("forge.chip") === '"play"');
    document.querySelectorAll("#chips .fchip")[0].click();
    T("All shows every section again", heads() === "Create,Play,Other", heads());

    const create = document.querySelector('.section[data-section="create"]');
    create.querySelector(".section-head").click();
    T("a heading collapses its section", create.classList.contains("collapsed"));
    T("and that is remembered", localStorage.getItem("forge.collapsed") === '["create"]');
    const hit = filterTiles("paint");
    T("a search finds apps in a collapsed section", hit === "paint" && heads() === "Create", `${hit} ${heads()}`);
    T("while searching, collapsed sections are shown open",
      document.getElementById("tiles").classList.contains("searching"));
    filterTiles("");
    create.querySelector(".section-head").click();

    const shown = () => [...document.querySelectorAll("#workspaces .ws")].filter(visible).map((n) => n.dataset.key).join(",");
    T("the bar has no icons before an app is opened", shown() === "", shown());
    selectWorkspace("stray", { instant: true });
    T("opening an app puts its icon in the bar", shown() === "stray", shown());
    window.forgeKey("1");
    T("Ctrl+1 still opens the first tile", current === "novel", String(current));
    T("both opened apps are on the bar", shown() === "novel,stray", shown());
    selectWorkspace(null, { instant: true });
    const recent = [...document.querySelectorAll("#recent .tile")].map((t) => t.dataset.key).join(",");
    T("home shows the recently opened apps, newest first", recent === "novel,stray", recent);
    T("the recent row is visible", !document.getElementById("recent-wrap").hidden);
    closeWorkspace("stray");
    T("closing an app takes its icon off the bar", shown() === "novel", shown());

    const kinds = {};
    for (const kind of ["embers", "constellation", "lively", "bogus", "off"]) {
      applyTheme({ animations: true, particles: kind });
      const c = document.getElementById("particles");
      kinds[kind] = `${c.dataset.kind}/${c.dataset.dots}`;
    }
    T("each particle kind draws its own number of lights",
      kinds.embers === "embers/90" && kinds.constellation === "constellation/95" && kinds.lively === "lively/110"
        && kinds.bogus === "soft/45" && kinds.off === "off/0", JSON.stringify(kinds));
    applyTheme({ animations: true, particles: "embers" });
    Particles.burst(100, 100);
    T("a press throws a burst of sparks", Particles.sparks.length === 34, Particles.sparks.length);
  } catch (e) {
    T("the harness ran without throwing", false, String((e && e.stack) || e));
  }

  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
