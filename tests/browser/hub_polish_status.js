// Fixture for hub_polish: forty apps in two sections, enough to overflow a
// dock that shows every app, like Emerson's thirty-one.
window.FORGE_SECTIONS = {
  make: { label: "Make", icon: "M", blurb: "", order: 1 },
  play: { label: "Play", icon: "P", blurb: "", order: 2 },
};
window.FORGE_STATUS = {};
for (let i = 1; i <= 40; i++) {
  const key = "app" + String(i).padStart(2, "0");
  window.FORGE_STATUS[key] = {
    available: true, state: "up", label: "App " + i, tagline: "tool number " + i,
    url: "about:blank", accent: "", icon: String.fromCharCode(64 + (i % 26) + 1),
    role: i === 40 ? "settings" : "", fullscreen: "", order: i, group: "",
    section: i % 2 ? "make" : "play",
  };
}
