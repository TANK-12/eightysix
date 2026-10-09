const test = require("node:test");
const assert = require("node:assert");
const A = require("./forge_attach.js");

const file = (name) => ({ name });
test("a paste's files come from files, else from file items", () => {
  assert.deepStrictEqual(A.pasted({ files: [file("a.png")], items: [], types: ["Files"] }), { files: [file("a.png")], desktop: false });
  const items = [{ kind: "string", getAsFile: () => null }, { kind: "file", getAsFile: () => file("b.jpg") }];
  assert.deepStrictEqual(A.pasted({ files: [], items, types: ["Files"] }).files, [file("b.jpg")]);
});
test("an image type with no file and no text asks the desktop clipboard", () => {
  assert.equal(A.pasted({ files: [], items: [], types: ["image/png"] }).desktop, true);
  assert.equal(A.pasted({ files: [], items: [], types: ["text/plain", "image/png"] }).desktop, false);
  assert.equal(A.pasted({ files: [], items: [], types: ["text/plain"] }).desktop, false);
  // WebKitGTK may name no type for a screenshot; HTML or a copied file is not one
  assert.equal(A.pasted({ files: [], items: [], types: [] }).desktop, true);
  assert.equal(A.pasted({ files: [], items: [], types: ["text/html"] }).desktop, false);
  assert.equal(A.pasted({ files: [], items: [], types: ["text/uri-list"] }).desktop, false);
  assert.deepStrictEqual(A.pasted(null), { files: [], desktop: false });
});

test("copied text that also holds a picture pastes as text", () => {
  assert.deepStrictEqual(A.pasted({ files: [file("cells.png")], items: [], types: ["text/plain", "Files"] }), { files: [], desktop: false });
});

// a box that keeps its listeners, enough for wire()
function fakeBox() {
  const on = {};
  return { on, classList: { add() {}, remove() {} }, contains: () => false, addEventListener: (k, f) => { on[k] = f; } };
}
const pasteOf = (files) => ({ preventDefault() { this.stopped = true; }, clipboardData: { files, items: [], types: ["Files"] } });

test("busy while a file uploads, then the file is added", async () => {
  const box = fakeBox(), added = [];
  let finish;
  const w = A.wire({ box, upload: () => new Promise((ok) => { finish = ok; }), onAdd: (s) => added.push(s) });
  assert.equal(w.busy(), false);
  const ev = pasteOf([{ name: "a.png", size: 3 }]);
  box.on.paste(ev);
  assert.equal(ev.stopped, true);
  assert.equal(w.busy(), true);
  finish({ name: "a.png", path: "/x/a.png" });
  await new Promise((r) => setTimeout(r, 0));
  assert.equal(w.busy(), false);
  assert.deepStrictEqual(added, [{ name: "a.png", path: "/x/a.png" }]);
});

test("a file over the limit is refused before upload, a refusing box takes none", async () => {
  const errs = [], ups = [];
  const box = fakeBox();
  const w = A.wire({ box, maxBytes: 10, upload: async (f) => { ups.push(f.name); return f; }, onAdd() {}, onError: (m) => errs.push(m) });
  await w.add([{ name: "big.mp4", size: 11 }, { name: "ok.txt", size: 10 }]);
  assert.deepStrictEqual(ups, ["ok.txt"]);
  assert.match(errs[0], /big\.mp4 is too big/);
  const box2 = fakeBox(), errs2 = [];
  const w2 = A.wire({ box: box2, refuse: () => "Jan reads text only", upload: async () => assert.fail("no upload"), onAdd() {}, onError: (m) => errs2.push(m) });
  const ev = pasteOf([{ name: "a.png", size: 1 }]);
  box2.on.paste(ev);
  assert.equal(ev.stopped, undefined, "the paste goes on as usual");
  await w2.add([{ name: "a.png", size: 1 }]);
  assert.deepStrictEqual(errs2, ["Jan reads text only"]);
});

test("a failed desktop paste says why", async () => {
  const box = fakeBox(), errs = [];
  A.wire({ box, upload: async () => ({}), pasteDesktop: async () => { throw new Error("There is no image on the clipboard"); }, onAdd() {}, onError: (m) => errs.push(m) });
  box.on.paste({ preventDefault() {}, clipboardData: { files: [], items: [], types: ["image/png"] } });
  await new Promise((r) => setTimeout(r, 0));
  assert.deepStrictEqual(errs, ["Could not paste the picture: There is no image on the clipboard"]);
});
