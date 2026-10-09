# AI Search channel: the latest two videos (read 2026-10-08)

date: 2026-10-08 · for: both

Channel: AI Search (https://www.youtube.com/@theAIsearch, brain icon, confirmed by yt-dlp: channel name "AI Search"). Both videos below are regular uploads; no newer Shorts showed in the newest six uploads.

How it was read: descriptions through yt-dlp. yt-dlp subtitle downloads failed with HTTP 429 (Too Many Requests) in json3 and vtt, so the transcripts came through the acchan video_transcript tool instead. Everything quoted is what the presenter says; none of it is tested here. Weights and sizes are as stated in the video, "not stated" where he did not say.

## Video 1: "The AI unlock has begun" (listed earlier as "AI is reverse engineering everything")

- Upload date: 2026-10-06, about 14.5 minutes
- Link: https://www.youtube.com/watch?v=h5zkzon0gM4
- Summary: AI models can now reverse engineer compiled software and games from the binary (he quotes over 99% success after four attempts on SRE Bench for GPT-6 Astra, and says Claude Opus 5.5 looks even better). People use this to mod games three ways: a pass-through mod that bridges two running games, rebuilding a game in Rust, and porting one game's mechanic into another. Nothing here is about speech, images or video generation, apart from the sponsor segment.

Models and tools mentioned:

| Name | What it does | Open weights? | Size | Link |
|---|---|---|---|---|
| GPT-6 Astra (OpenAI) | frontier chat/coding model, top SRE Bench score | no, hosted | not stated | none in description |
| Claude Opus 5.5 | frontier model, "works really well" for modding | no, hosted | not stated | none |
| GPT-6.1 Sol | cheaper OpenAI model, named as usable for modding | no, hosted | not stated | none |
| Universal Modder | agent skills incl. a mashup skill for pass-through mods | open source (GitHub) | not stated | https://github.com/rehan-remade/universal-modder |
| Reverse Engineer Anything (rea) | prebuilt skills and MCPs for reverse engineering | open source | not stated | https://github.com/morluto/rea |
| AI game modding guides | step-by-step guides, prompts, a pass-through and a Rust rewrite example | open source | not stated | https://github.com/trevaintdead/ai-game-modding-guides |
| Ghidra MCP | lets an agent drive Ghidra | open source | not stated | https://github.com/bethington/ghidra-mcp |
| IDA MCP | lets an agent drive IDA | open source | not stated | https://github.com/HexRaysSA/ida-mcp |
| ILSpy | .NET decompiler | open source | not stated | https://github.com/icsharpcode/ilspy |
| Cpp2IL | Unity IL2CPP decompile helper | open source | not stated | https://github.com/SamboyCoding/Cpp2IL |
| AnyPS5, PortPS5 | AI-assisted PS5 to PC porting projects | open source | not stated | https://github.com/boykopovar/AnyPS5 , https://github.com/yuriolive/PortPS5 |
| Runway (sponsor) | hosted creative suite; Runway Agent builds a video with dialogue, voiceover, music | no, hosted | n/a | https://runwayml.com/aisearch-oct (code MKTG50, 50% off first month) |

Also named in passing as hosted generators on Runway: GPT image, nano-banana (image), Seedance and Kling (video).

## Video 2: "Gemini 4, GPT 6.1, Plasma conjecture, Napoleon code solved, OpenAI Dots, Claude Sonnet 5.5: AI NEWS"

- Upload date: 2026-10-04, about 40 minutes
- Link: https://www.youtube.com/watch?v=lHmZoRHMZyM
- Summary: weekly news. Claude Sonnet 5.5 released (default on the free plan, but the most expensive model per task on one index). OpenAI Dev Day: Dots (a persistent cloud agent) and GPT 6.1 Sol. Google's Gemini 4 Argon (limited access). Two tiny open speech-to-text models, two new image models, 4-step video distillation, a camera-path video model, a video upscaler, and ElevenLabs V4 text to speech.

Models and tools mentioned:

| Name | What it does | Open weights? | Size / VRAM | Link |
|---|---|---|---|---|
| InSpatio World 1.5 | image(s), panorama or video plus a camera path in, a video walking through the scene out | code released; built on Wan 2.1 1.3B | under 6 GB, "fits most consumer GPUs" | https://inspatio.github.io/inspatio-world-1.5/ |
| Sol Refiner (NVIDIA) | one-step video upscale up to 4K, works on output of any video model (MiniMax H3, Cosmos, Wan); sharper but changes details, not faithful | code released | not stated | https://nvlabs.github.io/Sana/Sol-Refiner/ |
| Whistle (Cactus) | speech to text, 30 s per pass, auto language detect, word timestamps, CPU only, no dependencies, decodes about 6x faster than Whisper base, lower error rate than Whisper base on some benchmarks; install is a pip command, models on Hugging Face | open | 16.9 MB | https://cactuscompute.com/blog/whistle |
| Phonon 2 (Fermion) | speech to text (he calls it "tiny text to speech" but it is transcription): about an hour of audio in about 20 s; second lowest average error rate in its benchmark table; free Hugging Face spaces | open source | under 900 MB | https://www.fermionresearch.com/research/phonon-2/ |
| ElevenLabs V4 | text to speech, "most emotive", metatags in the script steer tone, direction, sound effects; he says it tops a TTS leaderboard; free plan gives 10,000 credits | no, hosted | n/a | https://elevenlabs.io/v4 |
| Claude Sonnet 5.5 | Anthropic smaller model; close to Opus 5.5, default on free plan, highest tokens per task so priciest on one index | no | not stated | https://www.anthropic.com/claude-sonnet-5-5 |
| Dots (OpenAI) | always-on cloud agent with its own computer; runs on GPT-6 Astra; Pro and business, not EU | no | n/a | https://openai.com/index/introducing-dots/ |
| Open Dots (two projects, same name) | self-hosted open alternatives; bring your own LLM | open source | n/a | https://github.com/Anil-matcha/Open-Dots , https://github.com/CopilotKit/OpenDots |
| GPT 6.1 Sol | near Astra intelligence for about a fifth of the price | no | n/a | https://openai.com/index/introducing-gpt-6-1-sol/ |
| Luma Ray 3.2 (sponsor) | hosted video model, good at motion and physics | no | n/a | https://lumalabs.ai/aisearch-oct1 |
| Comfy Agent | agent inside ComfyUI that plans, builds and runs node workflows and fixes errors; Comfy Cloud now, Comfy Desktop "in a few weeks" | n/a (feature) | n/a | https://blog.comfy.org/p/comfy-agent-the-first-agent-for-craft |
| PixelUMM (NVIDIA) | understands and generates images and video directly in pixel space, no latent decoder; quality below frontier, research preview | code and model released, mostly Apache 2 | not stated | https://nv-tlabs.github.io/PixelUMM/ |
| Ideogram 4.5 | image editing, only touches the edited region, bounding boxes for regions; plans to open source | not yet (planned) | n/a | https://ideogram.ai/models/4.5/ |
| Flux 3 image (BFL) | image gen and edit, bounding-box layout, up to 10 reference images; claims weights later, but Flux 3 video was promised months ago and is still not open | not yet | n/a | https://bfl.ai/models/flux-3-image |
| Gemini 4 Argon | Google frontier model, 1M output tokens, lowest hallucination rate quoted (15%); private access for now | no | n/a | https://blog.google/innovation-and-ai/models-and-research/gemini-models/gemini-4-argon/ |
| DMAD (ByteDance) | distillation: MiniMax H3 video in 4 steps instead of 20 to 30; LoRAs | code and LoRAs released | each LoRA 1.4 GB | https://yzmblog.github.io/projects/DMAD/ |
| PDMD (ByteDance) | second 4-step distillation, projects away critic errors, better motion than other methods | code and models released | full MiniMax H3 base 66 GB; or LoRA about 1.4 GB on a quantized MiniMax | https://pdmd2026.github.io/ |
| Plasma conjecture papers | GPT-6 Astra found counterexamples to a plasma-physics question open since 1967 | n/a | n/a | https://github.com/lukasliehr/Grad-Conjecture , https://github.com/landreman/analytic_3d_equilibria |
| Tactile Step | pressure insoles give humanoid feet a sense of touch; up to about 50% lower touchdown force | not stated | n/a | https://tactilestep.github.io/ |
| Humanoid badminton (Tsinghua, Unitree G1) | robot plays badminton | not stated | n/a | https://sunlight02.github.io/humanoid-badminton/ |
| Napoleon code | GPT-6 Astra decoded a 217-year-old cipher letter in about six hours | n/a | n/a | https://carter.church/writeups/the-letter-to-marmont/ |
| PAMI | text plus object to a 3D human-object interaction animation, MIT; model not yet out | code only | n/a | https://coral79.github.io/pami/ |
| Point2Part | point prompts split an image or mesh into clean separate parts; models planned | not yet | n/a | https://henrytsui000.github.io/Point2Part/ |
| AstaBrief (Ai2) | 8B model on Qwen3 writing cited reports from papers | fully open | 8B, about 32 GB on disk | https://allenai.org/blog/astabrief |
| Olmo Core 3 (Ai2) | training system for mixture-of-experts models, 2.7x faster training | open | n/a | https://allenai.org/blog/olmocore3 |
| IQuest Q1 | agentic model for command-line coding tools, 320B mixture of experts, 15B active | code released | 320B | https://github.com/IQuestLab/IQuest-Q1 |
| AREX 2 (BAAI) | 27B Qwen-based model that iterates on its own answers | open (Hugging Face) | 27B, about 55 GB | https://huggingface.co/BAAI/AREX-2 |

## Relevant to voice (speech-to-text, text-to-speech)

- Whistle (Cactus): the smallest speech-to-text model he has seen, 16.9 MB, runs on CPU only with no dependencies, handles 30 s per pass, detects the language, gives word-level timestamps, claims about 6x faster decoding than Whisper base and lower error than Whisper base on some benchmarks (not all). Install is a pip command with models on Hugging Face. Strong candidate for push-to-talk on this laptop; the claim comes from the presenter and the project page, not tested here. Link: https://cactuscompute.com/blog/whistle
- Phonon 2 (Fermion): under 900 MB, about an hour of audio in about 20 s, second lowest average error rate in the table he showed, open source with free Hugging Face spaces. Better fit for long recordings than for live commands. Link: https://www.fermionresearch.com/research/phonon-2/
- ElevenLabs V4 is the only text to speech item. It is hosted (not local), so it does not fit a local-only voice service, but its metatag idea (inline tags such as tone or sound effect inside the script) is worth copying as a feature. Free plan: 10,000 credits.
- Nothing in video 1 touches voice.

## Relevant to image and video (AI Studio)

- Wan 2.1 1.3B based InSpatio World 1.5: image plus camera path to a walkthrough video, under 6 GB, so it fits ordinary consumer GPUs. Code is released.
- DMAD and PDMD (ByteDance): 4-step video generation on MiniMax H3 instead of 20 to 30 steps, about 5 to 7 times fewer steps. The LoRAs are about 1.4 GB each. PDMD also ships a full distilled base (66 GB) or a LoRA on top of a quantized MiniMax, and is judged better on motion and consistency than other distillation methods. The same distillation idea is said to work on other video and image models, which suggests trying it on the Wan family AI Studio already runs. Links: https://yzmblog.github.io/projects/DMAD/ , https://pdmd2026.github.io/
- Sol Refiner (NVIDIA): one-step video upscale to 4K for any video model; caveat from him: sharper but changes details, not faithful. Link: https://nvlabs.github.io/Sana/Sol-Refiner/
- MiniMax H3 is called "the best open video model" in the video; it is the base the two distillations and the refiner target.
- Image side: Ideogram 4.5 and Flux 3 image are the two new editors, both hosted today. Both say weights will follow, but Flux has not delivered on Flux 3 video, so do not plan around either. Ideogram 4.5 is "pixel-consistent" region editing; Flux 3 takes up to 10 reference images and bounding-box layout.
- PixelUMM (NVIDIA): code and model released, pixel-space image and video generation, quality below frontier; research only.
- Comfy Agent: agent in ComfyUI that builds and runs workflows; Comfy Cloud only for now, desktop in a few weeks.
- Hosted only, no local use: Runway, Luma Ray 3.2.
