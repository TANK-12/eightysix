"""
Audiobook rendering with Piper -- a genuinely local, offline neural TTS.

Voice models (~50-100 MB ONNX) are fetched once from rhasspy/piper-voices into
~/NovelMakerData/tts_voices/ and everything after that is offline. Each codex
character can be mapped to its own voice; a best-effort regex attributor routes
quoted dialogue to that voice and everything else to the narrator. Chapters are
rendered to WAV and stitched with ffmpeg into one tagged, chaptered file.

Attribution is deliberately best-effort in the spirit of jsonrepair/textquality:
when it can't tell who is speaking the line simply goes to the narrator.
"""

import os
import re
import json
import wave
import shutil
import pathlib
import subprocess

from . import config
from .project import slugify

# Both engines drag in onnxruntime (and Kokoro also phonemizer/csvw), which is
# ~0.6 s of import time -- far too much to spend on every app launch when most
# sessions never open the Export tab. Availability is probed with find_spec,
# which only looks for the module, and the real import happens on first use.
def _have(mod):
    try:
        from importlib.util import find_spec
        return find_spec(mod) is not None
    except Exception:
        return False


PIPER_OK = _have("piper")
KOKORO_OK = _have("kokoro_onnx")
NUMPY_OK = _have("numpy")

_lazy = {}


def _piper():
    if "piper" not in _lazy:
        from piper import PiperVoice, SynthesisConfig
        from piper.download_voices import download_voice
        _lazy["piper"] = (PiperVoice, SynthesisConfig, download_voice)
    return _lazy["piper"]


def _kokoro_cls():
    if "kokoro" not in _lazy:
        from kokoro_onnx import Kokoro
        _lazy["kokoro"] = Kokoro
    return _lazy["kokoro"]


def _np():
    if "np" not in _lazy:
        import numpy
        _lazy["np"] = numpy
    return _lazy["np"]


PIPER_HINT = "Audiobooks need Piper.  Run:  pip install piper-tts"
KOKORO_HINT = "The realistic voices need Kokoro.  Run:  pip install kokoro-onnx"
FFMPEG = shutil.which("ffmpeg") or "/usr/bin/ffmpeg"
AUDIO_FORMATS = ("m4a", "mp3", "wav")

# Two engines, one id space. Ids are "<engine>:<name>", and a bare name means
# piper so voice maps written before Kokoro existed still load.
#
#   kokoro:am_michael                 Kokoro -- markedly more human, ~3x realtime
#   piper:en_US-ryan-high             Piper "-high" -- good, ~5x realtime
#   piper:en_US-libritts-high#57      a speaker inside a multi-speaker model
#
# Curated, not exhaustive: enough range to cast a novel without a wall of names.
KOKORO_CATALOG = [
    ("kokoro:am_michael",  "Michael — US male, warm ★★ most natural"),
    ("kokoro:af_heart",    "Heart — US female, warm ★★ most natural"),
    ("kokoro:bm_george",   "George — UK male, older ★★ most natural"),
    ("kokoro:bf_emma",     "Emma — UK female, poised ★★ most natural"),
    ("kokoro:am_fenrir",   "Fenrir — US male, deep and gruff ★★"),
    ("kokoro:am_puck",     "Puck — US male, light and quick ★★"),
    ("kokoro:af_bella",    "Bella — US female, rich ★★"),
    ("kokoro:af_nicole",   "Nicole — US female, soft and close ★★"),
    ("kokoro:am_adam",     "Adam — US male, plain ★★"),
    ("kokoro:af_sky",      "Sky — US female, young ★★"),
    ("kokoro:bm_fable",    "Fable — UK male, storyteller ★★"),
    ("kokoro:bf_alice",    "Alice — UK female, bright ★★"),
    ("kokoro:am_onyx",     "Onyx — US male, low and grave ★★"),
    ("kokoro:af_river",    "River — US female, cool and flat ★★"),
    ("kokoro:jf_alpha",    "Alpha — Japanese female ★★"),
    ("kokoro:jm_kumo",     "Kumo — Japanese male ★★"),
]
PIPER_CATALOG = [
    ("piper:en_US-ryan-high",     "Ryan — US male, natural ★ high quality"),
    ("piper:en_US-lessac-high",   "Lessac — US neutral, natural ★ high quality"),
    ("piper:en_GB-cori-high",     "Cori — UK female, natural ★ high quality"),
    ("piper:en_US-ljspeech-high", "LJSpeech — US female, natural ★ high quality"),
    # one 120 MB file, 904 distinct read-aloud speakers; a handful are surfaced
    # here and any other is reachable by editing the '#id' in voices.json
    ("piper:en_US-libritts-high#0",   "LibriTTS 0 — US, audiobook-trained ★"),
    ("piper:en_US-libritts-high#12",  "LibriTTS 12 — US, audiobook-trained ★"),
    ("piper:en_US-libritts-high#40",  "LibriTTS 40 — US, audiobook-trained ★"),
    ("piper:en_US-libritts-high#109", "LibriTTS 109 — US, audiobook-trained ★"),
    ("piper:en_US-hfc_female-medium", "HFC Female — US, clear (fast)"),
    ("piper:en_US-hfc_male-medium",   "HFC Male — US, clear (fast)"),
    ("piper:en_US-kristin-medium",    "Kristin — US female, soft (fast)"),
    ("piper:en_US-amy-medium",        "Amy — US female, bright (fast)"),
    ("piper:en_US-joe-medium",        "Joe — US male, low and calm (fast)"),
    ("piper:en_US-norman-medium",     "Norman — US male, gruff (fast)"),
    ("piper:en_US-bryce-medium",      "Bryce — US male, youthful (fast)"),
    ("piper:en_GB-alan-medium",       "Alan — UK male, RP (fast)"),
    ("piper:en_GB-jenny_dioco-medium", "Jenny — UK female (fast)"),
    ("piper:en_GB-northern_english_male-medium", "Northern English — UK male (fast)"),
    ("piper:en_GB-alba-medium",       "Alba — Scottish female (fast)"),
    ("piper:en_US-kusal-medium",      "Kusal — US male, accented (fast)"),
]
VOICE_CATALOG = (KOKORO_CATALOG if KOKORO_OK else []) + PIPER_CATALOG
VOICE_IDS = [v for v, _ in VOICE_CATALOG]
VOICE_LABELS = [f"{v}  ·  {d}" for v, d in VOICE_CATALOG]
DEFAULT_VOICE = "kokoro:am_michael" if KOKORO_OK else "piper:en_US-ryan-high"

