import { test } from "node:test";
import assert from "node:assert/strict";
import { nextIndex } from "../../static/js/music.js";
import { SETTINGS, defaults, clean } from "../../static/js/settings.js";

test("the playlist goes round and round", () => {
  assert.deepEqual([0, 1, 2].map((i) => nextIndex(i, 3)), [1, 2, 0]);
  assert.equal(nextIndex(0, 0), 0);
});

test("music volume is a setting of its own, kept apart from sound", () => {
  const row = SETTINGS.find((s) => s.key === "music");
  assert.ok(row && row.kind === "range" && row.min === 0 && row.max === 100);
  assert.equal(defaults().music, row.def);
  assert.equal(clean({ music: 250 }).music, 100);
  assert.equal(clean({ volume: 10 }).music, row.def);
});
