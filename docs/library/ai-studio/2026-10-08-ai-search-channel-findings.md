# What the AI Search YouTube channel says about local image, video and speech models

date: 2026-10-08 · for: both

Emerson pointed at the "AI Search" channel (@theAIsearch, brain logo) as the
best source on new local models. Read by Tetsu on 2026-10-08. Adds to
`2026-10-08-new-image-video-3d-models.md` (same folder); doesn't replace it.

**How it was read:** full transcripts for 4 videos (Qwen-Image 2.1, MiniMax H3
part 2, Ideogram 4, PiD). Only the descriptions and chapter lists for the rest,
because YouTube rate-limited the subtitle downloads (HTTP 429/403). All the
sizes and timings below come from the presenter's own PC: ComfyUI on an
**NVIDIA RTX 5000 Ada, 16 GB**. None of it has been run on Emerson's Iris Xe,
and none of it has been checked against stable-diffusion.cpp (sd.cpp), the
engine AI Studio uses.

## Image

| Model | What it does | Sizes he quoted | Links | Fits sd.cpp? |
|---|---|---|---|---|
| **Qwen-Image 2.1** (Alibaba, video BaE6UBfNdQk) | text to image, editing with up to 10 reference images, transparent PNGs, background removal | main model 14.2 GB (bf16) or 7.2 GB int8; GGUF Q3 is **3.19 GB** ("runs on 4 GB VRAM", quality close to full); text encoder Qwen3-VL W4A8 **6.3 GB** (skip the 9.5 GB prompt-enhancer files); VAE 676 MB. 29 s per image on his 16 GB card, 81 s per edit | `Comfy-Org/Qwen-Image-2.1`, GGUFs `Abiray/Qwen-Image-2.1-GGUF`, anime LoRA `WarmBloodAban/Qwen-Image-2.1-LoRAs` | upstream yes, but **needs an engine newer than our build** (841, 2026-09-04) |
| **Ideogram 4** (OA4gchz1Zcs) | best open text-in-image, bounding-box layout control, comics and manga | needs two models (main + "unconditional"), 9.28 GB each at fp8; text encoder Qwen3-VL 8B 10.6 GB fp8 / 6.3 GB NVFP4; "as low as 6 GB VRAM" with RAM offload | `Comfy-Org/Ideogram-4` | in the upstream list; not checked for our build |
| **PiD pixel diffusion** (NVIDIA, DlvhlQOBHBw) | 1K to 4K upscaler, and its own text-to-image | upscaler 2.7 GB bf16; t2i 2.6 GB; Gemma-2 2B encoder 2.6 GB fp8 / 5.2 GB fp16. The MXFP8 files only work on NVIDIA 50-series | `Comfy-Org/PixelDiT` | PiD is in the upstream list |
| Z-Image-Turbo | still his everyday base, often paired with PiD for 4K | bf16 12 GB; Qwen3-4B encoder | `Comfy-Org/z_image_turbo` | yes (already our top pick) |
| Flux 3, Ming-Image, LLaDA-Image, Fibo 1.5, Supra2-IMG, Bernini v2 | from news videos, descriptions only | n/a | see the descriptions | not checked |

## Video

| Model | What it does | Sizes he quoted | Links |
|---|---|---|---|
| **MiniMax H3** (8HutJ9W5pTg, G3YHSvXZP_g) | his "best open video generator": text, image or reference to video, video editing, makes its **own audio**, can do music-only and single-frame images | full bf16 40 GB; fp8/int8 21 GB; Kijai W4A8 **12 GB** ("about 8 GB VRAM"); unsloth GGUF Q2/Q4 **6.7 GB**; slimmer int8 video VAE 3 GB (official 5.2 GB); turbo LoRA 315 MB cuts 20 steps to 4-6; a preview TAE under 10 MB | `Comfy-Org/MiniMax-H3`, `Kijai/MiniMax-H3-experimental`, `unsloth/MiniMax-H3-GGUF`, `Abiray/MiniMax-H3-GGUF`, `Kijai/MiniMax-H3_comfy`, `lightx2v/Minimax-h3-Turbo`, `Kijai/MiniMax-H3-TAE`, prompt guides in `MiniMaxAI/MiniMax-H3/docs/` |
| **LTX 2.5** (ig3PUfSow5Y, "fastest local video") | text/image to video, first+last frame, LoRAs, has a low-VRAM chapter | transcript blocked; see the video at 12:50 | `Lightricks/LTX-2.5`, ltx.io/model/ltx-2-5 |
| Wan Animate 2 (in uJgzFn0GT7M) | character animation from a reference | n/a | humanaigc.github.io/wan-animate-2 |
| Viggle Animate, Viggle Meridian | character animation | n/a | `Viggle/Viggle-Animate`, `Viggle/Meridian` |
| VideoDeltaNet, Qwen Video Edit, JoyAI Video Edit, Magi 2 | editing or long video | n/a | in the descriptions |

