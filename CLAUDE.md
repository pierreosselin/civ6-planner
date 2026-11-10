# civ6-planner

Recommends Civ VI (Gathering Storm) city, district and improvement placement from the
map the player has revealed, and shows the plan in game as map tacks. The goal is an
optimiser that maximises yields under the game's placement rules. The MIP
(`model.py`) places as many cities as fit (`n_cities = "max"`), each with a Campus,
Industrial Zone, Commercial Hub, Holy Site, Theater, Encampment, (on coast) Harbor,
Aqueduct (next to the centre and fresh water) and Dam (floodplains with a river on 2+
edges, one per river), and gives the player's existing cities the ones they lack.
At most 3 specialty districts per city (`problem.max_specialty_districts`; the game's
population limit, RequiresPopulation; Aqueduct and Dam don't count), so the weights
decide which ones each city gets. Bonuses between a city's own planned districts (Industrial Zone next to Aqueduct/Dam,
Commercial Hub next to Harbor) are modelled with `y` variables. Improvements (Farm, Mine,
Quarry, Plantation, Camp, Pasture, Fishing Boats, Lumber Mill; placement from the DB):
up to 5 per city, each worth its gain plus the tile's own yields (an improved tile is
worked), only each city's 6 best options kept (`problem.improvement_candidates`; all of
them made the full maps hit the time limit); Industrial Zone bonuses from planned
quarries/mines/lumber mills via `q` variables. Each run's log ends
with metrics (`metrics.py`: districts per city, share of cities with each district
type, mean adjacency per type). Tacks are named per city
("City C1", "Campus C1", "Campus Rome");
Entertainment Complex left out on purpose. Objective: site yields + district
adjacency − covered tiles + improved tiles; food, production and science weighted 2 for now
(food so cities grow enough for their districts). All test
cases solve to optimal in ~67 s in total (full maps 11–32 s; city spacing written as
clique constraints, which made that possible). Kept simple on purpose: other adjacency
between *planned* districts ("+1 per 2 districts", across cities) isn't modelled
yet, because general coupling constraints made HiGHS slow.

Owner: Pierre. Plays on the **native Linux (Aspyr) port under Steam**, Wayland session.
Prefers developing without the game open, using the test maps and the HTML viewer.

## How the pieces fit

```
Civ VI + mod/mapdump ──(dump stored in game config → every save)──▶ civ6_planner
        ▲                                                              │ plan
        └── Ctrl+Shift+T re-reads Mods/mapdump/ui/mapdump_plan.lua ◀───┘
```

- `src/civ6_planner/`: `dump.py` (read `MAPDUMP|…` records from saves), `gamemap.py`
  (hex grid), `rules.py` (rules from the game DB), `planner.py` (decisions: `mip` or
  the old `greedy` stub), `model.py` (the optimiser: MIP formulation, `evaluate` to
  score any plan), `config.py` (loads the settings), `solver.py` (small MIP modelling layer over
  HiGHS via `scipy.optimize.milp`, captures the HiGHS log), `tacks.py` (writes the
  plan), `dataset.py` (test maps and masks), `viewer.py` (HTML view), `results.py`
  (results folders), `metrics.py` (plan statistics for the logs), `cli.py`.
- `config/default.toml`: every model and solver parameter (cities and districts to
  plan, yield weights, bonuses, site radius, loss factor, HiGHS options). `--config FILE`
  on plan/watch/view/results overlays a file that sets only what it changes (e.g.
  `config/science.toml`; an empty file means all defaults). Order: default.toml, then the
  test case's `config.toml`, then `--config`; unknown keys are an error,
  except in `[solver]`, which passes any `scipy.optimize.milp` option. New parameters go in
  default.toml and `config.Config`, not as constants in code.
- `docs/model.html`: the model's maths (KaTeX), for Pierre's Live Server
  (`http://127.0.0.1:5500/docs/model.html`). Keep it in step with `model.py`.
