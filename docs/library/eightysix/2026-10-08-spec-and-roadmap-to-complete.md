# Eighty Six: spec and roadmap to a complete game (1.0)

date: 2026-10-08 · for: both (Emerson, and any Claude session with no history) · written by Rin (Relay 97);
checked by two critic agents and corrected by Tsubaki (Relay 97) the same day (section 11).
Research only: no game code, data or test was changed for this document.

## 0. How to read this

This is the whole game as it should be at 1.0: the story and its tone, every feature, what exists today, the
gaps, and the order to build them in. It extends `2026-10-07-roadmap-to-beta.md`, which plans systems but has
no story or tone, and it builds on the honest ratings in `2026-10-07-handoff.md`. How to run, test and build:
`2026-10-07-guide.md`. It is a proposal: Emerson reorders, cuts or adds, and his word wins. Where a choice is
his, it is listed in section 8 with a recommended default, so work can start before he answers.

**Evidence tags** (on statuses and facts):
- **[seen]**: read in the game's code or data on 2026-10-08. Read, not run.
- **[handoff]**: from the 2026-10-07 handoff, which names the test or bot run that checked it.
- **[canon]**: from the 86 sources: Wikipedia's "List of 86 episodes" and the 86 fandom wiki (pages read
  through their APIs on 2026-10-08).
- **[new]**: a proposal. Nothing of it is built.

Nothing in this document was run, built or playtested by this session.

**Words used here.** A *Processor* is an 86 pilot. A *Handler* is the Republic officer who commands them from a
console far behind the wall. The *Para-RAID* links their hearing across any distance; it is the game's radio.
The *Legion* are the Empire's self-running war machines. A *Black Sheep* is a Legion unit carrying a crude copy
of a dead person's brain, repeating their last thoughts; a *Shepherd* is one with a full copy, which keeps the
person's mind and commands other units [canon]. A *beat* is a scripted story moment inside a mission. A
*vertical slice* is a short stretch of the game built to finished quality end to end, to prove the systems
before building the rest. The *base* (or hub) is the screen between missions.

## 1. The game at 1.0, in one paragraph

Eighty Six is a story campaign about the Spearhead squadron's last months on the front, played from inside
Undertaker's Juggernaut. You are Shinei "Shin" Nouzen, captain of a squadron the Republic has sent to die, and
the voice in your ear is Major Vladilena "Lena" Milizé, the Handler who refuses to treat you as a drone. Every
step, shot and fall is real physics. The fights are hard and the world is beautiful. Between missions the
squad lives at its base: talking with Lena over the Para-RAID at night, carving the names of the fallen, and
counting who is left. The story runs from the night Lena first speaks to the squad to the special
reconnaissance mission, the fight with your brother's ghost and the march beyond the border, the way the
anime's first part tells it.

### What "complete" (1.0) means

1.0 is reached when all of these hold:
1. **The whole story is playable:** a prologue, four acts and an epilogue: 13 missions (M0 to M12), two short
   chapters at Lena's console, the base between missions, an ending and credits. About 6 to 8 hours the first
   time through (an estimate from mission lengths today, not a measurement).
2. **Save and continue:** progress saves between missions (and at checkpoints in the long ones); a chapter
   select opens after the ending; every mission can be replayed for its grade.
3. **Every system rated "almost polished" or better** in a fresh honest handoff, on the 2026-10-07 scale.
4. **The Handler and the squad speak** (voices, or the alternative Emerson picks in D2), and every line is also
   subtitled.
5. **The tones in section 3 are all there:** the look, the music and the radio change with the act and the
   moment, not only per map.
6. **No known crash or game-breaking bug.** A campaign bot plays every mission from start to end, and a
   30-minute soak run on every map finishes clean.
7. **Emerson has played it through,** and his notes from that playthrough are done.
8. **A friend can play it:** a share copy installs and runs on a real Windows PC and a Mac without help, every
   asset in it is licensed to share and credited, and the decision on the 86 story in shared copies (D7) is
   taken and carried out.
9. **Frame rate measured and reported** per mission and preset. Graphics win over frame rate (Emerson,
   2026-10-02).

Three gates on the way: **content complete** (every mission plays start to end, rough edges allowed), **beta**
(the 2026-10-07 beta definition, now with the story in it) and **1.0** (the list above). Section 7 says which
phase reaches which gate.

## 2. Pillars: what every feature is judged by

1. **Fun from real physics** (Emerson, 2026-09-30, standing). The Juggernaut can only do what real motors,
   batteries and materials could. No forces from nowhere, no teleporting, no recoil reduction of any kind.
   New story mechanics follow the same rule: Lena's artillery has flight time and spread, a marsh bogs the legs
   through real sinkage and drag, Fido carries real mass.
2. **Remember the names.** Shin carries the names of every Processor who died beside him: 561 when he tells
   Lena of them [canon, episode 4], 576 when the five cross the border [canon, wiki]. The game carries them
   too. Every death in the story adds a name the player keeps. This is the emotional core and the reason the
   base exists.
3. **You hear them, you never see them** [new, D1]. The Para-RAID shares hearing, not sight. The Republic never
   looks at the 86, and neither does the game: the story is told through voices, text, the machines and the
   places, never through modelled people. It fits the canon's central device, and it skips the one asset this
   project cannot make well (human characters). The two canon scenes built around people, M6's flashback and
   Fido's memories in M11, are staged without a figure in view (section 4.3); any exception is Emerson's call
   under D1.
4. **A beautiful world and an ugly system.** The battlefields are gorgeous, gold grass and red poppies under a
   blue sky; what is done to the 86 is a quiet atrocity. The look never turns grey to signal sadness; the
   contrast does the work.
5. **Options over hand-holding** (Emerson, 2026-09-30). Analog first, hardcore available, the key figures
   exposed as settings, no slow safe defaults.
