/* Microphone recording for every Forge page, as a 16 kHz mono 16-bit WAV.

   Pages record through Web Audio, not MediaRecorder: in Forge's WebKitGTK
   2.54 a real microphone track reports a sample rate of 0, MediaRecorder's
   encoder is set up for rate=0 and hands over 0 bytes, so a browser mic in
   Forge sent an empty recording and the voice service answered 400 "no
   audio" (measured 2026-10-08 with a PipeWire test mic; WebKit's mock mic
   reports 44100, which is why mock-mic tests passed). An AudioContext reads
   the same track fine.

   ForgeMic.supported()                    -> whether this page can record
   ForgeMic.start({maxSeconds, onLevel, onLimit}) -> promise of a recording:
       rec.stop()    -> promise of a WAV Blob (audio/wav); frees the mic
       rec.cancel()  -> drops the recording and frees the mic
       rec.seconds() -> how much has been kept so far
       rec.peak      -> loudest sample so far, 0 to 1
       rec.silent()  -> true when the mic gave only silence (muted or dead)
       rec.rate      -> the rate the page records at (the WAV is 16 kHz)
     onLevel(0..1) is called about ten times a second while recording;
     onLimit() once when maxSeconds (default 110, under the voice service's
     120 s cap) is reached, after which nothing more is kept.

   The pure parts (downsample, encodeWav, level) take no browser and are
   tested with node --test (forge_mic.test.js). Loaded by pages as a plain
   script (window.ForgeMic) and by node as a CommonJS module. */
