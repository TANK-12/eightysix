# Voice cloning bake-off, the pick, and character stand-ins

date: 2026-10-09 · for: both

Relay task 120. Research behind it: `2026-10-08-voice-cloning-and-emotion-tts.md`
(AuK is the cloner from AI Search's 2026-09-13 news). Raw scores and the
scripts that made them: `bakeoff-2026-10-09/` (`scores.jsonl`, `bake.py`,
`bake_breeze.py`, `score.py`, `sim.py`). Sample clips: `samples/2026-10-09-cloning/`
(one per model and mood) and `samples/2026-10-09-eightysix/` (Lena and Shin stand-ins).

## The pick

- **English: Breeze TTS 2** (`breeze-tts-2`) is the default cloner. It made no
  word errors, scored the best voice match (0.70 on average, 0.81 at best), and
  takes the mood as a spoken direction. It's the slowest of the three: about
  4 s of work per second of speech, so a 3 s line takes about 12 s.
- **English, faster: AuK-Flash** (`auk-flash`) takes about 3 s of work per
  second of speech (2.95 in the table) and
  makes a voice's mood clips by editing its calm clip. Its voice match is
  lower (0.67) and it needs 7.5 GB of memory at peak. It speaks English and
  Chinese only: on Japanese it said nothing usable (100% error).
- **Japanese: Irodori-TTS v4.1 Anime** (`irodori-anime`) takes about 2.5 s of
  work per second of speech, with 3% character errors, reads emoji emotion tags, and designs new
  voices from a Japanese description. Its 0.90 voice match is inflated,
  because the reference voice was one Irodori had designed itself.
- **OmniVoice is out.** On Vulkan (the graphics chip) it returned empty audio,
  and on the processor alone it took 24 s of work per second of speech.

## How it was measured

This laptop: i5-1245U, Iris Xe through Vulkan, 32 GB. audio.cpp v0.9.1 was
built from source (the prebuilt one crashes, because it needs AVX-512).
English used the same reference clip for every model (Breeze's `harbour`
voice). Japanese used a voice Irodori designed. Each model spoke three game
lines, calm and in moods.

- **RTF** (real-time factor) is seconds of work per second of speech. Lower is
  faster, and 1.0 means real time. These are warm figures, with the model
  already loaded.
- **Error** is the word error rate for English and the character error rate
  for Japanese. It compares the line against SenseVoice-Small's transcript.
- **Voice match** is the cosine similarity of wespeaker ResNet34 speaker
  embeddings against the reference clip. 1.0 is the same voice. Two different
  people usually land below about 0.5.

| model | lang | cases | RTF | error | voice match |
|---|---|---|---|---|---|
| irodori-anime | ja | 8 | 2.56 | 0.03 | 0.90 |
| auk-flash | en | 8 | 2.95 | 0.015 | 0.67 |
| auk-flash | ja | 1 | 2.74 | 1.0 | 0.36 |
| breeze-tts-2 | en | 7 | 4.25 | 0.0 | 0.70 |
| omnivoice (CPU) | en | 1 | 24.0 | 0.18 | 0.45 |

Memory at peak, measured as the drop in MemAvailable: AuK 7.5 GB, Irodori
2.8 GB. An AuK mood edit takes about 13 s; all seven moods for `harbour` took
105 s.

**Not machine-verified: whether the moods sound right.** SenseVoice's emotion
tag came back EMO_UNKNOWN or NEUTRAL for nearly every mood clip (only Breeze
"sad" was heard as SAD). The right words are verified. Whether a line
actually sounds angry is for ears to judge. Listen to the samples.

## Stand-in voices for the game characters (2026-10-09, session 9)

Until Emerson's Eighty Six episodes are cut into clips, Lena and Shin use
stand-in voices. None of them is cloned from the anime's voice actors.

- **AuK's design mode is not good enough for reference clips.** The first try
  put the description in the words, and AuK ignored gender: Shin came out at
  a pitch of 250 Hz, the same as Lena (247 Hz). (Pitch in Hz: men usually
  speak below about 160 Hz, women above about 180 Hz.) The documented `instruct` option (now in
  the registry as `design_option`) gets the gender right, at 127-142 Hz. But
  every AuK design is breathy, with 50-100 voiced frames where real speech has
  about 300, and its first second is garbled. Both SenseVoice and Whisper heard
  "My Lord please leave me as his hand grown" for "This is Handler One". AuK
  then cloned those clips as mush ("Hlow your positions. Hol your
  positions..."), while the same line cloned from the real `harbour` recording
  was word-perfect. Lena's and Shin's designed voices also matched each other
  at 0.84-0.90.
- **So the English stand-ins are Kokoro preset voices**: Lena is `af_bella`
  and Shin is `am_michael`. Breeze clones them. Pitch: Lena 215 Hz, Shin
  123 Hz, and the two voices match each other at only 0.47, so they read as
  two different people.
- **The Japanese stand-ins are designed by Irodori** from the game's speaker
  notes: Lena at 304 Hz, Shin at 121 Hz. Shin's description says "young man"
  (若い男性), because "boy" (少年) gave 224 Hz.

The checked result came from a scratch voice backend (port 8497). It
rendered eight real game lines with Breeze in 7-13 s each. Lena's lines came
out at 194-206 Hz and Shin's at 103-140 Hz, with a voice match of 0.74-0.86 to
their stand-ins, and SenseVoice heard the right words. In Japanese,
`86-shin-ja` saying `[angry]` was 114 Hz with a match of 0.81, and `86-lena-ja`
saying `[worried]` was 348 Hz with a match of 0.92. Irodori added a short extra
phrase to the end of Lena's line, a known v4 habit.

## How to use it

Mood and sound tags go in the text: `[angry]`, `[whisper]`, `[laugh]`,
`[sigh]` and the rest of `shared/voice_emotions.json` (calm, happy, angry, sad,
fearful, surprised, disgusted, worried, whisper, gentle, shout, teasing, tired,
laugh, sigh, gasp, cough, pause). Each model gets them in its own form. Models
that cannot act them have the tags taken out, so no tag is ever read aloud.

    python3 ~/Forge/shared/forge_voice.py say --model breeze-tts-2 --voice harbour "[sad] I told you to fall back."
    python3 ~/Forge/shared/forge_voice.py say --model irodori-anime --voice 86-shin-ja "[angry] 下がれ。"

A voice is a profile folder, `models/voice/profiles/<id>/`, which is not in
git. Making one (in `apps/voice`, with the voice venv):

    .venv/bin/python profiles.py add <id> clip.wav --text "the words" --language en [--private]
    .venv/bin/python profiles.py design <id> --model irodori-anime --describe "..." --text "..."
    .venv/bin/python profiles.py moods <id> --model auk-flash      # angry/sad/... clips from the calm one

Irodori's rules say: don't clone a real person's voice, voice actors
included, without their consent, and they make no exception for private use.
Cloning the Eighty Six cast with Irodori would go against them even on this
laptop; that is Emerson's call. `--private` only marks a voice so nothing made
with it gets shared: it is a label, and no tool enforces it yet.

Game lines are rendered through `cast.py` with `casts/eightysix.json`. It
reads the game's dialogue without changing it and writes to
`outputs/voice-cast/eightysix/<lang>/` with a `manifest.json`:

    .venv/bin/python cast.py voices eightysix           # make missing stand-ins
    .venv/bin/python cast.py render eightysix --lang en [--speaker shin] [--limit 20]

Japanese rendering waits for the game to have Japanese text. On 2026-10-09
there was no `text_ja` field in any of its 438 lines, so all were skipped and
`render` says so.