- `mod/mapdump/`: the Lua mod; `civ6-planner install-mod` copies it to the
  game (keeps the current plan file).
- `data/<case>/`: one test case per folder, `map.json` + `config.toml` (settings for
  that case over `config/default.toml`; the six current ones are empty templates).
  `--map <case>` uses both. `continents`, `shuffle`: fully revealed 74×46 maps
  (turn 2, 12–13 AI/city-state cities already founded); every tile has `revealed`
  and `resource_visible` flags from capture time. `*-revealed` (what the player had
  revealed) and `*-radius6` (radius 6 around the player's start, visible resources
  only) are masked maps cut from them with `make-map`; their `scenario.source` names
  the full map's case.
- `results [-o DIR]` plans every test case in `data/` and writes `results/<date-time>/`
  (git-ignored): `index.html` (tacks and notes per case, links to each map),
  `summary.json` (with scores and settings), and per case `config.toml` (the complete
  settings used; `--config` on it repeats the run), `decisions.json`, `map.html` and
  `optimisation.log` (model settings, HiGHS log, decisions; also printed to the
  console unless `-q`). `--planner greedy`
  runs the old stub for comparison.

Environment: a uv virtualenv in `.venv` (git-ignored; `uv.lock` is committed). Set up
or refresh with `uv sync`; it installs the package editable, so no `PYTHONPATH` is needed.
Pierre activates it (`source .venv/bin/activate`; VS Code picks `.venv/bin/python`).
In Claude's shell, which isn't activated, prefix commands with `uv run` (or call
`.venv/bin/civ6-planner`). Run from the repo root:
`civ6-planner {plan,view,results,make-map,watch,clear,dump,install-mod} --help`.
Tests: `uv run python -m unittest discover -s tests`. Dependencies live in
`pyproject.toml` (add with `uv add <pkg>`, which updates `uv.lock`); currently only
SciPy (HiGHS via `scipy.optimize.milp`). Pierre expects to add more (other solvers,
libraries); keep each one justified.

Skills in `.claude/skills/`: **view-map**, **plan-in-game**, **capture-test-map**,
**mod-dev** (changing/debugging the mod). Read the relevant one before those tasks.

## Changing the optimiser

1. Edit `model.py`: one function per variable family, constraint and objective term,
   registered in the `VARIABLES`, `CONSTRAINTS` and `OBJECTIVE` lists (commenting a line
   out drops it; the log lists what was on). Add or adjust a test in `tests/test_planner.py` (the MIP's
   objective must equal `evaluate()` plus the bonuses).
2. `civ6-planner results -o results/<name>` and compare `summary.json`
   scores with the previous run and with `--planner greedy`; check each
   `optimisation.log` says `Optimal` and how long it took. Look at the maps (**view-map**).
3. Update `docs/model.html` (and the size/time table) and CLAUDE.md's summary.

Pierre prefers a simple model that solves fast over a complete one that's slow: if a
formulation makes HiGHS slow (seconds on the test maps, or a time limit), simplify the
constraints or objective first and note what was left out in `model.py` and
`docs/model.html`.

## Map data model

A dump is `{id, turn, player, w, h, scope, tiles: [...], cities: [...], pins: [...]}`
(`pins`: the player's own map tacks `{x, y, name, icon}`, not the mod's `[MD]` ones; the
planner places nothing on those tiles);
`scope` is `revealed` (normal) or `full` (fog ignored, test maps only).
Tile fields: `i x y revealed visible terrain feature resource resource_count
resource_visible improvement pillaged district wonder owner city is_city hills
mountain water lake coastal_land fresh_water natural_wonder impassable river river_w
river_nw river_ne cliff_w cliff_nw cliff_ne appeal continent neighbours YIELD_*`.
Type fields hold game type names (`TERRAIN_PLAINS_HILLS`, `RESOURCE_IRON`, `NONE`).

