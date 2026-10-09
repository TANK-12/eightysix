// Appended to a copy of the REAL hub/index.html by run.sh. Measures the
// background music's Web Audio chain (Music.chain: leveller, volume past
// 100%, limiter; A27) by rendering sine tones through it in an offline audio
// context. Runs without --virtual-time-budget: offline rendering never
// finishes on Chrome's virtual clock.
addEventListener("load", () => setTimeout(async () => {
  const out = [];
  const T = (name, ok, extra) =>
    out.push((ok ? "PASS" : "FAIL") + " :: " + name + (extra !== undefined ? " :: " + extra : ""));
  try {
    // --- the leveller, measured -------------------------------------------------------------
    const rate = 44100;
    const measure = async (amp, pct, level) => {
      const ctx = new OfflineAudioContext(1, rate, rate);
      const osc = ctx.createOscillator();
      osc.frequency.value = 220;
      const a = ctx.createGain();
      a.gain.value = amp;
      const chain = Music.chain(ctx);
      chain.set(pct, level);
      osc.connect(a);
      a.connect(chain.input);
      chain.output.connect(ctx.destination);
      osc.start();
      const buf = await ctx.startRendering();
      const x = buf.getChannelData(0).subarray(rate / 2); // settled half
      let sum = 0, peak = 0;
      for (const v of x) { sum += v * v; peak = Math.max(peak, Math.abs(v)); }
      return { db: 10 * Math.log10(sum / x.length), peak };
    };
    const quietOn = await measure(0.03, 100, true), loudOn = await measure(0.6, 100, true);
    const quietOff = await measure(0.03, 100, false), loudOff = await measure(0.6, 100, false);
    const gapOn = loudOn.db - quietOn.db, gapOff = loudOff.db - quietOff.db;
    T("without levelling the gap stays about 26 dB", Math.abs(gapOff - 26) < 1, gapOff.toFixed(1));
    T("levelling shrinks a 26 dB gap to under 12 dB", gapOn < 12, gapOn.toFixed(1));
    T("levelling lifts the quiet track", quietOn.db > quietOff.db + 6, `${quietOff.db.toFixed(1)} -> ${quietOn.db.toFixed(1)}`);
    const boosted = await measure(0.6, 200, false);
    T("200% of a loud track does not clip", boosted.peak <= 1.0, boosted.peak.toFixed(3));
    const quietBoost = await measure(0.03, 200, false);
    T("200% really is louder on a quiet track", quietBoost.db > quietOff.db + 5, `${quietOff.db.toFixed(1)} -> ${quietBoost.db.toFixed(1)}`);
  } catch (e) {
    T("the harness ran without throwing", false, String(e && e.stack || e));
  }
  const esc = (t) => t.replace(/&/g, "&amp;").replace(/</g, "&lt;");
  document.body.innerHTML = "<pre id='results'>RESULTS\n" + esc(out.join("\n")) + "\n</pre>";
}, 150));
