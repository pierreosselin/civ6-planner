---
name: capture-test-map
description: Add a new fully revealed test map (a test case data/NAME/) from a Civ VI game. Use when the user wants another map (a different map type or size) for developing the planner offline.
---

# Capture a test map

Test maps are full dumps (fog ignored) stored as test cases `data/NAME/map.json` (~2 MB
for a 74×46 map), each with a `config.toml` of settings for that case (empty = defaults). Two exist: `continents` and `shuffle`.

## Steps for the user

1. If the mod changed since the game was launched, restart Civ VI.
2. Start a new game with the wanted map type/size (turn 1 is fine; no need to play).
3. On the map, press **Ctrl+Shift+F**. Expect a status message
   "Map Dump: full map: 3404 tiles captured; save the game to keep them".
4. Save the game from the menu with a recognisable name.

## Then, from the repo root

```bash
ls -lt ~/.local/share/aspyr-media/"Sid Meier's Civilization VI"/Saves/Single/ | head
civ6-planner dump --full --save "<path to that save>" -o data/NAME/map.json   # also writes an empty config.toml
```

A save holding a full map is about 2 MB larger than usual. Sanity-check the result:
tile count = w × h, plausible land/mountain/river counts, then draw it with the
**view-map** skill (`view --map NAME`). Then cut the standard masked maps from it, so
`results` covers it like the others:

```bash
civ6-planner make-map --map NAME --mask revealed --resources visible NAME-revealed
civ6-planner make-map --map NAME --mask radius --size 6 --at-player --resources visible NAME-radius6
```

Commit the new maps when the user agrees.

If `dump --full` says no full map dump is in the save, it prints the mod's status lines
from the save; an `ERROR` there means the capture failed in game (see **mod-dev**).