# Narration modes -- how many actual voices end up in the finished book.
MODES = ("single", "cast", "narrator_voices")
MODE_LABELS = {
    "single": "Single narrator — one voice reads everything",
    "cast": "Full cast — a different voice model per character",
    "narrator_voices": "One narrator doing voices — same reader, shifted per character",
}

# (pitch, pace) inflections for "narrator doing voices": the narrator's own voice
# nudged up/down so characters are distinguishable without a second model.
INFLECTIONS = [(1.00, 1.00), (1.10, 0.97), (0.90, 1.03), (1.05, 1.03),
               (0.95, 0.97), (1.16, 1.01), (0.85, 0.99), (1.02, 0.94)]

# What the user picks from per character in "narrator doing voices" mode.
INFLECTION_CHOICES = [
    ("auto",              None),
    ("same as narrator",  (1.00, 1.00)),
    ("a little higher",   (1.06, 1.01)),
    ("higher",            (1.12, 1.00)),
    ("high and quick",    (1.18, 1.06)),
    ("a little lower",    (0.95, 0.99)),
    ("lower",             (0.89, 0.98)),
    ("low and slow",      (0.83, 0.92)),
    ("light and fast",    (1.04, 1.09)),
    ("heavy and slow",    (0.93, 0.89)),
]
INFLECTION_LABELS = [lbl for lbl, _v in INFLECTION_CHOICES]


def inflection_from_label(label):
    for lbl, val in INFLECTION_CHOICES:
        if lbl == label:
            return val
    return None


def label_for_inflection(val):
    if not val:
        return "auto"
    for lbl, v in INFLECTION_CHOICES:
        if v and abs(v[0] - float(val[0])) < 1e-6 and abs(v[1] - float(val[1])) < 1e-6:
            return lbl
    return "auto"


def parse_voice(vid):
    """'piper:en_US-libritts-high#57' -> ('piper', 'en_US-libritts-high', 57)."""
    vid = (vid or DEFAULT_VOICE).strip()
    engine, sep, rest = vid.partition(":")
    if not sep or engine not in ("piper", "kokoro"):
        engine, rest = "piper", vid          # legacy bare piper id
    base, _, spk = rest.partition("#")
    try:
        speaker = int(spk) if spk else None
    except ValueError:
        speaker = None
    return engine, base, speaker


