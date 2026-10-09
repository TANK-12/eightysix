# Plan: avatars, round 2 (more models, more Live2D, interactive, chattable)

**Built on 2026-09-25**: see `apps/claude/WIP.md`, "Avatars round 2", for
what exists and what was verified.

Asked for by Emerson on 2026-09-24, at the end of the session that built the
avatar stage (see `apps/claude/WIP.md`). That session stopped at 87% of the
5-hour usage window, per his stop rule. Start the next one with:
*"build ~/Forge/apps/claude/docs/PLAN-avatars-2.md"*.

## What he asked (verbatim)

- "ignor eht elive 2d gerator just iunsatll mroe models ok": stop working on
  the puppet generator (leave it as it is; nothing gets removed) and install
  more real Live2D models.
- "more models also put the generated ones at the bottom of the list and
  chaneg your avater to a differnt boy not generated"
- "more and more models", "and live 2d stuff", "and interactive and chattable"
- "dont make it never explicit for the girl ones": answered. Claude will not
  write explicit sexual content. The Yui and Ren prompts were turned up to
  "flirty and suggestive, bold teasing, no explicit sexual content"
  (personas/yui.json, ren.json, PERSONALITY.md and the output style). Do not
  reopen this.

## Already done (2026-09-24, end of session)

- Tetsu now wears the Live2D model **Mark** (a boy, not generated); his puppet
  is `alt_avatar`. Kira moved to **Rice**. Check by eye that Rice suits a hype
  boy, and swap him if a better boy arrives with the new models (Haruto, see
  below).
- Generated puppets are already listed after the Live2D models (under their
  own heading in the Studio, and after the models in the persona dropdown).
  Keep it that way as the list grows.
- 42 app tests pass after these changes.

## 1. More models (the main job)

The viewer (`shared/avatars/lib`, Nyarch's pixi-live2d-display) plays
**Cubism 4** models (`.model3.json`, moc3 formats 1 to 5) **and Cubism 2**
models (`.model.json`, because `live2d.min.js` is loaded). Most free models
are Cubism 2, so:

- `forge_avatars.list_models`: also find `*.model.json`, and record
  `"cubism": 2 or 4`.
- Motions for Cubism 2 are `.mtn` text files (`$fps=30` then
  `PARAM_ANGLE_X=v1,v2,...`), not motion3. Add `mtn(recipe, ids)` next to
  `motion3`. Cubism 2 ids are the standard `PARAM_*` names (`snake()` already
  maps them). Write them to `forge_motions/*.mtn` and test the format.
- `forge_avatar.js` Live2DBackend: for Cubism 2, add the motions to
  `settings.motions.Forge = [{file}]`. In `push()`, use
  `core.setParamFloat / addToParamFloat / getParamFloat` in place of the
  `*ParameterValueById` calls. Check whether wrapping `core.update` still
  works there.
- Sources to check and list for Emerson before downloading (up to 200 MB
  total on the local drive, his cap; about 28 MB is used so far):
  - Live2D Inc's official Cubism 2 samples (Free Material License): Shizuku,
    Koharu, **Haruto (boy)**, Hijiki and Tororo (cats), Epsilon, Hibiki,
    Izumi, Tsumiki, Chitose. The npm package `live2d-widget-models` (on
    jsDelivr) bundles them. Take only the Live2D samples.
  - **Skip** game rips in that package (Girls' Frontline, Azur Lane and
    similar): they are copyrighted game assets.
  - Unity-chan (Unity-Chan License, free with credit) is fine.
  - The jsDelivr listing call returned nothing twice at the end of the
    session. Try `https://cdn.jsdelivr.net/npm/live2d-widget-models@1.0.0/`
    (a directory page) or the GitHub repo `xiazeyu/live2d-widget-models`.
- Hard-link the new models into Nyarch's models folder, as before.
- The Studio tiles are grouped: Live2D (Cubism 4), Live2D (Cubism 2), then
  generated puppets last.

## 2. More Live2D features

- Use each model's own expressions (`.exp3.json` / `.exp.json`) by name
  alongside the parameter-offset expressions. Arch-chan's Smirk and the
  others would then be real.
- The model's own motions in the reaction lists (Arch-chan's Happy, Shy, Sad
  and so on), mapped per persona.
- Physics already runs (from each model's physics file). Check that the hair
  sways while a motion plays.

## 3. Interactive

- Hit areas: click the head or body (models that define `HitAreas`, or
  simple zones for the rest) to play a reaction: tap the head for a shy look,
  poke for a surprised one, and so on. pixi-live2d-display has `model.hitTest`.
- Drag to move and wheel to zoom the avatar in the stage; save the position
  per persona in `localStorage`.
- Double-click already plays a random reaction (stage.js).

## 4. Chattable

- A small chat box under the stage. It talks to the persona directly, without
  a Claude Code turn (which costs tokens). Use **Jan** with the Claude app's
  own role (`forge_jan.AppJan("claude", roles=("motions", "chat"))`): the
  system prompt is the persona's prompt plus "reply in 1 to 3 sentences, and
  end with one tag from [happy, think, shy, sad, surprised, wink]". Play the
  tag as a reaction and speak the reply with the persona's Kokoro voice.
- Keep a short history per persona in `<data>/avatar_chat/<id>.json` (the
  last 30 turns).
- Jan is shared: never restart it. The model loads on demand and is released
  when idle (forge_jan). Emerson's local-compute rule: one model on the iGPU.

## Checks (definition of done)

- Tests: Cubism 2 discovery, `.mtn` format, the chat reply-tag parser, and
  chat history trimming.
- Screenshots: the Studio with a Cubism 2 model loaded, and the stage with the
  chat box. Use the param probe method from `apps/claude/WIP.md` to prove that
  motions move a Cubism 2 model.
- black and pyright clean. Update `apps/claude/WIP.md` and `PROGRESS.json`.
