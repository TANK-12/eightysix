# Nyarch Assistant — manifest

Entry point for a session with no history. Read this, then `README.md` for the
architecture and the reasoning. Per-session records are in `sessions/`.

**Status (2026-09-22): Nyarch's brain is now Acchan.** Emerson reported that
Nyarch answered with bash-looking text or empty replies and did nothing when
asked to open Firefox, the file explorer or a terminal. Causes found: the
primary model was the 2B with Nyarch's "thinking" on, temperature 1.0 and
top-p 0.48 under Nyarch's long command-block prompts; the secondary 4B had no
`enable_thinking: false` at all, so it spent every reply thinking and
returned nothing. Fix (applied with `apply_settings.py`, previous keyfile
backed up in `~/Forge/backups/2026-09-22-acchan/`): the primary "openai"
provider now points at **Acchan** (`http://127.0.0.1:8451/v1`, model
`acchan`), the Forge app `apps/acchan`, which runs the whole agent with tools
for apps, windows, tabs, files, documents and media behind the OpenAI API;
the secondary 4B got the thinking-off body. **Verified:** Nyarch's own
`openai` library (run inside the Flatpak) streamed a reply from Acchan
("42 nya."); the same endpoint opened and closed GNOME Calculator for real.
**Not verified:** Nyarch driven by voice or typing in its own window after
the change (not done overnight: it speaks aloud). Avatars: `add_avatar.py`
installs any downloaded Live2D model; candidates are listed in
`~/Forge/apps/acchan/WIP.md`. The older long-text corruption bug (§3) may be
moot now that Acchan answers, but has not been rechecked.

---

## 1. Read before touching anything

**Jan is shared, and now autostarts at login too** (added 2026-09-12,
`~/.config/autostart/ai.jan.Jan.desktop`). It serves `127.0.0.1:1337` and
other things on this machine depend on it — Forge's Arcade backend, the
Dossier app, and often another Claude session. The user has asked twice not
to interfere with it. **Do not kill Jan, kill `llama-server`, or restart it
without asking.** Check first:

```bash
pgrep -a -x llama-server        # which models are resident
```

**Jan rewrites `router.preset.ini` from each model's `model.yml` on startup.**
Hand-edits to the preset are silently discarded. The file that decides the real
launch flags is:

```
~/.var/app/ai.jan.Jan/data/Jan/data/llamacpp/models/<model>/model.yml
```

Confirm a change landed by reading the actual process arguments, not the config:

```bash
pgrep -a -x llama-server | tr ' ' '\n' | grep -A1 -E "gpu-layers|mmproj|threads"
```

**`pkill -f <pattern>` will kill your own shell**, because the pattern matches
your own command line. This happened three times in one session and looks like a
mysterious exit code 144. Use `pkill -x <exact-name>` instead.

**Do not delete `~/.local/state/forge-nyarch/screencast-token`.** It is the
portal's remembered permission to capture the screen. Delete it and the user has
to approve a screen-share dialog again, which they explicitly said they do not
want to do.

---

## 2. Do this next, in order

### a. Finish diagnosing the long-text corruption (§3) — highest priority
Needs Jan free. Ask the user first.

### b. Wake word — needs the user, cannot be tested without them
Everything is configured; nobody has spoken to it. Ask them to say
**"hey nyarch"** (or "nyarch", "hey arch", "hey acchan", "acchan", "arch chan",
"hey computer" — all in the phrase list) with the app focused and report what
happens. If it does not fire:
- confirm `wakeword-on`, `wakeword-mode=secondary-stt`, `secondary-stt-on`
- the phrase list is the `wakeword` setting, comma separated
- `wakeword-energy-threshold` is 300; lower it if their mic is quiet
- the secondary engine is `whispercpp` with `tiny.en`, the only real Whisper
  model on disk (the other `for-tests-*.bin` files are 575 KB dummies)

### e. Confirm autostart actually fires on next login
Added 2026-09-12 (see `sessions/2026-09-12-autostart-wakeword.md`), never
tested through an actual login since it can't be verified mid-session.
Confirm both `~/.config/autostart/moe.nyarchlinux.assistant.desktop` and
`~/.config/autostart/ai.jan.Jan.desktop` exist and that after the user's next
login both the assistant window and Jan are open on their own.

### f. Confirm host command execution actually works
`virtualization` was set to `false` on 2026-09-12 so `execute_command` routes
through `flatpak-spawn --host` instead of running inside the Flatpak sandbox
— this is what lets the assistant open a real browser, launch real apps, or
touch anything outside its own sandbox. Only the setting and process health
were confirmed; nobody has asked it to actually open something and watched it
happen. Try "open firefox" or "open a terminal" and confirm a real host
window appears.

### c. Watch the model actually use the screen tools
The scripts were tested directly and work. **Nobody has seen the LLM call
`see_screen` or `scroll_screen` in a real conversation.** Open the app, ask
"what's on my screen?", and confirm the tool fires, the picture reaches the 4B,
and the reply is spoken. This is the single biggest untested gap.

### d. Confirm text-to-speech through the app
`forge_tts.py` was verified standalone (8.75 s of audio in 3.8 s). It has never
been verified through the app's `custom_command` handler, which substitutes
`{0}` for the output file and `{1}` for the text and calls out via
`flatpak-spawn --host`. Quoting is the likely failure point — test text with
apostrophes and newlines.

### e. Confirm image generation
`sd-cli`/`sd-server` are symlinks to AI Studio's binaries and `custom_models_dir`
points at its catalogue. The binaries run on the host (verified:
`stable-diffusion.cpp version master-841-6b3edaa`). Never actually generated an
image from the assistant.

---

## 3. Open bug: the 4B corrupts long text