def split_voice(vid):
    """Back-compat shim: (base, speaker) ignoring the engine."""
    _e, base, spk = parse_voice(vid)
    return base, spk


def label_to_id(label):
    return (label or "").split("  ·  ")[0].strip() or DEFAULT_VOICE


def id_to_label(vid):
    for v, d in VOICE_CATALOG:
        if v == vid:
            return f"{v}  ·  {d}"
    # a legacy bare piper id still needs to display as something sensible
    for v, d in VOICE_CATALOG:
        if v == f"piper:{vid}":
            return f"{v}  ·  {d}"
    return vid or DEFAULT_VOICE


# ==========================================================================
# voice files
# ==========================================================================
def voices_dir(settings=None):
    d = (settings or {}).get("tts_voices_dir", "") or os.path.join(config.DATA_ROOT, "tts_voices")
    os.makedirs(d, exist_ok=True)
    return d


KOKORO_FILES = {
    "kokoro-v1.0.onnx": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                        "model-files-v1.0/kokoro-v1.0.onnx",
    "voices-v1.0.bin": "https://github.com/thewh1teagle/kokoro-onnx/releases/download/"
                       "model-files-v1.0/voices-v1.0.bin",
}


def voice_file(vid, settings=None):
    engine, base, _spk = parse_voice(vid)
    if engine == "kokoro":
        return os.path.join(voices_dir(settings), "kokoro-v1.0.onnx")
    return os.path.join(voices_dir(settings), f"{base}.onnx")


def voice_installed(vid, settings=None):
    engine, _b, _s = parse_voice(vid)
    if engine == "kokoro":
        return all(os.path.exists(os.path.join(voices_dir(settings), f))
                   for f in KOKORO_FILES)
    return os.path.exists(voice_file(vid, settings))


def _download(url, dest, log=None):
    from urllib.request import urlopen
    log = log or (lambda _m: None)
    tmp = dest + ".part"
    with urlopen(url) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        got, step = 0, 0
        while True:
            block = r.read(1 << 20)
            if not block:
                break
            f.write(block)
            got += len(block)
            if total and got // (1 << 25) > step:      # a note every 32 MB
                step = got // (1 << 25)
                log(f"    {got / 1e6:.0f} / {total / 1e6:.0f} MB")
    os.replace(tmp, dest)
    return dest


def installed_voices(settings=None):
    d = voices_dir(settings)
    try:
        return sorted(f[:-5] for f in os.listdir(d) if f.endswith(".onnx"))
    except Exception:
        return []


# ---- disk management: these models are the biggest thing NovelForge stores ----
def _voice_files(vid, settings=None):
    """Every file on disk that belongs to this voice."""
    engine, base, _spk = parse_voice(vid)
    d = voices_dir(settings)
    if engine == "kokoro":
        return [os.path.join(d, f) for f in KOKORO_FILES]
    return [os.path.join(d, base + ext) for ext in (".onnx", ".onnx.json")]


def voice_bytes(vid, settings=None):
    return sum(os.path.getsize(p) for p in _voice_files(vid, settings) if os.path.exists(p))


def installed_report(settings=None):
    """[(voice_id, label, bytes, in_catalog)] for everything actually on disk.

    Kokoro's two shared files are reported once as the whole engine, because
    deleting one of them takes every Kokoro voice with it."""
    d = voices_dir(settings)
    rows = []
    if all(os.path.exists(os.path.join(d, f)) for f in KOKORO_FILES):
        size = sum(os.path.getsize(os.path.join(d, f)) for f in KOKORO_FILES)
        rows.append(("kokoro:*", "Kokoro engine — all 54 realistic voices", size, True))
    known = {parse_voice(v)[1] for v, _ in VOICE_CATALOG}
    for base in installed_voices(settings):
        if base.startswith("kokoro-"):
            continue
        vid = f"piper:{base}"
        rows.append((vid, id_to_label(vid).split("  ·  ")[-1], voice_bytes(vid, settings),
                     base in known))
    return sorted(rows, key=lambda r: -r[2])


def voices_total_bytes(settings=None):
    d = voices_dir(settings)
    total = 0
    for root, _dirs, files in os.walk(d):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def delete_voice(vid, settings=None):
    """Remove a downloaded model. It re-downloads on next use, so this is safe."""
    removed = 0
    for p in _voice_files(vid, settings):
        if os.path.exists(p):
            os.remove(p)
            removed += 1
    return removed


