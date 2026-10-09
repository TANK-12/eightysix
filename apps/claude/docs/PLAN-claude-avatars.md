> **Built 2026-09-24**, in the same session that wrote this plan. What exists, what is verified and the gaps are in `apps/claude/WIP.md`. Ren does not load (moc3 format 6).

# Plan: live avatars and personas in the Claude app

Asked for by Emerson on 2026-09-24. Designed in that session, to be **built
in a fresh session**. Start it with: *"build ~/Forge/apps/claude/docs/PLAN-claude-avatars.md"*.
Personality source: `~/.claude/self/PERSONALITY.md`, which has the personas,
the mood rules and his 16 answers.

## What it is

A living anime avatar panel in the Forge **Claude** app (`apps/claude`,
port 8445). The persona on screen changes with the kind of task. It reacts to
what Claude is doing, lip-moves and speaks replies, and follows the mouse. It
also has an **avatar generator, editor and saver**, so Emerson can make and
tweak characters, including Tetsu, Claude's own persona.

## Parts, in build order

1. **Avatar stage (renderer).** Reuse Nyarch's web stack, which is already
   on disk: `~/.var/app/moe.nyarchlinux.assistant/config/avatars/live2d/web/`
   (`pixi.min.js`, `live2d.min.js`, `live2dcubismcore.min.js`, `index.min.js`
   with pixi-live2d-display, and the model `models/Arch/` with Blink, Smirk
   and Mouse expressions). Copy the JS into `apps/claude/static/avatar/`
   (check the LICENSE file first; the Cubism Core has its own licence). The
   stage is a resizable side pane, and it can be popped out fullscreen (see
   the fullscreen memory).
2. **Status reactions.** `app.js` already streams events (text, tool calls,
   result, error). Map them to expressions and motions: thinking while a tool
   runs, happy on a passing pytest or a finished result, embarrassed on an
   error, sleepy when idle. The map lives in a JSON file per persona, not in
   code.
3. **Lip sync.** Drive `ParamMouthOpenY` from the loudness of the TTS audio
   (Web Audio analyser). With no audio, pulse it with the streamed text.
4. **Speaks aloud.** Kokoro TTS, reusing NovelForge's voice package through
   `~/Forge/shared` (forge-is-the-shared-asset-home), with one voice per
   persona. There's a mute toggle, it's off by default in battery mode, and it
   runs on the CPU at low priority (local-compute-contention).
5. **Follows the mouse.** pixi-live2d-display `model.focus(x, y)`, and the
   same head and eye parameters for generated avatars.
6. **Personas and mood switching.** A registry,
   `apps/claude/personas/<id>.json`, with name, avatar source, voice,
   expression map and system-prompt fragment. Adding a persona is one file.
   Mood is picked from the user's message and the task (rules in
   PERSONALITY.md: build, fix, status, downtime), and it can be pinned from a
   dropdown. The persona's prompt fragment goes into the `claude -p` system
   prompt with `--append-system-prompt`. The flirty persona is playful teasing
   only, never explicit, and drops back to work mode when a task starts.
7. **Downloaded models (up to 200 MB, local drive).** The official Live2D
   sample models under the Live2D Free Material License (free for
   individuals): Hiyori, Haru, Mao, Natori, Rice, and one for Tetsu until
   the generated one is finished. **Before downloading, list each file with
   its exact URL, licence and size for Emerson, and get his go-ahead** (the
   CLAUDE.md install rule). Store them in `~/Forge/shared/avatars/live2d/<name>/`,
   one shared copy for Claude, Nyarch and Crew Room.
8. **Avatar generator, editor and saver.** Real Live2D `.moc3` files can only
   be made in Live2D's own desktop editor (paid, Windows and Mac only), so the
   generator makes **layered 2D puppets** instead: SVG or canvas parts (back
   hair, face, eyes, brows, mouth shapes, front hair, outfit, accessory), each
   with pivot points. They animate like Live2D: blink, mouth open, head angle
   X/Y, eye follow, breathing sway and expressions.
   - Generator: sliders and colour pickers for every part, plus randomise,
     boy/girl/androgynous presets and a style preset (cute, cool, sexy).
     Generation is procedural and fully local, and it can take hints from Jan
     ("make me a grumpy silver-haired mage" becomes slider values as JSON)
     (jan-models-per-app-on-demand).
   - Editor: open any saved puppet, change parts, preview it animating, and
     undo or redo.
   - Saver: `~/Forge/shared/avatars/puppets/<name>.json`, plus a PNG
     thumbnail. PixelForge and Crew Room can read the same files
     (user-editable-generated-assets).
   - Ship **Tetsu** as the first saved puppet, matching the look in
     PERSONALITY.md.
   - Stretch goal: an "image to layers" import, if a local segmenter proves
     good enough. Otherwise leave it out and say so.
9. **Nyarch extras.** Copy (or symlink, since disk is tight) the downloaded
   models into Nyarch's `avatars/live2d/web/models/` so its avatar picker
   lists them. Generated puppets cannot run in Nyarch's Live2D viewer. Say so,
   and don't fake it.

## Checks (definition of done)

- Tests: persona registry loading, the mood picker (message to persona),
  expression-map validity, and the puppet JSON round trip (save, load, equal).
- A headless Chrome screenshot of the stage with Arch-chan, a generated
  puppet, and the generator page, in dark theme. **No white-on-white.**
- black and pyright on the touched Python. The Claude app's MANIFEST, WIP and
  `forge_app.json` manifest block updated.

## Open questions for Emerson (ask once, at the start)

- Does Tetsu's generated puppet or a downloaded Live2D model lead by default?
- Should Yui or Ren (downtime persona) be a girl or a boy, or both, alternating?
