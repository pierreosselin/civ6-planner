# civ6-planner

Plans Civ VI city and district placement from the map you have revealed, and shows
the plan in game as map tacks.

```
Civ VI + Map Dump mod ──(map dump inside each save)──▶ civ6_planner plan
        ▲                                                      │
        └──── Ctrl+Shift+T places tacks ◀── mod/…/mapdump_plan.lua
```

## Current planner (first iteration, no optimisation yet)

- **City**: a random revealed tile where a city can be founded.
- **Campus**: within 3 tiles of that city, on the tile with the most adjacent
  revealed mountains. Ties are broken at random.

It decides from the latest map dump in the newest save. The autosave written at the
start of a turn holds the dump taken at the start of the previous one, the turn you
just finished.

## Usage

From the repository root (VS Code's terminal sets `PYTHONPATH` for you; elsewhere
run `export PYTHONPATH=src` first, or `pip install -e .` to get a `civ6-planner`
command):

```bash
python3 -m civ6_planner plan          # plan from the newest save, then press Ctrl+Shift+T in game
python3 -m civ6_planner plan --dry-run --seed 1
python3 -m civ6_planner watch         # re-plan automatically after every save
python3 -m civ6_planner clear         # empty plan; Ctrl+Shift+T then removes the tacks
python3 -m civ6_planner dump -o map.json --csv tiles.csv
python3 -m civ6_planner install-mod   # copy mod/mapdump into the game's Mods folder
```

Tests: `python3 -m unittest discover -s tests` (or VS Code's Testing panel).

## In game

- **Ctrl+Shift+T** re-reads the plan file and places its tacks, with the result shown
  as a status message ("Map Dump: tacks placed 2, removed 2, …"). This works mid-game;
  no reload needed.
- The planner's tacks are named `[MD] …`. Only those are ever moved or removed; a tile
  holding one of your own tacks is skipped.
- Loading a save also places the current plan. Detailed Map Tacks, if enabled, shows
  the yields and adjacency of the planned tacks.

## Layout

| Path | What |
|---|---|
| `src/civ6_planner/dump.py` | reads the mod's `MAPDUMP|…` records out of saves (or Lua.log) |
| `src/civ6_planner/gamemap.py` | the revealed map: tiles, neighbours, hex distance (odd-r, east-west wrap) |
| `src/civ6_planner/rules.py` | placement rules, read from `Cache/DebugGameplay.sqlite` where possible |
| `src/civ6_planner/planner.py` | the placement decisions; the optimiser goes here |
| `src/civ6_planner/tacks.py` | writes the plan the mod reads |
| `mod/mapdump/` | the Civ VI mod (Lua); install with `install-mod` |

## Notes on the native Linux (Aspyr) port

Found while getting data out of the game; worth knowing before changing the mod:

- No `Lua.log` is ever written (even with `EnableTuner 1`), and `print()` output
  goes nowhere visible.
- `UIManager:SetClipboardString` doesn't reach the desktop clipboard.
- The mod's own UI context (`AddUserInterfaces`) never runs. The working entry point
  is `ReplaceUIScript` on `StatusMessagePanel` (`ui/mapdump_statusmessagepanel.lua`),
  which includes the original panel script and then MapDump's.
- What does work: `GameConfiguration.SetValue` (the value lands in the next save,
  partly zlib-compressed), and `include()` of a mod file re-reads it from disk, which
  is what lets Ctrl+Shift+T pick up a new plan mid-game.
- Use lowercase file names in mods.

## Rules not yet modelled

Districts: river/coast/hill requirements of other districts, geothermal fissures,
"one per city", population limits, tiles shared with other cities' districts.
Cities: the planner only sees revealed tiles, and doesn't avoid other civs' borders
beyond tile ownership.
