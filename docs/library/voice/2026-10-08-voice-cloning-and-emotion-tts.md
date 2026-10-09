# Voice cloning and emotion-tag TTS for Forge (October 2026)

date: 2026-10-08 · for: both

Written by Relay task 120 (sessions 4 to 6, finished 2026-10-09). The question:
which local voice cloner was the new one on AI Search in the last few weeks, and
which open text-to-speech (TTS) models take emotion or style tags in the text,
in English and Japanese, sized for this laptop (i5-1245U, Iris Xe shared with
Jan, no dedicated GPU, about 54 GB free disk). Task 113 had already covered the
fast default (Kokoro) and the best near-human voice (Breeze TTS 2):
`2026-10-08-tts-small-fast-and-best.md`. This doc does not repeat that.
Measurements on this laptop are in `2026-10-09-voice-cloning-bakeoff.md`.

## Answer

- **The cloner from AI Search is AuK** (Tencent Hunyuan with Shanghai Jiao Tong
  University). Open-sourced 2026-09-09 under MIT; AI Search covered it in the
  news video of 2026-09-13 (around 10:30). A 1.5-billion-parameter model that
  builds the sound up in a few refining steps, steered by Qwen2.5-Omni-3B (a
  model that understands the text and the reference clip), plus a VAE (the part
  that turns the model's output back into sound), 24 kHz mono out. One model does:
  - zero-shot cloning: give it a reference clip and it speaks new words in that
    voice (English and Chinese only);
  - voice design from a written description;
  - editing an existing clip by an instruction: change the emotion (happy,
    angry, sad, fearful, surprised, disgusted, calm, excited), turn it into a
    whisper, add a laugh or breath or cough at the start or end, change speed
    or pitch, swap words, clean up noise, split speech from music.
  - AuK-Flash is the 4-step distilled version (much faster, no guidance).
  The original weights are about 6.8 GB plus 12 GB for the Omni part. The
  compressed model files used here (GGUF files at 8-bit, for audio.cpp) take
  6.1 GB on disk: AuK-Flash 1.6 GB, Qwen2.5-Omni-3B 4.0 GB, the VAE 0.6 GB
  (measured with du, 2026-10-09; an earlier draft said 3.3 GB, which was wrong).
- **Emotion-tag TTS, Japanese: Irodori-TTS v4.1 Anime** (Aratako; MIT plus
  ethical rules). Trained on anime-style speech. Takes emoji tags in the text
  (😠 angry, 😭 crying, 👂 whisper, 🤭 giggle, 😮‍💨 sigh, 😱 scream, 😰 nervous,
  😆 joyful, 🫶 gentle, 😊 cheerful, 😟 worried, 😲 surprised; 45 in all),
  clones from a clip with no transcript needed, and designs a voice from a
  Japanese description. 1.1 GB at q8. The natural pick for Eighty Six in
  Japanese.
- **Emotion-tag TTS, many languages: OmniVoice** (k2-fsa). 600+ languages,
  cloning from a clip plus its transcript, voice design from attributes, and
  bracket tags in the text: [laughter] [sigh] [surprise-ah] [question-en]
  [dissatisfaction-hnn] and a few more. 1.35 GB at q8. Weights are CC-BY-NC
  (non-commercial) because of the training data.
- **Breeze TTS 2** (task 113 wired it in): cloning plus a free-text
  instruction ("speak angrily, close to tears") and vocal tags like (laugh)
  and (sigh). English and Chinese in the .cpp port. Already on disk; not
  fetched again.
- **Runtime: audio.cpp v0.9.1** (0xShug0/audio.cpp, released 2026-10-07). One
  C++ (ggml) program that runs 110+ speech model families from a CLI or an
  OpenAI-style HTTP server: auk (added 2026-09-20), irodori_tts, omnivoice,
  sense_asr (SenseVoice speech recognition with emotion labels),
  sortformer_diar (who-spoke-when), bs_roformer and mel_band_roformer (vocal
  separation), index_tts2, qwen3_tts, voxcpm2 and more. That covers the
  later Eighty Six pipeline too (separate the voices from music, find who
  speaks when, label the emotion of each line). The prebuilt Linux binaries
  crash here (they need AVX-512, which the i5-1245U lacks), so it is built
  from source for this processor, with Vulkan (so it runs on the Iris Xe
  graphics chip):
  `models/voice/bin/audio.cpp-src/build/linux-vulkan-release/bin/`.

## Candidates looked at

Published figures from model cards, not measured here unless the bake-off doc
says so. "ja" means Japanese.

| Model | Out | Licence | Languages | Emotion control | Cloning | Verdict |
|---|---|---|---|---|---|---|
| AuK / AuK-Flash (Tencent) | 2026-09-09 | MIT | en, zh | edit by instruction (8 emotions, whisper, nonverbal) | yes, from a clip | picked: the cloner |
| Irodori-TTS v4.1 Anime | 2026 | MIT + ethics | ja | 45 emoji tags | yes, no transcript | picked: Japanese |
| OmniVoice (k2-fsa) | 2026 | CC-BY-NC | 600+ | bracket tags, attributes | yes, with transcript | tried; see bake-off |
| Breeze TTS 2 (task 113) | 2026-08-25 | non-commercial | en, zh (.cpp) | instruction + (laugh) (sigh) | yes | already in Forge |
| IndexTTS 2.5 | 2026 | other | en, zh, ja | emotion text or vector | yes | later: 3.5 GB q8, disk |
| Qwen3-TTS 1.7B CustomVoice | 2026 | Apache-2.0 | 10 incl. ja | instruct text | Base model only | not tried |
| VoxCPM2 (OpenBMB) | 2026 | Apache-2.0 | multi | style text | yes | not tried |
| Higgs TTS 3 4B (Boson) | 2026 | other | multi incl. ja | emotion | yes | too big for the iGPU |
| Chatterbox (Resemble) | 2025 | MIT | multi incl. ja | exaggeration knob | yes | older; no tags |
| Kyutai Pocket TTS | 2026-01 | MIT | en | none | yes, CPU | small; no emotion |

## Things to know

- **Voice actors.** Irodori's rules say: don't clone a real person's voice,
  voice actors included, without their consent, and they make no exception for
  private use. Cloning the Eighty Six cast with Irodori would go against them
  even on this laptop; that is Emerson's call. `--private` only marks such a
  voice so nothing made with it gets shared; it does not make the cloning
  allowed.
- **Breeze is research and non-commercial** (task 113's doc): fine here, not
  for anything that earns money (PulseForge).
- **Languages.** AuK clones in English and Chinese only; Japanese lines go to
  Irodori. Breeze's .cpp port has no Japanese either.
- **Memory.** Measured at peak in the bake-off: AuK about 7.5 GB and Irodori
  about 2.8 GB (an earlier draft guessed 4 and 1.5 GB). Both go through task
  113's heavy-model guard (load only with the memory free and Jan idle,
  otherwise the fast voice speaks).
- **Disk.** Task 120 added about 9.2 GB: AuK 6.1 GB, the audio.cpp source and
  build 1.8 GB (about 0.7 GB of that is build leftovers), Irodori 1.1 GB,
  SenseVoice 0.24 GB. OmniVoice (1.3 GB) was ruled out and moved to the Trash
  on 2026-10-09; it frees the space once the Trash is emptied.

## Sources

- AuK: https://github.com/Tencent-Hunyuan/AuK, https://huggingface.co/tencent/AuK,
  https://huggingface.co/tencent/AuK-Flash, cookbook
  https://github.com/Tencent-Hunyuan/AuK/blob/main/docs/COOKBOOK.md
- AuK GGUF: https://huggingface.co/audio-cpp/AuK-Base-and-Flash-GGUF
- audio.cpp: https://github.com/0xShug0/audio.cpp (v0.9.1),
  https://github.com/0xShug0/audio.cpp/blob/main/docs/community_models/auk.md
- Irodori and OmniVoice GGUF: https://huggingface.co/audio-cpp/audio.cpp-gguf
  (Irodori-TTS-v4-Small-GGUF/irodori-tts-v4.1-anime-q8_0.gguf,
  OmniVoice-GGUF/omnivoice-q8_0.gguf)
- Irodori: https://huggingface.co/Aratako/Irodori-TTS-v4.1-Small (emoji table and
  ethics), OmniVoice: https://huggingface.co/k2-fsa/OmniVoice
- AI Search news video, 2026-09-13 (YouTube channel AI Search).
