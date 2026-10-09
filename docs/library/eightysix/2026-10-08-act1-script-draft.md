# Eighty Six, Prologue and Act I: Spearhead (M0 to M2): script draft

date: 2026-10-08 · for: both

Rendered by `tools/dialogue_script.py` from `data/dialogue/act1.json` in ~/Games/eightysix. The JSON is what the game reads; this copy is for reading and marking up. Notes go here or in chat, quoting a line's id, and the change is then made in the JSON.

## How to read this

- A line is the speaker in bold, how it is said in brackets, then the words. Lines with no other mark are on the Para-RAID: close and dry, as if beside you.
- *Italic paragraphs* are stage directions: what the player sees and hears. Nobody is ever seen; people are voices. A direction just before a line happens just before it.
- [if ...] means the line plays only when that holds (a teaching nudge, a bridge that fell).
- The code at the end of a line is its id in the JSON.
- Times are targets from the start of the mission.

## Cast

| Who | Callsign | How they speak |
|---|---|---|
| Shinei Nouzen | Undertaker | Few words, flat and calm, dry. Calls the Legion before anyone sees them. Never explains himself. The player. |
| Raiden Shuga | Werewolf | The vice-captain. Blunt and practical; argues with Shin and holds the squad together. |
| Theoto Rikka | Laughing Fox | Sharp tongue, quick temper, the sarcasm of the squad. Flies the blade-armed machine. |
| Kurena Kukumila | Gunslinger | The sharpshooter. Calls range and wind. The coldest voice toward any Handler. |
| Anju Emma | Snow Witch | Soft-spoken and kind; the quietest voice on the radio. Close to Daiya. |
| Kaie Taniya | Kirschblüte | Open and curious, cheerful. Leads the fourth platoon: suppressive fire [new, not checked against the wiki]. Curious about Lena. |
| Daiya Irma | Black Dog | Easy-going, the squad's joker, close to Anju. Grenadier. Adopted the cat. |
| Kujo Nico | Sirius | Cheerful; counts down the days of his service on the hangar blackboard. Kaie's platoon [new, not checked]. Callsign Sirius [canon: the 86 wiki's Spearhead Squadron page, read by the first writer on 2026-10-08; a web search the same day agrees]. Dies in M0. |
| Vladilena Milizé | Handler One | Formal and earnest. Reads from a script in M1, steadier by M2. The one warm voice from the Republic. |
| The old Handler | Handler | Bored and polite. Reads a checklist. His contempt is only in what he does not do. |
| Lev Aldrecht |  | The chief mechanic, an Alba in his fifties. Grumbles; heard at the base only. |
| Republic Defence Headquarters |  | Cheerful official broadcasts. Never cruel in words; the cruelty is what it says calmly. |
| Republic Military Academy, Handler course office |  | Text only, on Lena's console. Polite and banal. |
| Halberd Two | Halberd Two | A Processor of another squadron, cut off at night in M0. Steady, then gone. [new] |

## M0 · The 86th Sector

*Prologue · map small_map · light dusk_haze, then night (a new preset) · about 25 minutes*

A sortie under the old Handler, who logs off; the rescue at night; Kujo and the mercy shot. Replaces the tutorial stub (D12). Its mission entry does not exist yet.

### 0:00 · Base, late afternoon

*Tone: base. Starts on: the mission starts (a trigger the runner does not have yet).* `m0.base`

*Black screen. The hangar's sounds: a compressor, a radio playing low in the next room, the cat. Fade up on Undertaker's bay. Through the open door, two bunks are bare: Matthew's and Mina's. Nobody is seen; the squad is heard.*

**Kujo** (at the base) *(cheerful; chalk on the blackboard)*: One hundred and twenty-eight. `m0.base.010`

**Lev** *(from under a machine)*: Rub that out. Counting's bad luck. `m0.base.020`

**Kujo**: It's good luck, Lev. It goes down. `m0.base.030`

**Lev**: So does a Juggernaut. `m0.base.040`

**Daiya**: Has anyone fed the cat? `m0.base.050`

**Theo**: Whitey ate an hour ago. `m0.base.060`

**Kujo**: Blackie. Its name's Blackie. `m0.base.070`

**Anju**: I gave Calico some fish as well. `m0.base.080`

**Kurena**: So Kitty's had three dinners. `m0.base.090`

**Daiya**: It answers to whoever has the tin. `m0.base.100`

**Theo**: Kujo. That's Shin's box you're sitting on. `m0.base.110`

**Kujo** *(getting up quickly)*: Sorry. Sorry. `m0.base.120`

