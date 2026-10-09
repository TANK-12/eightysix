# Voice

date: 2026-10-08 · for: both

The one Forge process that loads speech models. Port 8467, section system,
starts with Forge. Other apps listen and speak through its HTTP API (the
client is `shared/forge_voice.py` for Python and `shared/forge_voice.js` for
pages); the Super+Z hotkey drives push-to-talk here.

    cd ~/Forge/apps/voice && \
    FORGE_SHARED_DIR=~/Forge/shared .venv/bin/python -m uvicorn web_app:app --host 127.0.0.1 --port 8467

## Layout

- `web_app.py`: FastAPI routes and the guard. Every route except `GET /`,
  `GET /api/status` and static files needs the header `X-Forge: 1` and a
  `Host` of `127.0.0.1:<port>` or `localhost:<port>`. CORS allows only
  `http://127.0.0.1:*` and `http://localhost:*` origins.
- `service.py`: registry and model files, settings (`~/.config/forge/voice.json`,
  written only here; app value, then global, then registry default), the model
  manager (load on first use, one lock per model, TTS unloaded after
  `resources.idle_unload_s`, STT kept), ffmpeg decode, the `pw-play` queue,
  `pw-record` capture with an RMS gate, the pure push-to-talk state machine
  `PTT`, routing to Acchan and Claude, earcons and the desktop notification.
