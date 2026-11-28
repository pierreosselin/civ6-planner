# civ6-planner

Recommends Civ VI (Gathering Storm) city, district and improvement placement from the
map the player has revealed, and shows the plan in game as map tacks. The core is a
mixed-integer programme (MIP, `model/`, solved with HiGHS) that maximises weighted
yields under the game's placement rules, read from the game's own database. Public repo:
github.com/pierreosselin/civ6-planner (MIT), so commit nothing private.

Owner: Pierre. Plays on the **native Linux (Aspyr) port under Steam**, Wayland session.
Prefers developing without the game open, using the test maps and the HTML viewer.
Prefers a simple model that solves fast over a complete one that's slow (see "Changing
the optimiser"). Commits and pushes only when he asks.

## The model in brief

Full maths, kept in step with the code: `docs/model.html` (constraints numbered (1)–(14)).

- **Cities**: as many new ones as fit (`n_cities = "max"`), more than 3 tiles from any
  city (clique constraints, which made the full maps solvable), from the best
  `max_city_candidates` sites by site value (400; the full maps' configs use all sites).
- **Districts** per city (new, and the player's existing cities get the ones they lack):
  Campus, Industrial Zone, Commercial Hub, Holy Site, Theater, Encampment, Harbor (coast),
  Aqueduct (next to the centre and fresh water), Dam (floodplains with a river on 2+
  edges, one per river), Entertainment Complex. At most 3 specialty districts per city
  (`max_specialty_districts`, the game's population limit; Aqueduct and Dam don't count),
  so the weights decide which ones.
- **Amenities and the Colosseum** (planned jointly): the Colosseum (`problem.wonders`, a
  world wonder: `k[b,t]`, one per world) goes on flat land next to one city's
  Entertainment Complex and gives +2 amenities to every city within 6 tiles. `a[c]`
  counts a city's amenities from districts (Entertainment Complex +1, Dam +1) and wonders,
  up to `amenities_needed` (2), each worth `amenity_value` (4, placeholder). The
  Entertainment Complex gets no district bonus (`no_bonus_districts`), so it's built only
  where it pays: on the test maps a single one, the Colosseum's. Only the
  `wonder_candidates` (1) tile(s) with the most city sites within 6 are variables: with
  all 481 on continents the root LP didn't finish in 60 s (no plan at all); with 10 the
  time-limited maps ended 24–29% from optimal without a Colosseum; with 1 they end where
  they did before (small maps: 10 gains at most 8 points).
- **Improvements** (Farm, Mine, Quarry, Plantation, Camp, Pasture, Fishing Boats, Lumber
  Mill): up to 5 per city, each worth its gain plus the tile's own yields (an improved
  tile is worked); only each city's 6 best options are variables (all of them made the
  full maps hit the time limit).
- **Objective**: site yields + district adjacency − covered tiles + improved tiles +
  bonuses between a city's own planned districts (`y`: Industrial Zone next to
  Aqueduct/Dam, Commercial Hub next to Harbor) and between its district and its planned
  improvements (`q`: Industrial Zone next to quarries/mines/lumber mills), plus a
  placement bonus per city (100) and district (10). Food, production and science weighted
  2, the rest 0.5 (placeholders).
- **Not modelled on purpose**: other adjacency between *planned* districts and wonders
  ("+1 per 2 districts", Theater +2 per wonder, across cities), because general coupling
  constraints made HiGHS slow; tile ownership (checked after solving by `validate.py`);
  wonders other than the Colosseum (their placement rules aren't all read: river, coast,
  mountain; `WonderRule.requires`); amenities from luxuries and buildings.
