# Text to speech for Forge: small and fast, and the best open weights (October 2026)

date: 2026-10-08 · for: both

Written by helper-2 (Rei) in crew `voice`, Relay task 113. Two questions: which small,
fast open-weight TTS should Forge's voice app speak with on this laptop (i5-1245U, no
dedicated GPU, Iris Xe shared with Jan), and which open-weight TTS is the best there is
right now and what would it cost to run here.

## Picks

- **Fast default: Kokoro-82M v1.0 (ONNX), engine `kokoro_onnx`.** Already on disk, no
  download. Best-rated small model on the Artificial Analysis open-weights arena
  (Elo 1064, tied 5th to 6th with NVIDIA's 357M Magpie, ahead of Maya1, Chatterbox,
  Higgs Audio V3 and VibeVoice). Measured here it ran faster than real time on the
  ~60-word sentence even with load average around 17. Apache-2.0. ONNX runtime only,
  no torch.
- **Best (published quality): Breeze TTS 2 (BreezeBlue, 3B, open weights Aug 25 2026).**
  Number 1 open-weights model on Artificial Analysis (Elo 1219; only about 65 behind
  the best hosted model). It is too slow for live replies here. It could work for
  offline narration only, through the Breeze-TTS-2.cpp GGUF build. The licence is
  research and non-commercial, which is fine for Emerson's personal use. Not
  downloaded or wired yet; the cost is under "What the best option would cost here".
- **For practical purposes, the best TTS for live replies on this laptop is still
  Kokoro.** Nothing ranked above it on the arena runs anywhere near real time on
  this CPU.
- Worth keeping on the list: **Kyutai Pocket TTS** (MIT, ~100M, the only CPU option
  that clones a voice from about 5 s of audio; needs torch) and **Supertonic 3**
  (OpenRAIL-M, 99M, ONNX, 31 languages; it lost to Kokoro here).

## Measured on this laptop (2026-10-08, 21:33 to 21:39)

All numbers in this table are **measured here**. Setup: scratch venv, Python 3.12,
onnxruntime 1.30.0 on CPU, `taskset -c 0-3` (the P-core threads), 4 intra-op threads,
`nice -n 10`. Each run loads the model, synthesizes the 20-word sentence twice (the first
call is "first audio"; these engines are not streamed, so first audio = the whole first
sentence), then the 60-word sentence twice; RTF comes from the second call (synthesis
time / audio length; under 1 is faster than real time).

**Caveat: the machine was busy.** Other crew sessions were running at the same time, and the
1-minute load average ran from 17 to 43 on a 12-thread CPU (logged per run). Absolute
times are pessimistic and the ranking between close candidates is noisy. Re-time on a quiet machine
before trusting small differences.

| Candidate | Model on disk | Load s | First audio s (20 w) | RTF 20 w | RTF 60 w | Peak RSS MB | Load avg (1/5/15 min) |
|---|---|---|---|---|---|---|---|
| Kokoro-82M v1.0 ONNX fp32, `af_heart` | 354 MB | 1.3 | 3.8 | 0.84 | **0.54** | 1347 | 17.4 / 8.4 / 3.5 |
| Piper en_US-ryan-high | 121 MB | 1.4 | 4.3 | 0.88 | 1.91 | 426 | 20.9 / 11.5 / 5.0 |
| Supertonic 3, 5 steps, M1 | 383 MB | 2.6 | 9.3 | 0.58 | 1.69 | 584 | 31.9 / 16.2 / 7.0 |
| Supertonic 3, 2 steps, M1 | 383 MB | 7.8 | 7.5 | 1.58 | 1.27 | 588 | 43.5 / 24.5 / 10.9 |
| KittenTTS nano 0.8, Jasper | ~55 MB (blob) | 11.6* | **2.0** | **0.30** | **0.49** | 858 | 34.5 / 24.4 / 11.3 |
| KittenTTS mini 0.8, Jasper | ~75 MB (blob) | 3.4 | 8.3 | 1.38 | 1.28 | 1149 | 24.1 / 23.4 / 12.1 |

\* Kitten nano's load includes the first `import kittentts`, which pulls in the
misaki/spaCy stack.

Install sizes measured in that venv: onnxruntime 62 MB, espeakng-loader 21 MB, kokoro-onnx
0.2 MB, phonemizer 0.4 MB (so the Kokoro stack is about 85 MB), piper-tts 46 MB,
supertonic 0.2 MB (+ onnxruntime). **kittentts 0.8.1 pulled torch 2.14.1 (1.2 GB) through
`misaki[en]` → curated-transformers**, which made the whole venv 5.7 GB. That alone rules
Kitten out as the default.

Reading the table: Kokoro is the best-rated model here and also had the best long-sentence
RTF of the ONNX models apart from Kitten nano. Kitten nano is the fastest, but published
reviews and the arena put its quality well below Kokoro's, and it needs torch. Supertonic's published
speed (RTF about 0.012 on an M4 Pro) did not show up on this CPU under load. Piper is light
on RAM but slower than real time on long text here.