**Symptom.** Given roughly 1,500 tokens of prose, `Qwen3_5-4B-IQ4_XS` returns
fluent English with garbage characters spliced in:

> "Photosynthesis**祖** organisms like plants and**ودود** convert sunlight…"
> "a**效** process", "sunlight**距光能**", "which is**不出去** in the atmosphere"

**What is known.** Reproduced twice, ~100 s per run. Every *image* prompt
(600–950 tokens) came back clean; both *long text* prompts (~1,560 tokens) were
corrupted. The vision encoder was suspected, moved back off the iGPU
(`mmproj_offload: false`), and **the corruption persisted** — so that was not it.

**Repro:** feed `sessions/article-sample.txt` to `Qwen3_5-4B-IQ4_XS` with
`"Explain this article in 3 sentences."` and scan the reply for characters in
the CJK or Arabic ranges.

**Next step — three runs, ~10 minutes, needs Jan free.** Run a second
`llama-server` on a spare port from Jan's own backend (this does not disturb
Jan's instance, though it does compete for the iGPU), with
`LD_LIBRARY_PATH` set to that `bin` directory, and vary one thing at a time:

| # | Config | Tests |
|---|---|---|
| 1 | `--n-gpu-layers 40 --flash-attn on --cache-type-k q8_0 --cache-type-v q8_0` | reproduces Jan's current setup |
| 2 | `--n-gpu-layers 40 --flash-attn on` (f16 cache) | is it the quantised attention cache? |
| 3 | `--n-gpu-layers 0` (CPU) | is it the iGPU at all? |

A ready script is at `sessions/isolate.sh` — **it was written but never run**,
the user stopped it because Jan was busy.

**Likely suspects, in order:** the quantised KV cache (`q8_0`) on Vulkan; the
Gated Delta Net fallback (llama.cpp logs `fused Gated Delta Net (chunked) not
supported, set to disabled` on this backend); flash-attention on Intel Vulkan.

**Until this is resolved,** treat long-text answers from the 4B as unreliable.
That includes the built-in `website` tool, which feeds it whole articles. Short
chat and screen-reading looked clean throughout.

---

## 4. What exists

| Path | What |
|---|---|
| `~/Forge/nyarch/screenview.py` | `shot` / `scroll` / `setup`, runs on the host |
| `~/Forge/nyarch/forge_tts.py` | Kokoro speech, run by NovelForge's interpreter |
| `~/Forge/nyarch/nyarch_screenview_extension.py` | registers `see_screen`, `scroll_screen` |
| `~/Forge/nyarch/apply_settings.py` | writes all assistant settings, idempotent |
| `~/.var/app/moe.nyarchlinux.assistant/config/extensions/` | where the extension must be copied |
| `~/.local/state/forge-nyarch/screencast-token` | the portal permission — do not delete |
| `~/.config/autostart/moe.nyarchlinux.assistant.desktop` | launches the assistant at login, added 2026-09-12 |

Read or write any setting:

```bash
flatpak run --command=gsettings moe.nyarchlinux.assistant \
  get moe.nyarchlinux.assistant <key>
```

After editing the extension:

```bash
cp ~/Forge/nyarch/nyarch_screenview_extension.py \
   ~/.var/app/moe.nyarchlinux.assistant/config/extensions/
# then restart the app - extensions load once at startup
```

---

## 5. Verified vs assumed

**Verified by running it:**
- fast model reply 0.34 s at 30 tok/s, with thinking disabled in the request body
- 4B read a real screenshot correctly, naming the app and the work in progress
- capture width is the speed dial: 1280px/956 tokens/47 s → 1024px/612 tokens/31 s
- the 2B vision model is *not* faster (49.5 s vs 51.5 s) and answers worse
- Kokoro: 8.75 s of audio in 3.8 s, 24 kHz mono
- screen capture and scroll both work; capture retries because the iGPU is shared
  between encoding the video stream and running the model
- the extension is loaded by the app (`screenview` appears in its extension list)
- Ollama structurally cannot use the iGPU: no `libggml-vulkan.so` in `/usr/lib/ollama/`
- `black` clean, `pyright` clean on all four files
- (2026-09-12) `wakeword` gsettings key updated and read back correctly with
  "hey nyarch" and "nyarch" added
- (2026-09-12) `~/.config/autostart/moe.nyarchlinux.assistant.desktop` passes
  `desktop-file-validate`
- (2026-09-12) manual launch after the settings change: window opens, avatar
  loads, web UI serves normally; two pre-existing non-fatal `get_models()`
  exceptions in background threads, unrelated to this session's changes
- (2026-09-12) wakeword detector confirmed actually starting with the new
  phrase list and threshold, via unbuffered log output after a clean restart
- (2026-09-12) `virtualization` set to `false` and read back; single clean
  assistant process confirmed running afterward
- (2026-09-12) Jan launched cold (was not previously running), confirmed
  serving `http://localhost:1337/v1/models` with both the 0.8b and 4B models
  listed, on the known-good 40-gpu-layer Vulkan split from 2026-09-10

**Reasoned about but NOT verified:**
- the wake word firing on speech (now includes "hey nyarch", still untested
  by an actual voice)
- autostart firing on an actual next login, for both the assistant and Jan
  (can't test mid-session)
- `execute_command` actually reaching the real host and opening something
  (e.g. a browser) end to end — only the sandbox setting itself was confirmed
- text-to-speech through the app's own handler
- image generation end to end
- the model choosing to call the screen tools on its own
- whether pinning the 4B to CPU would beat the current 40-layer split — three
  measurements exist but from different sessions under different load, so only
  the ordering is trustworthy: 40 layers 26.7 tok/s > CPU 20.6 > all layers 4.9
