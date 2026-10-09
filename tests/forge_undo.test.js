// node --test tests/forge_undo.test.js -- the key rules of shared/forge_undo.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function load() {
  const calls = [];
  let listener = null;
  const win = { addEventListener: (type, fn) => { if (type === "keydown") listener = fn; } };
  const doc = { execCommand: (what) => { calls.push(what); return true; } };
  const ctx = { window: win, document: doc };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "shared", "forge_undo.js"), "utf8"), ctx);
  return { undo: win.ForgeUndo, calls, listener };
}

const box = (tag, type = "", extra = {}) => ({ tagName: tag, getAttribute: () => type, ...extra });
const key = (k, mods = {}, target = box("TEXTAREA")) => {
  const e = { key: k, ctrlKey: true, shiftKey: false, altKey: false, metaKey: false, target,
    defaultPrevented: false, isComposing: false, prevented: false, ...mods };
  e.preventDefault = () => { e.prevented = true; e.defaultPrevented = true; };
  return e;
};

test("the keys map to undo and redo", () => {
  const { undo } = load();
  assert.strictEqual(undo.action(key("z")), "undo");
  assert.strictEqual(undo.action(key("Z", { shiftKey: true })), "redo");
  assert.strictEqual(undo.action(key("y")), "redo");
  assert.strictEqual(undo.action(key("z", { metaKey: true, ctrlKey: false })), "undo");
  assert.strictEqual(undo.action(key("z", { altKey: true })), null);
  assert.strictEqual(undo.action(key("z", { ctrlKey: false })), null);
  assert.strictEqual(undo.action(key("Y", { shiftKey: true })), null);
  assert.strictEqual(undo.action(key("x")), null);
});

test("only text boxes count", () => {
  const { undo } = load();
  assert.ok(undo.editable(box("TEXTAREA")));
  assert.ok(undo.editable(box("INPUT", "")));
  assert.ok(undo.editable(box("INPUT", "search")));
  assert.ok(undo.editable(box("DIV", "", { isContentEditable: true })));
  assert.ok(!undo.editable(box("INPUT", "range")));
  assert.ok(!undo.editable(box("INPUT", "checkbox")));
  assert.ok(!undo.editable(box("TEXTAREA", "", { readOnly: true })));
  assert.ok(!undo.editable(box("INPUT", "text", { disabled: true })));
  assert.ok(!undo.editable(box("CANVAS")));
  assert.ok(!undo.editable(null));
});

test("a key press in a text box runs the editing command", () => {
  const { calls, listener } = load();
  const e = key("z");
  listener(e);
  listener(key("Z", { shiftKey: true }));
  listener(key("y"));
  assert.deepStrictEqual(calls, ["undo", "redo", "redo"]);
  assert.ok(e.prevented);
});

test("a page's own undo and other targets are left alone", () => {
  const { calls, listener } = load();
  listener(key("z", { defaultPrevented: true }));
  listener(key("z", { isComposing: true }));
  listener(key("z", {}, box("CANVAS")));
  listener(key("a"));
  assert.deepStrictEqual(calls, []);
});

test("loading it twice binds the keys once", () => {
  const { undo } = load();
  const win = { ForgeUndo: undo, addEventListener: () => assert.fail("bound twice") };
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, "..", "shared", "forge_undo.js"), "utf8"), { window: win, document: {} });
});
