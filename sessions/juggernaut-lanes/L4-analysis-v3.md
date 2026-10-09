# L4: Anime analysis v3
Start line: `Read ~/Forge/sessions/juggernaut-lanes/L4-analysis-v3.md and do it.`
Read first: MASTER-PLAN.md and `refs/anime-motion/ANALYSIS.md` (Nagi's section, then "Batch 2").
The tool is `refs/anime-motion/cuts.py` (prep, detail, strip). Add to it; never rewrite others' files.

Emerson won't be finding more clips. Get more out of the footage yourself:
1. **Episode scan.** His LosslessCut projects (`*.llc` in the cuts folder) reference the full
   episodes `86 - 01.mkv` ... `86 - 09.mkv`. Find them (`find ~ -name '86 - 0*.mkv' -not -path '*/wineprefix/*'`).
   If they aren't on disk, say so in chat and work from the cuts. If they are, build a cheap
   scan (scene cuts plus one small tile per shot, like `prep`) to list every Juggernaut shot,
   especially the missing moves: a turn on the spot, a four-leg side-view walk, a gun firing
   without a cut away, blades in use.
2. **Four-leg tracking:** in the best walk and run shots, mark each foot's down and up frames
   to confirm which legs move together (Batch 2 only *assumed* diagonal pairs).
3. **Stride and speed** against the machine's own body length (stance 3.9 m long, 5.7 m wide,
   knee height 1.77 m) in side views.
4. **Blades and sub-arms** in motion (ep 1, 25.3-27.2 s in c5), and **spark and dust
   reference** for the effects (shape, colour, lifetime in frames).
5. Write `## Batch 3` in ANALYSIS.md: sure / medium / reasoned on every number, and a
   "measured / clip now / proposed" table. Post a one-line summary on the board.
Keep it cheap: overview sheets first, crops of single moves under 0.5 s, no subagents.
## Result
(write here)
