// Fixture for hub_sections: two sections with apps, one with none, a group
// in a section, and an app naming no section (which must land in "Other").
window.FORGE_STATUS = {
  novel: { available: true, state: "up", label: "Novel", tagline: "write books", url: "about:blank",
           accent: "#6ea8fe", icon: "N", role: "", fullscreen: "", order: 1, group: "", section: "create" },
  paint: { available: false, state: "idle", label: "Paint", tagline: "draw sprites", url: "about:blank",
           accent: "", icon: "P", role: "", fullscreen: "", order: 2, group: "", section: "create" },
  ember: { available: true, state: "up", label: "Ember", tagline: "farm the valley", url: "about:blank",
           accent: "#e08a3c", icon: "E", role: "", fullscreen: "", order: 3, group: "pixel", section: "" },
  stray: { available: true, state: "up", label: "Stray", tagline: "names no section", url: "about:blank",
           accent: "", icon: "S", role: "", fullscreen: "", order: 4, group: "", section: "nowhere" },
};
window.FORGE_GROUPS = {
  pixel: { id: "pixel", label: "Pixel games", tagline: "pick a world", icon: "G", accent: "",
           order: 3, section: "play", members: ["ember"] },
};
window.FORGE_SECTIONS = {
  create: { id: "create", label: "Create", icon: "C", blurb: "make things", order: 1 },
  play: { id: "play", label: "Play", icon: "G", blurb: "", order: 2 },
  empty: { id: "empty", label: "Empty", icon: "", blurb: "", order: 3 },
};
