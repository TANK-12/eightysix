"""Voices, script, SFX, music and the mixing hand-off. See CONTRACTS.md
"audio" and panelforge/audio/mix.py for mix_timeline, which helper-5's
render module calls.
"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

import forge_jan  # shared Jan client (sys.path set by web_app)

from .. import jobs, paths, store
from ..audio import cache, dsp, emotion, kokoro_engine, policy
from ..audio import script as script_mod
from ..audio import voices as voices_mod
from ..music import generate as music_generate
from ..music import plan as music_plan
from ..music import library as music_library
from ..sfx import library as sfx_library
from ..sfx import match as sfx_match
from ..sfx import recipes as sfx_recipes

router = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers --
def _cast_path(series: str) -> Path:
    return paths.series_dir(series) / "cast.json"


def _load_cast(series: str) -> dict | None:
    return store.read(_cast_path(series), None)


def _blank_cast() -> dict:
    return {
        "schema": 1,
        "cast": [],
        "narrator": {"voice": None},
        "extras": [],
        "backgrounds": [],
        "props": [],
    }


def _voice_for_speaker(cast_doc: dict | None, speaker: str | None) -> dict | None:
    if not speaker or not cast_doc:
        return None
    if speaker == "narrator":
        return (cast_doc.get("narrator") or {}).get("voice")
    for c in cast_doc.get("cast", []):
        if c.get("id") == speaker:
            return c.get("voice")
    return None


def _wav_response(samples: np.ndarray, sr: int) -> Response:
    buf = io.BytesIO()
    import wave

    stereo = dsp.to_stereo(samples)
    ints = (np.clip(stereo, -1.0, 1.0) * 32767.0).astype("<i2")
    with wave.open(buf, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(ints.tobytes())
    return Response(content=buf.getvalue(), media_type="audio/wav")


def _script_path(series: str, chapter: str) -> Path:
    return paths.chapter_dir(series, chapter) / "script.json"


def _blank_script() -> dict:
    return {"schema": 1, "lines": [], "sfx": [], "music": []}


# ------------------------------------------------------------------ voices #
@router.get("/voices")
def list_voices():
    err = kokoro_engine.load_error()
    names = kokoro_engine.voice_names()
    return {
        "voices": voices_mod.catalog(names),
        "available": kokoro_engine.available(),
        "error": err,
    }


class AuditionReq(BaseModel):
    voice: str
    text: str
    kind: str = "speech"
    speed: float | None = None


@router.post("/voices/audition")
def audition_voice(req: AuditionReq):
    if not kokoro_engine.available():
        raise HTTPException(503, kokoro_engine.load_error() or "Kokoro not available")
    em = emotion.rules_for(req.text, req.kind)
    speed = req.speed if req.speed is not None else em["speed"]
    text = emotion.normalize_text(req.text)
    try:
        samples, sr = kokoro_engine.synthesize_line(text, req.voice, em)
    except Exception as e:
        raise HTTPException(400, f"{type(e).__name__}: {e}")
    samples = emotion.apply(samples, sr, em)
    samples = dsp.limiter(samples, ceiling=0.98)
    return _wav_response(samples, sr)


class VoiceChoice(BaseModel):
    kokoro: str
    speed: float = 1.0
    pitch: float = 0.0
    gain_db: float = 0.0


@router.put("/series/{series}/cast/{cast_id}/voice")
def set_cast_voice(series: str, cast_id: str, voice: VoiceChoice):
    doc = _load_cast(series)
    if doc is None:
        raise HTTPException(
            404,
            "cast.json does not exist yet for this series -- run scene analysis first",
        )
    found = False
    for c in doc.get("cast", []):
        if c.get("id") == cast_id:
            c["voice"] = voice.model_dump()
            found = True
            break
    if not found:
        raise HTTPException(404, f"no cast member {cast_id!r} in cast.json")
    store.write(_cast_path(series), doc)
    return {"ok": True, "cast_id": cast_id, "voice": voice.model_dump()}


@router.put("/series/{series}/narrator/voice")
def set_narrator_voice(series: str, voice: VoiceChoice):
    doc = _load_cast(series) or _blank_cast()
    doc.setdefault("narrator", {})["voice"] = voice.model_dump()
    store.write(_cast_path(series), doc)
    return {"ok": True, "voice": voice.model_dump()}


# ------------------------------------------------------------ sound policy #
class SoundPolicy(BaseModel):
    echo: str | None = None  # none, comms or scene
    sfx: bool | None = None
    music: bool | None = None


@router.get("/sound")
def get_sound_policy():
    return policy.read()


@router.put("/sound")
def put_sound_policy(req: SoundPolicy):
    if req.echo is not None and req.echo not in policy.ECHO_MODES:
        raise HTTPException(400, f"echo must be one of {policy.ECHO_MODES}")
    return policy.write({k: v for k, v in req.model_dump().items() if v is not None})


# ------------------------------------------------------------------ script #
@router.get("/chapters/{series}/{chapter}/script")
def get_script(series: str, chapter: str):
    return store.read(_script_path(series, chapter), _blank_script())


@router.put("/chapters/{series}/{chapter}/script")
def put_script(series: str, chapter: str, doc: dict):
    doc.setdefault("schema", 1)
    store.write(_script_path(series, chapter), doc)
    return doc


@router.post("/chapters/{series}/{chapter}/script/build")
def build_script(series: str, chapter: str):
    cdir = paths.chapter_dir(series, chapter)

    def work(job):
        bubbles_doc = store.read(cdir / "bubbles.json", None)
        if bubbles_doc is None:
            job.log("no bubbles.json yet -- nothing to build from (run detect first)")
            bubbles_doc = {"bubbles": []}
        existing = store.read(_script_path(series, chapter), None)
        scene_doc = store.read(cdir / "scene.json", None)
        if scene_doc is None:
            job.log(
                "no scene.json yet -- lines get punctuation and lettering cues only"
            )
        new_script = script_mod.build_script(bubbles_doc, existing, scene_doc)
        store.write(_script_path(series, chapter), new_script)
        job.log(f"built {len(new_script['lines'])} lines")
        return {"lines": len(new_script["lines"])}

    job = jobs.start(
        "script-build",
        "Building script from bubbles",
        work,
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


def _image_chat(jan, model: str):
    """`chat_image(system, user, data_url) -> answer` through Jan: the
    picture goes as an OpenAI-style content part."""

    def chat_image(system: str, user: str, url: str) -> str:
        msgs = [
            {"role": "system", "content": system},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user},
                    {"type": "image_url", "image_url": {"url": url}},
                ],
            },
        ]
        with jan.using(model):
            return forge_jan.chat(
                model,
                "",
                "",
                temperature=0.1,
                max_tokens=300,
                timeout=600,
                extra={"messages": msgs},
            )

    return chat_image


class CastVoicesReq(BaseModel):
    only: list[str] | None = (
        None  # cast ids; None = everyone without a hand-chosen voice
    )


@router.post("/series/{series}/cast/voices/auto")
def cast_voices_auto(series: str, req: CastVoicesReq | None = None):
    """Let the model look at each character's card pictures and give every
    one without a hand-chosen voice a distinct, fitting Kokoro voice."""
    only = set(req.only) if req and req.only else None

    def work(job):
        import web_app

        from .. import janboot
        from ..audio import casting, llm_pass

        doc = _load_cast(series)
        if doc is None:
            raise RuntimeError("no cast.json -- run scene analysis first")
        if not janboot.ensure_router(job.log):
            raise RuntimeError(
                "Jan's model router is not running and could not be started"
            )
        model = web_app.jan.model_for(llm_pass.ROLE, llm_pass.DEFAULT_MODEL)
        job.log(f"model {model}")
        result = casting.cast_voices(
            doc,
            paths.series_dir(series),
            _image_chat(web_app.jan, model),
            kokoro_engine.voice_names(),
            job.log,
            check=job.check,
            only=only,
        )
        store.write(_cast_path(series), doc)
        return result

    job = jobs.start(
        "cast-voices",
        "Casting voices from the character pictures",
        work,
        lane="cpu",
        series=series,
    )
    return {"job_id": job.id}


class LlmReq(BaseModel):
    vision_only: bool = False  # skip the text pass, just look at the pictures
    vision_all: bool = False  # ask the picture for every line where 2+ stand


@router.post("/chapters/{series}/{chapter}/script/llm")
def llm_script(series: str, chapter: str, req: LlmReq | None = None):
    """Let the app's Jan model read the page: speakers, expressions, OCR fixes."""
    cdir = paths.chapter_dir(series, chapter)
    vision_only = bool(req and req.vision_only)
    vision_all = bool(req and req.vision_all)

    def work(job):
        import web_app  # the mounted Jan owner lives on the app

        from ..audio import llm_pass

        script = store.read(_script_path(series, chapter), None)
        if script is None:
            raise RuntimeError("no script.json -- run script/build first")
        bubbles_doc = store.read(cdir / "bubbles.json", {"bubbles": []})
        scene_doc = store.read(cdir / "scene.json", None)
        cast_doc = _load_cast(series)
        from .. import janboot

        if not janboot.ensure_router(job.log):
            raise RuntimeError(
                "Jan's model router is not running and could not be started"
            )
        model = web_app.jan.model_for(llm_pass.ROLE, llm_pass.DEFAULT_MODEL)
        job.log(f"model {model}")

        def chat(system: str, user: str) -> str:
            with web_app.jan.using(model):
                return forge_jan.chat(
                    model, system, user, temperature=0.2, max_tokens=1800, timeout=900
                )

        took = (
            {"speaker": 0, "expression": 0, "fix": 0, "delivery": 0}
            if vision_only
            else llm_pass.run(
                script,
                bubbles_doc,
                scene_doc,
                cast_doc,
                chat,
                job.log,
                check=job.check,
            )
        )

        chat_image = _image_chat(web_app.jan, model)
        panels = (store.read(cdir / "panels.json", {}) or {}).get("panels", [])
        took["vision_speaker"] = llm_pass.vision_pass(
            script,
            bubbles_doc,
            scene_doc,
            cast_doc,
            cdir,
            panels,
            chat_image,
            job.log,
            check=job.check,
            everyone=vision_all,
        )
        store.write(_script_path(series, chapter), script)
        return took

    job = jobs.start(
        "script-llm",
        "Reading the page with the local model",
        work,
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


# ------------------------------------------------------------- synthesis --#
def _effective_voice_and_emotion(
    line: dict, cast_doc: dict | None
) -> tuple[dict | None, dict, str]:
    """-> (voice choice dict or None, emotion dict, text). A per-line
    override always wins over the cast voice (new requirement)."""
    override = line.get("voice_override") or {}
    voice = None
    if override.get("voice"):
        voice = {
            "kokoro": override["voice"],
            "speed": override.get("speed", 1.0),
            "pitch": override.get("pitch", 0.0),
            "gain_db": override.get("gain_db", 0.0),
        }
    else:
        voice = _voice_for_speaker(cast_doc, line.get("speaker"))
    em = dict(line.get("emotion") or {})
    if override.get("emotion"):
        em.update(override["emotion"])
    if override.get("speed") is not None:
        em["speed"] = override["speed"]
    if override.get("gain_db") is not None:
        em["gain_db"] = em.get("gain_db", 0.0) + override["gain_db"]
    if voice and voice.get("pitch"):
        em["pitch"] = round(
            float(em.get("pitch", 0.0) or 0.0) + float(voice["pitch"]), 2
        )
    text = override.get("text") or line.get("text", "")
    return voice, policy.apply_echo(em), text


def _synth_line(
    cdir: Path, line: dict, voice: dict, em: dict, text: str
) -> tuple[np.ndarray, int, float]:
    kokoro_id = voice["kokoro"]
    key = cache.key(text, kokoro_id, em)
    cpath = cache.cache_path(cdir / "work", key)
    if cpath.exists():
        samples, sr = dsp.read_wav(cpath)
    else:
        samples, sr = kokoro_engine.synthesize_line(text, kokoro_id, em)
        samples = emotion.apply(samples, sr, em)
        base_gain = voice.get("gain_db", 0.0)
        if base_gain:
            samples = dsp.gain_db(samples, base_gain)
        samples = dsp.limiter(samples, ceiling=0.98)
        dsp.write_wav(cpath, samples, sr)
    dur = round(samples.shape[0] / sr, 3)
    return samples, sr, dur


class VoiceJobReq(BaseModel):
    # Preview only: a temporary voice used for lines whose speaker has no
    # voice set. Never written to cast.json -- Emerson still picks every
    # real voice. A helper-5 rough-movie preview can pass this so a chapter
    # is fully voiced even before every character has a chosen voice.
    preview_voice: str | None = None
    only_missing: bool = False  # speak just the lines with no sound yet


@router.post("/chapters/{series}/{chapter}/voice")
def synth_chapter_voice(series: str, chapter: str, req: VoiceJobReq | None = None):
    cdir = paths.chapter_dir(series, chapter)
    preview_voice = req.preview_voice if req else None
    only_missing = bool(req and req.only_missing)

    def work(job):
        script = store.read(_script_path(series, chapter), None)
        if script is None:
            raise RuntimeError("no script.json -- run script/build first")
        cast_doc = _load_cast(series)
        skipped = []
        previewed = 0
        done = 0
        lines = script.get("lines", [])
        for i, line in enumerate(lines):
            job.progress(i / max(1, len(lines)))
            job.check()
            if only_missing and line.get("audio"):
                continue
            voice, em, text = _effective_voice_and_emotion(line, cast_doc)
            used_preview = False
            if (not voice or not voice.get("kokoro")) and preview_voice and text:
                voice = {
                    "kokoro": preview_voice,
                    "speed": 1.0,
                    "pitch": 0.0,
                    "gain_db": 0.0,
                }
                used_preview = True
            if not voice or not voice.get("kokoro") or not text:
                skipped.append(
                    {
                        "line_id": line["id"],
                        "speaker": line.get("speaker"),
                        "reason": "no voice set" if not voice else "empty text",
                    }
                )
                continue
            if used_preview:
                previewed += 1
                job.log(
                    f"{line['id']} (speaker={line.get('speaker')}): no voice set, using preview_voice={preview_voice!r}"
                )
            samples, sr, dur = _synth_line(cdir, line, voice, em, text)
            out_path = cdir / "audio" / f"{line['id']}.wav"
            dsp.write_wav(out_path, samples, sr)
            line["audio"] = f"audio/{line['id']}.wav"
            line["dur"] = dur
            done += 1
        store.write(_script_path(series, chapter), script)
        for s in skipped:
            job.log(f"skipped {s['line_id']} (speaker={s['speaker']}): {s['reason']}")
        job.log(
            f"synthesised {done} lines ({previewed} on preview_voice), skipped {len(skipped)}"
        )
        return {"synthesised": done, "previewed": previewed, "skipped": skipped}

    job = jobs.start(
        "voice",
        "Synthesising voice lines",
        work,
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}


class LineVoiceOverride(BaseModel):
    voice: str | None = None
    speed: float | None = None
    pitch: float | None = None
    gain_db: float | None = None
    emotion: dict | None = None
    text: str | None = None


@router.post("/chapters/{series}/{chapter}/lines/{line_id}/voice")
def resynth_line(series: str, chapter: str, line_id: str, override: LineVoiceOverride):
    cdir = paths.chapter_dir(series, chapter)
    script = store.read(_script_path(series, chapter), None)
    if script is None:
        raise HTTPException(404, "no script.json for this chapter yet")
    line = next((ln for ln in script.get("lines", []) if ln["id"] == line_id), None)
    if line is None:
        raise HTTPException(404, f"no line {line_id!r} in script.json")

    line["voice_override"] = {
        k: v for k, v in override.model_dump().items() if v is not None
    }
    line["edited"] = True
    cast_doc = _load_cast(series)
    voice, em, text = _effective_voice_and_emotion(line, cast_doc)
    if not voice or not voice.get("kokoro"):
        raise HTTPException(
            400,
            "no voice available -- set voice_override.voice or a cast/narrator voice first",
        )
    if not text:
        raise HTTPException(400, "empty text")
    samples, sr, dur = _synth_line(cdir, line, voice, em, text)
    out_path = cdir / "audio" / f"{line_id}.wav"
    dsp.write_wav(out_path, samples, sr)
    line["audio"] = f"audio/{line_id}.wav"
    line["dur"] = dur
    store.write(_script_path(series, chapter), script)
    return {"audio": line["audio"], "dur": dur}


class LineEmotion(BaseModel):
    """Per-line override of the automatic voice-acting rules. Every field is
    optional. `expression`, `intensity` and `room` re-run the rules with
    that cue replaced; the numeric knobs then override the result directly.
    `reset` drops back to the automatic rules for this line."""

    expression: str | None = None
    intensity: float | None = None
    room: str | None = None
    speed: float | None = None
    gain_db: float | None = None
    pause_after: float | None = None
    reverb: float | None = None
    pitch: float | None = None
    tremolo: float | None = None
    grit: float | None = None
    breath: float | None = None
    eq: str | None = None
    blend: dict | None = None
    emphasis: list[str] | None = None
    reset: bool = False
    speak: bool = True


_KNOBS = (
    "speed",
    "gain_db",
    "pause_after",
    "reverb",
    "pitch",
    "tremolo",
    "grit",
    "breath",
    "eq",
    "blend",
    "emphasis",
)


@router.post("/chapters/{series}/{chapter}/script/lines/{line_id}/emotion")
def set_line_emotion(series: str, chapter: str, line_id: str, req: LineEmotion):
    cdir = paths.chapter_dir(series, chapter)
    script = store.read(_script_path(series, chapter), None)
    if script is None:
        raise HTTPException(404, "no script.json for this chapter yet")
    line = next((ln for ln in script.get("lines", []) if ln["id"] == line_id), None)
    if line is None:
        raise HTTPException(404, f"no line {line_id!r} in script.json")
    if req.expression is not None and req.expression not in emotion.EXPRESSIONS:
        raise HTTPException(400, f"unknown expression {req.expression!r}")
    if req.room is not None and req.room not in emotion.SPACES:
        raise HTTPException(400, f"unknown room {req.room!r}")
    if req.eq is not None and req.eq not in ("radio", "vehicle", "void", "none"):
        raise HTTPException(400, f"unknown eq {req.eq!r}")

    bubbles_doc = store.read(cdir / "bubbles.json", {"bubbles": []})
    scene_doc = store.read(cdir / "scene.json", None)
    ctx = (
        script_mod.line_context(bubbles_doc, scene_doc, line.get("bubble_id") or "")
        or {}
    )
    text = line.get("text", "")
    kind = line.get("kind") or "speech"

    if req.reset:
        em = emotion.rules_for(text, kind, ctx)
    else:
        em = dict(line.get("emotion") or {})
        by_hand = []
        if (
            req.expression is not None
            or req.intensity is not None
            or req.room is not None
        ):
            face = dict(ctx.get("expression") or {})
            if req.expression is not None:
                face = {"label": req.expression, "intensity": 0.7, "conf": 1.0}
                by_hand.append(f"expression {req.expression}")
            if req.intensity is not None:
                face = dict(face or {"label": em.get("expression") or "neutral"})
                face["intensity"] = max(0.0, min(1.0, req.intensity))
                face["conf"] = 1.0
                by_hand.append(f"intensity {face['intensity']:.2f}")
            if req.room is not None:
                ctx["acoustics"] = {"space": req.room, "size": 0.6}
                by_hand.append(f"room {req.room}")
            ctx["expression"] = face
            em = emotion.rules_for(text, kind, ctx)
        for knob in _KNOBS:
            val = getattr(req, knob)
            if val is not None:
                em[knob] = None if (knob == "eq" and val == "none") else val
                by_hand.append(knob)
        em["source"] = "user"
        if by_hand:
            em["cues"] = list(em.get("cues") or []) + [
                "set by hand: " + ", ".join(by_hand)
            ]
    line["emotion"] = em

    spoken = False
    cast_doc = _load_cast(series)
    voice, eff_em, eff_text = _effective_voice_and_emotion(line, cast_doc)
    if req.speak and voice and voice.get("kokoro") and eff_text:
        samples, sr, dur = _synth_line(cdir, line, voice, eff_em, eff_text)
        out_path = cdir / "audio" / f"{line_id}.wav"
        dsp.write_wav(out_path, samples, sr)
        line["audio"] = f"audio/{line_id}.wav"
        line["dur"] = dur
        spoken = True
    else:
        line["audio"], line["dur"] = None, None  # the voice job re-speaks it
    store.write(_script_path(series, chapter), script)
    return {"line": line, "spoken": spoken}


# --------------------------------------------------------------- sfx/music #
@router.get("/sfx")
def list_sfx():
    return {"recipes": sfx_recipes.names(), "library": sfx_library.list_library()}


@router.get("/music")
def list_music():
    return {"moods": music_generate.moods(), "library": music_library.list_library()}


class SfxAuditionReq(BaseModel):
    sound: str  # a recipe name, "synth:<name>", or a library id
    params: dict = {}


@router.post("/sfx/audition")
def audition_sfx(req: SfxAuditionReq):
    name = req.sound.split(":", 1)[1] if req.sound.startswith("synth:") else req.sound
    if name in sfx_recipes.RECIPES:
        samples, sr = sfx_recipes.render(name, **req.params)
        return _wav_response(samples, sr)
    try:
        samples, sr = sfx_library.load(name)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    return _wav_response(samples, sr)


class MusicAuditionReq(BaseModel):
    mood: str | None = None
    track: str | None = None
    seconds: float = 8.0


@router.post("/music/audition")
def audition_music(req: MusicAuditionReq):
    if req.track:
        try:
            samples, sr = music_library.load(req.track)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e))
        if samples.shape[0] / sr < req.seconds:
            samples = music_generate.tile_to_length(
                dsp.to_stereo(samples), sr, req.seconds
            )
        else:
            samples = samples[: int(req.seconds * sr)]
        return _wav_response(samples, sr)
    mood = req.mood or "calm"
    if mood not in music_generate.MOODS:
        raise HTTPException(
            400, f"unknown mood {mood!r}; choices: {music_generate.moods()}"
        )
    loop, sr = music_generate.generate(mood)
    samples = music_generate.tile_to_length(loop, sr, req.seconds)
    return _wav_response(samples, sr)


