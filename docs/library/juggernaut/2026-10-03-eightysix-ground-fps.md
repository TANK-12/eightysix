# Eighty Six ground rework (R1): frame rates before and after
date: 2026-10-03 · for: both

Iris Xe, 1920x1080 off screen, avg fps. Before = ground shader at HEAD fec6d04; after = commit following 46231f7. GPU shared with other Relay bot runs, so differences under about 15 % are noise. First version of the new shader (no far-distance shortcut) was 15-40 % slower; the shortcut fixed it. Details: ~/Forge/sessions/juggernaut-alpha/results/R1.md

| map | preset | view | before | after (final) |
|---|---|---|---|---|
| small | low | view / walk | 86.3 / 65.4 | 87.3 / 80.1 |
| small | medium | view / walk | 67.2 / 71.3 | 65.3 / 60.2 |
| small | high | view / walk | 67.0 / 63.4 | 52.9 / 51.3 |
| big | low | still / walk_a / walk_b / town | 58.1 / 58.4 / 59.8 / 55.9 | 74.6 / 78.2 / 72.4 / 74.5 |
| big | medium | still / walk_a / walk_b / town | 51.9 / 51.7 / 49.7 / 49.6 | 60.5 / 61.9 / 57.6 / 59.0 |
| big | high | still / walk_a / walk_b / town | 61.6 / 49.7 / 37.2 / 59.9 | 49.8 / 50.3 / 45.8 / 44.9 |
