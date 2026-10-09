"""
Subtitle translation.

Backends:
  * jan     -- your local LLM (batched, context-aware, no key, free)
  * google  -- deep-translator's free Google endpoint (optional dep)
  * deepl   -- DeepL API (needs key)

Works on parsed .srt / .ass cue lists. Translates in batches so the model keeps
tone/consistency and we don't do one HTTP call per line.
"""

import re
import time

# ---- SRT / VTT parsing (dependency-free) ----
_TS = r"\d{1,2}:\d{2}:\d{2}[,.]\d{3}"


def parse_srt(text):
    """Return [{'idx', 'start', 'end', 'text'}]."""
    text = text.replace("\r\n", "\n").strip()
    blocks = re.split(r"\n\s*\n", text)
    cues = []
    for b in blocks:
        lines = [ln for ln in b.split("\n") if ln.strip() != ""]
        if not lines:
            continue
        ti = 0
        if re.match(r"^\d+$", lines[0].strip()):
            ti = 1
        if ti >= len(lines):
            continue
        m = re.match(rf"({_TS})\s*-->\s*({_TS})", lines[ti])
        if not m:
            continue
        cues.append({"idx": len(cues) + 1, "start": m.group(1), "end": m.group(2),
                     "text": "\n".join(lines[ti + 1:]).strip()})
    return cues


def build_srt(cues):
    out = []
    for i, c in enumerate(cues, 1):
        out.append(f"{i}\n{c['start']} --> {c['end']}\n{c['text']}\n")
    return "\n".join(out)


def parse_ass(text):
    """Return (header_text, [{'raw_line', 'text', 'ref'}]) for Dialogue lines."""
    lines = text.replace("\r\n", "\n").split("\n")
    header, cues = [], []
    fmt_fields = []
    for ln in lines:
        if ln.startswith("Format:") and "Text" in ln and "[Events]" not in ln:
            fmt_fields = [f.strip().lower() for f in ln.split(":", 1)[1].split(",")]
        if ln.startswith("Dialogue:") and fmt_fields:
            body = ln.split(":", 1)[1]
            parts = body.split(",", len(fmt_fields) - 1)
            try:
                ti = fmt_fields.index("text")
            except ValueError:
                ti = len(parts) - 1
            cues.append({"raw": ln, "prefix": ",".join(parts[:ti]), "text": parts[ti]})
        else:
            header.append(ln)
    return "\n".join(header), cues


def build_ass(header, cues):
    out = header.rstrip("\n") + "\n"
    for c in cues:
        out += f"Dialogue:{c['prefix']},{c['text']}\n"
    return out


# ---- translation core ----
_TAG = re.compile(r"(\{\\[^}]*\}|<[^>]+>|\\N|\\n|\\h)")


def _split_tags(s):
    """Split an .ass/.srt line into (plain_chunks, tag_tokens) preserving order
    so tags survive translation."""
    return _TAG.split(s)


class Translator:
    def __init__(self, settings, jan_client=None, log=lambda s: None):
        self.s = settings
        self.jan = jan_client
        self.log = log
        self.backend = settings.get("translate_backend", "jan")
        self.target = settings.get("target_language", "English")
        self.source = settings.get("source_language", "auto")

    def translate_lines(self, lines, batch=40, kill=lambda: False):
        """lines: list[str] -> list[str] (same length)."""
        out = []
        for i in range(0, len(lines), batch):
            if kill():
                out.extend(lines[i:])
                break
            chunk = lines[i:i + batch]
            self.log(f"  translating lines {i + 1}–{i + len(chunk)} / {len(lines)}")
            try:
                out.extend(self._translate_batch(chunk))
            except Exception as e:
                self.log(f"  batch failed ({e}); keeping originals for this batch")
                out.extend(chunk)
            time.sleep(0.05)
        return out

    def _translate_batch(self, chunk):
        if self.backend == "google":
            return self._google(chunk)
        if self.backend == "deepl":
            return self._deepl(chunk)
        return self._jan(chunk)

    # -- Jan / local LLM --
    def _jan(self, chunk):
        if not self.jan:
            raise RuntimeError("Jan client not configured")
        model = self.s.get("jan_model") or (self.jan.models() or [""])[0]
        if not model:
            raise RuntimeError("no Jan model available")
        numbered = "\n".join(f"{i+1}| {t.replace(chr(10), ' ⏎ ')}" for i, t in enumerate(chunk))
        src = "" if self.source == "auto" else f" from {self.source}"
        system = (f"You are a professional subtitle translator{src} into {self.target}. "
                  "Translate each numbered line. Keep the SAME numbering and count. "
                  "Preserve any markup tags ({...}, <...>) and the ⏎ line-break marker "
                  "exactly. Natural spoken register. Output ONLY 'N| translation' lines.")
        raw = self.jan.chat(model, system, numbered, max_tokens=min(60 * len(chunk) + 200, 4096),
                            temperature=0.3)
        got = {}
        for ln in raw.splitlines():
            m = re.match(r"\s*(\d+)\s*[|.)]\s*(.*)", ln)
            if m:
                got[int(m.group(1))] = m.group(2).replace(" ⏎ ", "\n").strip()
        return [got.get(i + 1, chunk[i]) for i in range(len(chunk))]

    # -- deep-translator (Google, free) --
    def _google(self, chunk):
        from deep_translator import GoogleTranslator
        tgt = {"English": "en", "Japanese": "ja", "Spanish": "es", "French": "fr",
               "German": "de", "Korean": "ko", "Chinese": "zh-CN"}.get(self.target, "en")
        tr = GoogleTranslator(source="auto", target=tgt)
        return [tr.translate(t) if t.strip() else t for t in chunk]

    # -- DeepL --
    def _deepl(self, chunk):
        import requests
        key = self.s.get("deepl_key", "")
        if not key:
            raise RuntimeError("DeepL key not set")
        host = "https://api-free.deepl.com" if key.endswith(":fx") else "https://api.deepl.com"
        tgt = {"English": "EN", "Japanese": "JA", "Spanish": "ES", "French": "FR",
               "German": "DE", "Korean": "KO", "Chinese": "ZH"}.get(self.target, "EN")
        r = requests.post(f"{host}/v2/translate",
                          data=[("auth_key", key), ("target_lang", tgt)]
                          + [("text", t) for t in chunk], timeout=60)
        r.raise_for_status()
        return [x["text"] for x in r.json()["translations"]]


def translate_subtitle_file(in_path, out_path, settings, jan_client=None,
                            log=lambda s: None, kill=lambda: False):
    """Read .srt/.ass, translate cue text, write to out_path. Returns out_path."""
    text = open(in_path, "r", encoding="utf-8", errors="replace").read()
    tr = Translator(settings, jan_client, log)
    if in_path.lower().endswith((".ass", ".ssa")):
        header, cues = parse_ass(text)
        originals = [c["text"] for c in cues]
        translated = tr.translate_lines(originals, kill=kill)
        for c, t in zip(cues, translated):
            c["text"] = t
        open(out_path, "w", encoding="utf-8").write(build_ass(header, cues))
    else:
        cues = parse_srt(text)
        translated = tr.translate_lines([c["text"] for c in cues], kill=kill)
        for c, t in zip(cues, translated):
            c["text"] = t
        open(out_path, "w", encoding="utf-8").write(build_srt(cues))
    log(f"  wrote translated subtitles: {out_path}")
    return out_path
