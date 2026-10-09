// Prints what the browser side computes for the cases on stdin, so
// tests/test_agree.py can hold Python's mirror of it to the same answers.
// Input: {genomes, plants: [{plant, now_ms, max_gen}], strings, rule_texts}.
import { readFileSync } from "node:fs";
import { createHash } from "node:crypto";
import * as L from "../lsys.js";
import { genomeOk, parseRules } from "../words.js";

const sha = (text) => createHash("sha1").update(text).digest("hex");
const cases = JSON.parse(readFileSync(0, "utf8"));

const genomes = cases.genomes.map((g) => {
  const top = L.effectiveMaxGen(g);
  const steps = [];
  for (let gen = 0; gen <= Math.min(g.max_gen, 8) + 1; gen++) {
    const e = L.expand(g, gen);
    steps.push({ gen: e.gen, len: e.str.length, str: sha(e.str), fresh: sha(Array.from(e.fresh).join("")) });
  }
  const { str, fresh } = L.expand(g, top);
  const t = L.turtle(g, str, fresh, 1);
  let flowers = 0;
  for (let i = 5; i < t.buds.length; i += L.BUD) flowers += t.buds[i];
  return {
    top,
    steps,
    turtle: {
      segs: t.segs.reduce((n, s) => n + s.length / 5, 0),
      buds: t.buds.length / L.BUD,
      flowers,
      minX: t.minX,
      maxX: t.maxX,
      maxY: t.maxY,
    },
  };
});
const stages = cases.plants.map((c) => L.growthStage(c.plant, c.now_ms, c.max_gen));
const ok = cases.strings.map((s) => genomeOk(s));
const rules = cases.rule_texts.map((t) => {
  const r = parseRules(t);
  return typeof r === "string" ? null : r;
});
process.stdout.write(JSON.stringify({ genomes, stages, ok, rules }));
