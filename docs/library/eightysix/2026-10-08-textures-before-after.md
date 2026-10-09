# Eighty Six: textures pass, before and after measurements

date: 2026-10-08 · for: both

Emerson's ask: "the textures for everything but the Juggernaut suck". This is the measured part of the textures
pass (world ground, cliffs, roads, town walls and roofs, the Legion's paint). The full write-up is
`~/Forge/sessions/juggernaut-alpha/results/TEXTURES.md`.

## Frame rate on High, same sitting

The laptop's speed drifts a lot between sittings (one run earlier tonight showed 45 to 55 fps on a broken
shader, and the first before-set read 30 to 37 fps), so the cost was measured as an A/B within one sitting:
old files, new files, old files again, back to back, each the full `a011_views` bot on High, 1920x1080, off
screen. Numbers are the bot's 6-second measure at each map's spawn (chase camera). [measured]

| Map | avg fps old / new / old again | 1 % low old / new / old again | GPU ms per frame old / new / old again |
|---|---|---|---|
| Ashen valley | 35.7 / 32.5 / 35.6 | 29.4 / 29.9 / 31.8 | 27.7 / 30.5 / 27.8 |
| Sector 86 frontier | 38.8 / 35.7 / 40.1 | 32.5 / 35.3 / 25.9 | 25.5 / 27.8 / 24.7 |
| Palouse | 39.7 / 37.9 / 35.2 | 31.7 / 33.6 / 14.2 | 24.9 / 26.1 / 29.2 |
| Allegheny | 29.8 / 27.1 / 29.8 | 27.1 / 25.9 / 25.5 | 33.4 / 36.6 / 33.3 |
| Brilon | 44.2 / 39.9 / 45.0 | 35.4 / 37.9 / 39.3 | 22.4 / 24.8 / 21.9 |

Cost: about 2.5 to 3.3 ms of GPU time a frame, roughly 9 to 10 % of the average frame rate on every map
(Palouse's second old run was noisy). The 1 % lows are within run-to-run noise. Image folders:
`images/714-tex-ab4-old`, `715-tex-ab4-new`, `716-tex-ab4-old2` in `~/Games/eightysix`.

An earlier A/B (703 old, 704 new) with anisotropic filtering on every normal map cost 1.6 to 7 ms (Allegheny
the worst); dropping it on the normal maps and fetching the aerial relief only within 160 m brought it to the
table above.

## Tone ("never washed out")

`tools/histogram.py` over the 20 world shots, old (714) / new (715), same sitting, 0-255 sRGB:

| Shot | mean | black point | spread | mean saturation | clipped share |
|---|---|---|---|---|---|
| mean of 20 | 99.2 / 101.1 | 24.0 / 24.2 | 161.4 / 163.4 | 0.392 / 0.407 | 0.0085 / 0.0085 |

Saturation is up, the spread is a little wider, the black point and clipping did not move. Per map, Brilon's
saturation went down slightly (white and pale plaster walls, darker brick): start 0.367 to 0.341, street 0.316
to 0.292 (first before-set 687 against round-3 701).

## Disk

New texture sets in the repo: 13 world sets, 46 MB (2K JPG, quality 90), plus the Legion's paint, 3.8 MB:
49 MB in all. Download cache in `~/Forge/shared/assets/polyhaven/*/2k` (130 MB, includes three sets tried and
dropped) and `~/Forge/shared/assets/ambientcg/PaintedMetal004` (14 MB) and `PaintedMetal001` (15 MB, looked
at, not used). Check images of this pass: 27 folders, about 760 MB, in `~/Games/eightysix/images/687` to `717`.