def clear_previews(settings=None):
    d = voices_dir(settings)
    n = 0
    for f in os.listdir(d) if os.path.isdir(d) else []:
        if f.startswith("_preview_") and f.endswith(".wav"):
            os.remove(os.path.join(d, f))
            n += 1
    return n


def ensure_voice(vid, settings=None, log=None):
    """Download whatever this voice needs on first use, then never again."""
    engine, base, _spk = parse_voice(vid)
    log = log or (lambda _m: None)
    d = voices_dir(settings)

    if engine == "kokoro":
        if not KOKORO_OK:
            raise RuntimeError(KOKORO_HINT)
        for name, url in KOKORO_FILES.items():
            path = os.path.join(d, name)
            if not os.path.exists(path):
                log(f"  downloading {name} (one-off, shared by every Kokoro voice)…")
                _download(url, path, log)
                log(f"  ✓ {name} ready.")
        return os.path.join(d, "kokoro-v1.0.onnx")

    if not PIPER_OK:
        raise RuntimeError(PIPER_HINT)
    path = voice_file(vid, settings)
    if os.path.exists(path):
        return path
    log(f"  downloading voice {base} (one-off, ~60-120 MB)…")
    _piper()[2](base, pathlib.Path(d))                         # piper wants a Path
    if not os.path.exists(path):
        raise RuntimeError(f"voice '{base}' did not download")
    log(f"  ✓ {base} ready.")
    return path


# ==========================================================================
# per-project voice map  (<project>/voices.json)
# ==========================================================================
def map_path(project):
    return os.path.join(project.dir, "voices.json")


def load_voice_map(project, settings=None):
    default = {"narrator": (settings or {}).get("tts_voice", DEFAULT_VOICE) or DEFAULT_VOICE,
               "characters": {}}
    try:
        with open(map_path(project), encoding="utf-8") as f:
            d = json.load(f)
        if isinstance(d, dict):
            default["narrator"] = d.get("narrator") or default["narrator"]
            chars = d.get("characters")
            if isinstance(chars, dict):
                default["characters"] = {k: v for k, v in chars.items() if v}
            if d.get("mode") in MODES:
                default["mode"] = d["mode"]
            infl = d.get("inflections")
            if isinstance(infl, dict):
                default["inflections"] = infl
    except Exception:
        pass
    return default