6. **Stupid high quality** (Emerson's standing ask). AAA look, not low poly, never washed out; measure every
   effect's cost and report it, but looks win.

## 3. Tone and tones

### 3.1 The core tone

**Dignity under a death sentence.** The 86 know they are meant to die. They answer with competence, pride,
gallows humour and care for each other, never with self-pity. Raiden says it in episode 7: they keep fighting
to keep their pride, going down fighting rather than simply accepting death [canon]. The game plays it
straight: no melodrama, no cheap shocks, no power-fantasy swagger. Winning a fight is survival, not glory.

### 3.2 The tones palette

Seven tones, each with a home in the story and its own look, sound and voice. Weather ids are entries in
`data/weather.json` today [seen]; music ids are entries in `data/music.json` [seen], chosen here by title
and by their menu/explore/combat tags. **Emerson should listen and confirm every music pick**; the titles
suggest the use, nobody has matched them by ear.

| Tone | Where it lives | Look | Music (ids) | Radio and voice | Pace |
|---|---|---|---|---|---|
| **The grind**: routine dread | Act I patrols, the first minutes of most missions | `golden_afternoon`, `frontier_morning`, `overcast_morning` | `region`, `spear`, `eighty_six` | clipped, procedural, callsigns | walk, scan, wait |
| **The fight**: terror and competence | every battle | the map's light, smoke, HE, tracers | `legion`, `trigger_or_die`, `juggernaut`, `six_eighty`, `spearhead` | short, overlapping calls; Lena steady | fast, then silence |
| **The base**: warmth, gallows humour | the base between missions, the festival night, the school night (M12) | warm work lights (`hangar.json` presets `work_lights`, `floodlit_night`) | `tararatata`, `burarababa`, `unzari_kettari`, `talk_to_you` | relaxed, teasing, real names | slow, the player wanders |
| **The voices**: horror | Shin's hearing, Black Sheep, the Shepherd | darker grade, sound pulled thin | `the_voice_of_the_dead`, `no_reality`, `hear_my_voice` | whispers, the dead's last words; Shin calm | dread, then a rush |
| **The names**: grief and remembrance | after a death, the names screen, the epilogue | `dusk_haze`, low sun | `the_nameless_tragedy`, `rei`, `so_tired`, `alive_today` | quiet; nobody fills the silence | stillness |
| **The wall**: the Republic's clean lie | Lena's console chapters, HQ messages, the briefings | Lena's console (theme `handler_console`) | `st_magnolia`, `lena_annette`, `two_side`, `two_worlds_apart` | polite, bureaucratic, cheerful propaganda | measured |
| **Beyond the border**: fragile freedom | Act IV, the march east | `clear_noon`, `allegheny_mist`, `sauerland_evening` | `underneath_the_sky`, `the_same_sky_the_same_dusk`, `shin`, `kurena` | no Handler any more; the five talk freely | open, wandering |

The openings and endings (`3_pun_29_byou_opening_1_hitorie`, `avid_ending_1_...`,
`hands_up_to_the_sky_ending_2_...`) belong to the title screen and the credits. The OST is personal use only and
stays out of share copies [handoff]; every cue needs a fallback among the three Kevin MacLeod tracks that share
copies carry (`heartbreaking` for grief and the base, `five_armies` and `clash_defiant` for the fight) [seen].

### 3.3 Each act's look and sound

The light carries the calendar [new]: late summer to deep autumn, so the player feels time running out.

| Part | Season and light | Maps | Weather | Music leans on |
|---|---|---|---|---|
| Prologue and Act I | late summer, gold | Ashen valley, Sector 86 frontier | `golden_afternoon`, `frontier_morning`, a new night preset (M4) | the grind, the fight |
| Act II | early autumn, overcast, storms | Sector 86 frontier | `overcast_morning`, `storm_grey`, `dusk_haze`, festival night | the voices, the names |
| Act III | autumn, hard clear light | Sector 86 frontier, far east | `clear_noon`, then smoke and fire | the fight, the voices, `rei` for Shourei |
| Act IV | late autumn, mist and gold evenings | Allegheny forest, Brilon, Palouse | `allegheny_mist`, `sauerland_evening`, `golden_afternoon` | beyond the border |
| Epilogue | the empty base, then white | the base | soft overcast | the names, then an ending song |

### 3.4 How each character speaks

For writing lines and, later, casting voices. All of it from the canon's episode summaries and the wiki; the
lines themselves will be new writing.
- **Shin (Undertaker, the player):** few words, flat and calm, dry humour, calls Lena "Major". Hears the
  Legion and says what is coming before anyone sees it. Never explains himself unless asked.
- **Raiden (Werewolf):** the vice-captain. Blunt, practical, the one who argues with Shin and keeps the squad
  together.
- **Theo (Laughing Fox):** a sharp tongue and a quick temper; his rant at Lena in episode 3 and his apology in
  episode 4 are the first turn in how the squad sees her.
- **Kurena (Gunslinger):** the sharpshooter. Hot-tempered, hates the Alba (her parents were executed by them),
  jealous of how close Lena gets to Shin.
- **Anju (Snow Witch):** soft-spoken and kind; close to Daiya, and the one who grieves him longest.
- **Kaie, Daiya, Kujo and the rest:** each gets a voice of their own before they die. Kaie is open and curious
  about Lena and warns her not to get attached; Daiya is easy-going and close to Anju.
- **Lena (Handler One):** formal and idealistic at first, learns her own prejudice (episode 4), grows hard and
  resolute. Her voice is the one warm thing from the Republic. Her reason: an 86 pilot saved her life in the
  Legion ambush that killed her father, and that pilot was Shourei Nouzen, Shin's brother [canon, episodes 3
  to 5]. It ties her to Shin, and it gives M9 its weight for her too.
- **The Handler before Lena:** bored and contemptuous, worn down by a squad that torments its Handlers [canon,
  episode 1]; he cuts the link mid-fight [new]. One mission is enough to hate him.
- **Annette:** Lena's friend, the Para-RAID's researcher. Sardonic, with a guilt she names in episode 8: she let
  her 86 neighbours be taken away, and her father killed himself over the Para-RAID's experiments on 86s. In
  episode 9 Lena works out that those neighbours were Shin and Shourei [canon].
- **Shourei:** Shin's elder brother, heard only as a Shepherd's voice. Rage and grief that turn, at the very
  end, into an apology.
- **The Republic:** HQ orders and news in a cheerful official register ("no human casualties"). Never cruel in
  words; the cruelty is in what it says calmly.
- **The Legion:** no voices of their own. The Black Sheep repeat the dead's last words; only Shin hears them.
- **Fido:** no words. Beeps, servo whine and the way it follows Shin.

### 3.5 Tone rules (do and don't)

- **A death is never spectacle.** No final-kill cam, no slow motion, no score, no hit marker on a squad mate's
  death or a mercy shot. The radio goes quiet and the music drops out. The final-kill cam stays for the Legion.
- **The mercy shot is the player's, and it is never rewarded** (D4). It is what "Undertaker" means.
- **No game-over taunts.** Losing is the radio's "Juggernaut signal lost" (it exists in `radio.json`) and a
  quiet restart.
- **Humour lives among the 86 and at the base.** The Republic is played straight, which is what makes it
  ironic.
- **Beauty is real.** Grief is never desaturated to grey; the colours are poppy red, gold and sky blue (the
  first recap special is called "The Poppies Bloom Red on the Battlefield" [canon]).
- **Plain words, no shouting in capitals** in any line or screen (Emerson's standing rule). In a fight the
  radio is clipped and military.
- **Respect the canon.** The arc is the anime's first part. Where the game invents, it fills what the anime
  skips (patrol sorties, days at the base, nights on the Para-RAID); it does not change who lives or dies.

## 4. The story in full

### 4.1 Point of view

You play Shin in every mission. Lena is the voice of the Handler, heard over the Para-RAID; the radio already
speaks as "Handler One" to "Undertaker" [seen `radio.json`]. Twice you take Lena's seat: two short chapters at
her console, played in the Handler view (the squad seen from above, orders by click), which exists today
[handoff] (D6). The Republic side of the story (HQ orders, her uncle, Annette, the news) reaches the player as
messages on Lena's console, in the `handler_console` theme the menus already use [seen `themes.json`]; the main
menu already reads "Para-RAID · standing by" [seen `main_menu.gd`].

### 4.2 The arc at a glance

| # | Mission | Episode | Map | The beat | Plays as |
|---|---|---|---|---|---|
| M0 | The 86th Sector | 1 | Ashen valley | a sortie under the old Handler, who cuts the link; Kujo mortally wounded, Shin's mercy shot; that night Lena introduces herself | the tutorial, then the first death |
| M1 | First contact | 1 to 2 | Ashen valley | Lena's first sortie as their Handler [new]: by the book, and the squad wins its own way | waves (exists, reworked) |
| M2 | Spearhead | 2 | Sector 86 frontier | a big attack wave; Shin alone against the heaviest units | waves, the bridge (exists, reworked) |
| C1 | Lena: the map | 3 | Sector 86 (console) | Lena gets a better map and places the ambush | console chapter |
| M3 | The marsh | 3 | Sector 86 frontier | the ambush works; Kaie bogged down in a marsh and killed | ambush |
| M4 | Real name | 4 | Ashen valley, night | Lena asks their real names; the radio switches from callsigns | night patrol |
| M5 | Voices | 5 | Sector 86 frontier | Shin hears an offensive HQ has not seen; Lena hears the dead and goes silent | defend |
| M6 | Through to the end | 6 | Sector 86 frontier | the Legion adapts to the ambushes; Daiya and Lecca die; the second mercy shot | waves, then a choice-less beat |
| M7 | Festival | 7 | the base, then Sector 86 east | fireworks at the base; the attack on a Legion base meets long-range artillery; seven fall in the retreat; Shin tells Lena the truth | base, then retreat under fire |
| M8 | Let's go | 8 | the base, then the frontier | four more fall; Lena learns what the special reconnaissance is; her farewell; the five set out | base, march |
| M9 | The Shepherd | 9 | Sector 86 far east | Shin goes for Shourei; knocked out; Lena's guns (C2); Shin finishes it; past the border | boss, with console chapter C2 inside |
| M10 | The river | 10 | Allegheny forest | old Empire territory; slip past Legion patrols; a river they cannot cross | stealth travel |
| M11 | The town | 10 to 11 | Brilon | rest in an abandoned Imperial town; the Black Sheep Shin frees; Fido's last memories | explore, then a skirmish |
| M12 | Here we go | 11 | Brilon outskirts and Palouse | the night in the school; Shin as decoy; the others follow | last stand |
| E | Lena | 11 | the empty base | the replacement squad, the note, the kitten; then Shin's dream | epilogue, credits, coda |

Thirteen missions and two console chapters. All five maps are used, each where the story needs it: the
Republic's 86th Sector is Ashen valley and the Sector 86 frontier; old Empire territory beyond the border is
Allegheny, Brilon (a real German town for an empire whose machines have German names) and Palouse.

### 4.3 Mission by mission

Each entry: the canon beat, how it plays, and what it needs that does not exist yet.

**Prologue. M0 "The 86th Sector"** (Ashen valley). Before Lena: a routine sortie under the old Handler. The
squad torments every Handler sent to it, and each of Shin's Handlers has asked for a transfer, retired or
worse [canon, episode 1]; this one barely listens and cuts the link mid-fight [new]. The squad fights on
alone. It teaches walking, the gallop, the slide, the jump, the gun and the wire one step at a time, and
replaces the tutorial stub (D12). It introduces the squad's voices and Kujo. Late in the fight Kujo is
mortally wounded and Shin gives him the mercy shot: the campaign's first name [canon, episode 1; the wiki
names him]. That night a new voice comes over the Para-RAID: Lena introduces herself [canon, episode 1].
*Needs:* mission beats, squad voices on the radio, a tutorial built from beats (the stub's `tutorial.json`
steps can move into it), a scripted squad-mate death, the mercy-shot beat, the debrief adding Kujo's name,
Lena's first night talk.

