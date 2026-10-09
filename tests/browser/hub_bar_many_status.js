// Fixture for hub_bar_overflow: thirty apps (one plays the Settings role), so
// the bar has more open-app icons than any window is wide.
window.FORGE_STATUS = {};
for (let i = 1; i <= 30; i++) {
  const key = "app" + String(i).padStart(2, "0");
  window.FORGE_STATUS[key] = { available: true, state: "up", label: "App " + i, tagline: "app number " + i,
    url: "about:blank", accent: "", icon: String.fromCharCode(64 + ((i - 1) % 26) + 1), role: i === 30 ? "settings" : "",
    fullscreen: "" };
}
