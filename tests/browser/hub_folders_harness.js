// Appended to a copy of the REAL hub/index.html (fixture: hub_polish_status.js,
// forty apps in two sections). Folders: drag an app onto another to make a
// folder, drop onto a folder to join, rename, take out, ungroup.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const sent = [];
  window.webkit = { messageHandlers: { forge: { postMessage: (m) => sent.push(JSON.parse(m)) } } };
  const tileOf = (k) => parts[k] && parts[k].tile;
  const shows = (n) => !!n && getComputedStyle(n).display !== "none";
  const drag = (from, to) => {
    const dt = new DataTransfer();
    from.dispatchEvent(new DragEvent("dragstart", { dataTransfer: dt, bubbles: true }));
    const over = new DragEvent("dragover", { dataTransfer: dt, bubbles: true, cancelable: true });
    to.dispatchEvent(over);
    const lit = to.classList.contains("drop-into");
    to.dispatchEvent(new DragEvent("drop", { dataTransfer: dt, bubbles: true, cancelable: true }));
    from.dispatchEvent(new DragEvent("dragend", { bubbles: true }));
    return over.defaultPrevented && lit;
  };
  const menu = (key) => {
    AppMenu.open(key, 20, 20);
    const items = [...$("app-menu").querySelectorAll("button")].map((b) => b.textContent);
    Popup.close($("app-menu"));
    return items.join(" | ");
  };
  try {
    const plain = shown().filter((k) => !isGroup(k) && !Folders.declared(k));
    const [a, b, c] = plain;
    T("app tiles can be dragged", tileOf(a).draggable && tileOf(b).draggable);
    T("an app takes a dragged app", drag(tileOf(b), tileOf(a)));
    const f = folderOf(a);
    T("dropping one app on another makes a folder of both", !!f && folderOf(b) === f, f);
    T("the two tiles give way to one folder tile", !shows(tileOf(a)) && !shows(tileOf(b)) && shows(tileOf(f)));
    T("the folder tile shows both apps' icons", tileOf(f).querySelectorAll(".folder-icons span").length === 2);
    T("it sits in the first app's section", tileOf(f).closest(".section").dataset.section === sectionOf(a));
    T("and is named after that section", infoFor(f).label === ((sections[sectionOf(a)] || {}).label || "Folder"), infoFor(f).label);
    const saved = sent.filter((m) => m.settings && m.settings.app_folders).pop();
    T("saved as app_folders through forge.py", !!saved && JSON.stringify(Object.values(saved.settings.app_folders)[0].members) === JSON.stringify([a, b]), JSON.stringify(saved));
    T("a toast offers Undo", /folder/i.test($("toast-text").textContent) && !$("toast-undo").hidden, $("toast-text").textContent);
    T("the dock shows the folder, not the two apps", shows(parts[f].dock) && !shows(parts[a].dock) && !shows(parts[b].dock));
    T("dropping onto the folder adds an app", drag(tileOf(c), tileOf(f)) && folderOf(c) === f && infoFor(f).members.length === 3);
    selectWorkspace(f, { instant: true });
    await wait(100);
    T("the folder opens a chooser of its apps", parts[f].inner.querySelectorAll(".choice").length === 3);
    const name = parts[f].inner.querySelector(".folder-name");
    name.value = "My tools";
    name.dispatchEvent(new Event("change"));
    const f2 = folderOf(a);
    T("it is renamed from the chooser", infoFor(f2).label === "My tools" && Object.values(theme.app_folders)[0].label === "My tools");
    T("and the chooser stays open", current === f2 && !!parts[f2].inner.querySelector(".folder-name"));
    T("an app in a folder offers Take out", /Take out of folder/.test(menu(a)), menu(a));
    T("a folder offers Rename and Ungroup, not Pop out", /Rename folder/.test(menu(f2)) && /Ungroup/.test(menu(f2)) && !/Pop out/.test(menu(f2)), menu(f2));
    Folders.takeOut(c);
    T("Take out gives the app its own tile back", !folderOf(c) && shows(tileOf(c)) && infoFor(folderOf(a)).members.length === 2);
    $("toast-undo").click();
    T("Undo puts it back", folderOf(c) === folderOf(a));
    Folders.takeOut(c);
    Folders.takeOut(b);
    T("a folder left with one app dissolves", !folderOf(a) && !Object.keys(theme.app_folders).length && shows(tileOf(a)) && shows(tileOf(b)));
    T("and the hub went home as its folder closed", current === null);
    T("the dock is back in app order", [...$("dock").querySelectorAll(".dock-item[data-app]")].map((n) => n.dataset.app).join() === order.join());
    Folders.drop(b, a);
    Folders.ungroup(folderOf(a));
    T("Ungroup ends a folder", !folderOf(a) && !folderOf(b) && shows(tileOf(a)));
    T("an app does not take itself", !Folders.drop(a, a));
  } catch (e) {
    T("folders harness ran", false, String(e && e.stack || e));
  }
  delete window.webkit;
  document.body.insertAdjacentHTML("beforeend", "<pre id='results' style='position:fixed;left:-9999px'>RESULTS\n" + out.join("\n") + "\n</pre>");
}, 300));
