# Eighty Six: big map frame rate by preset

date: 2026-10-02 · for: both

`tools/bot_run.sh b5_fps --preset=<p>`, 1920x1080, off screen, quiet GPU, commit 5a3dd45 (Relay 22, images 369-372). Average fps (GPU ms per frame).

| preset | still | walking (two 10 s walks) | in front of the Kreuzberg buildings |
|---|---|---|---|
| Low | 103 (9.3) | 106-109 (8.8-9.1) | 84 (11.5) |
| Medium | 69 (14.2) | 69 (14.1-14.2) | 57 (17.3) |
| High | 49 (20.0) | 48-49 (20.0-20.3) | 42 (23.5) |
| Ultra | 15 (92) | 15 (109) | 15 (100) |

Ultra is the same as part 2 of the lane (92-111 ms). The averages hide the tile-build dips.
