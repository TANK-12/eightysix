// The making sections: Make an image, Edit an image, Make a video.
// Each form sends one request per press and shows the answer beside it.
"use strict";
(function (AS) {
  const $ = AS.$, el = AS.el;

  // ---------------- picture picker (file, drop, or the library) ----------------
  // value: null | {image: dataURL, url} | {source_id, url}
  AS.picker = function (box, { onChange } = {}) {
    let value = null;
    const file = el("input", { type: "file", accept: "image/png,image/jpeg,image/webp", hidden: true });
    const api = {
      get value() { return value; },
      set(v) { value = v; paint(); if (onChange) onChange(v); },
    };
    async function fromFile(f) {
      if (!f || !/^image\//.test(f.type)) { AS.toast("That isn't a picture file."); return; }
      if (f.size > 25e6) { AS.toast("That picture is too big to send (over 25 MB)."); return; }
      try {
        const data = await AS.fileToDataURL(f);
        api.set({ image: data, url: data, name: f.name });
      } catch (e) { AS.toast(AS.failText(e)); }
    }
    file.addEventListener("change", () => { fromFile(file.files[0]); file.value = ""; });
    box.addEventListener("dragover", (e) => { e.preventDefault(); box.classList.add("drop"); });
    box.addEventListener("dragleave", () => box.classList.remove("drop"));
    box.addEventListener("drop", (e) => { e.preventDefault(); box.classList.remove("drop"); fromFile(e.dataTransfer.files[0]); });
    function paint() {
      const shown = value
        ? el("img", { className: "pick-thumb", src: value.url, alt: "Chosen picture" })
        : el("div", { className: "pick-empty" }, "No picture yet");
      const buttons = el("div", { className: "pick-buttons" },
        el("button", { type: "button", className: "btn", onclick: () => file.click() }, "Choose a file"),
        el("button", { type: "button", className: "btn", onclick: async () => {
          const item = await AS.library.pick();
          if (item) api.set({ source_id: item.id, url: item.url });
        } }, "From your library"),
        value ? el("button", { type: "button", className: "btn", onclick: () => api.set(null) }, "Remove") : null,
      );
      box.replaceChildren(shown, buttons, file);
    }
    paint();
    return api;
  };
  // The picture fields the server takes: a library result by its address,
  // or a chosen file as a data URL.
  AS.pictureFields = (v) => (!v ? {} : v.source_id ? { start_image_url: v.url } : { start_image: v.image });

  // ---------------- running one request ----------------
  // Disables the form's button until the answer, shows a ticking clock in
  // the result area, and shows the error in words when it fails.
  async function run(form, resultBox, goText, endpoint, body, kind, job) {
    const go = form.querySelector(".go");
    const errorEl = form.querySelector(".error");
    if (go.disabled) return;
    errorEl.textContent = "";
    const wait = AS.heavy.reason(form);
    if (wait) { errorEl.textContent = wait; return; }
    // a video holds a big model: the other sections wait until it is done
    if (job) AS.heavy.set("video", "A video is being made. Wait for it or cancel it first.", form);
    const stage = resultBox.querySelector(".stage");
    const stats = resultBox.querySelector(".stats");
    const actions = resultBox.querySelector(".result-actions");
    go.disabled = true;
    go.textContent = "Working...";
    const clock = el("div", { className: "stage-empty" }, el("div", { className: "spinner" }), el("div", { className: "clock" }, "Working..."), el("div", { className: "job-line" }));
    stage.replaceChildren(clock);
    stats.textContent = "";
    actions.replaceChildren();
    const started = Date.now();
    const tick = ForgeIdle.poll(() => {
      clock.querySelector(".clock").textContent = `Working... ${AS.seconds((Date.now() - started) / 1000)} so far.`;
    }, 1000);
    try {
      let data = await AS.post(endpoint, body, "It didn't work");
      if (job) data = await follow(job, data, clock);
      show(resultBox, data, kind);
      AS.emit("library-changed");
    } catch (e) {
      errorEl.textContent = AS.failText(e);
      stage.replaceChildren(el("div", { className: "stage-empty" }, e.status === 409
        ? "Nothing was started. The reason is under the button."
        : "That didn't work. The reason is under the button."));
    } finally {
      tick.stop();
      go.disabled = false;
      go.textContent = goText;
      if (job) AS.heavy.set("video", null);
      else AS.emit("heavy");
    }
  }

  // A long job (a video model): the first answer is the job; ask how it is
  // going every 2 s (resting while hidden) until it is done, failed or
  // cancelled. A Cancel button sits under the clock meanwhile.
  function follow(job, first, clock) {
    return new Promise((done, fail) => {
      const line = clock.querySelector(".job-line");
      let cancelling = false;
      const cancel = el("button", { type: "button", className: "btn", onclick: async () => {
        if (cancelling) return;
        cancelling = true;
        cancel.disabled = true;
        cancel.textContent = "Cancelling...";
        try { await AS.post(job.cancel(first.id), undefined, "Couldn't cancel it"); } catch (e) { AS.toast(AS.failText(e)); }
      } }, "Cancel");
      clock.append(cancel);
      const look = (snap) => {
        const r = job.read(snap);
        if (r.line) line.textContent = r.line;
        if (r.status === "done") { poll.stop(); done({ id: first.id, ...r.result }); return true; }
        if (r.status === "failed" || r.status === "cancelled") {
          poll.stop();
          fail(new Error(r.status === "cancelled" ? "Cancelled." : r.message || "It stopped part way."));
          return true;
        }
        return false;
      };
      const poll = ForgeIdle.poll(async () => {
        try { look(await AS.get(job.state(first.id), "The job didn't answer")); }
        catch (e) { if (e.status === 404) { poll.stop(); fail(e); } else return false; }
      }, 2000, { backoff: 2, maxMs: 15000 });
      look(first);
    });
  }

  function show(resultBox, data, kind) {
    const stage = resultBox.querySelector(".stage");
    const stats = resultBox.querySelector(".stats");
    const actions = resultBox.querySelector(".result-actions");
    const put = (item) => {
      stage.replaceChildren(AS.media(item.url, kind, { play: true, muted: true }));
      actions.replaceChildren(...AS.resultActions({ id: item.id, url: item.url, kind }));
    };
    put(data);
    if (data.batch && data.batch.length > 1) {
      const strip = el("div", { className: "batch" });
      data.batch.forEach((b, i) => {
        const img = el("img", { src: b.url, alt: `Picture ${i + 1}`, className: b.id === data.id ? "on" : "", onclick: () => {
          strip.querySelectorAll("img").forEach((x) => x.classList.toggle("on", x === img));
          put(b);
        } });
        strip.append(img);
      });
      stage.after(strip);
      resultBox.querySelectorAll(".batch").forEach((s) => { if (s !== strip) s.remove(); });
    } else {
      resultBox.querySelectorAll(".batch").forEach((s) => s.remove());
    }
    stats.textContent = statsText(data);
  }

  function statsText(d) {
    if (d.batch) {
      const gpu = d.workers?.gpu?.frames_done || 0, cpu = d.workers?.cpu?.frames_done || 0;
      return `${d.batch.length} pictures in ${AS.seconds(d.wall_seconds)} (graphics chip made ${gpu}, processor ${cpu}).`;
    }
    const parts = [];
    if (d.gen_seconds) parts.push(`making ${AS.seconds(d.gen_seconds)}`);
    if (d.upscale_seconds) parts.push(`making it bigger ${AS.seconds(d.upscale_seconds)}`);
    if (d.interpolate_seconds) parts.push(`smoothing ${AS.seconds(d.interpolate_seconds)}`);
    if (!d.total_seconds) return "";
    return `Done in ${AS.seconds(d.total_seconds)}` + (parts.length > 1 ? ` (${parts.join(", ")}).` : ".");
  }

  // Buttons under a finished picture or video, also used by the library viewer.
  AS.resultActions = function (item) {
    const out = [];
    if (item.kind === "image") {
      out.push(el("button", { type: "button", className: "btn", onclick: () => AS.edit.use(item) }, "Edit this picture"));
      out.push(el("button", { type: "button", className: "btn", onclick: () => AS.video.startFrom(item) }, "Make a video from it"));
    }
    out.push(el("a", { className: "btn", href: item.url, download: "", target: "_blank" }, "Save a copy"));
    return out;
  };

  function modelMissing(form, kind) {
    if (AS.models.active(kind)) return false;
    const words = { image: "picture", video: "video", world: "3D world" }[kind];
    form.querySelector(".error").textContent = AS.models.loaded
      ? `There is no ${words} model in use yet. Use the button at the top of this form to get or pick one.`
      : "Still checking which models are on this laptop. Try again in a moment.";
    return true;
  }
  const baseSize = (kind) => Number(AS.models.active(kind)?.default_width) || 512;

  // ---------------- Make an image ----------------
  (function image() {
    const form = $("imageForm"), result = $("imgResult");
    const shape = AS.chips($("imgShape"));
    const scale = AS.chips($("imgUpscaleScale"));
    const finish = AS.chips($("imgFinish"));
    const format = AS.chips($("imgFormat"));
    $("imgUpscale").addEventListener("change", (e) => { $("imgUpscaleRow").hidden = !e.target.checked; });
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const errorEl = form.querySelector(".error");
      const prompt = $("imgPrompt").value.trim();
      if (!prompt) { errorEl.textContent = "Write what the picture should show first."; return; }
      if (modelMissing(form, "image")) return;
      const body = {
        prompt,
        negative_prompt: $("imgNeg").value,
        seed: Math.max(-1, AS.num("imgSeed", -1)),
        upscale: $("imgUpscale").checked,
        upscale_scale: Number(scale.value),
        quality_upscale: finish.value === "sharp",
        output_format: format.value,
        jpg_quality: 92,
        batch_count: AS.num("imgCount", 1),
        ...AS.shapeSize(shape.value, baseSize("image")),
      };
      const w = AS.num("imgW", null), h = AS.num("imgH", null);
      if (w !== null) body.width = w;
      if (h !== null) body.height = h;
      const steps = AS.num("imgSteps", null);
      if (steps !== null) body.steps = steps;
      const cfg = AS.num("imgCfg", null, true);
      if (cfg !== null) body.cfg_scale = cfg;
      run(form, result, "Make the picture", "/api/generate/image", body, "image");
    });
  })();

  // ---------------- Edit an image ----------------
  AS.edit = (function edit() {
    const form = $("editForm"), result = $("editResult");
    const picker = AS.picker($("editPicker"));
    const words = (v) => (v < 0.3 ? "a little" : v < 0.55 ? "some" : v < 0.8 ? "a lot" : "almost everything");
    const strength = $("editStrength");
    const paintStrength = () => { $("editStrengthWords").textContent = words(Number(strength.value)); };
    strength.addEventListener("input", paintStrength);
    paintStrength();
    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const errorEl = form.querySelector(".error");
      if (!picker.value) { errorEl.textContent = "Choose the picture to change first."; return; }
      const prompt = $("editPrompt").value.trim();
      if (!prompt) { errorEl.textContent = "Write what it should look like now."; return; }
      if (modelMissing(form, "image")) return;
      run(form, result, "Change the picture", "/api/generate/edit", {
        prompt,
        negative_prompt: $("editNeg").value,
        strength: Math.min(0.95, Math.max(0.1, Number(strength.value) || 0.6)),
        seed: Math.max(-1, AS.num("editSeed", -1)),
        upscale: $("editUpscale").checked,
        ...AS.pictureFields(picker.value),
      }, "image");
    });
    return {
      use(item) {
        picker.set(item.id ? { source_id: item.id, url: item.url } : { image: item.url, url: item.url });
        AS.show("edit");
        $("editPrompt").focus();
      },
    };
  })();

  // ---------------- Make a video ----------------
  const MOTIONS = [
    ["static", "Still"], ["pan-left", "Pan left"], ["pan-right", "Pan right"], ["pan-up", "Pan up"],
    ["pan-down", "Pan down"], ["zoom-in", "Move closer"], ["zoom-out", "Move back"],
    ["orbit-cw", "Circle right"], ["orbit-ccw", "Circle left"],
  ];
  const motionChips = (box, value) => {
    box.dataset.value = value;
    box.replaceChildren(...MOTIONS.map(([v, t]) => el("button", { type: "button", dataset: { value: v } }, t)));
    return box;
  };

  // The camera-move video answers at once with a job; its state lives at
  // /api/jobs/{id}/state {status, phase, completed_frames, total_frames,
  // error, url, and the timings once done}.
  const PHASES = {
    keyframes: "Making the pictures", upscale: "Making them bigger",
    interpolate: "Smoothing the motion", encode: "Putting the video together",
  };
  const WARP_JOB = {
    state: (id) => `/api/jobs/${encodeURIComponent(id)}/state`,
    cancel: (id) => `/api/jobs/${encodeURIComponent(id)}/cancel`,
    read: (j) => ({
      status: j.status, message: j.error,
      line: [PHASES[j.phase], j.total_frames ? `${j.completed_frames || 0} of ${j.total_frames} done` : ""].filter(Boolean).join(": "),
      result: j,
    }),
  };

  AS.video = (function video() {
    const form = $("videoForm"), result = $("videoResult");
    const WAY_HINT = {
      model: "A video model makes real movement from your words. It is slow: a short clip can take many minutes.",
      warp: "Makes a few pictures with your picture model and moves the camera across them. Quicker, and works with any picture model.",
    };
    const way = AS.chips($("videoWay"), paintWay);
    function paintWay() {
      form.querySelectorAll(".way").forEach((w) => { w.hidden = w.dataset.way !== way.value; });
      $("videoWayHint").textContent = WAY_HINT[way.value];
    }
    paintWay();
    const picker = AS.picker($("mvPicker"));
    const length = AS.chips($("mvLength"));
    const mvShape = AS.chips($("mvShape"));
    const motion = AS.chips(motionChips($("wpMotion"), "static"));

    // storyboard scenes
    let scenes = [];
    const sceneList = $("sceneList");
    function paintScenes() {
      sceneList.replaceChildren(...scenes.map((s, i) => {
        const prompt = el("textarea", { rows: 2, maxLength: 4000, placeholder: "What happens in this scene", value: s.prompt,
          oninput: () => { s.prompt = prompt.value; } });
        const moves = motionChips(el("div", { className: "chips motions" }), s.motion);
        AS.chips(moves, (v) => { s.motion = v; });
        const frames = el("input", { type: "number", min: 1, max: 30, value: s.frames,
          oninput: () => { s.frames = parseInt(frames.value, 10) || 1; } });
        return el("div", { className: "scene-card" },
          el("div", { className: "scene-head" }, el("b", {}, `Scene ${i + 1}`),
            scenes.length > 1 ? el("button", { type: "button", className: "btn", onclick: () => { scenes.splice(i, 1); paintScenes(); } }, "Remove") : null),
          prompt,
          el("div", { className: "field" }, el("label", {}, "Camera move"), moves),
          el("div", { className: "field" }, el("label", {}, "Pictures in this scene"), frames),
        );
      }));
    }
    const addScene = () => { scenes.push({ prompt: "", frames: 6, motion: "static", strength: 0.32 }); paintScenes(); };
    $("addSceneBtn").addEventListener("click", addScene);
    $("wpStory").addEventListener("change", (e) => {
      $("wpSimple").hidden = e.target.checked;
      $("wpScenes").hidden = !e.target.checked;
      if (e.target.checked && !scenes.length) { addScene(); addScene(); }
    });

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const errorEl = form.querySelector(".error");
      errorEl.textContent = "";
      if (way.value === "model") {
        const prompt = $("mvPrompt").value.trim();
        if (!prompt) { errorEl.textContent = "Write what happens in the video first."; return; }
        if (modelMissing(form, "video")) return;
        run(form, result, "Make the video", "/api/generate/model-video", {
          prompt,
          negative_prompt: $("mvNeg").value,
          frames: Number(length.value),
          seed: Math.max(-1, AS.num("mvSeed", -1)),
          ...AS.shapeSize(mvShape.value, baseSize("video")),
          ...AS.pictureFields(picker.value),
        }, "video", {
          state: (id) => `/api/generate/model-video/${encodeURIComponent(id)}`,
          cancel: (id) => `/api/generate/model-video/${encodeURIComponent(id)}/cancel`,
          // {state running|done|failed|cancelled, message, step, steps, url, seconds}
          read: (j) => ({
            status: j.state, message: j.message,
            line: j.steps ? `Step ${j.step || 0} of ${j.steps}` : "",
            result: { ...j, total_seconds: j.seconds },
          }),
        });
        return;
      }
      if (modelMissing(form, "image")) return;
      const story = $("wpStory").checked;
      const body = {
        prompt: $("wpPrompt").value.trim(),
        negative_prompt: $("wpNeg").value,
        seed: Math.max(-1, AS.num("wpSeed", -1)),
        hold_frames: AS.num("wpHold", 8),
        fps: AS.num("wpFps", 12),
        use_cpu: $("wpCpu").checked,
        upscale: $("wpUpscale").checked,
      };
      const native = AS.models.active("image");
      if (native && native.default_width && native.default_height) {
        body.width = Number(native.default_width);
        body.height = Number(native.default_height);
      }
      if (story) {
        body.scenes = scenes.filter((s) => s.prompt.trim()).map((s) => ({
          prompt: s.prompt, negative_prompt: body.negative_prompt,
          frames: Math.min(30, Math.max(1, s.frames || 1)), motion: s.motion, strength: s.strength,
        }));
        if (!body.scenes.length) { errorEl.textContent = "Write at least one scene."; return; }
      } else {
        if (!body.prompt) { errorEl.textContent = "Write what the video should show first."; return; }
        body.motion = motion.value;
        body.keyframes = AS.num("wpKeys", 4);
        body.motion_strength = Math.min(0.9, Math.max(0.05, Number($("wpStrength").value) || 0.32));
      }
      run(form, result, "Make the video", "/api/generate/video", body, "video", WARP_JOB);
    });

    return {
      startFrom(item) {
        way.value = "model";
        paintWay();
        picker.set(item.id ? { source_id: item.id, url: item.url } : { image: item.url, url: item.url });
        AS.show("video");
        $("mvPrompt").focus();
      },
    };
  })();
})(window.AS);
