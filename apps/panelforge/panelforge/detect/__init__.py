"""Detect: pages -> one virtual strip -> panels and speech bubbles with text.

Stages (each a module here, run in order by pipeline.run_detect):
    strip.py     stack pages into a virtual strip, read any row range lazily
    gutters.py   row statistics, gutter runs, slanted cut lines (pure numpy)
    panels.py    cut the strip into panels, classify, order, save crops
    text.py      letter-like strokes grouped into text lines and blocks
    balloons.py  enclosing balloon, balloon kind and tail direction
    ocr.py       OCR engines registry (tesseract CLI; classical fallback)
    normalize.py comic all-caps lettering -> sentence case for speech
    merge.py     re-detect keeps items Emerson edited
    pipeline.py  the detect job
"""