**Lev** *(the player's machine starts)*: Shin. Walk it out slow. `m0.base.130`

**Lev**: The last one who galloped out of my bay took the door with him. `m0.base.140`

**Raiden**: Look around on your way out. The cat sleeps under the legs. `m0.base.150`

**Lev** (at the base) *(only if the player has not moved)*: [if not_done: walk; beat_s at least 25] It walks forward, Shin. That's the whole trick. `m0.base.160`

*Pages turning. A pencil, scratching, somewhere near the bay door.*

**Kujo**: Fox. Did you finish the old Handler yet? `m0.base.170`

**Theo** *(not looking up from the page; setup 3, the Handler portraits)*: I've only got his voice. He's getting a moustache. `m0.base.180`

### 3:00 · The march out, the sun going down

*Tone: grind. Starts on: the player reaches bay_door.* `m0.march`

*Ashen valley under a low gold sun: grass, poppies on the verges. The old Handler's link opens. Somewhere on his end, a bag of crisps.*

**The old Handler** *(reading; bored)*: Spearhead, this is your Handler. Patrol route six, sweep and return. `m0.march.010`

**The old Handler**: Please confirm. `m0.march.020`

*Silence. Nobody else answers.*

**Shin** *(flat)*: Undertaker. Confirmed. `m0.march.030`

**The old Handler**: Expected contact is light. Keep the channel clear, please. `m0.march.040`

**Theo**: He's eating. `m0.march.050`

**Daiya**: Crisps. You can hear the bag. `m0.march.060`

**Raiden**: Road's clear to the bend. Open it up, Undertaker. Gallop. `m0.march.070`

**Raiden** *(only if the player has not galloped)*: [if not_done: gallop; beat_s at least 30] You can run, you know. We'd like to be back for dinner. `m0.march.080`

**Kaie**: Bend coming. Plant the legs and skid it. Don't plough the field. `m0.march.090`

**Kujo**: Moon's up already. `m0.march.100`

**Daiya**: You and that moon. `m0.march.110`

**Kujo** *(light; nobody answers)*: Mina used to say it came up early on purpose. `m0.march.120`

**The old Handler**: Sector log updated. Continue. `m0.march.130`

### 7:00 · Scouts, at dusk

*Tone: fight. Starts on: wave 1 starts.* `m0.scouts`

*Nothing in sight yet.*

**Shin**: Contact. North-east. Six. `m0.scouts.010`

**Raiden**: I don't see anything. `m0.scouts.020`

**Shin**: You will. `m0.scouts.030`

**Kurena**: There. Ameise, eight hundred. They're quick, so lead them. `m0.scouts.040`

**Anju**: Let the gun settle, then fire. No hurry. `m0.scouts.050`

**Daiya**: Count your rounds. Reload in a lull, not in their faces. `m0.scouts.060`

**Daiya** *(only if the player has not reloaded)*: [if not_done: reload; beat_s at least 60] Undertaker, you're nearly dry. Reload. `m0.scouts.070`

**The old Handler**: Contact noted. Proceed at your discretion. `m0.scouts.080`

*The last scout goes down.*

**Kujo**: Scouts down. Is that it? `m0.scouts.090`

**Shin**: No. `m0.scouts.100`

### 10:00 · The Handler signs off

*Tone: fight. Starts on: 10:00 in.* `m0.logoff`

*Mid-fight. The old Handler's voice is the same as ever.*

**The old Handler**: It's past six. I'm logging off. Don't call. `m0.logoff.010`

*The Handler's link closes. Nobody remarks on it.*

**Raiden**: Kirschblüte, take the left. Black Dog, the right. `m0.logoff.020`

**Kaie**: Kirschblüte, left. `m0.logoff.030`

**Daiya**: Right side. `m0.logoff.040`

### 11:00 · The pack, in the last light

*Tone: fight. Starts on: wave 2 starts.* `m0.pack`

*The sun on the hills. Grauwolves come in fast and close.*

**Shin**: Grauwolves. Fast. `m0.pack.010`

**Raiden**: They jump in close and swing. Slide under it. `m0.pack.020`

**Theo**: Wall on your left. Charge the jump, let go at the top. `m0.pack.030`

**Kaie**: Ridge above you. Wire up and shoot down at them. `m0.pack.040`

**Raiden** *(only if the player has not slid)*: [if not_done: slide; beat_s at least 40] Slide, Undertaker. Don't trade blows with a Grauwolf. `m0.pack.050`

**Kujo**: That's two. Who's buying? `m0.pack.060`

**Theo**: Nobody has any money, Sirius. `m0.pack.070`

**Kujo**: Then I'll owe you. `m0.pack.080`

### 14:00 · Nightfall: the rescue

*Tone: fight. Starts on: wave 2 is cleared.* `m0.rescue`

*Night falls (the new night preset). A link opens from another squadron.*

**Halberd Two** *(out of breath; steady)*: Any unit on this link, this is Halberd Two. `m0.rescue.010`

**Halberd Two**: We're cut off at the old mill. Three machines left. `m0.rescue.020`

**Raiden**: Other side of the valley. `m0.rescue.030`

**Halberd Two**: Anyone. `m0.rescue.040`

*The Halberd link goes quiet.*

**Shin**: We're going. `m0.rescue.050`

**Raiden**: No Handler to ask. `m0.rescue.060`

**Raiden**: No one to say no, either. On Undertaker. `m0.rescue.070`

**Kurena**: Can't see a thing past two hundred. `m0.rescue.080`

**Raiden**: Then listen. Grauwolves clank. And listen to him. `m0.rescue.090`

**Shin**: Left. Three hundred. `m0.rescue.100`

**Anju** *(no answer comes)*: Halberd Two, this is Snow Witch. We're coming. `m0.rescue.110`

### 16:00 · Kujo

*Tone: voices. Starts on: the player reaches mill_field.* `m0.kujo`

*The field before the mill. Something on the ground ahead, person-sized, moving like someone hurt.*

**Kujo**: [if alive: Kujo] There's someone down. In the field. He's moving. `m0.kujo.010`

**Kujo**: [if alive: Kujo] Must be one of Halberd's. I'll get him. `m0.kujo.020`

**Raiden**: [if alive: Kujo] Sirius, wait. `m0.kujo.030`

**Shin**: [if alive: Kujo] Sirius. Stop. `m0.kujo.040`

*The shape gets up and runs at Kujo's machine: a self-propelled mine. The blast. His Juggernaut is down, both legs gone.*

**Kujo** *(light)*: [if alive: Kujo] Huh. That's both legs. `m0.kujo.050`

**Raiden**: [if alive: Kujo] Hang on. We'll get you out. `m0.kujo.060`

**Shin**: [if alive: Kujo] Grauwolves. Closing on him. `m0.kujo.070`

**Kujo** *(light)*: [if alive: Kujo] Tell Lev I'm sorry about the paint. `m0.kujo.080`

**Raiden**: [if alive: Kujo] Tell him yourself. `m0.kujo.090`

**Kujo**: [if alive: Kujo] Hatch is jammed. `m0.kujo.100`

**Kujo** *(quieter)*: [if alive: Kujo] Undertaker. `m0.kujo.110`

**Shin**: [if alive: Kujo] Here. `m0.kujo.120`

**Kujo** *(quiet)*: [if alive: Kujo] Make mine neat. Your handwriting's awful. `m0.kujo.130`

**Shin**: [if alive: Kujo] I will. `m0.kujo.140`

**Kujo** *(very quiet; plays only if the player has not fired by then)*: [if alive: Kujo; beat_s at least 40] Undertaker. They're here. `m0.kujo.150`

### 18:00 · After

*Tone: names. Starts on: Kujo's machine is destroyed (a trigger the runner does not have yet).* `m0.after`

*The mercy shot is the player's: one shot. No hit marker, no kill cam. The music drops out; ten seconds of silence on the link. The squad finishes the Grauwolves without a word. No win screen. Undertaker's hatch opens. Close by Sirius's wreck, the sound of a cutter on aluminium. Fido rolls up, beeps once, and starts collecting what is left.*

**Raiden** *(after a long silence)*: Clear. `m0.after.010`

**Anju** *(very quiet)*: Halberd? `m0.after.020`

**Shin**: No one. `m0.after.030`

### 20:00 · Night at the base

*Tone: names. Starts on: the player reaches base.* `m0.night`

*The hangar at night. Sirius's bay is empty. The blackboard still says 128. The names screen, first use: 559 names scroll past, then a new one is carved: Kujo Nico.*

**Lev** (at the base) *(from his bench, to nobody in particular)*: Leave the board. `m0.night.010`

## N0 · Night talk: A new voice

*after M0*

Lena introduces herself; the squad's silence (canon, episode 1).

### 0:00 · The Para-RAID chimes

*Tone: wall. Starts on: after m0 (a trigger the runner does not have yet).* `n0.chime`

*The mess hall: chairs, plates, a tap dripping. Nobody talking. The Para-RAID chimes: a link nobody expected.*

**Lena** *(formal; a little nervous)*: Good evening. Is this... can everyone hear me? `n0.chime.010`

*Silence.*

**Lena**: This is Handler One, for Spearhead squadron. `n0.chime.020`

**Lena**: My name is Vladilena Milizé. From tomorrow I'm your Handler. `n0.chime.030`

**Lena**: I read today's report. I'm sorry about Sirius. `n0.chime.040`

*Silence. In the hangar the compressor cycles. Someone sets down a mug.*

**Lena**: I'll be on the link at seven. Thank you for listening. `n0.chime.050`

**Shin**: Undertaker. Acknowledged. `n0.chime.060`

**Lena**: Thank you, Undertaker. Good night. `n0.chime.070`

*The link closes.*

**Theo** (at the base): Sirius. `n0.chime.080`

**Kurena**: She read it off a form. `n0.chime.090`

**Anju**: She still read it. `n0.chime.100`

**Raiden**: Give it a week. `n0.chime.110`

## M1 · First contact

*Act I · the game's mission ashen_first_contact · map small_map · light golden_afternoon · about 20 minutes*

Lena's first sortie: by the book; Shin ignores the book and the squad wins its own way [new].

### 0:00 · Briefing, on Lena's console

*Tone: wall. Starts on: the mission starts (a trigger the runner does not have yet).* `m1.brief`

*Lena's console, her first briefing. HQ's morning broadcast first. Then Lena, reading from a script.*

**HQ** (broadcast) *(cheerful)*: Good morning from Defence Headquarters. `m1.brief.010`

**HQ**: The eastern front reports no human casualties this week. `m1.brief.020`

**Lena** *(reading)*: Handler One to Spearhead. Good morning. `m1.brief.030`

**Lena**: Today's operation: find and destroy Legion scouts in Ashen valley. `m1.brief.040`

**Lena**: Formation is wedge, two hundred metres apart, as the manual says. `m1.brief.050`

**Theo**: Which manual? `m1.brief.060`

**Lena** *(sincerely)*: The Processor field manual. Chapter four, page sixty-one. `m1.brief.070`

**Daiya**: She knows the page. `m1.brief.080`

**Kurena**: We don't have that manual. `m1.brief.090`

**Lena**: I'll have copies sent. `m1.brief.100`

**Shin**: Undertaker. Understood. `m1.brief.110`

### 2:00 · Wave 1

*Tone: fight. Starts on: wave 1 starts.* `m1.wave1`

*Ashen valley under a gold afternoon.*

**Lena**: All units, wedge formation, please. Undertaker at the point. `m1.wave1.010`

**Shin**: Understood. `m1.wave1.020`

*Shin turns off the road and drops into the craters. The squad follows him, not the wedge.*

**Lena**: Undertaker, you're out of formation. `m1.wave1.030`

**Kaie** *(cheerful)*: We're in ours, Handler One. `m1.wave1.040`

**Shin**: Craters. Two. `m1.wave1.050`

### 7:00 · Wave 1 cleared

*Tone: grind. Starts on: wave 1 is cleared.* `m1.wave1_clear`

**Lena**: Both scouts confirmed destroyed. Well done, everyone. `m1.wave1_clear.010`

**Theo**: Everyone. `m1.wave1_clear.020`

**Daiya**: Be nice. `m1.wave1_clear.030`

**Theo**: I'm always nice. `m1.wave1_clear.040`

### 8:00 · Wave 2: the ignored order

*Tone: fight. Starts on: wave 2 starts.* `m1.wave2`

**Lena**: Grauwolf pack north of the town. Three. `m1.wave2.010`

**Lena**: All units, hold your positions. Let them come to you. `m1.wave2.020`

**Shin**: Werewolf, Gunslinger. West. `m1.wave2.030`

**Raiden**: On you. `m1.wave2.040`

*Shin flanks west, the other way from her order.*

**Lena** *(after a pause)*: Noted. `m1.wave2.050`

**Theo**: Handler One, is there a page for this? `m1.wave2.060`

**Lena**: I'm looking. `m1.wave2.070`

**Kaie**: What's it like over there? Is it warm? `m1.wave2.080`

**Lena**: It's an office. It's warm, yes. `m1.wave2.090`

**Kaie**: Lucky. `m1.wave2.100`

**Kurena**: Can we have the channel back? `m1.wave2.110`

**Anju**: Leave her be, both of you. `m1.wave2.120`

*Thirty seconds later. She has not hung up.*

**Lena**: The pack is breaking west. Toward you, Undertaker. `m1.wave2.130`

### 14:00 · Wave 3: the Löwe

*Tone: fight. Starts on: wave 3 starts.* `m1.wave3`

**Shin**: Löwe. South. Heavy. `m1.wave3.010`

**Lena**: I have it, Undertaker. It can't climb the east slope. `m1.wave3.020`

**Lena**: It has to come up the south road, into the town. `m1.wave3.030`

**Shin**: Werewolf. South road. `m1.wave3.040`

*The squad turns south on her word. Nobody thanks her.*

**Kurena**: Löwe, nine hundred. Wind from the left, light. `m1.wave3.050`

**Anju**: Its gun is turning. Careful, Undertaker. `m1.wave3.060`

### 19:00 · Debrief

*Tone: grind. Starts on: the mission is won (a trigger the runner does not have yet).* `m1.debrief`

*The grade on the console.*

**Lena**: That's all of them. Thank you, everyone. `m1.debrief.010`

**Lena**: I'll file the report tonight. Good work. `m1.debrief.020`

**Theo** *(off the link; Lena cannot hear)*: She thanked us. `m1.debrief.030`

**Raiden** *(off the link)*: She did. `m1.debrief.040`

## N1 · Night talk: Dishes

*after M1*

Lena asks about their day; Theo and Kaie test her; she does not hang up [new].

### 0:00 · Dishes

*Tone: base. Starts on: after m1 (a trigger the runner does not have yet).* `n1.dishes`

*Night. The mess: dishes, a tap running. The Para-RAID chimes.*

**Lena**: Good evening, Spearhead. Is this a bad time? `n1.dishes.010`

**Theo**: We're doing the dishes, Handler One. Want to help? `n1.dishes.020`

**Lena**: If I could, I would. `n1.dishes.030`

**Kaie**: What did you have for dinner? Over there. `n1.dishes.040`

**Lena**: Soup. Bread. `n1.dishes.050`

**Theo**: Real bread? `n1.dishes.060`

**Lena** *(a pause)*: Yes. `n1.dishes.070`

**Daiya**: Ours comes in a block. It's meant to be chicken. `n1.dishes.080`

**Anju**: It's the shape of chicken. `n1.dishes.090`

**Lena**: I could ask the supply office about your rations. `n1.dishes.100`

**Theo**: Ask them what? `n1.dishes.110`

**Lena**: There are forms. I'll fill them in. `n1.dishes.120`

**Theo**: Forms. `n1.dishes.130`

**Kaie**: Let her try, Fox. `n1.dishes.140`

**Lena**: How was today? For you, I mean. Not the report. `n1.dishes.150`

**Theo**: Loud. `n1.dishes.160`

**Kaie**: Fox got sand in his cockpit and told us about it all the way home. `n1.dishes.170`

**Theo**: It's still in there. `n1.dishes.180`

**Lena**: Undertaker, are you there? `n1.dishes.190`

**Shin**, the player picks one:

- Here. `n1.dishes.200`
- Undertaker. `n1.dishes.210`
- *(says nothing)* ... `n1.dishes.220`

**Kaie**: How old are you, Handler One? `n1.dishes.230`

**Lena**: Sixteen. `n1.dishes.240`

**Kaie**: Same as us. `n1.dishes.250`

**Lena** *(after a pause)*: I'll be on the link at seven. Good night. `n1.dishes.260`

*The link closes.*

**Theo** (at the base): Twenty-two minutes. `n1.dishes.270`

**Kaie**: Is that a lot? `n1.dishes.280`

**Theo**: The last one never called at all. `n1.dishes.290`

## M2 · Spearhead

*Act I · the game's mission frontier_sweep · map big_map · light overcast_morning · about 30 minutes*

A big attack wave; the bridge; Shin alone against the heaviest units while Lena watches (canon, episode 2). Then the history class on her console.

### 0:00 · Briefing

*Tone: wall. Starts on: the mission starts (a trigger the runner does not have yet).* `m2.brief`

*Overcast morning. HQ's broadcast, then Lena: still on her script, but quicker.*

**HQ** (broadcast): Defence Headquarters wishes every sector a calm, productive week. `m2.brief.010`

**HQ**: Casualty figures for the eastern front remain at zero. `m2.brief.020`

**Lena**: Spearhead, Handler One. Command expects a Legion probe today. `m2.brief.030`

**Shin**: It's not a probe. `m2.brief.040`

**Lena**: How do you know? `m2.brief.050`

*Shin does not answer.*

**Raiden**: He's usually right, Handler One. You get used to it. `m2.brief.060`

**Lena**: Then all units, prepare for a full attack. `m2.brief.070`

### 1:00 · Scouts on the farm track

*Tone: fight. Starts on: wave 1 starts.* `m2.scouts`

**Shin**: Farm track. Two. More behind them. `m2.scouts.010`

**Lena**: I don't have anything on the track yet. `m2.scouts.020`

*Thirty seconds later the markers appear on her map.*

**Lena**: I have them now. Two scouts on the farm track. `m2.scouts.030`

### 7:00 · The pack over the hills

*Tone: fight. Starts on: wave 2 starts.* `m2.hills`

**Kurena**: Pack coming over the western hills. Nine hundred. `m2.hills.010`

**Lena**: Three Grauwolves. They're tracking you; they know where you are. `m2.hills.020`

**Raiden**: Then we stop being there. Move. `m2.hills.030`

**Daiya**: Moving. Snow Witch, with me. `m2.hills.040`

**Anju**: With you. `m2.hills.050`

### 15:00 · The Ash river bridge

*Tone: fight. Starts on: wave 3 starts.* `m2.bridge`

*The optional objective: the bridge comes down only through real hits on its bearings.*

**Lena**: Column on the Ash river bridge. Three Grauwolves, mid-span. `m2.bridge.010`

**Daiya**: Can we drop it on them? `m2.bridge.020`

**Raiden**: Gunslinger. The bearings on the near pier. `m2.bridge.030`

**Kurena**: Near pier. Six hundred. Give me ten seconds. `m2.bridge.040`

**Lena**: That bridge is listed as Republic infrastructure. `m2.bridge.050`

**Theo**: So's my Juggernaut, apparently. `m2.bridge.060`

**Lena** *(a pause)*: I'll log it as Legion damage. `m2.bridge.070`

**Daiya**: [if bridge_dropped: yes] There it goes. `m2.bridge.080`

**Kaie**: [if bridge_dropped: yes] And them with it. `m2.bridge.090`

**Raiden**: [if bridge_dropped: no] Bridge held. Fine. The slow way, then. `m2.bridge.100`

### 22:00 · The heaviest units

*Tone: fight. Starts on: wave 4 starts.* `m2.finale`

**Shin**: Löwe. Lake road. `m2.finale.010`

**Shin**: Werewolf, the road. I'll take it. `m2.finale.020`

**Raiden**: Alone. `m2.finale.030`

**Shin**: Yes. `m2.finale.040`

**Raiden**: Don't be long. `m2.finale.050`

**Lena**: Undertaker, you're leaving your squad. `m2.finale.060`

*Undertaker goes in alone. On her map his marker closes on the Löwe; the two from the shore turn after him.*

**Lena**: Two coming round the east shore, Undertaker. `m2.finale.070`

*One by one the Legion markers go out. A long silence.*

**Lena**: How did you do that? `m2.finale.080`

**Shin**: Returning. `m2.finale.090`

**Theo** *(off the link)*: She'll ask again. `m2.finale.100`

**Raiden** *(off the link)*: She will. `m2.finale.110`

### 30:00 · After: the history class

*Tone: wall. Starts on: the mission is won (a trigger the runner does not have yet).* `m2.class`

*Lena's console, that afternoon. She has been asked to cover a history class for the Handler course. The slides come first.*

**Course office** (on the console): Handler course. Modern history, lesson six: the Eighty-Sixth Sector. `m2.class.010`

**Course office**: In the war's first year, citizens of foreign descent were moved beyond the Gran Mur for their own safety. `m2.class.020`

**Course office**: Since the autonomous Juggernaut entered service, the Republic has not lost a single citizen in battle. `m2.class.030`

**Course office**: For discussion: why is the Republic's way of war the most humane in history? `m2.class.040`

**Lena** *(her draft note to the course office)*: Note on slide three: the Juggernaut is not autonomous. It has a pilot. `m2.class.050`

**Course office**: Thank you for covering the class, Major. Please teach from the approved slides. `m2.class.060`

**Lena**: Note on slide three withdrawn. `m2.class.070`

## N2 · Night talk: The footnote

*after M2*

Lena on the history class; Kaie gets curious [new].

### 0:00 · The footnote

*Tone: base. Starts on: after m2 (a trigger the runner does not have yet).* `n2.footnote`

*Night. The roof of the barracks, the sky over the wall. The Para-RAID chimes.*

**Lena**: Good evening. I taught a class today. History, for Handler recruits. `n2.footnote.010`

**Kaie**: Whose history? `n2.footnote.020`

**Lena**: The Republic's. The approved one. `n2.footnote.030`

**Kaie**: Are we in it? `n2.footnote.040`

**Lena** *(a pause)*: In a footnote. `n2.footnote.050`

**Kaie**: What does the footnote say? `n2.footnote.060`

**Lena**: That the front is held by unmanned drones. `n2.footnote.070`

**Theo**: That's me. Unmanned. `n2.footnote.080`

**Daiya**: Barely manned, Fox. `n2.footnote.090`

**Kaie**: Did anyone ask anything? `n2.footnote.100`

**Lena**: One recruit asked who repairs the drones. `n2.footnote.110`

**Kaie**: What did you tell her? `n2.footnote.120`

**Lena**: That I'd find out. Who does? `n2.footnote.130`

**Kaie**: Lev. And us, when Lev's asleep. `n2.footnote.140`

**Kaie**: What's the city like at night? Are there lights? `n2.footnote.150`

**Lena**: Streetlights. The trams run until midnight. `n2.footnote.160`

**Kaie**: Trams. `n2.footnote.170`

**Kaie**: I rode one once, I think. I must have been five. `n2.footnote.180`

**Lena** *(after a silence)*: Undertaker. This morning you said it wasn't a probe. How did you know? `n2.footnote.190`

**Shin**, the player picks one:

- Experience. `n2.footnote.200`
- It never is. `n2.footnote.210`
- *(says nothing)* ... `n2.footnote.220`

**Lena**: All right. Good night, everyone. Good night, Kirschblüte. `n2.footnote.230`

**Kaie**: Night, Handler One. `n2.footnote.240`

**Anju**: Good night. `n2.footnote.250`

*The link closes.*

**Daiya** (at the base): That's three nights running. `n2.footnote.260`

**Kaie**: She talks back. Most of them never did. `n2.footnote.270`

## Combat calls

The radio picks one of these when the event happens in a fight: a line whose missions and conditions match and that has not played in the last 3 minutes. Story lines above cut in over them; a call never cuts a story line.

### contact_heard: Shin hears Legion before anything is in sight (setup 4).

*About every 90 s in a fight; at least 2 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | They're coming. | M0, M1, M2 |  | `contact_heard.shin.1` |
| Shin | More of them. Out of sight. | M0, M1, M2 |  | `contact_heard.shin.2` |
| Shin | Contact. Closing. | M0, M1, M2 |  | `contact_heard.shin.3` |
| Shin | Something heavy. | M0, M1, M2 |  | `contact_heard.shin.4` |
| Shin | They're going round us. | M0, M1, M2 |  | `contact_heard.shin.5` |
| Shin | Wait. More coming. | M0, M1, M2 |  | `contact_heard.shin.6` |

### contact: Legion seen.

*About every 45 s in a fight; at least 4 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Contact. | M0, M1, M2 | after_death: no | `contact.shin.1` |
| Shin | There. | M0, M1, M2 | after_death: no | `contact.shin.2` |
| Raiden | Werewolf, contact. | M0, M1, M2 | after_death: no | `contact.raiden.1` |
| Raiden | Movement. Eyes up. | M0, M1, M2 | after_death: no | `contact.raiden.2` |
| Theo | Fox, contact. I see it. | M0, M1, M2 | after_death: no | `contact.theo.1` |
| Kurena | Contact. Lining it up. | M0, M1, M2 | after_death: no | `contact.kurena.1` |
| Kurena | More of them. Far out. | M0, M1, M2 | after_death: no | `contact.kurena.2` |
| Anju | Snow Witch. Contact. | M0, M1, M2 | after_death: no | `contact.anju.1` |
| Anju | They're moving. Careful. | M0, M1, M2 | after_death: no | `contact.anju.2` |
| Kaie | Kirschblüte, contact! Out in the open. | M0, M1, M2 | after_death: no | `contact.kaie.1` |
| Kaie | I see movement! | M0, M1, M2 | after_death: no | `contact.kaie.2` |
| Daiya | Black Dog. I see them. | M0, M1, M2 | after_death: no | `contact.daiya.1` |
| Kujo | Sirius, contact. I see them. | M0 | alive: Kujo; after_death: no | `contact.kujo.1` |
| Lena | New contacts on my map. | M1, M2 | handler: lena | `contact.lena.1` |
| Lena | More markers coming your way. | M1, M2 | handler: lena | `contact.lena.2` |
| Lena | Contact report: moving fast, toward you. | M1, M2 | handler: lena | `contact.lena.3` |

### engaging: A speaker opens fire.

*About every 25 s in a fight; at least 8 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Werewolf engaging. | M0, M1, M2 | after_death: no | `engaging.raiden.1` |
| Raiden | On it. Firing. | M0, M1, M2 | after_death: no | `engaging.raiden.2` |
| Theo | Fox engaging. Going in close. | M0, M1, M2 | after_death: no | `engaging.theo.1` |
| Theo | Blades out. Watch your fire. | M0, M1, M2 | after_death: no | `engaging.theo.2` |
| Kurena | Gunslinger firing. | M0, M1, M2 | after_death: no | `engaging.kurena.1` |
| Kurena | On it. Wind's light. | M0, M1, M2 | after_death: no | `engaging.kurena.2` |
| Kurena | Holding the lead. Firing. | M0, M1, M2 | after_death: no | `engaging.kurena.3` |
| Anju | Engaging. | M0, M1, M2 | after_death: no | `engaging.anju.1` |
| Anju | Firing now. | M0, M1, M2 | after_death: no | `engaging.anju.2` |
| Anju | On them. | M0, M1, M2 | after_death: no | `engaging.anju.3` |
| Kaie | Kirschblüte firing. Heads down, Legion. | M0, M1, M2 | after_death: no | `engaging.kaie.1` |
| Kaie | Suppressing. Go. | M0, M1, M2 | after_death: no | `engaging.kaie.2` |
| Daiya | Black Dog engaging. | M0, M1, M2 | after_death: no | `engaging.daiya.1` |
| Daiya | Lobbing one in. Heads down. | M0, M1, M2 | after_death: no | `engaging.daiya.2` |
| Kujo | Sirius engaging. | M0 | alive: Kujo; after_death: no | `engaging.kujo.1` |
| Kujo | Firing! | M0 | alive: Kujo; after_death: no | `engaging.kujo.2` |

### kill: A Legion unit destroyed.

*About every 20 s in a fight; at least 9 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Down. | M0, M1, M2 | after_death: no | `kill.shin.1` |
| Shin | One less. | M0, M1, M2 | after_death: no | `kill.shin.2` |
| Raiden | Got it. | M0, M1, M2 | after_death: no | `kill.raiden.1` |
| Raiden | That one's done. | M0, M1, M2 | after_death: no | `kill.raiden.2` |
| Theo | Scrap. | M0, M1, M2 | after_death: no | `kill.theo.1` |
| Theo | Cut in half. Next. | M0, M1, M2 | after_death: no | `kill.theo.2` |
| Theo | That one won't get up. | M0, M1, M2 | after_death: no | `kill.theo.3` |
| Kurena | Hit. It's down. | M0, M1, M2 | after_death: no | `kill.kurena.1` |
| Kurena | Through the optic. Done. | M0, M1, M2 | after_death: no | `kill.kurena.2` |
| Kurena | Got it. | M0, M1, M2 | after_death: no | `kill.kurena.3` |
| Anju | It's down. | M0, M1, M2 | after_death: no | `kill.anju.1` |
| Anju | Got it. Next. | M0, M1, M2 | after_death: no | `kill.anju.2` |
| Anju | Down. | M0, M1, M2 | after_death: no | `kill.anju.3` |
| Kaie | Got one! | M0, M1, M2 | after_death: no | `kill.kaie.1` |
| Kaie | That one's done for. | M0, M1, M2 | after_death: no | `kill.kaie.2` |
| Daiya | Ha. Got it. | M0, M1, M2 | after_death: no | `kill.daiya.1` |
| Daiya | That's mine. | M0, M1, M2 | after_death: no | `kill.daiya.2` |
| Kujo | Got it! One for the board. | M0 | alive: Kujo; after_death: no | `kill.kujo.1` |
| Kujo | Down. Nice. | M0 | alive: Kujo; after_death: no | `kill.kujo.2` |
| Lena | Confirmed. | M1, M2 | handler: lena | `kill.lena.1` |
| Lena | Marker's gone. Confirmed destroyed. | M1, M2 | handler: lena | `kill.lena.2` |
| Lena | One less on my map. | M1, M2 | handler: lena | `kill.lena.3` |

### kill_long: A kill past 800 m.

*About every 90 s in a fight; at least 2 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Kurena | Down. That was a long way. | M0, M1, M2 | after_death: no | `kill_long.kurena.1` |
| Kurena | Long one. It's down. | M0, M1, M2 | after_death: no | `kill_long.kurena.2` |
| Kurena | Wind held. Got it. | M0, M1, M2 | after_death: no | `kill_long.kurena.3` |

### reloading: A speaker reloads.

*About every 30 s in a fight; at least 6 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Reloading. | M0, M1, M2 | after_death: no | `reloading.shin.1` |
| Raiden | Reloading. Cover me a second. | M0, M1, M2 | after_death: no | `reloading.raiden.1` |
| Theo | Reloading. Somebody else be useful. | M0, M1, M2 | after_death: no | `reloading.theo.1` |
| Kurena | Reloading. Cover me. | M0, M1, M2 | after_death: no | `reloading.kurena.1` |
| Anju | Reloading. | M0, M1, M2 | after_death: no | `reloading.anju.1` |
| Anju | Loading. A moment. | M0, M1, M2 | after_death: no | `reloading.anju.2` |
| Kaie | Reloading! Nearly there. | M0, M1, M2 | after_death: no | `reloading.kaie.1` |
| Daiya | Reloading. | M0, M1, M2 | after_death: no | `reloading.daiya.1` |
| Daiya | Hang on, loading. | M0, M1, M2 | after_death: no | `reloading.daiya.2` |
| Kujo | Reloading. Give me a second. | M0 | alive: Kujo; after_death: no | `reloading.kujo.1` |

### moving: A speaker moves or flanks.

*About every 40 s in a fight; at least 5 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Moving. | M0, M1, M2 | after_death: no | `moving.shin.1` |
| Shin | On me. | M0, M1, M2 | after_death: no | `moving.shin.2` |
| Shin | Flanking. | M0, M1, M2 | after_death: no | `moving.shin.3` |
| Raiden | Moving up. Keep the line. | M0, M1, M2 | after_death: no | `moving.raiden.1` |
| Raiden | Werewolf, shifting. | M0, M1, M2 | after_death: no | `moving.raiden.2` |
| Theo | Going round the back of them. | M0, M1, M2 | after_death: no | `moving.theo.1` |
| Theo | Fox moving. Don't shoot me. | M0, M1, M2 | after_death: no | `moving.theo.2` |
| Kaie | Fourth platoon moving up. | M0, M1, M2 | after_death: no | `moving.kaie.1` |
| Daiya | Black Dog moving. Snow Witch, with me. | M0, M1, M2 | after_death: no | `moving.daiya.1` |
| Kujo | Sirius moving up with Kirschblüte. | M0 | alive: Kujo; after_death: no | `moving.kujo.1` |

### covering: A speaker covers another's move.

*About every 40 s in a fight; at least 5 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Covering. | M0, M1, M2 | after_death: no | `covering.shin.1` |
| Raiden | I've got your back. Go. | M0, M1, M2 | after_death: no | `covering.raiden.1` |
| Raiden | Covering. Move. | M0, M1, M2 | after_death: no | `covering.raiden.2` |
| Theo | Go. I'll keep them busy. | M0, M1, M2 | after_death: no | `covering.theo.1` |
| Kurena | I've got the high ground. Go. | M0, M1, M2 | after_death: no | `covering.kurena.1` |
| Kurena | Covering from the ridge. | M0, M1, M2 | after_death: no | `covering.kurena.2` |
| Anju | Go. I'm covering you. | M0, M1, M2 | after_death: no | `covering.anju.1` |
| Anju | I've got your side. | M0, M1, M2 | after_death: no | `covering.anju.2` |
| Kaie | Covering fire. Go now. | M0, M1, M2 | after_death: no | `covering.kaie.1` |
| Kaie | I'll keep them pinned. | M0, M1, M2 | after_death: no | `covering.kaie.2` |
| Daiya | Go, go. I'm on them. | M0, M1, M2 | after_death: no | `covering.daiya.1` |

### hit_taken: A speaker's machine takes a light hit.

*About every 30 s in a fight; at least 6 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Took one. Fine. | M0, M1, M2 | after_death: no | `hit_taken.raiden.1` |
| Raiden | Glancing hit. Keep going. | M0, M1, M2 | after_death: no | `hit_taken.raiden.2` |
| Theo | Ow. Rude. | M0, M1, M2 | after_death: no | `hit_taken.theo.1` |
| Theo | Hit. It's nothing. | M0, M1, M2 | after_death: no | `hit_taken.theo.2` |
| Kurena | I'm hit. Still shooting. | M0, M1, M2 | after_death: no | `hit_taken.kurena.1` |
| Anju | I'm hit. It's all right. | M0, M1, M2 | after_death: no | `hit_taken.anju.1` |
| Anju | Hit. Still here. | M0, M1, M2 | after_death: no | `hit_taken.anju.2` |
| Kaie | Hit, but I'm fine. | M0, M1, M2 | after_death: no | `hit_taken.kaie.1` |
| Daiya | Hit. Just paint. | M0, M1, M2 | after_death: no | `hit_taken.daiya.1` |
| Daiya | That's another dent for Lev to shout about. | M0, M1, M2 | after_death: no | `hit_taken.daiya.2` |
| Kujo | Hit! I'm fine. Mostly. | M0 | alive: Kujo; after_death: no | `hit_taken.kujo.1` |

### hit_heavy: A heavy hit (radio.json hit_heavy).

*About every 60 s in a fight; at least 3 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Hit. Still up. | M0, M1, M2 |  | `hit_heavy.shin.1` |
| Raiden | That one hurt. Still standing. | M0, M1, M2 |  | `hit_heavy.raiden.1` |
| Theo | That one rattled my teeth. | M0, M1, M2 |  | `hit_heavy.theo.1` |
| Anju | Bad hit. I'm still moving. | M0, M1, M2 |  | `hit_heavy.anju.1` |
| Daiya | That one went in. I'm all right. | M0, M1, M2 |  | `hit_heavy.daiya.1` |
| Lena | Undertaker, that was a heavy hit. Status? | M1, M2 | handler: lena | `hit_heavy.lena.1` |
| Lena | That was a direct hit. Undertaker, report. | M1, M2 | handler: lena | `hit_heavy.lena.2` |
| Kurena | Heavy hit. Optics still good. | M0, M1, M2 |  | `hit_heavy.kurena.1` |
| Kaie | Ow! That one went in. I'm all right. | M0, M1, M2 |  | `hit_heavy.kaie.1` |
| Kujo | Hit! That was a big one. | M0 | alive: Kujo | `hit_heavy.kujo.1` |

### armour_low: Armour low (radio.json armour_low).

*About every 120 s in a fight; at least 2 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Armour's thin. Still moving. | M0, M1, M2 |  | `armour_low.shin.1` |
| Raiden | Armour's paper here. Pulling back a bit. | M0, M1, M2 |  | `armour_low.raiden.1` |
| Theo | Fox is leaking. Not dead yet. | M0, M1, M2 | after_death: no | `armour_low.theo.1` |
| Anju | My armour's going. Staying close to you. | M0, M1, M2 |  | `armour_low.anju.1` |
| Lena | Undertaker, your armour readout is low. | M1, M2 | handler: lena | `armour_low.lena.1` |
| Lena | Your machine is in the red. Please pull back. | M1, M2 | handler: lena | `armour_low.lena.2` |
| Kurena | Armour's going. Shooting from further back. | M0, M1, M2 |  | `armour_low.kurena.1` |
| Kaie | Armour's thin. Kirschblüte pulling back a bit. | M0, M1, M2 |  | `armour_low.kaie.1` |
| Daiya | Armour's shot. Still up. | M0, M1, M2 |  | `armour_low.daiya.1` |
| Kujo | Armour's nearly gone. Still in it. | M0 | alive: Kujo | `armour_low.kujo.1` |

### ricochet: A shot bounces off Legion armour.

*About every 40 s in a fight; at least 5 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Bounced. Get a better angle. | M0, M1, M2 | after_death: no | `ricochet.raiden.1` |
| Theo | Bounced off. Of course it did. | M0, M1, M2 | after_death: no | `ricochet.theo.1` |
| Theo | Glanced off. Their plate's thicker than Werewolf's skull. | M0, M1, M2 | after_death: no | `ricochet.theo.2` |
| Kurena | Bounced. Too steep from here. | M0, M1, M2 | after_death: no | `ricochet.kurena.1` |
| Kaie | Bounced. They angle that front plate on purpose. | M0, M1, M2 | after_death: no | `ricochet.kaie.1` |
| Kujo | Bounced. Rude. | M0 | alive: Kujo; after_death: no | `ricochet.kujo.1` |

### part_leg: A Legion leg shot off.

*About every 60 s in a fight; at least 3 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Leg's off. Leave it limping. | M0, M1, M2 | after_death: no | `part_leg.raiden.1` |
| Kurena | Took its leg. It's not going anywhere. | M0, M1, M2 | after_death: no | `part_leg.kurena.1` |
| Kaie | Leg off! It's hopping. | M0, M1, M2 | after_death: no | `part_leg.kaie.1` |

### part_weapon: A Legion weapon shot off.

*About every 60 s in a fight; at least 3 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Theo | Took its gun off. Try shooting now. | M0, M1, M2 | after_death: no | `part_weapon.theo.1` |
| Kurena | Gun's off it. | M0, M1, M2 | after_death: no | `part_weapon.kurena.1` |
| Daiya | Its gun's off. Toothless. | M0, M1, M2 | after_death: no | `part_weapon.daiya.1` |

### lowe_fired: The Löwe fires (no Löwe in M0).

*About every 45 s in a fight; at least 4 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Theo | Löwe shot. That was close. | M1, M2 |  | `lowe_fired.theo.1` |
| Kurena | Löwe's ranging on us. Move. | M1, M2 |  | `lowe_fired.kurena.1` |
| Anju | Löwe's gun. Get down. | M1, M2 |  | `lowe_fired.anju.1` |
| Kaie | Löwe's shooting. Spread out. | M1, M2 |  | `lowe_fired.kaie.1` |
| Daiya | Löwe! Big gun. Move. | M1, M2 |  | `lowe_fired.daiya.1` |
| Lena | The Löwe is firing. Move, please. | M1, M2 | handler: lena | `lowe_fired.lena.1` |
| Lena | The Löwe has fired. Check in, everyone. | M1, M2 | handler: lena | `lowe_fired.lena.2` |

### wingman_hit: Someone checks on a hit squad mate.

*About every 60 s in a fight; at least 3 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | You hit? Talk to me. | M0, M1, M2 | after_death: no | `wingman_hit.raiden.1` |
| Raiden | Shake it off. You're still up. | M0, M1, M2 | after_death: no | `wingman_hit.raiden.2` |
| Theo | Still alive over there? | M0, M1, M2 | after_death: no | `wingman_hit.theo.1` |
| Anju | Are you hurt? | M0, M1, M2 | after_death: no | `wingman_hit.anju.1` |
| Anju | Pull back if you need to. I've got it. | M0, M1, M2 | after_death: no | `wingman_hit.anju.2` |
| Kaie | Still with us? | M0, M1, M2 | after_death: no | `wingman_hit.kaie.1` |
| Lena | Spearhead, someone's been hit. Report, please. | M1, M2 | handler: lena | `wingman_hit.lena.1` |
| Daiya | Snow Witch? Talk to me. | M0, M1, M2 | who: Anju; after_death: no | `wingman_hit.daiya.1` |
| Anju | Black Dog, are you all right? | M0, M1, M2 | who: Daiya; after_death: no | `wingman_hit.anju.3` |

### disabled: A wingman's machine is disabled; the pilot lives (D5).

*About every 300 s in a fight; at least 1 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Werewolf's legs are gone. I'm out. I'm fine. | M0, M1, M2 |  | `disabled.raiden.1` |
| Theo | Fox is down. Legs are scrap. I'm fine, stop asking. | M0, M1, M2 | after_death: no | `disabled.theo.1` |
| Kurena | Gunslinger's stuck. Legs are gone. I can still see, though. | M0, M1, M2 |  | `disabled.kurena.1` |
| Anju | Snow Witch is down. Legs gone. I'm all right. | M0, M1, M2 |  | `disabled.anju.1` |
| Kaie | Kirschblüte's stuck. No legs. I'm fine! | M0, M1, M2 |  | `disabled.kaie.1` |
| Daiya | Black Dog's down. Legs gone. I'm fine, really. | M0, M1, M2 |  | `disabled.daiya.1` |
| Kujo | Sirius can't move. I'm fine. Mostly. | M0 | alive: Kujo | `disabled.kujo.1` |

### wave_cleared: A wave destroyed.

*About every 180 s in a fight; at least 1 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Clear. Check your ammo. | M0, M1, M2 | after_death: no | `wave_cleared.raiden.1` |
| Raiden | That's the lot. Breathe. | M0, M1, M2 | after_death: no | `wave_cleared.raiden.2` |
| Anju | That's all of them, I think. | M0, M1, M2 | after_death: no | `wave_cleared.anju.1` |
| Daiya | That's the lot. Who's counting? | M0, M1, M2 | after_death: no | `wave_cleared.daiya.1` |
| Lena | My map is clear. For now. | M1, M2 | handler: lena | `wave_cleared.lena.1` |
| Lena | No more markers. Take a moment. | M1, M2 | handler: lena | `wave_cleared.lena.2` |

### lull: A quiet stretch: banter among the 86 (never after a death).

*About every 90 s in a fight; at least 2 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Raiden | Anyone else hungry, or just me? | M0, M1, M2 | after_death: no | `lull.raiden.1` |
| Raiden | Black Dog, if you start singing, I'm cutting the link. | M0, M1, M2 | after_death: no | `lull.raiden.2` |
| Theo | If I get sand in this cockpit again, I quit. | M0, M1, M2 | after_death: no | `lull.theo.1` |
| Theo | Who's on dishes tonight? Not me. | M0, M1, M2 | after_death: no | `lull.theo.2` |
| Theo | Black Dog, stop humming. | M0, M1, M2 | after_death: no | `lull.theo.3` |
| Kurena | Wind's picking up. Worse tonight. | M0, M1, M2 | after_death: no | `lull.kurena.1` |
| Anju | Black Dog, did you leave the stove on? | M0, M1, M2 | after_death: no | `lull.anju.1` |
| Anju | It's pretty out here, when it's quiet. | M0, M1, M2 | after_death: no | `lull.anju.2` |
| Kaie | Look at the poppies on that slope. | M0, M1, M2 | after_death: no | `lull.kaie.1` |
| Kaie | If we're back early, I'm first in the bath. | M0, M1, M2 | after_death: no | `lull.kaie.2` |
| Daiya | When we get back, I'm sleeping for a week. | M0, M1, M2 | after_death: no | `lull.daiya.1` |
| Daiya | Somebody remind me to feed the cat. | M0, M1, M2 | after_death: no | `lull.daiya.2` |
| Daiya | I could eat a whole block. The chicken one. | M0, M1, M2 | after_death: no | `lull.daiya.3` |
| Kujo | A hundred and twenty-eight. Twenty-seven tomorrow. | M0 | alive: Kujo; after_death: no | `lull.kujo.1` |
| Kujo | Somebody save me some of the chicken block. | M0 | alive: Kujo; after_death: no | `lull.kujo.2` |

### order: The Handler gives an order or report.

*About every 45 s in a fight; at least 4 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Lena | All units, regroup on Undertaker. | M1, M2 | handler: lena | `order.lena.1` |
| Lena | Spearhead, hold your positions, please. | M1, M2 | handler: lena | `order.lena.2` |
| Lena | Werewolf, Gunslinger, cover the others, please. | M1, M2 | handler: lena | `order.lena.3` |
| Lena | Spread out, please. You're too close together. | M1, M2 | handler: lena | `order.lena.4` |
| Lena | Undertaker, contacts closing on you. | M1, M2 | handler: lena | `order.lena.5` |
| Lena | Your sector is clear. All units, advance. | M1, M2 | handler: lena | `order.lena.6` |
| The old Handler | Proceed along your patrol route. | M0 | handler: old; after_death: no | `order.old_handler.1` |
| The old Handler | Maintain patrol speed. | M0 | handler: old; after_death: no | `order.old_handler.2` |
| The old Handler | Please keep the channel clear. | M0 | handler: old; after_death: no | `order.old_handler.3` |
| The old Handler | Logged. | M0 | handler: old; after_death: no | `order.old_handler.4` |

### ack: A Processor answers the Handler.

*About every 45 s in a fight; at least 4 lines in each mission so none repeats.*

| Who | Line | Missions | If | Id |
|---|---|---|---|---|
| Shin | Understood. | M0, M1, M2 | after_death: no | `ack.shin.1` |
| Shin | Undertaker. | M0, M1, M2 | after_death: no | `ack.shin.2` |
| Raiden | Werewolf, copy. | M0, M1, M2 | after_death: no | `ack.raiden.1` |
| Raiden | Copy that. | M0, M1, M2 | after_death: no | `ack.raiden.2` |
| Theo | Fox, copy. | M0, M1, M2 | after_death: no | `ack.theo.1` |
| Theo | Yes, Handler. Right away, Handler. | M0, M1, M2 | after_death: no | `ack.theo.2` |
| Kurena | Gunslinger, copy. | M0, M1, M2 | after_death: no | `ack.kurena.1` |
| Anju | Snow Witch, understood. | M0, M1, M2 | after_death: no | `ack.anju.1` |
| Kaie | Kirschblüte, copy. | M0, M1, M2 | after_death: no | `ack.kaie.1` |
| Daiya | Black Dog, copy. | M0, M1, M2 | after_death: no | `ack.daiya.1` |
| Kujo | Sirius, copy. | M0 | alive: Kujo; after_death: no | `ack.kujo.1` |

## Numbers

Choice lines count every option here, though only one is heard.

| Who | Story lines | Combat calls | Words |
|---|---|---|---|
| Lena | 57 | 21 | 528 |
| Raiden | 25 | 26 | 254 |
| Kaie | 24 | 21 | 239 |
| Theo | 23 | 25 | 226 |
| Daiya | 15 | 22 | 187 |
| Kurena | 9 | 24 | 169 |
| Kujo | 18 | 15 | 157 |
| Anju | 10 | 25 | 153 |
| Shin | 31 | 19 | 110 |
| Course office | 5 | 0 | 71 |
| The old Handler | 6 | 4 | 54 |
| Lev | 6 | 0 | 40 |
| HQ | 4 | 0 | 32 |
| Halberd Two | 3 | 0 | 20 |
| All | 236 | 202 | 2240 |
