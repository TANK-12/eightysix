// Fixture for hub_groups: a plain tool, two games in a "Pixel games" group
// (one still starting), and an app naming a group that has no file, which must
// keep its own tile rather than disappear.
window.FORGE_STATUS = {
  tool: { available: true, state: "up", label: "Tool", tagline: "a tool", url: "about:blank",
          accent: "", icon: "T", role: "", fullscreen: "", order: 1, group: "" },
  ember: { available: true, state: "up", label: "Ember", tagline: "farm the valley", url: "about:blank",
           accent: "#e08a3c", icon: "E", role: "", fullscreen: "auto", order: 2, group: "pixel-games" },
  stray: { available: true, state: "up", label: "Stray", tagline: "names a missing group", url: "about:blank",
           accent: "", icon: "S", role: "", fullscreen: "", order: 3, group: "no-such-group" },
  town: { available: false, state: "idle", label: "Town", tagline: "an npc town", url: "about:blank",
          accent: "", icon: "N", role: "", fullscreen: "auto", order: 4, group: "pixel-games" },
};
window.FORGE_GROUPS = {
  "pixel-games": { id: "pixel-games", label: "Pixel games", tagline: "Pick a pixel world to play",
                   icon: "\u{1F47E}", accent: "#9d7bff", order: 2, members: ["ember", "town"] },
};