Geometry (verified against the game's own adjacency, 282/282 pairs):
- `i = y * w + x`; **y grows northwards**; **odd rows are shifted half a hex east**
  ("odd-r"). Maps wrap east–west (assumed; `GameMap(wrap_x=True)`).
- `neighbours` = plot indices in direction order 0..5 = NE, E, SE, SW, W, NW
  (-1 off map). For even y: NE=(x,y+1), NW=(x-1,y+1); odd y: NE=(x+1,y+1), NW=(x,y+1).
- River/cliff flags say which side of the river the plot is on: `river_w` (IsWOfRiver)
  = the plot is *west of* a river, so the river runs along its **E** edge; `river_nw`
  → its **SE** edge; `river_ne` → its **SW** edge. Its W, NW, NE edges are on the
  neighbours' flags (`GameMap.river_edge`). Earlier code read them as W/NW/NE edges
  (mirrored); fixed 2026-11-10, checked against `IsRiver` on every tile (0 mismatches)
  and floodplains (all touch a river).

## Rules data

`~/.local/share/aspyr-media/Sid Meier's Civilization VI/Cache/DebugGameplay.sqlite`
is the full gameplay DB, rewritten each time a game loads (so it reflects the
expansions/mods in use). Open read-only with Python's `sqlite3` (the `sqlite3` CLI
isn't installed). Useful so far: `GlobalParameters` (`CITY_MIN_RANGE`=3: new city
centre must be >3 tiles from others; `CITY_MAX_BUY_PLOT_RANGE`=3), `Resources.ResourceClassType`
(bonus/luxury/strategic/artifact), `Features.Settlement` (0 = can't found a city),
`Districts`, `District_ValidTerrains` (Campus has none: any non-mountain land),
`District_Adjacencies` + `Adjacency_YieldChanges` (adjacency bonuses, e.g.
`Mountains_Science1..5`, `District_Science`, `Jungle_Science`, `Reef_Science`,
`Geothermal_Science`). Engine rules not in the DB are written out and marked in
`rules.py` (e.g. districts can't go on luxury/strategic resources). The README lists
rules not modelled yet.

## Lessons learnt connecting to Civ VI (Linux port) — read before touching the mod

User data: `~/.local/share/aspyr-media/Sid Meier's Civilization VI/` (Mods, Saves,
Logs, Cache, AppOptions.txt). Install: `~/.local/share/Steam/steamapps/common/Sid Meier's Civilization VI/`
(game Lua/XML under `steamassets/`, all lowercase; useful references:
`steamassets/base/assets/ui/popups/mappinpopup.lua`, `ui/maptacks.lua`,
`ui/panels/statusmessagepanel.lua`). Workshop mods: `~/.local/share/Steam/steamapps/workshop/content/289070/`
(Detailed Map Tacks 2428969051 and Quick Deals 2460661464 are installed and work;
good examples of working modinfo/UI patterns).

What does **not** work on this install (each cost game restarts to establish):
- **No Lua.log**, even with `EnableTuner 1` (set in AppOptions.txt; original saved as
  `AppOptions.txt.bak`). `print()` output appears nowhere: not in Logs, not in
  Steam's `~/.local/share/Steam/logs/console-linux.txt`, not in the journal.
- **Clipboard**: `UIManager:SetClipboardString` doesn't reach the desktop clipboard.
- **The mod's own UI context** (`AddUserInterfaces`, `ui/mapdump.xml` + `mapdump.lua`)
  is applied per Modding.log but never runs. Tried: lowercase names, `ui/` subfolder,
  `CompatibleVersions`, importing the XML. Unresolved. Those files and the clipboard
  code are leftovers and can be removed.
- The Lua `io` library doesn't exist; the game can't read arbitrary files, open
  sockets or launch programs.

What **does** work:
- **`ReplaceUIScript` on `StatusMessagePanel`** (`ui/mapdump_statusmessagepanel.lua`):
  `include("statusmessagepanel")` then `include("mapdump_core")`. This is the mod's
  real entry point. The base panel only sets an input handler in debug mode, so the
  hook owns `ContextPtr:SetInputHandler` (hotkeys) and can call the panel's
  `OnStatusMessage(text, seconds, ReportingStatusTypes.DEFAULT)` for on-screen feedback.
- **Output via `GameConfiguration.SetValue(key, text)`**: the value is written into the
  next save (autosaves included). Keys are stored hashed; values appear as plain text
  or inside zlib streams. `dump.save_lines()` scans raw bytes plus every `78 9c` zlib
  stream (fed in 4 KB pieces so output before a bad chunk boundary is kept) for
  `MAPDUMP|…\n` lines. End stored values with `\n`. A 2 MB value (full map) works.
- **Input via `include()`**: it re-reads the file from disk each call, even mid-game.
  That's how Ctrl+Shift+T applies a freshly written `mapdump_plan.lua` without reload.
- **`UpdateDatabase`** components from the local mod load (verified with a probe table
  visible in DebugGameplay.sqlite).
- **Map tacks**: `PlayerConfigurations[pid]:GetMapPin(x, y)` gets *or creates* a pin;
  `:SetName`, `:SetIconName("ICON_" .. DistrictType/ImprovementType/BuildingType)`;
  `:GetMapPins()`, `:DeleteMapPin(id)`; then `Network.BroadcastPlayerInfo()`. Our
  tacks are named `[MD] …` and only those are ever moved/deleted.

Timing and reload rules:
- The mod stores a revealed-map dump at game load and at each `LocalPlayerTurnBegin`;
  the autosave is written *before* that, so the autosave at the start of turn N holds
  the dump from the start of turn N−1 (the turn just finished). `plan` uses the newest
  save.
- `.modinfo` changes (new files, components) need a **full game restart**. Lua-only
  changes apply when a save is loaded (restart if in doubt).
- Use **lowercase file names** in the mod (the port goes through a `C:/Emu/…` path
  layer on a case-sensitive FS).
- No Lua interpreter is installed locally: Lua can't be syntax-checked here, so keep
  mod edits small, wrap risky calls in `pcall`, and report errors through the save
  (`MAPDUMP|ERROR|…`, `MAPDUMP|TACKS|…`, `MAPDUMP|STATUS|…`; `plan` prints them when
  no dump is found).

Hotkeys (in game): **Ctrl+Shift+T** place tacks from the plan; **Ctrl+Shift+F**
capture the whole map (fog ignored) into the next save; **Ctrl+Shift+C** remove the
planner's tacks; **Ctrl+Shift+X** remove every tack (the player's too).

Map tacks: never delete pins inside a `GetMapPins()` loop (it crashed the game to
desktop with a few dozen pins): collect ids, then `DeleteMapPin(id)` (`RemoveTacks` in
core). Detailed Map Tacks only shows a tack's adjacency after `LuaEvents.DMT_MapPinAdded(pin)`
(its popup sends it); the mod sends that, and `DMT_MapPinRemoved` before deleting.

## Working conventions

- Type-hint function parameters, return values and dataclass fields with the real
  classes (`GameMap`, `Rules`, `Config`, `Plan`, `Model`, `Instance`), never `object`;
  shared aliases: `Tile`, `XY` (gamemap.py), `Yields` (config.py), `Var` (solver.py),
  `AdjacencyRule` (rules.py). Check with
  `uvx mypy --ignore-missing-imports --check-untyped-defs src/civ6_planner/{model,planner,config,solver,gamemap,rules,results,metrics}.py`.

- The old `Mods/MapExtractorMod` (an earlier attempt) is still installed but disabled
  in game; leave it unless Pierre asks.
- To show the viewer inside the Claude desktop app, use the preview server in
  `.claude/launch.json` (the browser pane can't open `file://` pages); see **view-map**.
- Generated pages `view*.html`, `/map.json` (repo root only), `*.csv` are git-ignored.
