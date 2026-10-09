const test = require("node:test");
const assert = require("node:assert");
const T = require("./forge_session_title.js");

test("a relay session reads as task number and short description", () => {
  const s = { id: "x", name: "relay-109-work", label: "Yui", relay: { task: 109, title: "Mission Control conversation view: part one, the long tail" } };
  assert.equal(T.displayName(s), "#109 Mission Control conversation view");
  assert.equal(T.personaTag(s), "Yui");
});
test("a name alone marks a relay run; neither falls back to the persona or id", () => {
  assert.equal(T.displayName({ name: "relay-5-work", label: "Rin" }), "#5 Rin");
  assert.equal(T.displayName({ id: "abcdef123456" }), "abcdef12");
});