Listening: six 60-word wavs were saved under `/tmp/voice-tts-bench-out/*.wav` for a
listening pass. **No listening was done in this session**, so every quality claim
above comes from published arena or UTMOS figures.

## Candidates, small and fast (published figures)

| Model | Released | Params | Licence | Published quality and speed | Runtime | Link |
|---|---|---|---|---|---|---|
| Kokoro-82M v1.0 | Jan 2025 | 82M | Apache-2.0 | AA open-weights Elo 1064 (5th to 6th); UTMOS 4.44 (ONNX); CPU RTF 0.64 (heyneo, Jul 2026) | ONNX (`kokoro-onnx`) | https://huggingface.co/hexgrad/Kokoro-82M |
| Supertonic 3 | 2026 | ~99M | OpenRAIL-M (code MIT) | UTMOS 4.32 at 5 steps, 1.53 at 2 steps; RTF 0.24 / 0.12 (heyneo); "1,200+ chars/s" vendor claim; 31 languages, 44.1 kHz | ONNX (`supertonic` 1.3.1) | https://huggingface.co/Supertone/supertonic-3 |
| Supertonic 2 | 2025 | ~66M | OpenRAIL-M | RTF 0.012-0.015 on an M4 Pro CPU (vendor) | ONNX | https://huggingface.co/Supertone/supertonic-2 |
| Kyutai Pocket TTS | Jan 2026 | ~100M | MIT | UTMOS 4.10, RTF 0.71 flat (heyneo); 5 s zero-shot voice cloning on CPU | PyTorch CPU | https://huggingface.co/kyutai/pocket-tts |
| KittenTTS nano / mini 0.8 | 2026 | 15M / 80M | Apache-2.0 | about 17x real time (nano, picovoice) | ONNX, but the package pulls torch | https://github.com/KittenML/KittenTTS |
| KittenTTS 2 | 2026 | 1.7B | Stellon Labs Community Licence (commercial limits) | "2-3x slower than real time" on CPU; 47 voices, cloning | `KittenTTS-ml` | https://stork.ai/blog/kittentts-2-got-biggerand-more-complicated |
| Chatterbox Nano / Turbo | 2026 / 2025 | 110M / 350M | MIT | Nano: 3x real time on 8 CPU cores (vendor); Turbo collapses the decoder to one step | PyTorch | https://www.resemble.ai/learn/models/chatterbox-nano |
| Inflect-Nano-v1 | 2026 | 4.6M | Apache-2.0 | RTF 0.145, but "buzzy and robotic" by ear; one male voice | small | https://huggingface.co/owensong/Inflect-Nano-v1 |
| Piper (ryan-high) | 2023+ | ~30M | MIT (voice cards vary) | RTF under 1 on a Raspberry Pi for short text | ONNX (`piper-tts` 1.8.0) | https://github.com/OHF-Voice/piper1-gpl |

Not covered in the time available (no 2026 figures gathered): Soprano, NeuTTS Air/Nano,
Kani-TTS. They were not measured.

## Candidates, best quality (published figures)

Artificial Analysis open-weights Speech Arena, read 2026-10-08
(https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights):

| Rank | Model | Elo | Released | Params | Licence | Can it run here? |
|---|---|---|---|---|---|---|
| 1 | Breeze TTS 2 | 1219 | Aug 2026 | 3B | BreezeBlue research and non-commercial | Offline only: GGUF build, Vulkan or CPU, 1.2x real time on an RTX 3060, so expect several times slower than real time here |
| 2 | Fish Audio S2 Pro | 1117 | Mar 2026 | 4.6B (4B + 400M Dual-AR) | Fish Audio Research Licence (non-commercial) | No: 12 GB VRAM minimum |
| 3 | Step Audio EditX | 1097 | Feb 2026 | n/a | n/a | not checked |
| 4 | Voxtral TTS (Mistral) | 1083 | Mar 2026 | 4B | CC BY-NC 4.0 | No: 4B, GPU |
| 5-6 | Magpie-TTS Multilingual 357M (NVIDIA) | 1066 | Feb 2026, v2607 Jul 2026 | 364M | NVIDIA Open Model License | Maybe, but it needs NeMo plus torch and is GPU-tuned; CER 0.37-3.17%, speaker similarity 0.73-0.83 |
| 5-6 | **Kokoro 82M v1.0** | 1064 | Jan 2025 | 82M | Apache-2.0 | **Yes, measured above** |
| 7-9 | Maya1 | 1048 | Jun 2025 | 3B | Apache-2.0 | No (GPU) |
| 6-10 | OpenAudio S1 Mini | 1044 | Jun 2025 | 0.5B | CC BY-NC-SA | Slow on CPU |
| 7-10 | Higgs Audio V3 TTS | 1037 | Jun 2026 | n/a | n/a | not checked |
| 10 | Chatterbox | 1025 | May 2025 | 0.5B | MIT | Slow on CPU |
| 12-13 | VibeVoice 1.5B | 958 | Aug 2025 | 1.5B | MIT | No |

