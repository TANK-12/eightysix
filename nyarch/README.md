# Nyarch Assistant setup

> **Start with [`MANIFEST.md`](MANIFEST.md)** — it lists what to check and do
> next, and the one open bug. This file explains how the thing is built and why.
> Per-session records are in [`sessions/`](sessions/).

Glue that turns **Nyarch Assistant** (the Flatpak `moe.nyarchlinux.assistant`,
a Newelle fork) into a voice assistant that can see the screen, read documents
aloud and run terminal commands, using models and voices this machine already
has. Nothing here downloads a model.

This is **not** a Forge app — there is deliberately no `forge_app.json`, so
`forge.py` will not discover it. It lives under `~/Forge/` only because
everything it borrows (Kokoro voices, Stable Diffusion models) lives here too.

## What runs where

```
Nyarch Assistant (virtualization=false, so this is the HOST, not a sandbox)
  ├── chat  ──────────► Jan's OpenAI-compatible API at 127.0.0.1:1337
  │                       ├── primary   qwen35-0_8b…      fast replies (~0.3 s)
  │                       └── secondary Qwen3_5-4B-IQ4_XS vision + harder work
  ├── voice ──────────► flatpak-spawn --host → forge_tts.py
  │                       └── NovelForge's .venv + Kokoro (already installed)
  ├── screen ─────────► flatpak-spawn --host → screenview.py
  │                       ├── shot    screen-share portal → PipeWire → PNG
  │                       └── scroll  ydotool
  ├── files ──────────► built-in file_editing tools (read/write/glob/grep), home-wide
  ├── terminal ───────► built-in execute_command tool, flatpak-spawn --host (real system)
  └── images ─────────► AI Studio's stable-diffusion.cpp binaries + models
```

The assistant routes any chat containing an image to the **secondary** model
automatically (`secondary-llm-vision`), so a screenshot always lands on the 4B
that can actually see, while ordinary typing stays on the fast 0.8B.

**`virtualization` is off (2026-09-12), on purpose, with the user's
confirmation.** With it on, `execute_command` runs inside the Flatpak's own
sandbox — no real browser, no real apps, nothing outside the sandbox. Off,
every command runs for real on the host via `flatpak-spawn --host`, the same
route `forge_tts.py`/`screenview.py` already use. This is what makes "open
the browser" / "launch an app" possible, and it means a voice-triggered wake
word can now run arbitrary host commands with the user's own permissions
(bounded only by the short builtin blocklist in `command_permissions.py` —
`rm -rf`, `mkfs`, `dd`, and a few others — since `default-risk-level` is
`allow`).

## Files

| File | What it does |
|---|---|
| `screenview.py` | `shot` / `scroll` / `setup`. Runs on the host. |
| `forge_tts.py` | Speaks text with Kokoro, run by NovelForge's interpreter. |
| `nyarch_screenview_extension.py` | Registers `see_screen` and `scroll_screen`. Copied into the Flatpak's `config/extensions/`. |
| `apply_settings.py` | Writes all the assistant's settings. Idempotent; re-run after changing this file. |
| `~/.config/autostart/moe.nyarchlinux.assistant.desktop` | Launches the assistant automatically at login (added 2026-09-12). Not tracked in this directory since it's a real XDG autostart location, not part of the assistant's own config. |

After editing the extension, copy it across and restart the assistant:

```bash
cp nyarch_screenview_extension.py \
   ~/.var/app/moe.nyarchlinux.assistant/config/extensions/
```

## Why it is built this way

**Ollama was removed.** The Arch `ollama` package ships only CPU backends —
there is no `libggml-vulkan.so` in `/usr/lib/ollama/`, so `OLLAMA_IGPU_ENABLE=1`
could never have worked. Jan's bundled llama.cpp *does* have the Vulkan backend
and is confirmed loading `libvulkan_intel.so`, so Jan is the only engine now.

**Screenshots go through the screen-share portal.** On GNOME 50 both obvious
routes are blocked: `gnome-screenshot` is refused by the shell
("Screenshot is not allowed") and `grim` fails because GNOME does not implement
wlr-screencopy. The portal grants once, hands back a *restore token* stored in
`~/.local/state/forge-nyarch/screencast-token`, and every capture after that is
silent. **Deleting that token means being asked to approve sharing again.**

