"""OCR engines, as a registry. Detection asks for the first available engine.

Adding an engine = one class with `name`, `available()` and `recognize()`, plus
one entry in ENGINES. The tesseract engine uses the system `tesseract` binary
(already installed on this laptop, English data included) through its TSV
output, so there is no Python dependency.

Crops are normalised before recognition: light-on-dark lettering is inverted,
text is scaled to a comfortable letter height and binarised, then many crops are
stacked into one tall sheet so tesseract starts once per batch instead of once
per balloon.
"""

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import style

TARGET_LINE_H = 40  # px letter height handed to the recogniser
GAP = 48  # px of white between stacked crops
MAX_SHEET_H = 16000


@dataclass
class OcrResult:
    text: str
    conf: float  # 0..1
    lines: list[str]
    words: list[dict] = field(
        default_factory=list
    )  # prepared-image coords plus lettering measures


def prepare(crop: np.ndarray, polarity: str, line_h: float) -> np.ndarray:
    """Grey, dark-on-white, scaled to TARGET_LINE_H letters, padded."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if polarity == "light":
        g = 255 - g
    scale = float(np.clip(TARGET_LINE_H / max(6.0, line_h), 0.5, 4.0))
    g = cv2.resize(
        g,
        (max(1, round(g.shape[1] * scale)), max(1, round(g.shape[0] * scale))),
        interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA,
    )
    _t, b = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Otsu on a mostly-white crop keeps letters black; if the crop came out
    # mostly black the polarity guess was wrong, so flip it.
    if (b < 128).mean() > 0.5:
        b = 255 - b
    return cv2.copyMakeBorder(b, 16, 16, 24, 24, cv2.BORDER_CONSTANT, value=255)


class TesseractEngine:
    name = "tesseract"

    def available(self) -> bool:
        return shutil.which("tesseract") is not None

    def _run(self, sheet: np.ndarray) -> list[dict]:
        with tempfile.TemporaryDirectory(prefix="pf-ocr-") as d:
            p = Path(d) / "sheet.png"
            cv2.imwrite(str(p), sheet)
            r = subprocess.run(
                ["tesseract", str(p), "stdout", "-l", "eng", "--psm", "4", "tsv"],
                capture_output=True,
                text=True,
                timeout=600,
            )
        words = []
        for row in r.stdout.splitlines()[1:]:
            f = row.split("\t")
            if len(f) < 12 or f[0] != "5":
                continue
            text = f[11].strip()
            if not text:
                continue
            words.append(
                {
                    "block": int(f[2]),
                    "par": int(f[3]),
                    "line": int(f[4]),
                    "x": int(f[6]),
                    "y": int(f[7]),
                    "w": int(f[8]),
                    "h": int(f[9]),
                    "conf": float(f[10]),
                    "text": text,
                }
            )
        return words

    def recognize(self, items: list[tuple[np.ndarray, str, float]]) -> list[OcrResult]:
        """items: (crop BGR, polarity, typical letter height). One result per item."""
        prepared = [prepare(c, pol, lh) for c, pol, lh in items]
        results: list[OcrResult] = [OcrResult("", 0.0, []) for _ in items]
        start = 0
        while start < len(prepared):
            batch, h = [], 0
            while start + len(batch) < len(prepared):
                im = prepared[start + len(batch)]
                if batch and h + im.shape[0] + GAP > MAX_SHEET_H:
                    break
                batch.append(im)
                h += im.shape[0] + GAP
            width = max(im.shape[1] for im in batch)
            sheet = np.full((h, width), 255, np.uint8)
            spans = []
            y = 0
            for im in batch:
                sheet[y : y + im.shape[0], : im.shape[1]] = im
                spans.append((y, y + im.shape[0]))
                y += im.shape[0] + GAP
            words = self._run(sheet)
            for k, (a, b) in enumerate(spans):
                mine = [w for w in words if a <= w["y"] + w["h"] / 2 < b]
                results[start + k] = _assemble(mine, batch[k], a)
            start += len(batch)
        return results


def _assemble(
    words: list[dict], binary: np.ndarray | None = None, y0: int = 0
) -> OcrResult:
    if not words:
        return OcrResult("", 0.0, [])
    measured = []
    for w in words:
        item = {
            "text": w["text"],
            "conf": w["conf"],
            "x": w["x"],
            "y": w["y"] - y0,
            "w": w["w"],
            "h": w["h"],
        }
        if binary is not None:
            item.update(
                style.measure_word(binary, (item["x"], item["y"], item["w"], item["h"]))
            )
        measured.append(item)
    words.sort(key=lambda w: (w["y"], w["x"]))
    # rebuild lines by vertical position (tesseract line ids restart per block)
    lines: list[list[dict]] = []
    for w in words:
        for line in lines:
            ref = line[0]
            if abs((w["y"] + w["h"] / 2) - (ref["y"] + ref["h"] / 2)) < 0.6 * max(
                w["h"], ref["h"]
            ):
                line.append(w)
                break
        else:
            lines.append([w])
    texts = [
        " ".join(x["text"] for x in sorted(l, key=lambda w: w["x"])) for l in lines
    ]
    n = sum(len(w["text"]) for w in words)
    conf = sum(max(0.0, w["conf"]) * len(w["text"]) for w in words) / max(1, n) / 100
    return OcrResult(" ".join(texts), round(conf, 3), texts, measured)


ENGINES = [TesseractEngine()]


def engine(name: str | None = None):
    """The named engine, or the first available one; None when OCR is impossible."""
    for e in ENGINES:
        if (name is None or e.name == name) and e.available():
            return e
    return None
