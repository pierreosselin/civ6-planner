# civ6-planner

Recommends Civ VI (Gathering Storm) city, district and improvement placement from the
map the player has revealed, and shows the plan in game as map tacks. The goal is an
optimiser that maximises yields under the game's placement rules. First MIP
backbone (`model.py`): one city and its Campus, maximising a placeholder objective
(site yields + Campus adjacency − covered tile). Kept simple on purpose: adjacency
between *planned* districts (other than a district's own city centre) isn't
modelled yet, because the coupling constraints made HiGHS slow.

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
  the old `greedy` stub), `model.py` (the optimiser: MIP formulation, objective
  weights, `evaluate` to score any plan), `solver.py` (small MIP modelling layer over
  HiGHS via `scipy.optimize.milp`, captures the HiGHS log), `docs/model.html` (the model's
  maths, for Live Server; update it whenever `model.py` changes), `tacks.py` (writes the plan), `dataset.py` (test maps and
  masks), `viewer.py` (HTML view), `cli.py`.
- `mod/mapdump/`: the Lua mod; `python3 -m civ6_planner install-mod` copies it to the
  game (keeps the current plan file).
- `data/maps/continents.json`, `shuffle.json`: fully revealed 74×46 maps (turn 2,
  12–13 AI/city-state cities already founded). Every tile has `revealed` and
  `resource_visible` flags from capture time.
  `*-revealed.json` (what the player had revealed) and `*-radius6.json` (radius 6
  around the player's start, visible resources only) are masked maps cut from them
  with `make-map`; their `scenario.source` names the full map.
- `results [-o DIR]` plans every map in `data/maps` and writes `results/<date-time>/`
  (git-ignored): `index.html` (tacks and notes per map, links to each map),
  `summary.json` (with scores), and per map `decisions.json`, `map.html` and
  `optimisation.log` (model settings, HiGHS log, decisions). `--planner greedy`
  runs the old stub for comparison.

Run things from the repo root with `PYTHONPATH=src` (VS Code's terminal sets it):
`python3 -m civ6_planner {plan,view,results,make-map,watch,clear,dump,install-mod} --help`.
Tests: `PYTHONPATH=src python3 -m unittest discover -s tests`. Only third-party
dependency: SciPy (for HiGHS; already installed system-wide). Add others only for a
strong reason.

Skills in `.claude/skills/`: **view-map**, **plan-in-game**, **capture-test-map**,
**mod-dev** (changing/debugging the mod). Read the relevant one before those tasks.

## Map data model

A dump is `{id, turn, player, w, h, scope, tiles: [...], cities: [...]}`;
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
- River/cliff flags cover only this plot's W, NW and NE edges; the other three edges
  are on the neighbours' flags.

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
capture the whole map (fog ignored) into the next save.

## Working conventions

- The old `Mods/MapExtractorMod` (an earlier attempt) is still installed but disabled
  in game; leave it unless Pierre asks.
- To show the viewer inside the Claude desktop app, use the preview server in
  `.claude/launch.json` (the browser pane can't open `file://` pages); see **view-map**.
- Generated pages `view*.html`, `map.json`, `*.csv` are git-ignored.
