// Fixture for hub_immersive: three apps, one of which asks for full screen
// automatically and one of which plays the Settings role.
window.FORGE_STATUS = {
  tool: { available: true, state: "up", label: "Tool", tagline: "a tool", url: "about:blank",
          accent: "", icon: "T", role: "", fullscreen: "" },
  game: { available: true, state: "up", label: "Game", tagline: "a game", url: "about:blank",
          accent: "", icon: "G", role: "", fullscreen: "auto" },
  prefs: { available: true, state: "up", label: "Prefs", tagline: "settings", url: "about:blank",
           accent: "", icon: "P", role: "settings", fullscreen: "" },
};
