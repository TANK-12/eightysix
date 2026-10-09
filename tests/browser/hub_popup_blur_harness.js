// Appended to a copy of the REAL hub/index.html by run.sh. Emerson
// (2026-09-27): the music popout and the size panel should go away when he
// clicks outside them. A click on an app lands in its frame, so the hub only
// sees its window lose focus.
addEventListener("load", () => setTimeout(() => {
  const out = [];
  const T = (name, ok) => out.push((ok ? "PASS" : "FAIL") + " :: " + name);
  window.webkit = { messageHandlers: { forge: { postMessage: () => {} } } };
  try {
    applyTheme(Object.assign({}, theme, { animations: false }));
    Music.panel(true);
    T("the music panel opens", Popup.isOpen($("music-panel")));
    dispatchEvent(new Event("blur"));
    T("clicking into an app closes the music panel", !Popup.isOpen($("music-panel")));
    Sizes.panel(true);
    T("the size panel opens", Popup.isOpen($("size-panel")));
    dispatchEvent(new Event("blur"));
    T("clicking into an app closes the size panel", !Popup.isOpen($("size-panel")));
    Sizes.panel(true);
    document.body.dispatchEvent(new PointerEvent("pointerdown", { bubbles: true }));
    T("clicking elsewhere in the hub still closes it", !Popup.isOpen($("size-panel")));
    Popup.open($("toast"));
    dispatchEvent(new Event("blur"));
    T("the toast is left alone", Popup.isOpen($("toast")));
  } catch (e) { out.push("FAIL :: threw :: " + e.message); }
  const pre = document.createElement("pre");
  pre.id = "results";
  pre.textContent = "RESULTS\n" + out.join("\n") + "\n";
  document.body.append(pre);
}, 300));