**Act I: Spearhead**

**M1 "First contact"** (Ashen valley; today's mission, reworked). Lena's first sortie as Handler One, in the
week the anime skips between her introduction and episode 2's battle [new]: earnest, formal, a little out of
her depth, giving orders by the book that Shin quietly ignores while the squad wins its own way. Three waves
as today. The squad's teasing, and Lena's refusal to be driven off, are the mission's story. *Needs:* Lena's
lines, the squad's banter, a beat when an order is ignored, the second night talk.

**M2 "Spearhead"** (Sector 86 frontier; today's Frontier sweep, reworked). A week later a big attack wave hits
the squad's position; Lena watches Shin destroy the heaviest Legion units alone [canon, episode 2]. The Löwe
hunt and the bridge drop (it exists) are the set pieces. Between M2 and M3, Lena's console shows the Handler
recruits' history class she takes over: the Republic's lie in its own words [canon]. *Needs:* the frontier's
finale re-run after the slope change and the bridge drop played once with real shells [handoff known bug 9],
Lena's console messages (the history class).

**C1 "Lena: the map"** (console chapter, Sector 86). Lena secures a more accurate map of the battlefield
[canon, episode 3]. The player, as Lena, reads it in the Handler view and marks the ambush positions for M3.
Five to ten minutes. *Needs:* the Handler view with pan, zoom and marks the player places [handoff: missing
today; it already draws live markers for the squad and the Legion they can see, seen `handler_view.gd`]; a
"setup" phase for missions.

**M3 "The marsh"** (Sector 86 frontier, a new marsh). In a night talk, Kaie, fascinated by Lena, asks why she
cares so much about the 86; Lena says an 86 pilot once saved her life on the battlefield, and Kaie warns her not
to get too attached and to transfer out before her ideals hurt her [canon, episode 3]. The ambush plays out from
Lena's marks and works; at the end of the fight Kaie's Juggernaut gets bogged down in a marsh and is destroyed
[canon, episode 3]. Lena blames herself for missing the marsh, and Theo's rant at her follows over the radio
[canon, episode 3]. *Needs:* soft ground with real sinkage and drag (a new ground type beside the existing ground
hardness the ricochets use), the marsh area, an ambush mission type, Kaie's scripted death.

**M4 "Real name"** (Ashen valley, at night). A quiet patrol. Lena apologises and asks for their real names;
Shin tells her of the custom he keeps, the names of every fallen comrade, 561 by now, Kujo's and Kaie's among
them [canon, episode 4]. When he gives his own name, she asks whether he knows a Shourei Nouzen: his brother
[canon, episode 4]. From here on the radio uses real names, not callsigns, and Lena knows of the names the
player has kept since M0. *Needs:* a night weather preset (none of the eight is night [seen]; the Hangar's
`floodlit_night` light and a "Night" Legion finish already exist [seen]), the mission choosing its weather,
the Juggernaut's own lamps, flares, the callsign-to-name switch.

**Act II: Black Sheep**

**M5 "Voices"** (Sector 86 frontier). Shin warns Lena of a Legion offensive her command has not reported, and
tells her to cut the link because of Black Sheep; she stays connected, hears the voices of the dead (Kaie's
last words among them) and goes into shock [canon, episode 5]. Play: a defence mission in which Shin's hearing
appears as a sense the player can use (section 5.10); for two minutes the Handler is silent and the squad
fights blind. Afterwards Lena calls again; Shin explains what he hears, and she tells him how Shourei saved
her life in the ambush that killed her father [canon, episode 5]. Between M5 and M6, Kariya and Ochi fall
off-screen [canon, wiki: between episodes 5 and 6]; the player learns it at the base, as two names to carve,
not as a scene. *Needs:* Shin's hearing, Black Sheep, a defend mission type, a silent-Handler beat.

**M6 "Through to the end"** (Sector 86 frontier). The Legion changes its tactics to beat the squad's ambushes;
Daiya and Lecca die, and Shin gives Daiya the mercy shot so the Legion cannot take his brain [canon, episode 6].
It opens with a short flashback: four years earlier, a young Shin searching an old battlefield and finding his
brother's headless body [canon, episode 6] (P2, section 5.2). Staged without a figure (pillar 3): a
first-person walk at a child's height through old wrecks, a child's breathing, ending on a wreck and a name;
the body is never shown [new]. *Needs:* Legion that adapt (flanking an ambush), two scripted deaths, the
second mercy shot, Legion that try to collect the fallen.

**M7 "Festival"** (the base, then Sector 86 east). Lena smuggles a crate of fireworks to the squad for the
Revolution Festival; the base night is the warmest scene in the game [canon, episode 7]. Then the ordered attack
on a Legion base under construction meets ultra-long-range artillery: heavy losses, a retreat under shellfire,
only a handful left [canon, episodes 6 and 7]. Seven fall here: Mikuri, Myna, Shuri, Louie, Chise, Touma and
Kuroto [canon, wiki]. Afterwards Shin tells Lena the truth: Spearhead is where the 86 are sent to die,
replenished only when every member is dead [canon, episode 7]. *Needs:* the festival night at the base, a Legion
long-range artillery type (Skorpion [canon, wiki]) with spotters, a retreat mission type (reach a point under
fire), seven scripted deaths, most of them heard rather than seen.

**Act III: Special Reconnaissance**

**M8 "Let's go"** (the base, then the frontier). Shin tells Raiden he heard Shourei's voice among the Legion;
Lena learns of the "special reconnaissance missions" earlier Spearheads were sent on, and from Annette that the
Para-RAID was built on experiments on 86s, that Annette's father killed himself over it, and that Annette let
her 86 neighbours be taken away; her uncle explains why the Republic needs the 86 gone; she can only say
goodbye [canon, episode 8]. Four more fall in this episode, Hariz, Io, Tohzan and Haruto, leaving the five
[canon, wiki]; the summary does not say how, so watch the episode before scripting it (a last sortie, or news
at the base). Play: the last night at the base (the farewell talk), then the march out with Fido and a first
contact beyond the line. *Needs:* Fido, a march mission, the farewell night talk, Lena's console messages
from her uncle and Annette, four more names.

**M9 "The Shepherd"** (Sector 86 far east, a new boss arena). While the squad engages the main Legion force,
Shin goes alone for Shourei's Shepherd, a heavy unit too well armoured for him, and is knocked out [canon,
episode 9]. The screen goes dark and the player becomes Lena (**C2 "Lena: the guns"**): she has worked out
that Annette's lost neighbours were Shin and Shourei, and out of that guilt Annette hacks the Republic's
artillery for her; the player calls fire missions on the Legion and on Shourei [canon, episode 9]. Then back
in the cockpit: Shin wakes and finishes it [canon]. The blades are the tool for it [new]: the wiki says the
high-frequency blades cut even a Dinosauria's armour [canon], so the resonance blade gets its big moment.
Shourei, himself again, apologises. The squad decides to go on, east, past the border; Lena hears them leave
the Para-RAID's range [canon]. The radio fades to static and her voice is gone for the rest of the game.
*Needs:* a heavy Legion boss (the wiki's Dinosauria, the heavy tank type: 100 t, a 155 mm gun [canon]),
Shepherd behaviour (a commander that coordinates the units around it), the artillery fire mission tool, the
knocked-out beat, the Para-RAID fade.

**Act IV: Beyond the border**

**M10 "The river"** (Allegheny forest). Old Empire territory. No Handler, no map but Fido's, no resupply but
what Fido carries. Slip past Legion patrols through the firs (their sight and hearing exist [handoff]) until a
river the Juggernauts cannot cross alone stops them [canon, episode 10]. *Needs:* Legion on a real-place map
(its grid exists but knows only slopes and water, and no Legion has walked it yet [seen `big_map.gd`]), a
stealth travel mission type, the river found in the map's water data.

**M11 "The town"** (Brilon). The squad rests and explores an abandoned Imperial town; Shin seems lighter now that
he has freed Shourei [canon, episode 10]. He hears a damaged Black Sheep in the town and frees it by destroying
its core [canon]. Two weeks later, a skirmish: all but one Juggernaut disabled, most supplies gone, and Fido too
crippled to move, so they leave it behind [canon, episodes 10 and 11]. Fido's last memories of being found by
Shin play as a short sequence from Fido's own camera [canon, episode 10], staged without a figure (pillar 3): a
low, close view of a wrecked field and a Juggernaut's open hatch, and a younger Shin's voice [new]. *Needs:*
Brilon's mission streets breakable (its houses are solid today [handoff]), a free-roam stretch with story points,
Fido's memory sequence, the squad disabled by script.

**M12 "Here we go"** (Brilon's outskirts, then Palouse). The night in a school, the five briefly playing at
being students [canon, episode 11], at the base-tone's warmest. Next day Shin takes the last working Juggernaut
out alone as a decoy so the others can escape; they follow him anyway, and in the fight he hears another
Shepherd [canon]. Play: a last stand that cannot be won. Hold as long as you can; the mission ends by script,
not by a lose screen. *Needs:* the school night (base-style scene), a last-stand mission type (timer, scripted
end), a second Shepherd voice.

**Epilogue "Lena"** (the empty base). The replacement Spearhead arrives. Lena walks the empty base and finds
the squad's note of farewell and their request that she take in the kitten; she resolves to keep fighting
[canon, episode 11]. Told as her console log and the base scene, empty, with the names. Credits. Then the
coda: Shin's dying dream of meeting Shourei [canon, episode 11], white, and a stranger's voice saying
"welcome" (the title of episode 12, where the Federacy finds them [canon]): the door to Part 2.

### 4.4 The squadron and its fallen

The squad today is four wingmen, Raiden, Theo, Kurena and Anju, with their callsigns and colours [seen
`squad.json`]; Theo already flies the blade-armed variant [seen]. The story needs the whole squadron: the five
who live, Kujo and Kaie, and the fifteen who fall after them. The roll, from the 86 wiki's Spearhead page
[canon, wiki]:

| When (anime) | Who | Mission |
|---|---|---|
| episode 1 | Kujo Nico | M0 |
| episode 3 | Kaie Taniya | M3 |
| between episodes 5 and 6 | Kariya Rohga, Ochi Anton | after M5, off-screen |
| episode 6 | Daiya Irma, Lecca Lin | M6 |
| episode 7 | Mikuri Cairo, Myna Yatomika, Shuri Gilith, Louie Kino, Chise Authen, Touma Sauvy, Kuroto Hinie | M7 |
| episode 8 | Hariz Senya, Io Dodanthe, Tohzan Sasha, Haruto Keats | M8 |

The count agrees with canon: 561 names when Shin tells Lena in M4 (so he carries 559 into M0), plus the
fifteen makes 576 at the border, the number of fragments the wiki says the five leave there. The wiki also
lists two deaths from the light novels' Volume 10, Mashu Nanaki and Mina Shiroka, with no episode; this plan
counts them among the 559. **Watch the episode before scripting any death:** the summaries say who, not
always how.

Who flies with you (D8): up to four full-physics wingmen beside you, as today, and the rest of the squadron as
a second group at a distance, heard on the radio and shown in the Handler view, simpler to simulate. Each
Processor is one `squad.json` entry: callsign, name, personal mark, loadout, voice, and the mission they fall
in (if they fall).

### 4.5 After 1.0: Part 2

The anime's second part (the Federacy, the Reginleif, Frederica, the Morpho railgun) is a second campaign,
not part of 1.0. Keep it possible: the campaign is data (one file per campaign), mechs come from `mechs.json`,
so a Reginleif and a Federacy campaign are new entries, not new systems.

## 5. Every feature: today, the gap, the priority

Priorities: **P0** 1.0 cannot ship without it · **P1** should be in 1.0, the game is clearly poorer without it ·
**P2** could be in 1.0 if time allows · **Later** after 1.0. "Done" means nothing is left for 1.0 beyond polish.

### 5.1 Campaign and progression

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Campaign flow: briefing, sortie, debrief, base, next | none; the main menu has Deploy, Select map, Hangar, Settings, Quit to desktop [seen `main_menu.gd`] | a campaign file (acts, missions in order, base scenes) read by one campaign runner | P0 |
| Save game | none; `user://` holds settings, bindings, music, hints seen and personal bests only [seen] | one save file: mission reached, who is alive, the names, loadout, emblem, records; a version number so old saves still load | P0 |
| Continue, New campaign, Chapter select | none [seen] | menu entries; chapter select after the ending | P0 |
| Checkpoints in long missions | none seen | a checkpoint at wave boundaries (the 4 km missions run long) | P0 (the 1.0 definition, item 2) |
| Replay with grades and bests | S-to-D grade and per-mission bests exist [handoff, seen `sortie_log.gd`] | bests shown in the chapter select | P1 |
| Difficulty | four separate settings: damage you take, damage you deal, permanent part damage, limited or unlimited reserve ammunition [seen `settings.json`] | presets that set those plus Legion accuracy and squad survival: Story, Normal, Hard and "86" (anyone can die) | P1 |
| Credits | a music credits row in Settings > Audio only [seen, Relay 95] | a credits screen after the epilogue and from the menu, with every asset licence | P0 |
| Patrol mode, after the campaign | the wave system can already spawn any Legion on any map [seen `missions.json`] | generated patrols on any map: random waves and weather, a grade; the 86's endless grind as replay | P1 |
| Free roam, Keep exploring | exists [seen `mission_end.gd`] | none | done |
| Unlocks | none | emblems, finishes, music, photo-mode items through the campaign; never power | P2 |

### 5.2 Story delivery

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Mission beats | none: the mission script knows waves, groups, routes, alerted waves and tracking only [seen `mission.gd`] | a `beats` list per mission in `missions.json`: a trigger (wave started or cleared, unit destroyed, area entered, timer, part shot off, health below) and actions (radio line, objective, spawn, music cue, camera move, fade, scripted death, end mission). One action is one small handler, one beat is one entry | P0 |
| Radio | Handler One as typed text; lines per event (waves, kills, parts, Löwe ranging, heavy hits, armour low, won, lost), picked at random [seen `radio.json`] | squad speakers, HQ, the dead; story lines fired by beats; callsigns to real names after M4; Para-RAID static and the range fade (M9); Lena silent in M5 and gone after M9 | P0 |
| Voices | none, text only [handoff]; Piper text-to-speech already runs locally in Forge (NovelForge narrates with it) [seen] | per D2 | P1 |
| Briefing | one line of briefing text per mission [seen `missions.json`] | a briefing on Lena's console: map, objectives, her voice, HQ's order | P0 |
| Loading screen | the map's description and a random tip; maps can add their own tips [seen `loading_screen.gd`, `tips.json`] | mission lines and lore while it loads | P2 |
| Debrief | the after-action card: grade, accuracy, parts off, kills, bests [handoff], and each wingman's armour and shots, or "lost" [seen `mission_end.gd`] | the names added, Lena's word, real names instead of callsigns after M4 | P0 |
| The base | none; the Hangar showroom (five light presets, orbit, part picking) is the starting point [handoff, seen `hangar.json`] | the squad's hangar as the hub: Juggernauts in their bays with personal marks, Fido, the kitten, the fireworks crate; things to look at, each with a line from its owner; loadout; the names; the night talk | P0 |
| Night talks | none | a Para-RAID conversation with Lena after most missions; a few replies to pick, flavour only (D3) | P1 |
| The names | none | a names screen: the 559 names Shin carries into M0 (to be written), then each campaign death at its beat, 561 by M4 and 576 at the border (section 4.4); carving a new name is a short quiet scene; the full list rolls in the epilogue | P0 |
| Shin's hearing | none: no Black Sheep, Shepherd or voices anywhere in the code [seen] | section 5.10 | P0 |
| Lena's console chapters | the Handler view: squad from above with live markers, click to move or attack; no pan, zoom, contact list or waypoints [handoff, seen `handler_view.gd`] | C1 (ambush marks) and C2 (artillery): pan, zoom, marks the player places, a chapter that plays in this view only | P0 while D6 stays yes (the 1.0 definition, item 1) |
| Lena's console messages | the `handler_console` theme exists [seen] | HQ orders, her uncle, Annette, the news, between missions | P0 for the ones that carry the story (M2's history class, M8's uncle and Annette) · P1 the rest |
| Camera moments | the final-kill cam and photo-mode cameras exist [seen `scripts/camera/`] | a beat action that flies the camera along a short path and back, with fades: the Shepherd reveal, the knocked-out beat, the coda | P1 |
| Fido's memory sequence, Shin's flashback | none | M11's scene from Fido's camera; M6's opening walk | P2 |
| Epilogue and coda | none | M12's scripted end, the empty base, the note, the kitten, the dream, "welcome" | P0 |
| People on screen | none, and not planned (D1) | none unless D1 changes | Later |

### 5.3 Missions

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Missions | two: First contact (Ashen valley, three waves) and Frontier sweep (Sector 86, four waves, the bridge) [seen `missions.json`] | thirteen (M0 to M12) and two console chapters | P0 |
| Mission types | destroy every wave; waves can arrive alerted, track the player, march a route and wait for a trigger distance [seen] | defend, ambush with a setup phase, stealth travel, escort (Fido), retreat under fire, boss, last stand, night patrol, console chapter | P0 |
| Win and lose | win: every wave destroyed; lose: the player's Juggernaut destroyed [seen] | reach an area, survive a time, keep a unit alive, a beat ends it | P0 |
| Objectives on screen | one objective line and a guide to the nearest Legion [seen `mission.gd` guide()] | several objectives, optional ones (the bridge drop already is one), markers in the world and on the map | P1 |
| Weather and time per mission | each map names a default in `maps.json`; `set_weather(id)` already switches it live, and bots use it; missions have no weather field [seen `small_map.gd`, `big_map.gd`] | a mission weather field and a beat action that calls `set_weather`; the night presets (5.8) | P0 |
| Story places | none exist | the base, a marsh on Sector 86, a Legion base under construction, Shourei's arena, the river, the school | P0 |

### 5.4 The Juggernaut

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Movement: walk, gallop to 70 km/h, slide, jump, flips | almost polished [handoff] | the air-turn and belly-scrape regression since 013, cause unknown [handoff bug 2]; Emerson's map-edge wall climbing (010), never reproduced [handoff] | P1 |
| Standing back up | the leg-push version is written, uncommitted, one test failing in the full suite [handoff; still uncommitted, seen `git status`] | finish, commit, save version 019 | P0, first |
| Ledge climb | working; lifts toward a target speed [handoff] | check against the physics-only rule | P1 |
| Legs touching the world | only the hull collides [handoff bug 10] | leg colliders | P1 |
| Hardcore manual walking | a setting, never playtested [handoff] | a playtest and a pass | P2 |
| Loadouts | the Hangar names the slots (main gun, sub-arms, sub-arm guns) but nothing is picked per sortie [seen `hangar.json`, roadmap-to-beta]; the player's Juggernaut has both the 12.7 mm guns and the blade strike [seen PLAYTEST]; a blade-armed variant exists (`mechs.json` `juggernaut_m2_blades`, flown by Laughing Fox, loadable on the bench) [seen] | a loadout per sortie: `juggernaut_m2` or `juggernaut_m2_blades` (the canon choice of 12.7 mm guns or high-frequency blades on the sub-arms), the long-barrel gun kit [canon, wiki], the ammunition mix | P1 |
| Personal marks | Undertaker's headless skeleton and "none" [seen `emblems.json`] | every squad mate's mark on their machine, at the base and in the Handler view | P1 |
| Damage between missions | part damage lasts one mission [seen settings] | in Act IV damage carries over and Fido repairs | P2 |
| Power as gameplay | Emerson's 2026-09-30 idea (sprint, reel, gun and actuators share one power bus with a real peak) [PLAN.md]. A battery-and-bus actuator model (voltage sag, heat, cutouts, breakages) exists and runs on any map when Settings > Gameplay > Physics > Physics mode is "Test bench"; only the legs draw from it [seen `bench_rig.gd`, `bench_driver.gd`, `standin_mech.gd`] | put the gun, the reel and the sprint on the same bus; tune bench mode for a mission; try it for Act IV's scarcity and keep it if it plays well | P2 |
| Cockpit interior | the cockpit view looks out from the front sensor [handoff] | the cramped cockpit with its screens: a strong mood piece, a big model job | Later |

### 5.5 Combat

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| 57 mm, ballistics, damage per part | working: four ammunition types, 12 in the magazine, 60 in reserve, armour in mm, ricochets, near-miss crack [seen `weapons.json`, handoff] | none | done |
| Where shells land against the crosshair | never measured; the third-person aim mark locks onto hills [handoff, bug 3] | a bot that fires at marked targets at known ranges and logs the miss; change only what the numbers show; fix the aim mark | P0 |
| Legion accuracy | they hit almost every shot (012); four fixes offered, his pick pending [handoff] | D13 | P0 |
| Hit feedback | the radio names some parts shot off [seen] | on the HUD: what you hit and what it did | P1 |
| Resonance blade | works on X, no pad button [handoff] | a pad button; its moment against the Shepherd | P1 |
| Wire anchor | working, frozen by Emerson's choice [handoff] | nothing until he says so | frozen |
| Artillery fire missions | none; the blast system exists [seen `blast.gd`] | C2's tool: mark a point, shells arrive after real flight time with spread; friendly fire possible | P0 |
| Resupply in the field | none; the reserve lasts the sortie [seen `weapon_state.gd`] | Fido refills | P1 |
| Balance | a first pass [handoff] | a measured table: shots and time to kill per Legion type and round, survival per wave, per difficulty | P1 |

### 5.6 The Legion

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Types | Ameise (scout, 8 mm armour), Grauwolf (pack hunter, 15 mm), Löwe (heavy, 240 mm) [seen `enemies.json`] | Skorpion, long-range artillery (M7); Dinosauria, the heavy tank type (100 t, 155 mm), Shourei's body (M9); Eintagsfliege, a jamming swarm (Acts II and III); self-propelled mines optional [canon, wiki] | P0 Skorpion, Dinosauria · P1 Eintagsfliege · P2 mines |
| Black Sheep and Shepherds | none [seen] | a flag on any unit: it carries a voice Shin hears; a Shepherd also commands the units near it (coordinated flanks, faster calls) | P0 |
| Shapes like the anime | the first boxy blockouts [handoff] | the B2 reshape list: Grauwolf's swept head, the Löwe's tapered turret, the Ameise's ringed sensor | P1 |
| AI | working, rough: the Grauwolf flanks, Ameise and Grauwolf back off when hurt, scouts call in the rest [seen `pack_hunter.gd`, `legion_brain.gd`, `enemies.json`]; crater pile-ups on Ashen valley (no path grid there), accuracy unsettled [handoff] | a path grid on Ashen valley; suppressing fire, flanks coordinated across a group, regrouping after a retreat | P0 grid · P1 the rest |
| Legion on the real-place maps | never tried [roadmap-to-beta]; `big_map.gd` already builds a grid on all three, with bridge corridors, but it knows only slopes and water, not houses or forest [seen] | houses and forest in the grids; a wave-arrival test on each map; sized up, since one wave's reliable arrival once took five sessions [roadmap-to-beta] | P0 |
| Collecting the fallen | none | Legion that go to a wreck to take what is in it: why the mercy shot matters | P1 |

### 5.7 Squad, Handler and Fido

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Wingmen | full-physics Juggernauts flown by AI through the same controls; orders 1 to 4; they fire only when the shell would land and no friend is in line [handoff] | slide and jump; the wire, which waits on the same freeze as the player's (Emerson's call) [handoff]; voices; personal marks; scripted deaths (P0); the rest of the squadron as a distant group (D8) | P1 |
| Handler view | squad from above with live markers (callsign, armour, order, and the Legion the squad can see), click to move or attack, orders follow, hold, attack and regroup [handoff, seen `handler_view.gd`] | pan, zoom, contact list, waypoints, long paths on the big map; marks the player places (C1); C2 fire missions | P0 for what C1 and C2 need (while D6 stays yes) · P1 the rest |
| Fido | none | a Scavenger about 2.5 m tall with crane arms and a container, with Shin from episode 1 [canon, wiki]: follows Shin, refills ammunition, collects; a model through the `~/Models` pipeline, an AI, an escort role. At the base from the slice, following in the field from Act II, a full unit in Acts III and IV | P1 (P0 if D9) |

### 5.8 World and maps

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Maps | Ashen valley (1 km), Sector 86 frontier (4 km, streamed), Palouse, Allegheny and Brilon (real places), a test range, two bench grounds [seen `maps.json`] | the story places (5.3) | P0 |
| Weather | eight presets; five maps name a default, using four of them, and four are spare; none at night [seen `weather.json`, `maps.json`] | night (M4, the festival, the school), weather per mission, weather that changes during one | P0 night and weather per mission · P1 changes during one |
| Destruction | kit-built towns break and fall, bridges drop spans; real-map houses, props and trees do not break [handoff] | Brilon's mission streets breakable (M11, M12) | P1 |
| Trees | do not break [handoff] | breakable trees where Allegheny's fights happen | P2 |
| The look | a big jump since 010; weak spots: big-map crags, Allegheny's sun blow-out, far shrubs as dark blobs, grass ends at 60 m, boxy Legion [handoff] | the look strand (section 7, 0.8) | P1 |

### 5.9 Sound, music, menus and HUD

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Sound | almost polished: real recordings in 3D at the speed of sound [handoff]; a few Mixkit-licensed sounds and no sound section in `assets/SOURCES.md` [handoff bug 11] | credit or replace | P0 for sharing |
| Music | 56 tracks, each with a use (menu, explore or combat) and a kind (opening, ending or score); three free CC BY tracks already stand in for the 86 music in share copies [seen `music.json`, Relay 95] | cues by story moment (act, beat, boss, death, base, credits) through beat actions, with a free fallback per cue | P0 (the 1.0 definition, item 5) |
| The voices of the dead | none | whispers placed in 3D, a thinner mix while they speak | P0 |
| Radio sound | text typed out with a soft tick; no voice, filter or static [seen `radio.gd`] | a radio filter, Para-RAID static, the range fade | P1 |
| Menus, settings, HUD | almost polished: settings search, two themes, pad support, Hangar, photo mode [handoff] | the campaign screens (Continue, chapters, briefing, debrief, base, names, credits) in the same style | P0 |
| Accessibility | Settings > Accessibility: menu and text size, high contrast, a colour filter (protanopia, deuteranopia, tritanopia, greyscale) with a strength slider, reduce motion, reduce flashing, subtitles with size, box and speaker names; keys rebindable [seen `settings.json`]; the blade has no pad button [handoff] | shapes as well as colours on HUD and map marks (the filter recolours the screen; it adds no shapes), a visual ring for Shin's hearing, a pad button for the blade, every new action rebindable, an option to let the game take the mercy shot | P1 |
| Tutorial | a seven-step stub, off by default [seen `tutorial.json`] | replaced by M0 (D12) | P0 |

### 5.10 Shin's hearing, specified

The one new mechanic the story cannot do without.
- **What it is:** Shin hears every Black Sheep and Shepherd within range (about 2 km to start; a tuning figure)
  as voices. The player gets their direction and rough number before anything is in sight: whispers placed in
  3D sound, and a ring of marks on the HUD for anyone who cannot hear them (a setting).
- **Why:** it is how Shin predicts the Legion's moves [canon, episode 5], and it turns the series' horror into
  play: you know they are coming and cannot see them yet.
- **Limits:** only units carrying a voice, not every Legion; direction and loudness, no distance figure; a
  Shepherd drowns out the rest (M9). In Act I Shin uses it only through his radio calls ("They're coming.
  North-east."); the player gets it in M5, when Lena hears it too.
- **Settings:** voices volume, the visual ring, a comfort option (whispers without words).
- **Data:** a `voice` field on a Legion entry or a mission group; the dead's lines in the style of `radio.json`.
- **Physics rule:** perception only; nothing moves because of it.

### 5.11 Frame rate, builds, sharing, tests

| Feature | Today | Gap to 1.0 | Priority |
|---|---|---|---|
| Frame rate | test range: Low 66.5, Medium 58.4, High 35.2, Ultra 15.1 fps; per map High 22 to 37; Ultra on a 15 fps floor everywhere; all taken before 0.1.1's denser grass (about 1.6x), with no after-set [handoff] | measure per mission (Acts II to IV have more units, artillery and smoke); find the Ultra floor | P0 to measure per mission (the 1.0 definition, item 9) · P1 to raise the floor |
| Builds and versions | `tools/play.sh`; `builds.py` save and share; 18 saved versions; zips for three platforms; Linux verified, Windows and Mac never run on a real machine [handoff] | run on a real Windows PC and a Mac; fix what breaks | P0 |
| Licences | OpenStreetMap (ODbL) and the Mixkit sounds not credited yet [handoff bug 11] | credits in the game, `SOURCES.md` and the zips | P0 |
| The 86 story in share copies | the OST is kept out [handoff]; the squad's names and the radio already ship | D7 | P0 (a decision) |
| Tests and bots | 63 test files, 528 of 529 passing at the last full run (the failure is the uncommitted stand-up work), 116 bot scripts [handoff, seen `git log` 68ffc36]; the off-screen bot stalls now and then, cause not found [handoff bug 6] | find the stall's cause first; then a campaign bot that plays every mission to its end, save/load round-trip tests, a test per beat action, soak runs | P0 |

## 6. The gaps, most important first

1. **A clean, saved, played version** (019): everything else builds on it.
2. **Mission beats.** Every story moment rides on them; without them there is no story.
3. **Campaign runner and save game.** Without them there is nothing to come back to.
4. **Briefing, debrief, the base and the names.** Where the story and the tone live between fights.
5. **A radio with many speakers and real story lines** (voices follow, D2).
6. **A fair fight, measured:** the shell-landing bot and Legion accuracy (D13). Every mission rests on it.
7. **The mission types:** defend, ambush, retreat, stealth travel, boss, last stand.
8. **Shin's hearing, the Black Sheep and the voices of the dead:** the series' signature, needed from M5.
9. **Path grids and Legion on every mission map:** a grid for Ashen valley; houses and forest taught to the
   real places' grids, which know only slopes and water today; a Legion test on each. The riskiest job on the
   list.
10. **Night and weather per mission** (M4, M7, M12 and the act palettes).
11. **Scripted deaths and the mercy shot,** done by the tone rules.
12. **Skorpion artillery and the retreat under fire** (M7).
13. **The Dinosauria Shepherd and Lena's guns** (M9, C2).
14. **Fido** (at the base from the slice; a full unit in Acts III and IV).
15. **The Handler view's pan, zoom and markers** (C1, C2).
16. **The story places:** the base, the marsh, the Legion base, the boss arena, the river, the school.
17. **Brilon's streets breakable** (M11, M12).
18. **Credits, licences, Windows and Mac runs, D7.**
19. **A campaign bot and soak runs,** once the off-screen bot's stall is found (handoff bug 6).
20. **Music cues per act and beat,** with a free fallback for each.

## 7. Order of work

**How it is ordered.** A playable, saved version ends every phase, and Emerson plays it before the next one
starts. The story spine is built first as a vertical slice on what already works (two maps, three Legion
types); then the game widens act by act, and each act brings only the new systems its missions need. All the
dialogue is written early, so voices come late, once the lines are stable. The look strand runs alongside, one
GPU job at a time on this laptop.

Sizes, as in the beta roadmap: S = one session (one Relay task), M = 2 to 4, L = 5 to 10, XL = more than 10.
Guesses from how long the alpha's jobs took, not promises.

**0.1.2 Clean slate** (S to M, 1 to 2 sessions). The beta roadmap's 0.1.2 as written: finish and commit the
stand-up work and the stray `.uid` files, full suite green, version bump, "what's new" in PLAYTEST.md, save
version 019, the Linux export boots, re-run the frontier finale and play the bridge drop once with real shells
(handoff bug 9). Emerson plays 019 and answers D13 and the handoff's open questions.

**0.2 The story spine: a vertical slice** (L to XL, 9 to 14). M0, M1 and M2 as a campaign, start to end, with
everything between them: the campaign file and runner, save game, Continue and New campaign, the first beat
actions, the radio with several speakers, briefing and debrief, the base (the Hangar scene reworked), the names
screen with the 559 names Shin carries in, the first night talks, Kujo's death and the mercy shot under the tone
rules, M0 in place of the tutorial stub, Lena's console messages (M2's history class), Act I's script written for
Emerson to read. First, the cause of the off-screen bot's stalls (handoff bug 6), since the campaign bot is built
on it. Fido's model starts in the look strand so it can stand at the base. *Done when* a bot plays M0 to M2 in
order through saves and Emerson has played the slice. *Why first:* it proves every campaign system on maps and
Legion that already work; after it, most missions are data and beats.

**0.3 A fair fight and the rest of Act I** (L to XL, 10 to 15). The shell-landing bot and what it shows, and
the aim mark that locks onto hills (handoff bug 3); Legion accuracy by D13; hit feedback; the blade on a pad
button; the balance table (saved in the docs library); the leg colliders and the air-turn regression (handoff
bugs 10 and 2), and a try at reproducing the map-edge wall climb; a path grid on Ashen valley; weather per
mission (a mission field and a beat action on the existing `set_weather`), the night preset, lamps and flares;
several and optional objectives with markers; the Handler view's pan, zoom and player marks; C1; the marsh
ground and M3; M4 with the switch to real names; the squad's personal marks; difficulty presets. *Done when*
Act I plays through.

**0.4 Act II: the voices** (L to XL, 11 to 17). Act II's script first, read by Emerson. Black Sheep and Shin's
hearing with its sound and its ring; Shepherd coordination; defend and retreat missions; the Skorpion with
spotters; the Eintagsfliege; Legion that adapt and collect the fallen; the festival night; M5, M6, M7 and
their eleven names; loadouts per sortie (guns or blades); checkpoints; Fido following in the field; the
wingmen's slide and jump (their wire stays frozen with the player's); the rest of the squadron as a distant
group (D8). A first Legion trial on Allegheny's existing grid, to price Act IV early. *Done when* Act II plays
through and Emerson has played Acts I and II.

**0.5 Act III: the Shepherd** (L to XL, 11 to 16). Act III's script first, read by Emerson. Fido as a full
unit (AI, resupply, escort); the march mission; the Dinosauria model and its boss AI; Lena's fire missions
(C2) and the Handler view's contact list, waypoints and long paths; M8's console messages (her uncle,
Annette); the knocked-out beat and the Para-RAID fade; camera moments; M8 with its four names, M9 and its
arena. *Done when* Act III plays through.

**0.6 Act IV and the ending: content complete** (XL, 13 to 18). Act IV's script first, read by Emerson.
Legion on Allegheny, Brilon and Palouse, their grids taught houses and forest; stealth travel and the last
stand; Brilon's mission streets breakable; the river and the school; Fido's memory scene; M10, M11, M12; the
epilogue, credits and coda; the chapter select and replay bests. *Gate: content complete.* Emerson plays the
whole campaign once, rough edges and all.

**0.7 Voices and presentation** (L, 5 to 8). Voices by D2, the radio filter and static; music cues per act
and beat with share-copy fallbacks; camera moments polished; the rest of Lena's console messages, and polish
for all of them; the M6 flashback (P2); the title screen.

**0.8 The world, stupid high quality** (L, 6 to 10 in total; runs alongside from 0.2). The beta roadmap's 0.6
list, the story places brought to Brilon's standard, the act palettes, the Legion reshaped to the anime, the
Juggernaut's remaining critic fixes.

**0.9 Runs everywhere, shareable: beta** (L, 6 to 10). The beta roadmap's 0.7 and the beta half of its 0.8:
frame pacing, High toward 30 where it costs no looks, frame rate measured per mission, real Windows and Mac
runs, licences, D7 carried out, soak runs, the campaign bot, a bug bash with every bot, Emerson's playthrough
of the whole campaign with his notes done, and a fresh honest handoff. *Gate: beta,* the 2026-10-07 definition
with the story in it.

**1.0 The finish line** (L, 5 to 8). What 1.0 adds beyond beta: balance per difficulty; the accessibility
pass; patrol mode; Emerson's last playthrough and all its notes; a final bug bash; a fresh honest handoff that
meets section 1; save 1.0, make the share zips, "what's new" in PLAYTEST.md.

**The P2 items** (section 5) have no phase of their own and are not counted in the sizes: each rides with the
phase whose missions use it if time allows, and each is the first thing cut when time runs short (risk 1). Power
as gameplay, damage carried between missions and breakable trees go with Act IV (0.6), the self-propelled mines
with any act that has room; loading-screen lore, unlocks and the hardcore walking playtest go with 1.0. Fido's
memory scene (0.6) and the M6 flashback (0.7) are already placed.

**Total: roughly 77 to 118 sessions from today,** the phase sizes added up. The beta roadmap's 40 to 60 sessions
assumed 8 to 10 missions and no story; this adds the story systems, three to five more missions, two console
chapters and the presentation. Two strands run side by side: the game strand (0.2 to 0.7, then 0.9 and 1.0) and
the look-and-models strand (0.8, plus the Skorpion, Dinosauria, Eintagsfliege and Fido models and the story
places).

**What this changes in the 2026-10-07 beta roadmap:** its 0.2 ("something to do") becomes 0.2 to 0.6 here,
ordered by the story, and a mission on every map still happens, where the story puts it; its 0.3 (a sharper
fight) stays early; its 0.4 (Legion) and 0.5 (squad) are split across the acts that need them; its 0.6 (the
world) runs alongside as 0.8; its 0.7 becomes 0.9; its 0.8 (the finish line) is split, so that the beta
gate can be met: the bug bash, the playthrough and the fresh handoff close 0.9, and the accessibility pass
closes 1.0. Its artillery type and its note on the real-place maps' grids are corrected (section 10).

## 8. Decisions for Emerson

Each has the default a session uses until he answers.

- **D1. People on screen?** Default: no. Voices, text, machines and places only (pillar 3); M6's flashback and
  Fido's memories are staged without a figure. Later options: 2D portraits beside the radio lines, or stills.
- **D2. Voices.** Default: Piper (local, already in Forge) through a radio filter for the fight calls; story
  lines stay text with sound until a test scene shows Piper carries the emotion. Other options: friends record
  the lines; or text only.
- **D3. Branching.** Default: none. The canon arc holds; night-talk replies are flavour.
- **D4. The mercy shot.** Default: the player takes it, one shot, never rewarded; an accessibility setting lets
  the game take it instead.
- **D5. Squad deaths.** Default: only the canon deaths, at their beats; a wingman "destroyed" elsewhere is
  disabled and back next mission. On the "86" difficulty anyone can die and the names grow.
- **D6. Lena's console chapters (C1, C2).** Default: yes, short.
- **D7. The 86 story in share copies.** *86* is Asato Asato's copyrighted work. A non-commercial fan game
  shared with friends is common, but it is not licensed; today's share zips already carry the squad's names and
  the Handler's radio, and the full story would carry much more. Options: (a) share with friends only, never
  publicly, as now; (b) share copies swap in original names and story text; (c) share copies carry the sandbox
  only (free roam, patrol mode). Default: (a), and nothing is published publicly without his decision. This is
  a flag, not legal advice.
- **D8. Squad scale.** Default: up to four full-physics wingmen, plus the rest of the squadron as a distant,
  simpler group.
- **D9. Fido as a real unit.** Default: yes. It is with Shin from episode 1 [canon], stands at the base from the
  slice, and Acts III and IV lean on it.
- **D10. Part 2 after 1.0.** Default: yes, as a second campaign file.
- **D11. Act IV's shape.** Default: three linear missions. Later: a march map where you pick routes and spend
  supplies, as a replay mode.
- **D12. The tutorial.** Default: M0 replaces the stub.
- **D13. Legion accuracy** (open since 012). Default: measure their hit rate with a bot first, then the
  difficulty presets set it with whichever fix the numbers favour.
- Still open from the 2026-10-07 handoff, unchanged: blades swinging level in a slide, the spawn sparks and
  falling through the map, rumble switched off in his settings, the Godot add-ons (Terrain3D, GUT), re-sizing
  the bench motors, the Legion's masses. Also his: when the wire freeze ends, for the player and the wingmen.

## 9. Risks

1. **Scope.** About 77 to 118 sessions is months of Relay work. The slice comes first, every phase ends playable,
   and the P2 items are cut first, then Act IV's P1 extras.
2. **Legion on the real-place maps.** One wave's arrival took five sessions on the big map. Their grids
   know only slopes and water today. The Legion trial on Allegheny in 0.4 prices this before Act IV depends
   on it.
3. **The writing.** The script is the story; Claude writes it, Emerson reads it. Act I's lines are written in
   0.2 and read by him before anything is voiced.
4. **Voices against the tone.** Flat text-to-speech in a death scene would hurt it. Hence D2's default and a test
   scene first.
5. **Canon accuracy.** The roll of the fallen (section 4.4) comes from the wiki, and the summaries rarely say
   how anyone dies: watch the episode before scripting any death, and mark every invention in the script.
6. **Frame rate in the big fights.** More units, artillery and smoke in Acts II to IV. Measure per mission; the
   distant squad group is cheap by design.
7. **Sharing the 86 story** (D7).
8. **Emerson's time to play.** Every phase needs his play and his taste for the base and the story; keep the
   short "try this" notes per version.
9. **The tone drifting** across many sessions. Section 3 is the reference: every story session reads it, and a
   critic checks new lines against the tone rules.
10. **One GPU job at a time.** Look work and bot runs compete for the laptop's GPU; fps runs were paused by
    Emerson on 2026-10-07.
11. **The bot harness.** The off-screen bot stalls now and then, cause not found (handoff bug 6), and the
    campaign bot and the soak runs that gate beta and 1.0 run on it. 0.2 looks for the cause first.

## 10. Corrections to earlier docs

- `2026-10-07-roadmap-to-beta.md`, milestone 0.4, names "a long-range artillery type (Stachelschwein)". The 86
  wiki lists the Stachelschwein as anti-aircraft; the long-range artillery type is the Skorpion [canon, wiki].
  This plan uses the Skorpion for M7. The same milestone calls the Dinosauria "a super-heavy"; the wiki calls it
  the heavy tank type (100 t, a 155 mm gun).
- The same roadmap's 0.2 says the real-place maps "need the nav grid the big map has". They already load the
  same `big_map` scene and build that grid (`big_map.gd`, `_build_nav()`), but it knows only slopes and water,
  and no Legion has walked them [seen]. The work is teaching the grid houses and forest and testing Legion
  there, not building a grid.

## 11. Sources and what was checked

Read for this document on 2026-10-08 (nothing was run):
- **Docs:** `2026-10-07-handoff.md` and `2026-10-07-roadmap-to-beta.md` (this folder), `2026-10-07-guide.md`
  by reference; `~/Games/eightysix/NOTES.md`, `PLAYTEST.md`; `~/Forge/sessions/juggernaut-alpha/PLAN.md` (the
  goal, raising the bar, Emerson's notes during the wave).
- **Game data:** `missions.json`, `squad.json`, `radio.json`, `tutorial.json`, `enemies.json`, `music.json`,
  `maps.json`, `weather.json`, `weapons.json`, `mechs.json`, `emblems.json`, `themes.json`, `hints.json`,
  `tips.json`, `hangar.json`, `settings.json` (the Difficulty page).
- **Code, by listing and search:** the `scripts/` folders; `main_menu.gd`, `pause_menu.gd`, `mission_end.gd`,
  `mission.gd`, `sortie_log.gd`, `weapon_state.gd`; every `user://` path; `scenes/`, `tests/`; `git log` (last
  commit 68ffc36, Relay 95) and `git status` (Relay 62's stand-up work still uncommitted).
- **Canon:** Wikipedia, "List of 86 episodes" (episode summaries 1 to 23, from the page's wikitext); the 86
  fandom wiki: "M1A4 Juggernaut" (armament), "Fido", "Spearhead Squadron" (the roll of the fallen), "Kujo
  Nico", the pages of Raiden, Theo, Kurena and Anju, and the Legion types.
- **Not checked:** the handoff's test results (taken as written there); the music picks by ear; how most of the
  fallen die (the summaries say who, not how); the light novels beyond what the wiki says.
- **Review:** two critic agents (Opus, fresh context) checked this document on 2026-10-08. One checked every
  claim about today's game against its code and data: 11 findings, chiefly that the power bus and the
  real-place grids already exist in part, plus smaller misses on loadouts, weather, accessibility, AI, the
  debrief, the radio, music, the Handler view and the loading screen. The other checked canon, the request and
  the earlier docs: 19 findings, chiefly that Kujo dies before Lena's introduction, the 561 count and the roll
  of the fallen, Lena's and Annette's ties to Shin and Shourei, items with no phase, the beta gate, the bot
  stall, priority labels and the session sums. All 30 are fixed in this version; the other claims both
  critics tested held up. A last read-through the same day (Sora, Relay 97) brought M3 closer to the
  episode 3 summary and gave the P2 items a place in section 7; no other content changed.