**Kokoro is hard-linked, not copied.** `config/models/kokoro_cache/` contains
hard links to `~/NovelMakerData/tts_voices/`, so the 325 MB model exists once on
disk under two names. Copying either file (rather than moving it) would spend
the space for real.

**The fast model is told not to think.** Qwen3.5 reasons before answering by
default, which turned a 0.3 s reply into a 4 s one that arrived *empty* because
the whole token budget went into hidden reasoning. The assistant's own
"Thinking Mode" toggle only changes how it parses replies, so the flag has to be
sent in the request body — see `custom_body` in `apply_settings.py`.

## Verified on 2026-09-10

| Thing | Result |
|---|---|
| Fast model reply | **0.34 s**, 30 tok/s (thinking disabled) |
| 4B reads a screenshot | **correct** — named the app and summarised the work |
| 4B vision latency | **31 s** at the 1024 px default (was 58 s at 1280 px) |
| Kokoro speech | 8.75 s of audio in 3.8 s, 24 kHz mono |
| Screen capture | 1280×720 PNG, readable text |
| Scroll | confirmed — view moved, then moved back |
| Extension loaded | `screenview` present in the assistant's extension list |
| `black` / `pyright` | clean on all four files |

## Capture width is the speed dial

The vision model's time is dominated by how many tokens the *picture* becomes,
not by how big the model is. Measured here on one screenful of terminal text:

| Capture width | Image tokens | Time | Still correct? |
|---|---|---|---|
| 1280 px | 956 | 47 s | yes |
| **1024 px (default)** | **612** | **31 s** | **yes** |
| 800 px | 386 | 23 s | yes |
| 640 px | 256 | 19 s | yes, less detail |

Swapping the 4B for the smaller 2B vision model was tried and is **not** worth
it: 49.5 s versus 51.5 s on the same picture, and a visibly worse answer. Both
models pay the same image-token cost, so shrinking the picture is the only lever
that matters. `see_screen(high_detail=True)` goes back to 1280 px for small print.

## Known rough edges

- **Reading a long document is still slow** at roughly half a minute per
  screenful. Usable for "what's on my screen?" and for being taught a page at a
  time; tiring for a whole manual.
- **Screen capture can fail while a model is generating** — the Iris Xe encodes
  the video stream and runs inference on the same silicon. `take_shot` retries
  three times, which cleared it in testing, but under sustained load it may
  still give up.
- **`n-gpu-layers` must stay at 40, not 99.** Qwen3.5 uses a Gated Delta Net
  attention block that the Vulkan backend cannot do, and llama.cpp says so out
  loud: `fused Gated Delta Net (chunked) not supported, set to disabled`. Push
  every layer onto the iGPU and prompt processing collapses to 4.9 tok/s; the
  current 40-layer split measured 26.7 tok/s, and pure CPU sat between them at
  20.6 tok/s. So the iGPU *is* worth using here, but only for the layers it can
  actually run. These three numbers came from different sessions with different
  background load, so treat the ordering as reliable and the exact figures as
  rough.
- **Wake word is configured but not yet confirmed by speaking to it.** It was
  switched from `openwakeword` mode (which only knows four fixed phrases, had no
  model installed, and had sensitivity pinned at an unreachable 1.0) to
  `secondary-stt` mode, which transcribes with Whisper `tiny.en` and matches any
  phrase in the `wakeword` setting. Say **"hey nyarch"** (added 2026-09-12,
  alongside the original "hey arch" family, which still works).
- **Autostart added 2026-09-12, unconfirmed.**
  `~/.config/autostart/moe.nyarchlinux.assistant.desktop` launches the full
  window (not `--mini`) at login. This machine's systemd runs
  `xdg-desktop-autostart.target` and already generates `app-*@autostart.service`
  units for other apps, so a plain XDG autostart `.desktop` file is the right
  mechanism — `hyprland.conf` was not touched. Never confirmed through an
  actual login/logout cycle.
- **Image generation is wired but untested.** `sd-cli`/`sd-server` are symlinks
  to AI Studio's binaries and `custom_models_dir` points at its catalog.