def save_voice_map(project, vmap):
    try:
        with open(map_path(project), "w", encoding="utf-8") as f:
            json.dump(vmap, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def character_names(project):
    return sorted((project.codex.get("characters") or {}).keys())


# ==========================================================================
# best-effort dialogue attribution
# ==========================================================================
_SAID = (r"said|says|asked|asks|replied|replies|answered|answers|shouted|whispered|"
         r"muttered|murmured|growled|snapped|called|cried|added|continued|breathed|"
         r"hissed|laughed|sighed|began|offered|observed|admitted|insisted|demanded|"
         r"warned|explained|repeated|echoed|countered|urged|barked|drawled|purred|"
         r"managed|told|yelled|screamed|rasped|chuckled|grumbled|noted|agreed")
_QUOTE_RE = re.compile(r"[“\"]([^”\"]{1,4000})[”\"]")


def _name_regex(names):
    """Match full codex names and their distinctive first names."""
    keys = {}
    for n in names:
        n = (n or "").strip()
        if not n:
            continue
        keys[n] = n
        first = n.split()[0]
        if len(first) >= 3 and first not in keys:
            keys[first] = n
    if not keys:
        return None, {}
    alts = "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True))
    return re.compile(rf"\b({alts})\b"), keys


def _attribute(narration, name_re, keys):
    """Who is speaking, judged from the un-quoted text around the line."""
    if not name_re or not narration.strip():
        return None
    # a name sitting next to a speech verb wins over one merely mentioned
    tagged = re.search(rf"(?:{_SAID})\s+(?:the\s+)?([A-Z][\w'’-]+)", narration)
    if tagged:
        hit = name_re.match(tagged.group(1))
        if hit:
            return keys.get(hit.group(1))
    tagged = re.search(rf"([A-Z][\w'’-]+)[^.?!\"”]{{0,40}}?\b(?:{_SAID})\b", narration)
    if tagged:
        hit = name_re.match(tagged.group(1))
        if hit:
            return keys.get(hit.group(1))
    found = {keys[m.group(1)] for m in name_re.finditer(narration)}
    return found.pop() if len(found) == 1 else None


def split_segments(text, names, alternate=True):
    """-> [(speaker_or_None, spoken_text)]. Narrator segments have speaker None."""
    name_re, keys = _name_regex(names or [])
    segments = []
    recent = []                       # last two distinct attributed speakers

    for para in re.split(r"\n\s*\n|\n", text or ""):
        para = para.strip()
        if not para:
            continue
        quotes = list(_QUOTE_RE.finditer(para))
        if not quotes:
            segments.append((None, para))
            continue

        narration = _QUOTE_RE.sub(" ", para)
        speaker = _attribute(narration, name_re, keys)
        if speaker is None and alternate and len(narration.split()) <= 3 and recent:
            # a bare "…" line in an exchange: the two speakers are trading turns
            speaker = recent[1] if len(recent) == 2 else recent[0]
        if speaker:
            recent = [s for s in recent if s != speaker]
            recent.insert(0, speaker)
            del recent[2:]

        if not speaker:
            # unattributed: read the paragraph whole so the narrator's prosody
            # isn't chopped up for nothing
            segments.append((None, para))
            continue

        pos = 0
        for q in quotes:
            lead = para[pos:q.start()].strip()
            if lead:
                segments.append((None, lead))
            line = q.group(1).strip()
            if line:
                segments.append((speaker, line))
            pos = q.end()
        tail = para[pos:].strip()
        if tail:
            segments.append((None, tail))
    return segments


# ==========================================================================
# rendering
# ==========================================================================
def _resample(arr, src_rate, dst_rate):
    if src_rate == dst_rate or not NUMPY_OK:
        return arr
    n = max(1, int(round(len(arr) * dst_rate / float(src_rate))))
    np = _np()
    x = np.linspace(0, len(arr) - 1, n)
    return np.interp(x, np.arange(len(arr)), arr.astype(np.float32)).astype(np.int16)


class _PiperAdapter:
    def __init__(self, voice, speaker):
        self.voice, self.speaker = voice, speaker
        self.rate = voice.config.sample_rate

    def chunks(self, text, speed, variation):
        cfg = _piper()[1](
            speaker_id=self.speaker,
            length_scale=(1.0 / speed) if abs(speed - 1.0) > 1e-3 else None,
            noise_w_scale=max(0.4, min(1.2, variation)))
        for c in self.voice.synthesize(text, syn_config=cfg):
            yield c.audio_int16_array if NUMPY_OK else c.audio_int16_bytes, c.sample_rate


class _KokoroAdapter:
    """Kokoro has no prosody knobs beyond speed -- its default read is already
    much less flat than Piper's, which is the whole reason it's here."""

    def __init__(self, kokoro, name):
        self.k, self.name, self.rate = kokoro, name, 24000

    def chunks(self, text, speed, _variation):
        samples, sr = self.k.create(text, voice=self.name,
                                    speed=max(0.5, min(2.0, speed)), lang="en-us")
        np = _np()
        arr = np.asarray(samples, dtype=np.float32)
        yield (np.clip(arr, -1.0, 1.0) * 32767).astype(np.int16), sr


class _VoicePool:
    """Loads each model once and keeps it. Every Kokoro voice shares one file."""

    def __init__(self, settings=None, log=None):
        self.settings = settings or {}
        self.log = log or (lambda _m: None)
        self._loaded = {}
        self._kokoro = None

    def get(self, vid):
        engine, base, speaker = parse_voice(vid)
        key = (engine, base, speaker)
        if key not in self._loaded:
            path = ensure_voice(vid, self.settings, self.log)
            if engine == "kokoro":
                if self._kokoro is None:
                    self._kokoro = _kokoro_cls()(
                        path, os.path.join(os.path.dirname(path), "voices-v1.0.bin"))
                self._loaded[key] = _KokoroAdapter(self._kokoro, base)
            else:
                self._loaded[key] = _PiperAdapter(_piper()[0].load(path), speaker)
        return self._loaded[key]

    def close(self):
        self._loaded.clear()
        self._kokoro = None


def _write_segment(wav, adapter, text, rate, speed=1.0, variation=0.85,
                   pitch=1.0, pace=1.0):
    """Pitch is faked the cheap honest way: synthesize `pitch` times slower, then
    resample by `pitch`. Duration comes out unchanged and the formants shift, so
    one narrator can voice several characters."""
    eff_speed = speed * pace / pitch
    for arr, sr in adapter.chunks(text, eff_speed, variation):
        if not NUMPY_OK:
            wav.writeframes(arr)                       # bytes; no shifting possible
            continue
        if abs(pitch - 1.0) > 1e-3:
            arr = _resample(arr, sr, int(round(sr / pitch)))
        if sr != rate:
            arr = _resample(arr, sr, rate)
        wav.writeframes(arr.tobytes())


def narration_mode(settings=None, vmap=None):
    """Explicit `tts_mode` wins; otherwise fall back to the old boolean so voice
    maps and settings written before modes existed keep behaving the same."""
    s = settings or {}
    mode = (vmap or {}).get("mode") or s.get("tts_mode")
    if mode in MODES:
        return mode
    return "cast" if s.get("tts_per_character_voices", True) else "single"


def inflection_for(name, vmap):
    """Which pitch/pace slot a character gets when one narrator does the voices.
    Stable across runs: an explicit choice, else position in the sorted cast."""
    explicit = (vmap.get("inflections") or {}).get(name)
    if isinstance(explicit, (list, tuple)) and len(explicit) == 2:
        return float(explicit[0]), float(explicit[1])
    order = sorted((vmap.get("characters") or {}).keys() | {name})
    return INFLECTIONS[(order.index(name) + 1) % len(INFLECTIONS)]


def render_chapter(project, n, out_path, pool, vmap, settings, kill=None):
    """One chapter -> one WAV, voiced according to the narration mode."""
    s = settings or {}
    mode = narration_mode(s, vmap)
    narrator_id = vmap.get("narrator") or DEFAULT_VOICE
    narrator = pool.get(narrator_id)
    rate = narrator.rate
    speed = float(s.get("tts_speed", 1.0) or 1.0)
    variation = float(s.get("tts_variation", 0.85) or 0.85)

    text = project.load_chapter(n)
    segs = ([(None, text)] if mode == "single"
            else split_segments(text, character_names(project)))

    tmp = out_path + ".part"
    with wave.open(tmp, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        if s.get("tts_announce_chapter", True):
            ct = project.chapter_title(n)
            _write_segment(wav, narrator, f"Chapter {n}." + (f" {ct}." if ct else ""),
                           rate, speed, variation)
            wav.writeframes(b"\x00\x00" * int(rate * 0.6))
        for speaker, chunk_text in segs:
            if kill is not None and kill.hard:
                break
            voice, pitch, pace = narrator, 1.0, 1.0
            if speaker and mode == "cast":
                vid = (vmap.get("characters") or {}).get(speaker)
                if vid:
                    voice = pool.get(vid)
            elif speaker and mode == "narrator_voices":
                pitch, pace = inflection_for(speaker, vmap)
            try:
                _write_segment(wav, voice, chunk_text, rate, speed, variation, pitch, pace)
            except Exception:
                continue          # one unspeakable line must not kill the chapter
    if kill is not None and kill.hard:
        os.remove(tmp)            # never leave a truncated WAV looking "rendered"
        raise RuntimeError("cancelled")
    os.replace(tmp, out_path)
    return out_path


def _silence_wav(path, rate, ms):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * int(rate * ms / 1000.0))
    return path


def _wav_ms(path):
    try:
        with wave.open(path, "rb") as w:
            return int(w.getnframes() * 1000.0 / w.getframerate())
    except Exception:
        return 0


def _run_ffmpeg(args, kill=None):
    proc = subprocess.Popen([FFMPEG, "-hide_banner", "-loglevel", "error", "-y"] + args,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    while proc.poll() is None:
        if kill is not None and kill.hard:
            proc.terminate()
            raise RuntimeError("cancelled")
        try:
            proc.wait(timeout=0.4)
        except subprocess.TimeoutExpired:
            pass
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr.read() or "ffmpeg failed").strip()[:400])


