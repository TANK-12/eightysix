# Disk usage survey
date: 2026-10-08 · for: both

Disk: 230G, 192G used, 27G free (88%). Home ~155G, system ~37G. Measured with du/df; nothing deleted.

## Biggest users
- Steam (flatpak) 29G: Backrooms Escape Together 15G, Ultimate Epic Battle Simulator 6.3G, Proton 1.5G, compatdata 2G, two demos ~1G
- Jan models 27G: qwen3.8-27b-iq4 14G (last read 2026-09-27), Qwen3.5-9B 5.3G, 4B 3.2G, 2B-Uncensored 1.9G (last read 2026-09-02), VibeThinker-3B 1.8G (last read 2026-08-31), 0.8B 416M
- /var/lib/flatpak 20G (apps + runtimes; 6 unused 26.08 runtimes removable)
- Games/eightysix 11G, of which images/ 8G (661 check-image folders, ~130-150M each for legion_watch)
- Downloads 12G: Demon Lord 2099 4.3G, Ore wa Subete wo Parry suru 3.5G, OneDrive_1_05-09-2026 (PDFs) 2.9G, drive-download (extracted) 981M
- Chrome flatpak 9.9G: headless cache 5.1G (pure cache), headless config 1.7G, comix/panelforge fetch profiles ~1.1G
- Forge 12G: apps/ai-studio/models 3.5G, shared/assets 1.2G
- /var/cache/pacman/pkg 7.1G (paccache -rk1 would free 3.2G)
- Trash 4.6G (86 episodes, drive-download zip, ogg files)
- ~/.local/share/komikku 2.3G, ~/.cache 3.5G, coredumps 342M, AN3-backup 587M

## Cleanup done the same day
Disk went from 27G free (88%) to **81G free (64%)**, measured with df.
- Trash emptied; Jan qwen3.8-27b and VibeThinker-3B deleted (2B Uncensored kept, Forge uses it); 4 Steam games removed; 5109 leftover headless Chrome temp profiles removed; pacman cache trimmed to 1 version; unused flatpak runtimes removed.
- Automatic from now on: `~/Forge/tools/cache_trim.py` (limits in `cache_trim.json`, every 6h via forge-cache-trim.timer) and paccache.timer weekly, keeping 1 version.
