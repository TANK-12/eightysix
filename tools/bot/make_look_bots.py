#!/usr/bin/env python3
"""Writes the two look-pass bot scripts (lane LOOK): the same fixed views on each map, HUD off, so a before and
an after run can be set side by side (tools/contact_sheet.py). Views are maps.json "viewpoints" ("l_*" are the
look pass's own) plus the Juggernaut parked beside buildings. Run from the project folder.
"""

import json


def bot(name, map_id, about, views, parked):
    steps = [
        {"at": 0.5, "wait": "level"},
        {"at": 0.6, "setting": "gameplay.default_view", "value": "third"},
        {"at": 0.6, "setting": "gameplay.move_hints", "value": False},
        {"at": 0.7, "call": "show_hud", "args": [False]},
    ]
    t = 2.0
    steps.append({"at": t, "shot": "jg_spawn"})
    t += 0.8
    for key, wait in views:
        steps.append({"at": t, "call": "look_from", "args": [key]})
        t += wait
        steps.append({"at": t, "shot": key})
        t += 0.7
    steps.append({"at": t, "call": "follow_mech"})
    t += 0.3
    for call, args, label in parked:
        steps.append({"at": t, "call": call, "args": args})
        t += 3.5
        steps.append({"at": t, "shot": label})
        t += 0.7
    steps.append({"at": t + 0.5, "quit": True})
    with open(f"tools/bot/{name}.json", "w") as f:
        json.dump(
            {"name": name, "map": map_id, "_about": about, "steps": steps}, f, indent=1
        )


bot(
    "look_small",
    "small_map",
    "Lane LOOK: fixed look-pass views on Ashen valley (ground close up, street, ruins, bridge, ridges, river, lake, mast, town, overview) and the Juggernaut beside buildings. tools/bot_run.sh look_small --preset=ultra",
    [
        ("l_ground", 1.2),
        ("l_street", 1.2),
        ("l_ruins", 1.2),
        ("l_bridge", 1.2),
        ("l_ridge_n", 1.5),
        ("l_ridge_w", 1.5),
        ("river", 1.2),
        ("lake", 1.2),
        ("mast", 1.2),
        ("town", 1.2),
        ("overview", 1.5),
    ],
    [
        ("park_at", [-34, -160, 0], "jg_ruin_house"),
        ("park_at", [-38, -92, 0], "jg_ruin_block"),
    ],
)
bot(
    "look_big",
    "big_map",
    "Lane LOOK: fixed look-pass views on the big map (ground close up, Kreuzberg street and wide, Brook, the Ash bridge, a ridge, the depot, the valley) and the Juggernaut beside buildings. tools/bot_run.sh look_big --preset=ultra",
    [
        ("l_ground", 1.5),
        ("l_street", 3.5),
        ("kreuzberg", 3.5),
        ("l_brook", 3.5),
        ("brook", 3.5),
        ("depot", 3.5),
        ("bridge_side", 3.5),
        ("ford", 3.5),
        ("l_ridge", 3.5),
        ("l_ridge_n", 3.5),
        ("river_valley", 3.5),
        ("front_line", 3.5),
        ("overview", 3.5),
    ],
    [
        ("face_building", ["kreuzberg", 0, 26], "jg_kreuzberg_a"),
        ("face_building", ["kreuzberg", 2, 30], "jg_kreuzberg_b"),
        ("face_building", ["depot", 0, 28], "jg_depot"),
    ],
)


def aa_bot():
    """The same still view and the same 1.4 s of walking under each anti-aliasing mode (Ultra's choice)."""
    modes = [
        ("taa_msaa2", "taa", "2x"),
        ("msaa4", "off", "4x"),
        ("fxaa_msaa4", "fxaa", "4x"),
        ("fxaa_msaa2", "fxaa", "2x"),
        ("msaa2", "off", "2x"),
    ]
    steps = [
        {"at": 0.5, "wait": "level"},
        {"at": 0.6, "setting": "gameplay.default_view", "value": "third"},
        {"at": 0.6, "setting": "gameplay.move_hints", "value": False},
        {"at": 0.7, "call": "show_hud", "args": [False]},
    ]
    t = 2.0
    for label, aa, msaa in modes:
        steps.append({"at": t, "setting": "graphics.screen_aa", "value": aa})
        steps.append({"at": t, "setting": "graphics.msaa", "value": msaa})
        steps.append({"at": t, "call": "park_at", "args": [-38, -92, 0]})
        t += 2.5
        steps.append({"at": t, "shot": f"{label}_still"})
        steps.append({"at": t + 0.2, "measure": 2.0, "label": label})
        t += 2.6
        steps.append({"at": t, "press": "move_forward", "strength": 1.0, "for": 1.6})
        steps.append(
            {"at": t + 0.2, "press": "turn_right", "strength": 0.6, "for": 1.2}
        )
        t += 1.45
        steps.append({"at": t, "shot": f"{label}_moving"})
        t += 0.6
    steps.append({"at": t + 0.5, "quit": True})
    with open("tools/bot/look_aa.json", "w") as f:
        json.dump(
            {
                "name": "look_aa",
                "map": "small_map",
                "_about": "Lane LOOK: Ultra's anti-aliasing options on one still view and 1.4 s of walking and turning: TAA + MSAA 2x (the old Ultra), MSAA 4x alone, FXAA + MSAA 4x, FXAA + MSAA 2x, MSAA 2x alone. tools/bot_run.sh look_aa --preset=ultra; compare with tools/sharpness.py",
                "steps": steps,
            },
            f,
            indent=1,
        )


aa_bot()
