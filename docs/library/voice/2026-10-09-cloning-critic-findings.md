# Voice cloning: what the two critics found and what became of it

date: 2026-10-09 · for: both · Relay task 120, sessions 10-12

Two critic agents reviewed the task 120 commits (49e7405, c1ee8fe, ff2ed80,
cd95a71) in session 10: a code critic that wrote failing probes, and a
creative / Emerson-lens critic that checked the asks, the docs and the
numbers. Their full reports are kept in `~/Forge/backups/relay120/s10/`
(`critic_code.md`, `critic_lens.md`, probes in `critic_probes/`; not in git).

Every "fixed" below has a test that failed on cd95a71 and passes now
(mostly `apps/voice/tests/test_cloning_edges.py`, plus the engine, cast,
profiles, `shared/forge_mic.test.js` and `tests/test_forge_mic.py` tests).
Voice suite 184 pass, forge_mic node 12, forge_voice node 11,
test_forge_mic 6, test_forge_voice 20, WebKit mic check 8/8 (2026-10-09 03:41).

## Code critic

| # | Finding | Now |
|---|---|---|
| F1 | A line that is only tags ("[laugh]", "(sighs)") unloaded the loaded heavy model, then answered 400 | Fixed: engines raise an input error, the service answers 400 and keeps the model |
| F2 | Breeze would not load when `models/voice/profiles` was missing | Fixed: the profiles folder is not counted as a model file |
| F3 | A wrong or unknown voice silently spoke as another one, and the header named the asked one; cast.py kept such clips | Fixed: the service picks the voice per row (asked, else app setting, else default), the header names the voice used, Breeze re-saves a lost copy once, cast.py checks the header |
| F4 | Kokoro dropped ordinary words in round brackets ("(normal)") | Fixed: round brackets count only for sounds and pauses |
| F5 | One typo in `shared/voice_emotions.json` broke every bracketed line | Fixed: the last good list is kept and the error logged |
| F6 | A Japanese line fell back to the English Kokoro | Fixed: the fall-back must speak the line's language, else the reason is returned |
| F7 | cast.py missed a changed calm clip for mood lines | Fixed: the clip key covers the calm clip and the mood clip with their words |
| F8 | A new calm clip kept the old voice's mood clips | Fixed: they move to `old-<time>/` in the profile |
| F9 | Two "..." game lines always failed | Fixed: skipped as "nothing to say (no words)" |
| F10 | Mic error paths left the mic open; a hung resume left the button dead | Fixed: one close for every failure, a 3 s limit on resume |
| F11 | Pop-outs gave the mic to any page, and screen requests were not refused | Fixed: mic only on a Forge page (file or this laptop's server), camera and screen refused |
| F12 | Ids "x 1" and "x_1" wrote one file | Fixed: a short hash suffix when a name had to be changed |
| F13 | "[angry]" on its own line got a full stop; "[sad](sigh)" was read as a link | Fixed: tags are handled before the markdown clean-up |
| F14 | Japanese tags and full-width brackets were read aloud; an empty audio answer gave no reason | Fixed: Japanese aliases, full-width brackets, and a "no audio" reason |
| F15 | `say --voice <profile>` without `--model` failed with no reason; `say` waited only 60 s | Fixed: the voice resolves per row, `say` waits 600 s and prints a fall-back |
| F16 | The `private` flag is a label only | Not fixed (design): no private voice exists yet; needed once episode clips arrive |

Missed asks it named:

- Callers could not pick a voice per line: fixed for pages
  (`ForgeVoice.speak(text, {model, voice})`) and the shell (`say`/`clip
  --voice`). Acchan's own `speak()` still sends only its app name, so Acchan
  uses the Voice page's per-app setting. Not changed (Acchan's file).
