/*
 * The simple editor: one page, four steps, in the order the work actually
 * happens.
 *
 * The full editor can do everything, which is exactly why it is hard to start
 * in: Compose alone had twenty-one controls with no order implied between them.
 * This page asks for the four things a background-music video actually needs --
 * music, pictures, a look, a title -- picks sensible defaults for the rest, and
 * gets out of the way.
 *
 * It writes the *same* project fields as the full editor and calls the same
 * endpoints. There is no second data model, so anything set here can be opened
 * and refined in Advanced, and "Fine-tune this shot" does exactly that. Nothing
 * here is a dead end.
 */
(function (global) {
  "use strict";

  const el = (t, c, h) => Controls.el(t, c, h);
  const S = { presets: [], grades: [], ambience: [], busy: false };
  global.SimpleState = S;

  async function jget(u) {
    const r = await fetch(u);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function jpost(u, body) {
    const r = await fetch(u, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  const slug = () => encodeURIComponent(global.PROJECT.slug);
  const toast = (m, k) => (global.toast ? global.toast(m, k) : console.log(m));

  // ---------------------------------------------------------------- step 1
  function renderMusic() {
    const box = document.getElementById("smSongs");
    const songs = PROJECT.data.playlist || [];
    const cards = PROJECT.data.cards || [];
    box.innerHTML = songs.length
      ? ""
      : '<p class="muted">No music yet. Add one track or twenty — they play in order.</p>';
    songs.forEach((name, i) => {
      const row = el("div", "sm-row");
      row.innerHTML =
        `<span class="sm-num">${i + 1}</span>` +
        `<input class="sm-title" value="${(cards[i] || {}).title || ""}" ` +
        `placeholder="${name}" data-i="${i}">`;
      const up = el("button", "btn btn-sm", "↑");
      up.disabled = i === 0;
      up.onclick = () => move(i, i - 1);
      const down = el("button", "btn btn-sm", "↓");
      down.disabled = i === songs.length - 1;
      down.onclick = () => move(i, i + 1);
      const rm = el("button", "sc-x", "×");
      rm.onclick = async () => {
        Object.assign(
          PROJECT.data,
          await jpost(`/api/projects/${slug()}/songs/remove`, { name })
        );
        refresh();
      };
      row.appendChild(up);
      row.appendChild(down);
      row.appendChild(rm);
      box.appendChild(row);
    });
    box.querySelectorAll(".sm-title").forEach((inp) => {
      inp.onchange = () => {
        const i = +inp.dataset.i;
        PROJECT.data.cards = PROJECT.data.cards || [];
        while (PROJECT.data.cards.length <= i) PROJECT.data.cards.push({});
        PROJECT.data.cards[i].title = inp.value;
        save({ cards: PROJECT.data.cards });
      };
    });
  }

  async function move(from, to) {
    const order = (PROJECT.data.playlist || []).slice();
    if (to < 0 || to >= order.length) return;
    [order[from], order[to]] = [order[to], order[from]];
    Object.assign(PROJECT.data, await jpost(`/api/projects/${slug()}/songs/order`, { order }));
    refresh();
  }

  // ---------------------------------------------------------------- step 2
  function renderPictures() {
    const box = document.getElementById("smShots");
    const shots = (PROJECT.data.shots || []).filter((s) => s.kind !== "card");
    box.innerHTML = shots.length
      ? ""
      : '<p class="muted">No pictures yet. Each one you add becomes a scene in the video.</p>';
    shots.forEach((shot) => {
      const idx = (PROJECT.data.shots || []).indexOf(shot);
      const tile = el("div", "sm-tile");
      if (shot.image) {
        const img = el("img");
        img.src = `/api/projects/${slug()}/asset-file?name=${encodeURIComponent(shot.image)}`;
        img.alt = shot.image;
        img.onerror = () => { img.style.display = "none"; };
        tile.appendChild(img);
      }
      tile.appendChild(el("span", null, shot.image || "no picture"));
      const tune = el("button", "btn btn-sm", "Fine-tune →");
      tune.title = "Open this scene in the full editor";
      tune.onclick = () => global.openInAdvanced(idx);
      const rm = el("button", "sc-x", "×");
      rm.onclick = () => {
        PROJECT.data.shots.splice(idx, 1);
        save({ shots: PROJECT.data.shots });
        refresh();
      };
      tile.appendChild(tune);
      tile.appendChild(rm);
      box.appendChild(tile);
    });
  }

  // ---------------------------------------------------------------- step 3
  function renderLook() {
    const grid = document.getElementById("smPresets");
    const current = (PROJECT.data.shots || [])[0] || {};
    grid.innerHTML = "";
    for (const p of S.presets) {
      const b = el("button", "sc-preset" + (current.preset === p.id ? " on" : ""));
      b.innerHTML = `<strong>${p.label}</strong><span>${p.description}</span>`;
      b.onclick = () => applyLook({ preset: p.id });
      grid.appendChild(b);
    }
    const grade = document.getElementById("smGrade");
    if (!grade.options.length) {
      grade.innerHTML = S.grades
        .map((g) => `<option value="${g.id}">${g.label}</option>`)
        .join("");
    }
    grade.value = (current.look || {}).grade || "none";
    const amb = document.getElementById("smAmbience");
    if (!amb.options.length) {
      amb.innerHTML =
        '<option value="">No ambient sound</option>' +
        S.ambience.map((a) => `<option value="${a.id}">${a.label}</option>`).join("");
    }
    amb.value = (PROJECT.data.ambience || {}).bed || "";
  }

  async function applyLook(patch) {
    if (S.busy) return;
    if (!(PROJECT.data.shots || []).length) return toast("add a picture first", "err");
    S.busy = true;
    const note = document.getElementById("smLookNote");
    note.textContent = "applying to every scene…";
    try {
      const body = {
        preset: patch.preset || "",
        grade: patch.grade || "",
        grade_amount: 0.7,
        auto_regions: true,
      };
      const res = await jpost(`/api/projects/${slug()}/apply-look-to-all`, body);
      PROJECT.data.shots = res.shots;
      note.textContent = `applied to ${res.touched} scene(s)`;
      renderLook();
      refreshStill();
    } catch (e) {
      note.textContent = String(e).replace(/^Error:\s*/, "").slice(0, 160);
    }
    S.busy = false;
  }

  let stillTimer = null;
  function refreshStill(delay) {
    clearTimeout(stillTimer);
    stillTimer = setTimeout(doStill, delay === undefined ? 150 : delay);
  }

  async function doStill() {
    const img = document.getElementById("smStill");
    // prefer an actual picture: a title card previews as a near-black frame,
    // which tells you nothing about the look you just chose
    const shots = PROJECT.data.shots || [];
    const shot = shots.find((x) => x.kind !== "card" && x.image) || shots[0];
    if (!shot) {
      img.hidden = true;
      return;
    }
    try {
      const r = await fetch(`/api/projects/${slug()}/still`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ shot, t: 2.0, width: 760 }),
      });
      if (!r.ok) return;
      const blob = await r.blob();
      if (img.dataset.url) URL.revokeObjectURL(img.dataset.url);
      const url = URL.createObjectURL(blob);
      img.dataset.url = url;
      img.src = url;
      img.hidden = false;
    } catch (e) {
      /* the preview is a convenience */
    }
  }

  // ---------------------------------------------------------------- step 4
  function renderFinish() {
    setVal("smTitle", (PROJECT.data.cards || [])[0]?.title || PROJECT.data.name || "");
    const hours = (PROJECT.data.target_seconds || 0) / 3600;
    setVal("smLength", [0, 1, 2, 3].includes(hours) ? String(hours) : "0");
  }

  async function save(patch) {
    const r = await fetch(`/api/projects/${slug()}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (r.ok) global.PROJECT = await r.json();
  }

  function refresh() {
    if (!global.PROJECT) return;
    renderMusic();
    renderPictures();
    renderLook();
    renderFinish();
    refreshStill(300);
    const ready = (PROJECT.data.playlist || []).length && (PROJECT.data.shots || []).length;
    document.getElementById("smMake").disabled = !ready;
    document.getElementById("smReadyNote").textContent = ready
      ? ""
      : "Add at least one track and one picture first.";
  }

  // ------------------------------------------------------------------ init
  async function open(project) {
    global.PROJECT = project;
    if (!S.presets.length) {
      [S.presets, S.grades, S.ambience] = await Promise.all([
        jget("/api/presets"),
        jget("/api/grades"),
        jget("/api/ambience"),
      ]);
    }
    // simple mode picks the things you would otherwise have to know about
    const wants = {};
    if (!PROJECT.data.song_crossfade) wants.song_crossfade = 1.5;
    if (PROJECT.data.scene !== "living") wants.scene = "living";
    if (Object.keys(wants).length) await save(wants);
    refresh();
  }

  function mount() {
    document.getElementById("smSongUp").onclick = async () => {
      const files = Array.from(document.getElementById("smSongFile").files || []);
      if (!files.length) return toast("pick some audio first", "err");
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch(`/api/projects/${slug()}/songs`, { method: "POST", body: fd });
        if (!r.ok) return toast(await errText(r, "upload failed"), "err");
        Object.assign(PROJECT.data, await r.json());
      }
      toast(files.length > 1 ? `${files.length} tracks added` : "track added", "ok");
      refresh();
    };

    document.getElementById("smLevel").onclick = async (e) => {
      const btn = e.target;
      btn.disabled = true;
      const before = btn.textContent;
      btn.textContent = "measuring…";
      try {
        const r = await jpost(`/api/projects/${slug()}/level-playlist`);
        PROJECT.data.song_gain = r.gains;
        toast(r.spread_before > 0.5 ? `evened out ${r.spread_before} dB` : "already even", "ok");
      } catch (err) {
        toast(String(err).replace(/^Error:\s*/, ""), "err");
      }
      btn.textContent = before;
      btn.disabled = false;
    };

    document.getElementById("smPicUp").onclick = async () => {
      const files = Array.from(document.getElementById("smPicFile").files || []);
      if (!files.length) return toast("pick some pictures first", "err");
      const added = [];
      for (const f of files) {
        const fd = new FormData();
        fd.append("file", f);
        const r = await fetch(`/api/projects/${slug()}/asset`, { method: "POST", body: fd });
        if (!r.ok) return toast(await errText(r, "upload failed"), "err");
        const res = await r.json();
        added.push(res.added);   // the stored filename, which may be slugified
      }
      // one picture, one scene -- the whole of step 2
      const res = await jpost(`/api/projects/${slug()}/shots-from-images`, {
        images: added, hold: 20, transition: "dissolve", transition_s: 1.5,
      });
      PROJECT.data.shots = res.shots;
      toast(`${res.added} scene(s) added`, "ok");
      refresh();
    };

    document.getElementById("smGrade").onchange = (e) =>
      applyLook({ grade: e.target.value });

    document.getElementById("smAmbience").onchange = (e) => {
      PROJECT.data.ambience = {
        bed: e.target.value,
        level: (PROJECT.data.ambience || {}).level ?? 0.25,
      };
      save({ ambience: PROJECT.data.ambience });
    };

    document.getElementById("smTitle").onchange = (e) => {
      const title = e.target.value.trim();
      PROJECT.data.cards = PROJECT.data.cards || [];
      if (!PROJECT.data.cards.length) PROJECT.data.cards.push({});
      PROJECT.data.cards[0].title = title;
      save({ cards: PROJECT.data.cards });
    };

    document.getElementById("smLength").onchange = (e) => {
      PROJECT.data.target_seconds = (parseFloat(e.target.value) || 0) * 3600;
      save({ target_seconds: PROJECT.data.target_seconds });
    };

    document.getElementById("smAdvanced").onclick = () => global.openInAdvanced(0);
    document.getElementById("smMake").onclick = () => global.startRender();
  }

  global.Simple = { open, mount, refresh, state: S };
})(window);
