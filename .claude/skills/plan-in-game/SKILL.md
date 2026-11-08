---
name: plan-in-game
description: Run the planner on the user's live Civ VI game and get its tacks onto the in-game map (Ctrl+Shift+T), or check what the mod did. Use when the user is playing and wants a plan shown in game.
---

# Plan in a live game

1. **Make sure the input is current.** `plan` reads the newest `.Civ6Save` under
   `~/.local/share/aspyr-media/Sid Meier's Civilization VI/Saves/`. The autosave at the
   start of turn N holds the map dump from the start of turn N−1. For the current turn,
   ask the user to make a manual save first.
2. **Plan**:
   ```bash
   PYTHONPATH=src python3 -m civ6_planner plan              # writes Mods/mapdump/ui/mapdump_plan.lua
   PYTHONPATH=src python3 -m civ6_planner plan --dry-run    # print only
   ```
   The default planner is the MIP (`model.py`); it's deterministic and prints its
   score and HiGHS status in the notes. `--planner greedy` runs the old random stub
   (`--seed N` makes it repeatable). `watch [--planner …]` re-plans after every save.
   `clear` writes an empty plan (Ctrl+Shift+T then removes our tacks).
   The city may be anywhere in the revealed area (no travel cost is modelled yet).
3. **Place**: the user presses **Ctrl+Shift+T** in game. A status message appears:
   "Map Dump: tacks placed N, removed M, skipped K (your own tack there)". Works
   mid-game, no reload. Loading a save also places the current plan.
4. Optionally show the same plan off-game: the **view-map** skill with `view --plan`
   (same `--planner`, and `--seed` for greedy).

## Checking what happened

The mod records results in the game config, so they appear in the next save:

```bash
PYTHONPATH=src python3 - <<'EOF'
from civ6_planner import dump, paths
for line in dump.status_lines(dump.save_lines(paths.newest_save())):
    print(line)
EOF
```

Lines: `MAPDUMP|STATUS|msg=N tiles, turn T, stored in config` (dump ok),
`MAPDUMP|TACKS|msg=placed …` or `…|ERROR|msg=tacks: …`, and
`MAPDUMP|STATUS|msg=statusmessagepanel hook started` (the hook ran).

If nothing shows in game and no status lines appear: check that Map Dump is enabled in
Additional Content, that the game was restarted after any `.modinfo` change, and that
`Mods/mapdump` matches `mod/mapdump` (`python3 -m civ6_planner install-mod`).

## Tack icons

`ICON_` + a type name: `ICON_DISTRICT_CITY_CENTER`, `ICON_DISTRICT_CAMPUS`,
`ICON_DISTRICT_HOLY_SITE`, `ICON_IMPROVEMENT_FARM`, `ICON_IMPROVEMENT_MINE`, …; stock
pins like `ICON_MAP_PIN_CIRCLE`. Add new ones to the viewer's `TACK` table too.
Detailed Map Tacks (installed) shows yields and adjacency for district tacks in game,
which is a free check of the planner's numbers.