- Relay could not speak: `forge_voice.py clip ... --out x.ogg` now makes a
  voice note a session sends with `relay send-file`. Relay's prompt was not
  changed (not this task's file).
- No prompt tells Jan, Claude or Relay about mood tags. Not done: open.

## Emerson-lens critic

| # | Finding | Now |
|---|---|---|
| 1 | Nothing new is live until a restart, but a 02:20 message said cloning works | The final reply opens with "restart Forge (Ctrl+Shift+R)"; WIP and the how-to say it too |
| 2 | Relay cannot send a voice line | `forge_voice.py clip` (see above) |
| 3 | Cloned voices are slow for live replies; moods never reach Acchan or Mission | Written in the README (about 4 s of work per second of speech, Acchan's 90 s limit, where tags work) |
| 4 | The how-to said Mission had no voice buttons and nothing about cloning | Fixed: Mission line corrected, "Character voices and moods" section added |
| 5 | The voice-actor licence read as if private use were fine | Reworded neutrally in the research doc, bake-off doc and README: Irodori's rules make no private-use exception; Emerson's call |
| 6 | Disk 3.3 GB and memory 4/1.5 GB were wrong; OmniVoice was dead weight | Fixed: AuK 6.1 GB on disk, 7.5 GB and 2.8 GB at peak; OmniVoice moved to the Trash (1.3 GB, freed when the Trash is emptied) |
| 7 | Eighty Six progress read bigger than it is | WIP: 8 of 124 Lena/Shin lines made, 305 lines of other characters have no voice, the game plays none yet |
| 8 | "4x real time" reads as fast | Fixed: "about 4 s of work per second of speech" |
| 9 | Terms without a first explanation (GGUF, Vulkan, Hz, flow-matching) | Explained in the research and bake-off docs |
| 10 | Samples are hard to find on the laptop | The reply and the how-to give the folder |
| 11 | `say` gave no sign of a fall-back | Fixed (F15) |

## Second code critic (session 12, on ec48e73)

A fresh critic checked the fixes above with different inputs (all of the
first critic's probes now fail, as they should) and found 10 more, three of
them caused by the fixes. All 10 are fixed; each has a test that fails on
ec48e73 and passes now (12 of 14 new voice cases, 3 root tests, and the old
mic code hangs on the new mic test). Report kept in
`~/Forge/backups/relay120/s10/critic_s12.md`.

| # | Finding | Now |
|---|---|---|
| G1 | A link whose words are a tag ("[Calm](url)") lost its words and became a mood (from F13) | Fixed: the space goes in only before a second tag, so a link stays a link |
| G2 | AuK or Irodori with no usable voice loaded the heavy model for every line, then unloaded it (from F2) | Fixed: "has no voice in en: add one" is a fall-back reason before any load |
| G3 | A tag line joined onto "# Alert" or "- item" hid the markdown marker (from F13) | Fixed: the tag goes after the marker; never joined onto a code fence |
| G4 | A tag file of the wrong shape (valid JSON) still gave 500 on every bracketed line | Fixed: the shape is checked too; the log says honestly when no good list exists yet |
| G5 | A mic setup failure waited on a close that may never finish | Fixed: closing waits at most 2 s |
| G6 | The pop-out screen check read a property WebKit 2.54 does not have | Fixed: uses WebKit's own function (checked present); no page known means refused |
| G7 | A new calm clip moved files outside the profile (hand-edited paths) | Fixed: only the profile's own clips move |
| G8 | `say` stayed quiet when another voice spoke; `clip` saved a fall-back under the asked name | Fixed: `say` prints who spoke; `clip` saves nothing unless `--any-voice` |
| G9 | A loaded Irodori said nothing while Jan was busy (no Japanese fall-back) | Fixed: a loaded voice speaks when no other voice speaks its language; not loaded, it still waits for Jan |
| G10 | Japanese moods in full-width round brackets （怒って） were read aloud | Fixed: full-width （…） takes every tag; half-width ( ) keeps the strict rule |

Still open: a tag file that is already broken when the voice app starts has
no last good list, so tags are read aloud until the file is fixed (logged).

Ideas not built yet: a "try a voice" box with a mood list on the Voice
page; voices for the rest of the squad from spare Kokoro presets with a
default mood each; a radio-style filter per game channel; one prompt line so
Acchan's replies can carry a mood tag.