def _panel_moods_from_scene(scene_doc: dict) -> list[tuple[str, str]]:
    return [
        (pid, p.get("mood", "calm")) for pid, p in scene_doc.get("panels", {}).items()
    ]


def _panel_moods_from_bubbles(bubbles_doc: dict) -> list[tuple[str, str]]:
    """Fallback when scene.json doesn't exist yet: guess a mood per panel
    from dialogue cues (shout -> action, whisper -> mystery, else calm)."""
    order: list[str] = []
    kinds: dict[str, list[str]] = {}
    for b in bubbles_doc.get("bubbles", []):
        pid = b.get("panel_id")
        if not pid:
            continue
        if pid not in kinds:
            kinds[pid] = []
            order.append(pid)
        kinds[pid].append(b.get("kind", "speech"))
    out = []
    for pid in order:
        ks = kinds[pid]
        if "shout" in ks:
            mood = "action"
        elif "whisper" in ks:
            mood = "mystery"
        else:
            mood = "calm"
        out.append((pid, mood))
    return out


@router.post("/chapters/{series}/{chapter}/audio/auto")
def auto_audio(series: str, chapter: str):
    cdir = paths.chapter_dir(series, chapter)

    def work(job):
        bubbles_doc = store.read(cdir / "bubbles.json", {"bubbles": []})
        scene_doc = store.read(cdir / "scene.json", None)
        script = store.read(_script_path(series, chapter), None) or _blank_script()

        kept_sfx = [
            x
            for x in script.get("sfx", [])
            if x.get("source") == "user" or x.get("edited")
        ]
        new_sfx = []
        n = 0
        for b in bubbles_doc.get("bubbles", []):
            if b.get("kind") != "sfx" or not (b.get("text") or "").strip():
                continue
            name, params = sfx_match.match_text(b["text"])
            n += 1
            new_sfx.append(
                {
                    "id": f"x{n:04d}",
                    "panel_id": b.get("panel_id"),
                    "source": "auto",
                    "sound": f"synth:{name}",
                    "at": "panel-start",
                    "gain_db": 0,
                    "params": params,
                }
            )
        if scene_doc:
            for pid, p in scene_doc.get("panels", {}).items():
                for sx in p.get("sfx_text", []) or []:
                    name, params = sfx_match.match_text(sx.get("text", ""))
                    n += 1
                    new_sfx.append(
                        {
                            "id": f"x{n:04d}",
                            "panel_id": pid,
                            "source": "auto",
                            "sound": f"synth:{name}",
                            "at": "panel-start",
                            "gain_db": 0,
                            "params": params,
                        }
                    )
        job.log(f"auto-placed {len(new_sfx)} sfx ({len(kept_sfx)} user/edited kept)")

        kept_music = [
            m
            for m in script.get("music", [])
            if m.get("source") == "user" or m.get("edited")
        ]
        panel_moods = (
            _panel_moods_from_scene(scene_doc)
            if scene_doc
            else _panel_moods_from_bubbles(bubbles_doc)
        )
        scene_of = {
            pid: p.get("scene_id")
            for pid, p in ((scene_doc or {}).get("panels") or {}).items()
        }
        new_music = [
            {
                "id": f"m{m:02d}",
                "from_panel": seg["from_panel"],
                "to_panel": seg["to_panel"],
                "mood": seg["mood"],
                "track": None,
                "source": "auto",
                "gain_db": -14,
            }
            for m, seg in enumerate(
                music_plan.segments(
                    [(pid, mood, scene_of.get(pid)) for pid, mood in panel_moods]
                ),
                1,
            )
        ]
        job.log(
            f"auto-placed {len(new_music)} music segments ({len(kept_music)} user/edited kept)"
        )

        script["sfx"] = kept_sfx + new_sfx
        script["music"] = kept_music + new_music
        store.write(_script_path(series, chapter), script)
        # the saved film plan lists music by id; a plan built before this
        # pass would keep naming the old segments, so it is told the new ones
        tl_path = cdir / "timeline.json"
        tl = store.read(tl_path, None)
        if tl is not None:
            tl["music"] = [m["id"] for m in script["music"]]
            store.write(tl_path, tl)
        return {"sfx": len(new_sfx), "music": len(new_music)}

    job = jobs.start(
        "audio-auto",
        "Auto SFX and mood music",
        work,
        lane="cpu",
        series=series,
        chapter=chapter,
    )
    return {"job_id": job.id}