- **Optional, off by default**: *regional buildings* (`objective.regional_buildings`, e.g.
  `["BUILDING_FACTORY"]`: +3 production to every city within 6 tiles of an Industrial
  Zone, across cities): `r`/`on` variables, constraint `regional_reach`. On, continents,
  shuffle and shuffle-radius18 end 7–30% from optimal at 60 s with worse plans, and every
  city is reached anyway on the test maps (commenting out `regional_reach` alone restores
  the times). A start from the plan without it would fix that (needs highspy back:
  scipy can't pass a start).

**Solve times** (60 s limit, 2026-11-26, with the Colosseum): revealed maps 4–11 s,
radius-6 6–13 s, continents-radius18 56 s, all optimal; shuffle-radius18, continents and
shuffle hit the limit at gaps 1.35%, 5.1%, 21%. That day's machine was slower: the
previous version (no Colosseum) ended them at 1.5%, 8%, 18% against 1.3%, 0.07%, 0.33%
the day before, so compare runs from the same day (time-limited gaps vary between runs).

## Status (2026-11-26)

- Timing (when each city and district comes) was removed on 2026-11-26 (Pierre's
  decision; to be redone later). The last version (periods, settler schedule, build rate,
  border delays, where/when/joint stages through highspy, yield curves) is in git
  history: commit a15a44f and before.
- Regional buildings: off; open choice between a warm start and leaving it off.
- In game, placing a 142-tack plan (16 cities) seemed to freeze the game after
  Ctrl+Shift+T (probably Detailed Map Tacks recomputing for each tack). Not fixed; the
  proposed fix is fewer tacks in game (no improvement tacks, only what is due soon).
- Entertainment Complex and Colosseum added 2026-11-26 (amenities, constraints (12)–(14)).
- Next topic: more wonders (read the remaining placement rules first).
- Ideas discussed, not started: an expansion rule (new cities within 6–8 tiles of an
  earlier one), an LLM around the optimiser (explaining plans by re-solving what-if
  questions; tuning the objective's weights from a player's feedback by inverse
  optimisation), a simulator to measure plans in game terms.

## Code map: `model/`

- `plan.py`: `Plan` (the result: `cities`, `districts`, `improvements` and `wonders` as
  (type, tile, city), `info` with solver status, `config`; `planned()`, `improved()`),
  `CITY_CENTER`, `WONDER`.
- `values.py`: `site_value`, `improvement_value`, `covered_value`, `wonder_value`, `regional_value`.
- `existing.py`: what the player already has (cities and their districts, improvements,
  wonders, and the amenities those give: `existing_amenities`).
- `instance.py`: `Instance` (candidate sites, district tiles `spots`, improvement options
  `ispots`, wonder tiles `wspots` with the (city, district tile) pairs that may build
  each, and the variables once created: `x` cities, `z` districts, `y`, `w`
  improvements, `q`, `r`/`on`, `k` wonders, `a` amenities).
- `preprocess.py`: `prepare()` builds the Instance (`city_sites`, `district_spots`,
  `improvement_options`, `wonder_spots`).
- `formulation/`: one file per feature holding its variables, constraints and objective
  terms (`cities`, `districts`, `district_rules`, `tiles`, `neighbour_bonus`,
  `improvements`, `improvement_bonus`, `regional`, `wonders`, `amenities`); `__init__.py`
  registers them in the
  `VARIABLES`, `CONSTRAINTS`, `OBJECTIVE` lists and `build()` runs them, logging what
  each adds.
- `solve.py`: `optimise()` (prepare, build, solve), `postprocess.py`: `read_plan`.
- `evaluate.py`: `evaluate(gmap, rules, plan)` scores any plan in plain Python (the MIP's
  or the greedy stub's), bonuses left out, returning (score, parts); `regional_cover`,
  `city_amenities`.
  Tests require MIP objective = evaluate + bonuses.
- `solver.py` (outside the package): `Model` (`var`, `row`, `add_obj`), solved through
  `scipy.optimize.milp`; `capture.py` captures HiGHS's log.

## How the pieces fit

```
Civ VI + mod/mapdump ──(dump stored in game config → every save)──▶ civ6_planner
        ▲                                                              │ plan
        └── Ctrl+Shift+T re-reads Mods/mapdump/ui/mapdump_plan.lua ◀───┘
```

- `src/civ6_planner/`: `dump.py` (read `MAPDUMP|…` records from saves), `gamemap.py`
  (hex grid), `rules/` (rules from the game DB: `tables.py` types and defaults,
  `database.py`, `placement.py` (incl. `can_place_wonder`), `adjacency.py`, the `Rules`
  class in `rules.py`),
  `planner.py` (decisions: `mip` or the old stub in `greedy.py`; tacks and notes),
  `model/` (the optimiser, see the code map above), `config.py` (loads the settings),
  `solver.py` (small MIP modelling layer over HiGHS via `scipy.optimize.milp`),
  `capture.py` (captures the HiGHS log), `tacks.py` (writes the plan), `dataset.py`
  (test maps and masks), `viewer.py` + `viewer.html` (HTML view; the page is a template
  file), `results.py` + `results_page.py` (results folders and their index page),
  `metrics/` (plan and map statistics for the logs, and their text), `validate.py`
  (checks a plan against rules the model leaves out), `paths.py` (the game's folders;
  override with `CIV6_USER_DIR`), `cli/` (`__init__.py` the parser, `maps.py` which map
  and settings, `commands.py` one function per command). Keep files short: a few
  functions each, split by topic. Tests: `tests/test_<area>.py` (geometry, rules,
  greedy, solver, optimiser, regional, improvements, amenities, validate, data, config), sharing
  the small maps in `tests/helpers.py`.
- `config/default.toml`: every model and solver parameter (cities and districts to
  plan, yield weights, bonuses, site radius, loss factor, HiGHS options). `--config FILE`
  on plan/watch/view/results overlays a file that sets only what it changes (e.g.
  `config/science.toml`; an empty file means all defaults). Order: default.toml, then the
  test case's `config.toml`, then `--config`; unknown keys are an error,
  except in `[solver]`, which passes any `scipy.optimize.milp` option. New parameters go in
  default.toml and `config.Config`, not as constants in code.
- `docs/model.html`: the model's maths (KaTeX), for Pierre's Live Server
  (`http://127.0.0.1:5500/docs/model.html`; when that isn't running,
  `python3 -m http.server 8765 --bind 127.0.0.1` from the repo root and
  `http://127.0.0.1:8765/docs/model.html`). Keep it in step with `model/`.
  `docs/mip-solving.html` and `docs/solver-log.html` explain MIP solving and how to read
  HiGHS's log.
- `mod/mapdump/`: the Lua mod; `civ6-planner install-mod` copies it to the
  game (keeps the current plan file).
- `data/<case>/`: one test case per folder, `map.json` + `config.toml` (settings for
  that case over `config/default.toml`; empty templates except `continents`, `shuffle` and
  `shuffle-revealed`, which set `max_city_candidates = 1000`: all legal sites; on
  continents 710 sites, 88 cities, hits the 60 s limit).
  `--map <case>` uses both. `continents`, `shuffle`: fully revealed 74×46 maps
  (turn 2, 12–13 AI/city-state cities already founded); every tile has `revealed`
  and `resource_visible` flags from capture time. `*-revealed` (what the player had
  revealed) and `*-radius6` / `*-radius18` (radius 6 / 18 around the player's start, visible
  resources only; both radius-18 maps hit the 60 s limit) are masked maps cut from them with `make-map`; their `scenario.source` names
  the full map's case.
- `results [-o DIR]` plans every test case in `data/` and writes `results/<date-time>/`
  (git-ignored): `index.html` (tacks and notes per case, links to each map),
  `summary.json` (with scores and settings), and per case `config.toml` (the complete
  settings used; `--config` on it repeats the run), `decisions.json`, `map.html` and
  `optimisation.log`: the run in five stages, printed live to the console unless `-q`
  ([1/5] map statistics (`metrics.map_summary`: tiles, land/water, terrain, features,
  rivers, resources, cities, tacks, rules), [2/5] candidates, [3/5] each variable/
  constraint/objective function with the counts it adds, [4/5] HiGHS's log streamed as
  it solves (through a pseudo-terminal, `solver._capture_stdout`), [5/5] score, compact
  metrics incl. city spacing, a validation of the solution against rules the model
  leaves out (`validate.py`: tiles next to another city's centre, which that city claims
  when founded; tiles another of your cities owns; range; shared tiles; spacing), and
  where to open the map). `run.log` in the run folder holds exactly what the
  terminal showed for the whole run. Individual placements are in `decisions.json` and
  `index.html`, not the log (the map page shows only the map and its legend). `--planner greedy`
  runs the old stub for comparison.

Environment: a uv virtualenv in `.venv` (git-ignored; `uv.lock` is committed). Set up
or refresh with `uv sync`; it installs the package editable, so no `PYTHONPATH` is needed.
Pierre activates it (`source .venv/bin/activate`; VS Code picks `.venv/bin/python`).
In Claude's shell, which isn't activated, prefix commands with `uv run` (or call
`.venv/bin/civ6-planner`). Run from the repo root:
`civ6-planner {plan,view,results,make-map,watch,clear,dump,install-mod} --help`.
Tests: `uv run python -m unittest discover -s tests`. Dependencies live in
`pyproject.toml` (add with `uv add <pkg>`, which updates `uv.lock`); currently
SciPy (HiGHS via `scipy.optimize.milp`; highspy was removed with timing, add it back
for a starting plan). Pierre expects to add more (other solvers,
libraries); keep each one justified.

Skills in `.claude/skills/`: **view-map**, **plan-in-game**, **capture-test-map**,
**mod-dev** (changing/debugging the mod). Read the relevant one before those tasks.

## Changing the optimiser

1. Edit `model/formulation/`: one function per variable family, constraint and objective
   term, in the file of its feature (a new feature gets its own file), registered in the
   `VARIABLES`, `CONSTRAINTS` and `OBJECTIVE` lists of `formulation/__init__.py`
   (commenting a line out drops it; the log lists what was on). New candidate sets go in
   `preprocess.py`, new values in `values.py`, and `evaluate.py` must score the new term.
   Add or adjust a test in `tests/test_optimiser.py` (or the feature's test file; the
   MIP's objective must equal `evaluate()` plus the bonuses).
2. `civ6-planner results -o results/<name>` and compare `summary.json`
   scores with the previous run and with `--planner greedy`; check each
   `optimisation.log` says `Optimal` and how long it took. Look at the maps (**view-map**).
3. Update `docs/model.html` (and the size/time table) and CLAUDE.md's summary.

Pierre prefers a simple model that solves fast over a complete one that's slow: if a
formulation makes HiGHS slow (seconds on the test maps, or a time limit), simplify the
constraints or objective first and note what was left out in `model/formulation/` and
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
  `uvx mypy --ignore-missing-imports --check-untyped-defs src/civ6_planner/{model,rules,metrics} src/civ6_planner/{planner,greedy,config,solver,capture,gamemap,results,results_page,validate}.py`.

- The old `Mods/MapExtractorMod` (an earlier attempt) is still installed but disabled
  in game; leave it unless Pierre asks.
- To show the viewer inside the Claude desktop app, use the preview server in
  `.claude/launch.json` (the browser pane can't open `file://` pages); see **view-map**.
- Generated pages `/view*.html` and `/map.json` (repo root only), `*.csv` are git-ignored.
