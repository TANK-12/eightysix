const test = require("node:test");
const assert = require("node:assert");
const { unwrap } = require("../static/docs_text.js");

test("wrapped paragraph lines join into one", () => {
  assert.strictEqual(unwrap("This folder is where\nimportant docs go.\n\nNext one."),
    "This folder is where important docs go.\n\nNext one.");
});

test("list items keep their breaks, wrapped item text joins its item", () => {
  assert.strictEqual(unwrap("- one folder per topic. Make a new\n  folder when none fits.\n- dated names\n1. first\n2. second"),
    "- one folder per topic. Make a new folder when none fits.\n- dated names\n1. first\n2. second");
});

test("headings, tables and code are left alone", () => {
  const src = "# Title\nfirst line\n| a | b |\n| - | - |\n```\ncode line\nmore code\n```\nafter";
  assert.strictEqual(unwrap(src), "# Title\nfirst line\n| a | b |\n| - | - |\n```\ncode line\nmore code\n```\nafter");
});

test("front matter becomes a yaml block", () => {
  assert.strictEqual(unwrap("---\nname: x\ndescription: y\n---\n\nBody\ntext"),
    "```yaml\nname: x\ndescription: y\n```\n\nBody text");
});

test("empty input", () => {
  assert.strictEqual(unwrap(""), "");
  assert.strictEqual(unwrap(null), "");
});