def stitch(chapter_wavs, out_path, work_dir, rate, fmt="m4a", pause_ms=900,
           title="", author="", chapter_titles=None, kill=None):
    """Concatenate chapter WAVs (with gaps) into one tagged, chaptered file."""
    if not os.path.exists(FFMPEG):
        raise RuntimeError(f"ffmpeg not found at {FFMPEG} — install ffmpeg to stitch audiobooks.")
    gap = _silence_wav(os.path.join(work_dir, "_gap.wav"), rate, pause_ms) if pause_ms else None

    listing = os.path.join(work_dir, "_concat.txt")
    lines, marks, t = [], [], 0
    for i, w in enumerate(chapter_wavs):
        if i and gap:
            lines.append(f"file '{gap}'")
            t += pause_ms
        lines.append("file '" + w.replace("'", "'\\''") + "'")
        dur = _wav_ms(w)
        marks.append((t, t + dur, (chapter_titles or [])[i] if chapter_titles and i < len(chapter_titles)
                      else f"Chapter {i + 1}"))
        t += dur
    with open(listing, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    metafile = os.path.join(work_dir, "_meta.txt")
    with open(metafile, "w", encoding="utf-8") as f:
        f.write(";FFMETADATA1\n")
        f.write(f"title={title}\n" if title else "")
        f.write(f"artist={author}\n" if author else "")
        f.write("genre=Audiobook\n")
        for start, end, name in marks:
            f.write(f"\n[CHAPTER]\nTIMEBASE=1/1000\nSTART={start}\nEND={end}\ntitle={name}\n")

    codec = {"m4a": ["-c:a", "aac", "-b:a", "96k"],
             "mp3": ["-c:a", "libmp3lame", "-q:a", "5"],
             "wav": ["-c:a", "pcm_s16le"]}.get(fmt, ["-c:a", "aac", "-b:a", "96k"])
    _run_ffmpeg(["-f", "concat", "-safe", "0", "-i", listing,
                 "-i", metafile, "-map_metadata", "1", "-map", "0:a"] + codec + [out_path],
                kill=kill)
    for junk in (listing, metafile, gap):
        if junk and os.path.exists(junk):
            try:
                os.remove(junk)
            except Exception:
                pass
    return out_path


def build_audiobook(project, settings=None, vmap=None, log=None, progress=None,
                    kill=None, keep_wavs=False):
    """Render every written chapter and stitch one audiobook. Cancelable."""
    if not PIPER_OK:
        raise RuntimeError(PIPER_HINT)
    s = settings or {}
    log = log or (lambda _m: None)
    progress = progress or (lambda **_k: None)
    vmap = vmap or load_voice_map(project, s)

    total = project.chapter_count()
    if total == 0:
        raise RuntimeError("No chapters written yet.")

    out_dir = os.path.join(project.dir, "audiobook")
    os.makedirs(out_dir, exist_ok=True)

    mode = narration_mode(s, vmap)
    pool = _VoicePool(s, log)
    needed = [vmap.get("narrator") or DEFAULT_VOICE]
    if mode == "cast":
        needed += [v for v in (vmap.get("characters") or {}).values() if v]
    log(f"  mode: {MODE_LABELS.get(mode, mode)}")
    for vid in dict.fromkeys(needed):
        ensure_voice(vid, s, log)
    rate = pool.get(vmap.get("narrator") or DEFAULT_VOICE).rate

    wavs, titles = [], []
    try:
        for n in range(1, total + 1):
            if kill is not None and kill.any:
                log("stopped — partial chapters kept.")
                break
            wav = os.path.join(out_dir, f"chapter_{n:03d}.wav")
            progress(stage="tts_chapter", chapter=n, chapter_total=total)
            # a WAV newer than its source chapter is still good: resume cheaply
            fresh = (os.path.exists(wav) and
                     os.path.getmtime(wav) >= os.path.getmtime(project.chapter_path(n)))
            if fresh:
                log(f"  chapter {n}/{total} — already rendered")
            else:
                log(f"  chapter {n}/{total} — rendering…")
                try:
                    render_chapter(project, n, wav, pool, vmap, s, kill=kill)
                except RuntimeError as e:
                    if "cancelled" not in str(e):
                        raise
                    log("  cancelled mid-chapter — stitching what's done.")
                    break
            wavs.append(wav)
            titles.append(f"Chapter {n}" + (f" — {project.chapter_title(n)}"
                                            if project.chapter_title(n) else ""))
    finally:
        pool.close()

    if not wavs:
        raise RuntimeError("Nothing rendered.")
    if kill is not None and kill.hard:
        # killed outright: skip the stitch and keep the rendered chapter WAVs so
        # a later run resumes from where this one stopped
        log(f"  killed — {len(wavs)} chapter WAV(s) kept in {out_dir}")
        return ""

    fmt = s.get("tts_format", "m4a")
    if fmt not in AUDIO_FORMATS:
        fmt = "m4a"
    title = project.bible.get("title") or project.name.replace("_", " ").title()
    out_path = os.path.join(out_dir, f"{slugify(title)}.{fmt}")
    log(f"  stitching {len(wavs)} chapters with ffmpeg…")
    stitch(wavs, out_path, out_dir, rate, fmt=fmt,
           pause_ms=int(s.get("tts_chapter_pause_ms", 900) or 0),
           title=title, author=s.get("author_name", ""), chapter_titles=titles, kill=kill)

    if not keep_wavs:
        for w in wavs:
            try:
                os.remove(w)
            except Exception:
                pass
    progress(stage="tts_done", chapter=len(wavs), chapter_total=total)
    log(f"  ✓ audiobook → {out_path}")
    return out_path


# ==========================================================================
# LLM casting director
# ==========================================================================
def cast_voices(project, client, model, settings=None, log=None, temperature=0.3):
    """Ask the local model to cast the codex against the voice list.

    Best-effort like everything else here: whatever it returns is filtered to
    real character names and real voice ids, and an unusable answer just leaves
    the existing map alone."""
    from .jsonrepair import extract_json
    log = log or (lambda _m: None)
    s = settings or {}
    names = character_names(project)
    if not names:
        raise RuntimeError("The codex has no characters to cast yet.")

    codex = project.codex.get("characters", {})
    who = []
    for n in names[:60]:
        e = codex.get(n, {})
        bits = [e.get("desc", "").strip()]
        if e.get("traits"):
            bits.append("traits: " + ", ".join(e["traits"][:6]))
        if e.get("status"):
            bits.append("status: " + e["status"])
        who.append(f"- {n}: " + " | ".join(b for b in bits if b))

    options = [f"- {vid}  ({desc})" for vid, desc in VOICE_CATALOG]
    system = ("You are a casting director for an audiobook. You match character "
              "descriptions to narrator voices by apparent gender, age, accent and "
              "temperament. You reply with JSON only.")
    user = ("Cast these characters using ONLY voice ids from the list.\n\n"
            "CHARACTERS:\n" + "\n".join(who) +
            "\n\nAVAILABLE VOICES:\n" + "\n".join(options) +
            "\n\nAlso choose one voice for the NARRATOR: neutral, unobtrusive, and "
            "different from the main characters.\n"
            "Give distinct voices to characters who talk to each other. Reuse a voice "
            "only for minor characters.\n\n"
            'Reply with JSON exactly like:\n'
            '{"narrator": "<voice id>", "characters": {"<name>": "<voice id>"}}')

    log(f"Casting {len(who)} characters with {model}…")
    raw = client.complete(model, system, user,
                          max_tokens=min(2600, 220 + 26 * len(who)),
                          temperature=temperature).text
    data = extract_json(raw)
    if not isinstance(data, dict):
        raise RuntimeError("the model didn't return usable JSON — voices left unchanged")

    valid = set(VOICE_IDS)
    by_base = {parse_voice(v)[1]: v for v in VOICE_IDS}       # tolerate a bare name

    def clean(v):
        v = (v or "").strip().strip('"')
        if v in valid:
            return v
        return by_base.get(parse_voice(v)[1], "")

    out = {"characters": {}}
    narrator = clean(data.get("narrator"))
    if narrator:
        out["narrator"] = narrator
    lower = {n.lower(): n for n in names}
    for k, v in (data.get("characters") or {}).items():
        real = lower.get(str(k).strip().lower())
        vid = clean(v)
        if real and vid:
            out["characters"][real] = vid
    if not out["characters"]:
        raise RuntimeError("the model named no castable characters — voices left unchanged")
    log(f"  cast {len(out['characters'])}/{len(names)} characters"
        + (f", narrator {out['narrator']}" if out.get("narrator") else ""))
    return out


SAMPLE_LINE = ("The lantern guttered in the wind, and for a moment she thought the road "
               "itself had moved. \"You should not have come here,\" she said, not "
               "looking up from the map.")


def preview_voice(vid, out_path, settings=None, text=None, log=None,
                  pitch=1.0, pace=1.0):
    """Short sample so a voice can be auditioned before a ten-hour render."""
    s = settings or {}
    pool = _VoicePool(s, log)
    adapter = pool.get(vid)
    with wave.open(out_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(adapter.rate)
        _write_segment(w, adapter, text or SAMPLE_LINE, adapter.rate,
                       float(s.get("tts_speed", 1.0) or 1.0),
                       float(s.get("tts_variation", 0.85) or 0.85), pitch, pace)
    pool.close()
    return out_path