Breeze TTS 2 facts (vendor claims via https://www.orcarouter.ai/blog/breeze-tts-2-tops-open-weights-speech-arena):
50 languages, voice design from a text description, voice direction, cloning, speaker
similarity 0.67 (vendor-reported), sub-40 ms streaming latency on their GPUs. The official
PyTorch build needs a 12 GB GPU (24 GB for the fast path).

The AI Search channel's two latest videos (helper-6,
`2026-10-08-ai-search-latest-two-videos.md`) mention no new open TTS. ElevenLabs V4 is
hosted only; its inline tone tags are an idea to copy later. The two speech-to-text models
they mention (Whistle, Phonon 2) are helper-1's area.

## The best option, wired in and measured here (2026-10-08 late, Relay task 113)

Breeze TTS 2 through Breeze-TTS-2.cpp (https://github.com/HoppouAI/Breeze-TTS-2.cpp,
Apache-2.0 code, GGUF weights at https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp) is
installed and is Forge's "best voice" (commit d0f4ece, fixes in 77faebd).

- Weights: q4_k, 2.4 GB, in `~/Forge/models/voice/tts/breeze-tts-2/` (size matches
  Hugging Face), with `ref_voice.wav`, the clip the default "harbour" voice is cloned
  from (transcript: "The harbour lights came on one by one as the evening tide began to
  turn."). Other sizes: q6_k 2.9 GB, q8_0 3.3 GB ("no audible loss"), f16 5.9 GB.
- Build (as run): in `~/Forge/models/voice/bin`, `git clone --recursive --depth 1 --branch
  v0.1.0 --shallow-submodules https://github.com/HoppouAI/Breeze-TTS-2.cpp`, then in it
  `cmake -B build -G Ninja -DCMAKE_BUILD_TYPE=Release && cmake --build build -j 6`. The
  default build used Vulkan on the Iris Xe. The binaries link ggml libraries inside that
  build folder, so keep the whole folder (643 MB with the other voice binaries).
- Measured (verified): Vulkan on the Iris Xe, real-time factor 5.0 and 4.4 (seconds of
  compute per second of speech) while the GPU was shared with a Godot render; CPU only
  9.0. Whisper heard both test lines back word for word. Through the Voice page on a
  scratch backend: 2.72 s of speech made in 24.2 s. The earlier guess (4 to 12 s per
  second of audio) held.
- So it suits narration or a one-off "say this nicely", not live replies; Kokoro stays
  the default voice.
- How Forge runs it: registry row `breeze-tts-2` (`heavy`, tier best, `ram_mb` 3500,
  `idle_unload_s` 120) and `defaults.tts_best`; `apps/voice/engines/breeze_cpp.py` starts
  `breeze-server` on a free local port when the row is first used and stops it after 2
  minutes idle. It loads only with 5000 MB free (`ram_mb` + 1500) and Jan idle; otherwise,
  or on any failure, Kokoro speaks and the `X-Voice-Fell-Back` header says why.
- Licence: the weights are research and non-commercial only (BreezeBlue).

Cheaper "better than Kokoro in some way" option: Kyutai Pocket TTS, for a cloned voice.
It needs a separate torch CPU venv (torch about 1.2 GB installed, model about 0.4 GB) and
ran at RTF 0.71 in the published benchmark, so with this machine's load expect roughly
real time.

## Sources

- Artificial Analysis open-weights arena: https://artificialanalysis.ai/text-to-speech/leaderboard/provider-voice/open-weights
- heyneo CPU benchmark, Jul 2026 (Kokoro, Supertonic 3, Inflect-Nano, Pocket TTS): https://heyneo.com/blog/kokoro-supertonic-inflect-nano-pocket-tts-cpu-benchmark
- Picovoice on-device TTS benchmark 2026: https://picovoice.ai/blog/on-device-tts/
- Breeze TTS 2: https://www.orcarouter.ai/blog/breeze-tts-2-tops-open-weights-speech-arena , https://huggingface.co/HoppouAI/Breeze-TTS-2.cpp
- Fish Audio S2 licence: https://fish.audio/fr/blog/what-we-mean-by-open-source-for-s2/ , weights https://huggingface.co/fishaudio/s2-pro
- Voxtral TTS: https://siliconangle.com/2026/03/26/mistral-releases-open-weights-speaking-AI-model-voxtral-tts/
- Magpie-TTS Multilingual: https://huggingface.co/nvidia/magpie_tts_multilingual_357m
- Supertonic 3: https://huggingface.co/Supertone/supertonic-3 ; KittenTTS 2 review: https://stork.ai/blog/kittentts-2-got-biggerand-more-complicated
- Chatterbox Nano: https://www.resemble.ai/learn/models/chatterbox-nano
