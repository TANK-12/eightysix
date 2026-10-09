# 2026-09-28 PrintForge and the Juggernaut print files (ejb-fc, Tetsu)

Emerson's asks, in order:
1. "make a stl and 3d model of the mesh images and stuff for the mech so i can make great 3d prints"
2. "just do what's best and do multiple, talk to the other session see if he can share work"
3. "make sure you dont mess with the other guys work" (ejb-a3 owns ~/Models/juggernaut/v2 and the on-screen Blender)
4. "make a stl 3d app in forge and put it in there"

Owns: `apps/printforge/` (new app), `shared/vendor/three/` (new, a copy of Cosmos's three.js r186 so
any app can use it; Cosmos itself is untouched), and `~/Models/juggernaut/print/` (print pipeline).
Reads only: `~/Models/juggernaut/v2/*.blend`.

## State
- Ask 1 (STL and 3D model for prints): done and checked. Five STLs from v2 milestone m16 in ~/Models/juggernaut/print/stl/ (statue resin 1:35 and 1:56, statue filament, base, statue on base). Filament files watertight; resin files one piece with touching edges a slicer repairs. No test print made.
- Ask 2 (do multiple; share work with the other session): done. Five variants. ejb-a3 got printcheck.py (in its cycle.py as PRINTCHECK=True) and the floating/open-piece lists, and fixed the floaters in m15/m16.
- Ask 3 (don't mess with the other session's work): done and checked. Only read v2 .blend files, headless Blender only; nothing written under ~/Models/juggernaut/v2.
- Ask 4 (STL app in Forge with the files in it): done and checked. apps/printforge; pytest 11 passed; headless screenshots looked at. Needs a Forge restart to show up.
- Not done: plug-together kit; fully watertight exact resin statue (needs about 20 GB memory, run when the machine is free).
