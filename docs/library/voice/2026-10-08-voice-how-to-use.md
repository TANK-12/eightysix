# Talking to Forge: how to use voice

date: 2026-10-08 (updated 2026-10-09) · for: Emerson

Relay task 113. What works tonight, how to use it, and the checks only you can
do (they need a real mic and speaker).

## The short version

- **Press Super+Z** (GNOME, installed and live), say what you want, then stop
  talking. It sends after about 1.2 seconds of quiet, or when you press
  Super+Z again (GNOME only sees the press, so this key is tap-to-talk).
- **Hyprland**: hold Super+Alt+Z while you talk and let go to send. Written to
  `~/.config/hypr/custom/keybinds.lua` (backup beside it), not tried in a live
  Hyprland session yet.
- **To shut it up**: press the key again while it is talking, or say "stop",
  "quiet" or "hush" ("cancel" drops what you just said). "Say that again" repeats the last answer.
- **Pressing while it thinks** drops the answer, so you hear nothing more. It does
  not undo the command: if Acchan or Claude already started it ("turn off wifi"),
  it still happens.
- You hear a short sound when it starts listening and when it is done, and one
  desktop notification shows what it heard and the reply.

## Who answers

- **A plain command with no name** ("pause the music", "volume 40", "what time
  is it", "open Firefox", "next track") goes to Acchan's command list. No model
  runs, so the command itself takes milliseconds (measured: "what time is it"
  in 27 ms inside Acchan); most of the wait is turning speech into text and the
  reply back into speech. Commands come from the same tools Acchan already has;
  each tool now carries its own natural phrasings, so new wording is one edit
  on the tool, not a new list.
- **"Jan, ..." or "Acchan, ..."** goes to Acchan with Jan's local models when
  no command matches.
- **"Claude, ..."** (also heard as "cloud", "clod", "Tetsu") goes into one
  conversation called "Voice" in the Claude app, and the reply is read out.
  This needs the Claude app restarted once (see Known gaps).
- **Anything else with no name** goes to Jan for now. Change it on the Voice
  page (setting "anywhere target").
- **Risky things are never done from voice**: closing tabs or windows,
  deleting, typing keys, running shell commands. It replies "That one needs a
  yes from you: confirm it in Acchan."

## Where things are

- **Voice page**: Forge sidebar, System section, "Voice" (or
  http://127.0.0.1:8467). It shows what the voice app is doing, which models
  are on disk, a speech-to-text model, voice and speed per app (Acchan, Claude,
  anywhere), a mic test with a level bar, buttons to hear the voices, and the
  last 50 rounds.
- **Models** live in one shared place, `~/Forge/models/voice/stt/` and
  `~/Forge/models/voice/tts/`, not per app. The list of models is
  `~/Forge/shared/voice_registry.json`: a new model is one row there.
- **Speech-to-text** is whisper base.en q5_1 (whisper.cpp, 60 MB, CPU), the
  pick of the research doc beside this one (`2026-10-08-stt-under-100mb.md`,
  measured on this laptop). Whisper tiny.en is there as the quicker, less
  robust option. Speech-to-text stays loaded.
- **Text-to-speech** is Kokoro v1 (82M, ONNX, CPU), the fast voice. It loads
  on first use and unloads after 5 minutes idle.
- **Claude app**: a mic button in the composer types what you say into the
  box, and a "speak replies" toggle reads answers out (after the restart).
- **Acchan** listens and speaks through the Voice app, and falls back to its
  old voice path if the Voice app is down.
- **Mission Control**: a mic and a speaker button beside the attach button
  (commit ab4b723).
- **From a terminal**: `python3 ~/Forge/shared/forge_voice.py status`,
  `... say "hello"`, `... hush`, `... tap`.

## Checks only you can do (real mic and speaker)

1. Voice page, mic test: talk and watch the level bar; it shows what it heard.
2. Voice page: press the button to hear the fast voice.
3. Super+Z, "what time is it": it should say the time within about 2 to 3
   seconds of you stopping.
4. With music playing, Super+Z, "pause the music".
5. Super+Z, "Jan, what is the capital of Japan": slower, it depends on Jan.
6. After restarting the Claude app: Super+Z, "Claude, what day is it": a
   "Voice" conversation appears in the Claude app and the reply is read out.
7. Super+Z while it is talking: it should stop at once.
8. Super+Z and say nothing: it should give up quietly without inventing words.
9. In Hyprland: hold Super+Alt+Z, talk, let go.

If something is off, the log is `~/Forge/outputs/voice.log`.

## The best voice (installed 2026-10-08 late)

- Breeze TTS 2, the near-human one, is installed. Hear it with "Hear the best
  voice" on the Voice page, or set it for one app there (per-app voice model).
  From a terminal: `python3 ~/Forge/shared/forge_voice.py say --model
  breeze-tts-2 "Some text"`.
- It is slow here: about 5 s of work per second of speech on the Iris Xe (a
  2.7 s line took 24 s), so it suits reading something out, not live replies.
- It needs about 5 GB of free memory and an idle Jan. When it cannot run, the
  normal voice (Kokoro) speaks instead, and the Voice page says why. It frees
  its memory after 2 minutes unused.

## Samples you can play (kept 2026-10-09)

- `~/Forge/outputs/voice-checks/2026-10-08/` holds what the checks made: the
  near-human voice (`breeze/`), the small fast voices side by side
  (`tts-small/`, Kokoro is the default), the clips the speech-to-text pick was
  measured on, and screenshots of the Voice page and Mission Control's mic.
  `README.txt` there says which is which. Not in git.

## Character voices and moods (2026-10-09, task 120)

- First restart Forge once (Ctrl+Shift+R). Until then the voice app and the
  pop-out mic fix run older code.
- Make Lena say a line: `python3 ~/Forge/shared/forge_voice.py say --model
  breeze-tts-2 --voice 86-lena-en "[worried] Can everyone hear me?"`. Shin is
  `86-shin-en`. For Japanese, use `--model irodori-anime --voice 86-shin-ja`.
  Expect 10 to 40 s before you hear it.
- Save it as a voice note instead: the same with `clip ... --out
  /tmp/lena.ogg`.
- Moods go in square brackets: [angry] [sad] [whisper] [laugh] [sigh] and
  more (the list is `~/Forge/shared/voice_emotions.json`). The fast voice
  drops them, so a tag is never read out.
- To give Acchan or Mission a character voice: on the Voice page, in that
  app's row, set Voice model to "Breeze TTS 2" and Voice to "86-lena-en".
  It is slow, so it suits short replies.
- Every voice: `cd ~/Forge/apps/voice && .venv/bin/python profiles.py list`.
  Samples: `~/Forge/docs/library/voice/samples/`. Lena and Shin are stand-in
  voices until the season 1 episodes are cut into clips.

## Known gaps (updated 2026-10-09)

- The Claude app (port 8445) still runs its old code until it is restarted
  (or Forge is restarted). Until then "Claude, ..." answers "Claude is not
  answering". Not restarted for you because it may be running your chats.
- The voice backend inside Forge also runs the code from 21:34 on 2026-10-08
  until it restarts: close and reopen Voice in Forge (or restart Forge) to get
  the evening's fixes, the best voice's memory check among them.
- Mission Control has a mic and a speaker button beside the attach button
  (commit ab4b723); checked in headless Chrome, not with a real mic.
- The Hyprland key is untested, and nothing has been tried with a real
  microphone: the tests here used recorded speech in place of the mic.
