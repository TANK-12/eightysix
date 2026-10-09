# Which 3D world models can run on this laptop (feasibility check)

date: 2026-10-08 · for: both · by Rei (helper-2, crew ai-studio)

Full write-up, runner design and install plan: `~/Forge/apps/ai-studio/docs/WORLDS.md`.
Sizes from the Hugging Face API; [v] = verified, [r] = reasoned.

| Model | Download a run needs | Needs NVIDIA (CUDA)? | Verdict here |
|---|---|---|---|
| InSpatio-World 1.5 | 24.4 GB [v] | as shipped yes (code exits without CUDA); no custom kernels, flash-attn optional [v] | maybe on the CPU after a patch; slow, RAM risk [r]; not installed |
| WorldCrafter-Fast | 147.2 GB [v] | yes (README) [v] | no |
| SolarWM Wan2.2 5B | ~74 GB, gated [v] | yes [v] | no |
| Evoke | 80.5 GB (repo 411 GB) [v] | yes; UI quoted on 5x H200 [v] | no |
| H3-World | 131 MB add-on + 33B MiniMax-H3 [v] | needs their attention patch [v] | no |
| HY-World 2.0 | 174.7 GB+ [v] | yes, CUDA kernels [v] | no |
| 4DAnyone | 21.3 GB [v] | pose stack CUDA-first [r] | no; people-to-4D, not a walk-through |
| One Video One World | many parts; >=40 GB graphics memory [v] | yes, compiles CUDA [v] | no |
| Atlas, Marble, Runway GWM | closed / cloud | n/a | never a card |

- PyTorch's Intel GPU support does not list Alder Lake Iris Xe [v].
- What runs: an approximate walk-through made with stable-diffusion.cpp +
  Wan2.1 VACE 1.3B (6.3 GB, our build has `--control-video`) [v]. Speed untimed.
- InSpatio's weights have the Wan2.1 1.3B layout with a 36-channel input [v].
