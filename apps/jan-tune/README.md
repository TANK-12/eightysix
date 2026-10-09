# Jan Tune

Finds the fastest settings for each Jan model by measuring them. Port 8461.

Pick a model (the list is scanned from Jan's `llamacpp/models/*/model.yml`,
embedding models skipped) and press **Find fastest settings**. Each test
starts a scratch `llama-server` from Jan's own Vulkan build on a spare port
(never Jan's own instance), sends one fixed ~1,500-token prompt, generates 128
tokens, and records llama.cpp's own speed figures. When the run finishes,
**Apply to Jan** writes the winner into the model's `model.yml` (after a backup
in `data/backups/`). Jan uses it from its next restart.

## What it tries (`KNOBS` in tune.py; one entry per setting)

| setting | values | written to model.yml |
|---|---|---|
| iGPU layers (`n_gpu_layers`) | 0, 25, 50, 75, 100% of the model's layers | yes |
| batch (`batch_size`) | 512, 1024, 2048 | yes |
| ubatch (`ubatch_size`) | 128, 256, 512 | yes |
| experts on CPU (`cpu_moe`) | off, on (mixture-of-experts models only) | yes |
| threads | 4, 6, 8 | no: Jan-wide, shown as a tip |

**Never changed:** the KV cache type (Jan's q8_0, which Emerson keeps for
answer quality) and the context size (set by him or by the apps).

The search starts from the model's current settings and tunes one setting at a
time, keeping the best found so far. Each setup runs twice (the median counts).
The fastest generation wins; within 3%, the faster prompt read breaks the tie.
A setup that fails to load (for example iGPU out of memory) is recorded as a
result, not a crash.

## Safety

Before each test it waits while any Jan model is working, while someone has a
`jan:` claim on the crew board, or while free memory is below the model size
plus 1.5 GB (no swap on this laptop). By default it first unloads idle,
unclaimed Jan models so the iGPU numbers are clean (they reload on the next
request). It claims `jan:<model>` as `jan-tune` while running and posts a note
on the `jan` board when done (see the Board app).

Results are saved to `data/results/<model>.json` after every test. A stopped
run resumes where it stopped.

## Advanced mode

Choose which values to try, runs per setting, the pause between tests
(default 10 s, so heat does not skew results), and whether to unload idle Jan
models first.

## Command line

    .venv/bin/python tune.py                        # list models
    .venv/bin/python tune.py MODEL [--apply]        # tune one

Tests: `.venv/bin/python -m pytest -q tests` (fake timings, never touches Jan).
