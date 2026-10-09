/* The JavaScript side of the agreement sweep in test_glyphs.py: reads
 * {"cases": [{src, t, n}], "seeds": [int]} on stdin and prints, for every
 * case, either {show, values} or {error: {message, col}}, and compose(seed)
 * for every seed. Not a node --test file; pytest runs it. */
import { parse, show, frame, GlyphError } from "../lang.js";
import { compose } from "../compose.js";

let text = "";
for await (const chunk of process.stdin) text += chunk;
const job = JSON.parse(text);
const cases = job.cases.map(({ src, t, n }) => {
  try {
    const ast = parse(src);
    return { show: show(ast), values: frame(src, t, n) };
  } catch (e) {
    if (e instanceof GlyphError) return { error: { message: e.message, col: e.col } };
    throw e;
  }
});
const seeds = job.seeds.map((s) => compose(s));
process.stdout.write(JSON.stringify({ cases, seeds }));
