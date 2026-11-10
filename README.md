# civ6-planner

Plans Civ VI city and district placement from the map you have revealed, and shows
the plan in game as map tacks.

```
Civ VI + Map Dump mod ──(map dump inside each save)──▶ civ6_planner plan
        ▲                                                      │
        └──── Ctrl+Shift+T places tacks ◀── mod/…/mapdump_plan.lua
```

## Current planner

The default planner is a MIP solved with HiGHS (`src/civ6_planner/model.py`): it places
as many cities as fit, each with a Campus, Industrial Zone, Commercial Hub, Holy Site,
Theater, Encampment, (on coast) Harbor, Aqueduct and Dam, and up to 5 tile improvements, to maximise the cities' site yields plus the
districts' adjacency, minus the yields of the tiles they cover. See `docs/model.html`. The first stub below is still there
as `--planner greedy`, for comparison.

Its parameters (yield weights, bonuses, cities and districts to plan, HiGHS time limit
and gap) are in `config/default.toml`. `--config FILE` overrides some of them, e.g.
`civ6-planner results --config config/science.toml`.

### Greedy stub

- **City**: a random revealed tile where a city can be founded.
- **Campus**: within 3 tiles of that city, on the tile with the best science
  adjacency from the game database (mountains, rainforest, reefs, geothermal
  fissures, other districts including the planned city). Ties are broken at random.

It decides from the latest map dump in the newest save. The autosave written at the
start of a turn holds the dump taken at the start of the previous one, the turn you
just finished.

## Usage

Set up once with [uv](https://docs.astral.sh/uv/): `uv sync` creates `.venv` with the
dependencies and the package (editable, so code changes apply at once). Then, from the
repository root:

```bash
source .venv/bin/activate     # or prefix each command with `uv run`
```

```bash
civ6-planner plan          # plan from the newest save, then press Ctrl+Shift+T in game
civ6-planner plan --dry-run --seed 1
civ6-planner watch         # re-plan automatically after every save
civ6-planner clear         # empty plan; Ctrl+Shift+T then removes the tacks
civ6-planner dump -o map.json --csv tiles.csv
civ6-planner install-mod   # copy mod/mapdump into the game's Mods folder
```

## Developing without the game

`view` writes a standalone HTML page of a map: terrain, hills, mountains, features,
resources (by class), rivers, borders, and the planner's tacks. Drag to pan, scroll to
zoom, hover for a tile's fields.

```bash
civ6-planner view --plan --open                 # newest save, with the plan
civ6-planner view --map continents-radius6 --plan --open    # a test case from data/
```

Every command that reads a map (`plan`, `view`) takes `--map NAME|FILE` instead of
the newest save, and `--mask` to hide all but part of it, so the planner can be tried
on more or less of a map:

```bash
civ6-planner view --map earth1 --mask blob --size 80 --mask-seed 3 --plan --open
civ6-planner plan --map earth1 --mask radius --size 6 --centre 30 20 --dry-run
```

- `blob`: `--size` tiles grown at random from the centre, like an explored area.
- `radius`: every tile within `--size` of the centre.
- `revealed`: exactly what the player had revealed when the map was captured.
- `--centre X Y` (default: random land), `--mask-seed N` (repeatable masks),
  `--resources visible` (drop resources the player's techs didn't show).

In the page, "Show hidden tiles" draws the masked-out part of the map faded.

### Test cases (`data/<case>/`)

Each test case is a folder with `map.json` and `config.toml` (settings for that case,
overlaid on `config/default.toml`; empty means the defaults). `--map <case>` uses both;
`results` runs every case. Full maps come from real games, captured once:

1. In game (any game you don't mind seeing in full), press **Ctrl+Shift+F**. A status
   message confirms how many tiles were captured.
2. Save the game.
3. `civ6-planner dump --full -o data/NAME/map.json` (also creates an empty `config.toml`)

Each tile keeps `revealed` and `resource_visible` from the moment of capture.

Tests: `python -m unittest discover -s tests` (or VS Code's Testing panel).

## In game

- **Ctrl+Shift+T** re-reads the plan file and places its tacks, with the result shown
  as a status message ("Map Dump: tacks placed 2, removed 2, …"). This works mid-game;
  no reload needed.
- **Ctrl+Shift+F** captures the whole map, fog ignored, into the next save (for test
  maps; see above).
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
| `src/civ6_planner/dataset.py` | test maps and masking them into partial scenarios |
| `src/civ6_planner/viewer.py` | the HTML map view |
| `data/<case>/` | test cases: `map.json` + `config.toml` |
| `config/` | default settings (`default.toml`) and example overrides |
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
