// node --test tests/markdown.test.js  (run by tests/test_enjoy_js.py too)
// The answer renderer (shared/forge_convo.js, loaded through claude_common.js): Markdown tables (look critic #5,
// 2026-10-07), and that lists, headings and plain lines still come out.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const sandbox = { window: {}, document: {}, console };
for (const file of ["../../../shared/forge_convo.js", "../static/claude_common.js"]) {
  vm.runInNewContext(fs.readFileSync(path.join(__dirname, file), "utf8"), sandbox);
}
const md = sandbox.window.ClaudeCommon.markdown;

test("a pipe table with a rule line becomes a table, aligned", () => {
  const html = md("Here:\n\n| Name | Tokens |\n|:-----|------:|\n| System **prompt** | 7.1k |\n| Free | 173k |\n\nafter");
  assert.match(html, /<div class="table-wrap"><table><thead><tr>/);
  assert.match(html, /<th>Name<\/th>|<th[^>]*>Name<\/th>/);
  assert.match(html, /<td style="text-align:right">7\.1k<\/td>/);
  assert.match(html, /<td>System <strong>prompt<\/strong><\/td>/);
  assert.strictEqual((html.match(/<tr>/g) || []).length, 3);
  assert.match(html, /^<p>Here:<\/p>/);
  assert.match(html, /<p>after<\/p>$/);
});

test("pipes without a rule line stay plain text, and escape HTML", () => {
  const html = md("| not <b>a</b> table |\nnext");
  assert.ok(!html.includes("<table>"));
  assert.match(html, /&lt;b&gt;/);
});

test("a table right after a list ends the list", () => {
  const html = md("- one\n- two\n| a | b |\n|---|---|\n| 1 | 2 |");
  assert.match(html, /<ul><li>one<\/li><li>two<\/li><\/ul><div class="table-wrap">/);
});

test("lists, headings and code still render", () => {
  const html = md("## Head\n1. a\n2. b\n\n```js\nx < 1\n```");
  assert.match(html, /<h3>Head<\/h3><ol><li>a<\/li><li>b<\/li><\/ol><pre><code>x &lt; 1\n<\/code><\/pre>/);
});