(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  else root.ForgeMic = api;
})(typeof self !== "undefined" ? self : this, function () {
  "use strict";

  const RATE = 16000; // what whisper reads; also keeps uploads small
  const SILENT = 1e-4; // a peak below this (-80 dBFS) is a muted or dead mic

  // --- pure helpers ---------------------------------------------------------

  /* Joins Float32Array chunks recorded at `from` Hz into one Float32Array at
     `to` Hz; each output sample is the mean of the input samples it covers (a
     box filter, enough to keep speech clean for speech to text). A rate at or
     below `to` is only joined. Returns {samples, rate}. */
  function downsample(chunks, from, to) {
    let n = 0;
    for (const c of chunks) n += c.length;
    const all = new Float32Array(n);
    let at = 0;
    for (const c of chunks) {
      all.set(c, at);
      at += c.length;
    }
    if (!(from > to)) return { samples: all, rate: from };
    const ratio = from / to;
    const out = new Float32Array(Math.floor(n / ratio));
    for (let i = 0; i < out.length; i++) {
      const a = Math.floor(i * ratio);
      const b = Math.min(n, Math.floor((i + 1) * ratio));
      let sum = 0;
      for (let j = a; j < b; j++) sum += all[j];
      out[i] = b > a ? sum / (b - a) : all[a];
    }
    return { samples: out, rate: to };
  }

  /* A mono 16-bit PCM WAV file (ArrayBuffer) holding `samples` (-1..1). */
  function encodeWav(samples, rate) {
    const buf = new ArrayBuffer(44 + samples.length * 2);
    const v = new DataView(buf);
    const text = (at, s) => {
      for (let i = 0; i < s.length; i++) v.setUint8(at + i, s.charCodeAt(i));
    };
    text(0, "RIFF");
    v.setUint32(4, 36 + samples.length * 2, true);
    text(8, "WAVE");
    text(12, "fmt ");
    v.setUint32(16, 16, true); // fmt chunk size
    v.setUint16(20, 1, true); // PCM
    v.setUint16(22, 1, true); // mono
    v.setUint32(24, rate, true);
    v.setUint32(28, rate * 2, true); // bytes per second
    v.setUint16(32, 2, true); // bytes per frame
    v.setUint16(34, 16, true); // bits per sample
    text(36, "data");
    v.setUint32(40, samples.length * 2, true);
    for (let i = 0, at = 44; i < samples.length; i++, at += 2) {
      const x = Math.max(-1, Math.min(1, samples[i]));
      v.setInt16(at, Math.round(x < 0 ? x * 0x8000 : x * 0x7fff), true);
    }
    return buf;
  }

  /* The loudest sample in a block, 0 to 1. */
  function level(block) {
    let peak = 0;
    for (let i = 0; i < block.length; i++) {
      const a = Math.abs(block[i]);
      if (a > peak) peak = a;
    }
    return Math.min(1, peak);
  }

  // --- browser --------------------------------------------------------------

  function audioContextClass() {
    if (typeof window === "undefined") return null;
    return window.AudioContext || window.webkitAudioContext || null;
  }

  function supported() {
    return !!(
      typeof navigator !== "undefined" &&
      navigator.mediaDevices &&
      navigator.mediaDevices.getUserMedia &&
      audioContextClass()
    );
  }

  function withLimit(promise, seconds, why) {
    let timer = null;
    const late = new Promise((_, reject) => {
      timer = setTimeout(() => reject(new Error(why)), seconds * 1000);
    });
    return Promise.race([promise, late]).finally(() => clearTimeout(timer));
  }

  async function start(opts) {
    const o = opts || {};
    const Ctx = audioContextClass();
    if (!Ctx || !supported()) throw new Error("this page cannot record sound");
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    let ctx = null;
    let source = null;
    let proc = null;
    let closed = false;
    // every way out lets go of the microphone, even when setting up failed
    const close = () => {
      if (closed) return Promise.resolve();
      closed = true;
      try {
        if (proc) proc.disconnect();
        if (source) source.disconnect();
      } catch (e) {
        /* already disconnected */
      }
      stream.getTracks().forEach((t) => t.stop());
      if (!ctx) return Promise.resolve();
      // a stuck sound system may never finish closing: never wait on it for long
      const done = new Promise((ok) => ok(ctx.close()));
      return withLimit(done, o.closeSeconds || 2, "close").catch(() => {});
    };
    try {
      ctx = new Ctx();
      source = ctx.createMediaStreamSource(stream);
      proc = ctx.createScriptProcessor(4096, 1, 1);
    } catch (e) {
      await close();
      throw e;
    }
    const cap = Math.round((o.maxSeconds || 110) * ctx.sampleRate);
    const chunks = [];
    let kept = 0;
    let limited = false;
    let result = null;
    const rec = { peak: 0 };

    proc.onaudioprocess = (e) => {
      if (closed || kept >= cap) return;
      const block = e.inputBuffer.getChannelData(0);
      const lv = level(block);
      if (lv > rec.peak) rec.peak = lv;
      if (o.onLevel) o.onLevel(lv);
      const take = Math.min(block.length, cap - kept);
      chunks.push(block.slice(0, take)); // a copy: the browser reuses the block
      kept += take;
      if (kept >= cap && !limited) {
        limited = true;
        if (o.onLimit) o.onLimit();
      }
    };
    try {
      source.connect(proc);
      proc.connect(ctx.destination); // a ScriptProcessor only runs while connected; it outputs silence
      if (ctx.state === "suspended") {
        await withLimit(ctx.resume(), o.startSeconds || 3, "the microphone did not start; press again");
      }
    } catch (e) {
      await close();
      throw e;
    }

    rec.rate = ctx.sampleRate;
    rec.silent = () => rec.peak < SILENT;
    rec.seconds = () => kept / ctx.sampleRate;
    rec.cancel = () => {
      close();
    };
    rec.stop = () => {
      if (!result)
        result = close().then(() => {
          const { samples, rate } = downsample(chunks, ctx.sampleRate, RATE);
          return new Blob([encodeWav(samples, rate)], { type: "audio/wav" });
        });
      return result;
    };
    return rec;
  }

  return { RATE, SILENT, downsample, encodeWav, level, supported, start };
});
