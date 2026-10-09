// Appended to a copy of the REAL hub by run.sh. S23 (Emerson, 2026-09-27):
// "separate things from the wallpaper like people to make 2.5d or 3d
// effects". The layers come from shared/forge_layers.py; here they are
// stood in for by two data URLs.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  // the moving values live on the layers (MOVING_LAYERS), not on <html>
  const px = (name) => parseFloat(getComputedStyle(document.getElementById(name.startsWith("--fg") ? "wall-fg" : "wall")).getPropertyValue(name)) || 0;
  const dot = "data:image/gif;base64,R0lGODlhAQABAAAAACw=";
  try {
    const fg = document.getElementById("wall-fg"), wall = document.getElementById("wall");
    T("off by default: no subject layer", getComputedStyle(fg).display === "none");
    const base = Object.assign({}, theme, { animations: true, wall_parallax: 1, wallpaper: "orig.jpg" });
    applyTheme(Object.assign({}, base, { wall_3d: true, wall_3d_depth: 1.5, wall_3d_beat: true,
      wallpaper_fg: dot + "#fg", wallpaper_bg: dot + "#bg" }));
    await wait(30);
    T("on with layers made: the subject layer shows", document.body.classList.contains("wall-3d") && getComputedStyle(fg).display === "block");
    T("it wears the cut-out", /#fg/.test(fg.style.backgroundImage), fg.style.backgroundImage.slice(0, 60));
    T("and the picture behind is the filled-in one", /#bg/.test(wall.style.backgroundImage), wall.style.backgroundImage.slice(0, 60));
    const kids = [...document.body.children];
    T("it sits over the particles and under the visualiser",
      kids.indexOf(fg) > kids.indexOf(document.getElementById("particles")) && kids.indexOf(fg) < kids.indexOf(document.getElementById("visual")));
    T("it is a little bigger than the picture (nearer)", px("--fg-scale") > px("--wall-scale"), `${px("--fg-scale")} > ${px("--wall-scale")}`);
    document.dispatchEvent(new PointerEvent("pointermove", { clientX: 0, clientY: 0, bubbles: true }));
    WallFx.x = WallFx.tx; WallFx.y = WallFx.ty; WallFx.put();
    T("a pointer move restyles only the layers, never the whole page (task 71)",
      document.documentElement.style.getPropertyValue("--wall-x") === "" && document.documentElement.style.getPropertyValue("--fg-x") === ""
      && getComputedStyle(document.body).getPropertyValue("--fg-x").trim() === "", document.documentElement.style.cssText.slice(0, 80));
    T("the pointer moves the subject further than the picture", Math.abs(px("--fg-x")) > Math.abs(px("--wall-x")) + 10,
      `${px("--fg-x")} vs ${px("--wall-x")}`);
    T("with the wallpaper's own parallax off it still moves", (() => {
      applyTheme(Object.assign({}, base, { wall_parallax: 0, wall_3d: true, wall_3d_depth: 1.5, wallpaper_fg: dot + "#fg", wallpaper_bg: dot + "#bg" }));
      WallFx.tx = WallFx.x = 1; WallFx.put();
      return Math.abs(px("--fg-x")) > 10 && px("--wall-x") === 0;
    })(), `${px("--fg-x")} ${px("--wall-x")}`);
    T("moves to the beat marks the page", document.body.classList.contains("wall-3d-beat"));
    applyTheme(Object.assign({}, base, { wall_3d: true, wall_3d_beat: false, wallpaper_fg: dot + "#fg", wallpaper_bg: dot + "#bg" }));
    T("and can be turned off", !document.body.classList.contains("wall-3d-beat"));
    applyTheme(Object.assign({}, base, { wall_3d: true, wallpaper_fg: "", wallpaper_bg: "" }));
    T("on but not made yet: flat, the original picture", !document.body.classList.contains("wall-3d") && /orig\.jpg/.test(wall.style.backgroundImage));
    applyTheme(Object.assign({}, base, { wall_3d: false, wallpaper_fg: dot + "#fg", wallpaper_bg: dot + "#bg" }));
    T("off: flat again", !document.body.classList.contains("wall-3d") && /orig\.jpg/.test(wall.style.backgroundImage));
  } catch (e) {
    T("the checks ran without an error", false, e && (e.message + " " + (e.stack || "").split("\n")[1]));
  }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "\n" + out.join("\n");
  document.body.appendChild(pre);
}, 600));