He says that in ComfyUI the int8 / W4A8 builds now beat GGUFs on quality.
sd.cpp only loads GGUF/safetensors, so for AI Studio **GGUF is still the
format to use.**

## 3D worlds (news only, all papers or NVIDIA-class)

H3 World, WorldClaw (Tencent), Hunyuan3D Buffalo, Inspatio World 1.5,
WorldCrafter, Block 3D, One Video One World, Evoke, 4DAnyone, Atlas (World
Labs, cloud), Runway GWM Worlds 2 (cloud). None runs through sd.cpp.

## Speech and music (passed to the TTS/STT session)

TTS: Index TTS 2.5 (`IndexTeam/IndexTTS-2.5`), Audio8 TTS 0.1B
(`Audio8/Audio8-TTS-Preview-0.1b`), Dots TTS (rednote-hilab), WavTTS
(wavtts.github.io), Higgs Audio v3 (boson.ai), VocalRender, LeapTalk,
VoiceMem. STT: CrisperWhisper (nyra-labs.com/crisperwhisper). Cloud only:
Gemini 3.8 TTS, Gemini 3.5 Transcribe. Music: MiniMax Music 3 (ComfyUI
docs), YuE2 (video 9RtywbN--QE), MiniMax H3 audio-only, Mirelo audio to MIDI.

## What this changes for the AI Studio build

- Add **Qwen-Image 2.1 Q3 GGUF (3.19 GB)** as a compact pick if the new
  engine loads it. It's the only small model that does editing and
  transparency.
- Add **MiniMax H3 Q2/Q4 GGUF (6.7 GB)** as the video model to try first
  after Wan2.2 5B. It makes sound too.
- Keep the big ones (Ideogram 4, LTX 2.5, MiniMax fp8) as connected-only.

## World models that build the world as you go (added same day)

Emerson is most interested in these. Checked on the project pages and in the
news-video transcripts (ngyFRCNq0Yc, lHmZoRHMZyM, rQ4yX5qNYdY):

| Model | What it does | Open? | Size quoted | Links |
|---|---|---|---|---|
| **Inspatio World 1.5** | one image (or a few, a panorama, a video) plus a camera path, then a walk-through video; "real-time scene roaming"; can freeze for bullet time | code + weights | built on Wan 2.1 1.3B, **under 6 GB** | github.com/inspatio/inspatio-world-v1.5, hf `inspatio/world-1.5` |
| **WorldCrafter** (TencentARC) | streaming interactive world, few-step distilled for real time | code + weights | n/a | github.com/TencentARC/WorldCrafter, hf `TencentARC/WorldCrafter-Fast` |
| **SolarWM** | turns a video model into a real-time interactive world for an hour or more; versions for Wan 5B, Wan 14B, LTX 2.5, MiniMax H3; data set released | code + weights | the Wan 5B one is the smallest | github.com/Junchao-cs/SolarWM, hf collection `junchaoh-cs/solarwm` |
| **H3 World** | MiniMax H3 as a game engine: key presses become actions in the video | code released | MiniMax H3 sizes (6.7 GB GGUF up to 40 GB) | danzer1xxxxchan.github.io/H3-World |
| **Evoke** | 14B, 3-step, joystick-driven world, add events by prompt ("add balloons"), sessions for hours | fully open, Apache-2 | **57 GB** | github.com/SII-YuanyangYin/Evoke, hf `SII-YuanyangYin/Evoke` |
| 4DAnyone | a video of a person becomes a 4D Gaussian splat you can view from any side | open | 12 GB | 4danyone.github.io |
| One Video One World | a video becomes an explorable 3D/4D scene, GLB export | code | n/a | github.com/yisuanwang/OVOW |
| Atlas (World Labs), Runway GWM Worlds 2 | the best ones | **closed / cloud**, waitlist | n/a | n/a |

All of these are PyTorch projects aimed at NVIDIA cards. Not checked: whether
any of them runs on an Intel iGPU or the CPU. That is helper-2's first job in
the rebuild (`apps/ai-studio/docs/WORLDS.md`).