- `engines/<engine>.py`: one file per engine, picked by the registry row's
  `engine` field. `whisper_cpp` (runs `whisper-cli`, env `FORGE_WHISPER_CLI`,
  default Nyarch's build), `kokoro_onnx`, `breeze_cpp` (the best voice,
  Breeze TTS 2 through its own `breeze-server`) and `audio_cpp` (AuK-Flash and
  Irodori-TTS through audio.cpp's `audiocpp_server`, one per loaded row). A new
  engine is one new file with a class `Engine(row, files, threads)`; a new
  model is one row in `shared/voice_registry.json`.
- `expressive.py`: mood and sound tags (`[angry]`, `[whisper]`, `[laugh]` ...,
  the list is `shared/voice_emotions.json`) written the way each model reads
  them (the row's `expressive` style); rows without one get them taken out.
- `profiles.py`: cloned and designed voices, one folder each in
  `models/voice/profiles/<id>/` (a calm clip, optional mood clips); a CLI to
  add, design and make mood clips.
- `cast.py` + `casts/<name>.json`: character voices for a game; renders its
  dialogue through this API into `outputs/voice-cast/<name>/<lang>/`.
- `static/`: the page (state, models, per-app picks, mic test, hear the fast
  or best voice, history).
- `tests/`: pytest with a fake engine and fake Acchan/Claude servers.

## API

| Route | What |
|---|---|
| `GET /api/status` | `{state, loaded, mic, level, version}`, no text, unguarded |
| `GET /api/registry` | models with `present`, defaults, free disk |
| `GET/POST /api/settings` | POST merges a validated partial object |
| `GET /api/apps` | `anywhere` plus every app whose `forge_app.json` has `voice` |
| `POST /api/stt?app=` | raw audio body (anything ffmpeg reads) -> `{text, model, ms}`; 400 empty, over 120 s or 20 MB; 503 engine failure |
| `POST /api/tts` | `{text, app?, model?, voice?, speed?}` -> `audio/wav`, headers `X-Voice-Model`, `X-Voice-Voice`, `X-Voice-Seconds`, and `X-Voice-Fell-Back` (one line: why a heavy voice could not run) |
| `POST /api/say` | same body, played on the laptop (queued) -> `{ok, queued}` |
| `POST /api/hush` | stop speech and clear the queue |
| `POST /api/ptt/{down,up,tap,cancel}?target=auto\|jan\|claude\|text` | -> `{state}` |
| `GET /api/history` | last 50 rounds, in memory |
| `POST /api/unload` | free every model |

## Push-to-talk

States idle -> listening -> transcribing -> thinking -> speaking -> idle.
Hold longer than `ptt.hold_s` then let go: stop and process. A short press:
keep listening until `ptt.silence_s` of quiet after speech, another tap, or
`ptt.max_s`. A press while an app's `/api/say` line plays and no round is
running only hushes it (the mic stays shut, so the line is not heard back).
A press or tap while speaking hushes (the mic stays closed while
speaking). A press or tap while transcribing or thinking cancels the round: the
late answer is dropped, not spoken; a command Acchan or Claude already
started still runs (there is no undo). `cancel` discards. On Hyprland the release
can reach the service before its own press (two processes), so the CLI sends
`up` once more after 0.3 s when the answer is idle.

After speech-to-text the words go through `forge_voice.clean_heard`; stop,
cancel and say that again are handled here. A leading wake name (registry
`wake` map: "Claude, ...", "Acchan ...") or a hotkey `?target=` picks Claude or
Jan directly and is never redirected. Anything else goes to `anywhere.target`
(auto means Claude): Acchan's own commands get it first with no model
(`use_model: false`, so "volume 40" or "open firefox" takes milliseconds), then
Claude; when the Claude app is not running, Jan answers instead (`answer()` in
`service.py`). A history row's `target` says who answered.
Jan: `POST :8451/api/voice/command`; Claude: `POST :8445/api/voice/ask` then
`GET /api/voice/reply?id=&wait=25` for up to 5 minutes. A down service gives a
spoken "Acchan is not answering" or "Claude is not answering". Jan stands in
only when the Claude app never got the request (refused, 404, not JSON); once
it may have it, a dropped request or answer is reported ("Claude may not have
got that; check the Voice chat before you say it again", or "the answer did not
come back"), never sent to Jan as well.

## Heavy voices

A row with `"heavy": true` (Breeze TTS 2) loads only with its `ram_mb` + 1500
MB free and Jan idle; otherwise, or when it fails, the registry's default
voice speaks and `X-Voice-Fell-Back` says why. Before that memory check,
`engines.clear_stale(row, files)` lets the engine stop a server a dead backend
left (the engine file's optional `clear_stale`). `breeze_cpp` keeps one pid
file per backend in `~/.cache/forge/voice/` (`<row>@<backend pid>.pid`), so a
second backend (a test run) never stops the live one's server. A row's own
`idle_unload_s` (120 s for Breeze) wins when shorter than the global one; the
reaper checks again once a running synth is done.

## Cloned voices and mood tags

Three rows clone a voice from a short clip: `breeze-tts-2` (English, the best
words and match), `auk-flash` (English, faster, makes mood clips) and
`irodori-anime` (Japanese, anime style). Their voices are the profiles in
their `languages`, listed by `/api/registry`; `voice` in `/api/tts` names one.
The voice that speaks is the asked one when the row has it, else the app's
voice setting for that row, else the row's default; `X-Voice-Voice` names the
one used. A line's first mood tag picks that profile's mood clip if it has
one, and the row's style also acts the tags out (Breeze turns the mood into
its spoken direction, Irodori into emoji, AuK uses the mood clip). Moods go in
square brackets (`[angry]`, `[whisper]`); round brackets count only for sounds
and pauses (`(laughs)`, `(sighs)`, `(pause)`), so "(normal)" inside a sentence
stays words. Kokoro and other rows without `expressive` get every tag taken
out, so a tag is never read aloud, and a line that is only tags is refused
(400) without unloading the model. The tag list is `shared/voice_emotions.json`;
a broken edit there keeps the last good list. When a heavy row cannot run, the
fall-back voice speaks only if it speaks the line's language (a Japanese line
never goes to the English Kokoro); a loaded heavy row with no such fall-back
speaks even while Jan is busy, and a cloning row with no voice falls back
before it loads. Full-width （…）, how Japanese scripts write directions, take
every tag. Results, the pick and why:
`docs/library/voice/2026-10-09-voice-cloning-bakeoff.md`.

    python3 ~/Forge/shared/forge_voice.py say --model breeze-tts-2 --voice harbour "[sad] I told you to fall back."
    python3 ~/Forge/shared/forge_voice.py clip --model breeze-tts-2 --voice 86-lena-en "[worried] Can everyone hear me?" --out /tmp/lena.ogg
    .venv/bin/python profiles.py add <id> clip.wav --text "the words" --language en [--private]
    .venv/bin/python profiles.py moods <id> --model auk-flash
    .venv/bin/python cast.py voices eightysix && .venv/bin/python cast.py render eightysix --lang en

`clip` saves the line instead of playing it (an `.ogg` is a voice note a Relay
session can send with `relay send-file`); it saves nothing when another model
or voice made the line (a fall-back) unless `--any-voice`, and `say` prints
which voice spoke when it was not the one asked. Pages call `ForgeVoice.speak(text, {model, voice})`.

For live replies keep the fast voice. A cloned voice takes about 4 s of work
per second of speech, and Acchan gives up on the Voice app after 90 s and uses
its old voice. A mood only reaches a voice when the text carries the tag:
today that means `forge_voice.py say`/`clip`, `/api/tts` and `cast.py`, not
Acchan's or Claude's replies (no prompt tells Jan or Claude about tags yet).

`"private": true` in a profile marks a voice cloned from a real person without
their consent, so nothing made with it gets shared. It is a label only: no
tool enforces it yet, and it does not make such cloning allowed (Irodori's
rules forbid cloning voice actors without consent, private use included).
Saving a new calm clip moves the profile's old mood clips to `old-<time>/`,
because they were made from the old voice. audio.cpp
v0.9.1 is built from source in `models/voice/bin/audio.cpp-src` (the prebuilt
release needs AVX-512, which this CPU lacks) and runs with that folder as its
working directory.

## Test environment

`FORGE_VOICE_CAPTURE=<wav>` replaces the mic, `FORGE_VOICE_PLAYER` replaces
`pw-play`, `FORGE_VOICE_SETTINGS`, `FORGE_VOICE_REGISTRY`, `FORGE_MODELS_DIR`,
`FORGE_APPS_DIR`, `FORGE_ACCHAN_URL`, `FORGE_CLAUDE_URL`, `FORGE_VOICE_PORT`.

    cd ~/Forge/apps/voice && .venv/bin/python -m pytest -q tests
