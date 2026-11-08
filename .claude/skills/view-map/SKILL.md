---
name: view-map
description: Draw a Civ VI map (a test map, a masked map, or the newest save) with the planner's tacks as an HTML page, or write a results folder of the planner run on every test map, and show it to the user or check it. Use whenever a map, a plan, the optimiser's decisions or a planner change should be looked at.
---

# View a map, or the planner's results

The viewer (`src/civ6_planner/viewer.py`) writes one self-contained HTML page of SVG
hexes. What a tile shows:
- fill = terrain; `^^` hills; dark triangle mountain; coloured hex outline = owner;
  white square = city, grey square = district; yellow ring = natural wonder.
- dot top-left = feature (forest, rainforest, marsh, floodplains, reef… colours in the
  legend); dot top-right = resource (green bonus, purple luxury, red strategic) with
  its name under the centre.
- bottom row = the tile's yields from the game as coloured badges, zero yields left
  out: green food, orange production, yellow gold, blue science, purple culture,
  white faith. A tacked tile adds what the planned district would give as `+n`
  badges with a white border (e.g. the Campus's science adjacency, from `Tack.yields`).
- blue edges = rivers.
- tacks: badge only, no text (red **C** city, blue **S** campus) plus a thick hex
  outline in the tack's colour. The side panel lists the tacks (click to zoom to
  one) and the planner's notes.

Hover shows every tile field; drag pans, scroll zooms; checkboxes for hidden tiles
(faded), resource labels, yields and coordinates.

## Results folder: the planner on every test map (usual way to check the optimiser)

```bash
PYTHONPATH=src python3 -m civ6_planner results -o results/demo      # default: results/<date-time>
PYTHONPATH=src python3 -m civ6_planner results --only radius6 --planner greedy --seed 3
```

It plans every map in `data/maps` and writes (git-ignored):
- `index.html`: a card per map with the tacks placed (tile, terrain, yields) and the
  planner's notes, each linking to its map;
- `<map>/map.html`: the map with the tacks; `<map>/decisions.json`: the scenario,
  tacks (with tile fields and yields), notes, score and its parts, solver stats;
  `<map>/optimisation.log`: model settings, the full HiGHS log, the decisions;
  `summary.json`: all of them, for comparing runs (e.g. before/after a planner change).
- `--planner greedy` runs the old stub instead of the MIP; both are scored by
  `model.evaluate`, so their `score`s are comparable.

## Test maps in data/maps

- `continents`, `shuffle`: full 74×46 captures (see **capture-test-map**).
- `<map>-revealed`: what the player had revealed at capture (43 tiles);
  `<map>-radius6`: radius 6 around the player's start. Both keep only resources
  visible at capture. Their `scenario.source` names the full map, so the viewer can
  show the hidden tiles faded.
- Cut new ones with `make-map` (`--at-player` centres on the middle of the revealed
  area, since the test maps have no player city yet):
  ```bash
  PYTHONPATH=src python3 -m civ6_planner make-map --map continents --mask radius --size 8 --at-player --resources visible continents-radius8
  ```
  Masks: `revealed`, `radius` (`--size` = hex radius), `blob` (`--size` tiles grown at
  random, `--mask-seed`). `--centre X Y` for a fixed centre.

## A single page

```bash
PYTHONPATH=src python3 -m civ6_planner view --map continents-radius6 --plan --seed 1 -o view.html
PYTHONPATH=src python3 -m civ6_planner view --map shuffle --mask blob --size 80 --mask-seed 3 --plan -o view.html
PYTHONPATH=src python3 -m civ6_planner view --plan -o view.html          # newest save instead of a test map
```

`--map` takes a name in `data/maps` or any dump JSON; `--mask …` masks on the fly
without saving; `--plan` runs the planner (`--planner mip|greedy`, `--seed` for greedy). Name pages `view*.html`
(git-ignored).

## Show it

- **User at their desktop**: `xdg-open <page>` (or `--open` on `view`/`results`).
  Pierre usually has VS Code Live Server on port 5500 serving the repo root:
  `http://127.0.0.1:5500/results/<run>/index.html`. Otherwise
  `python3 -m http.server 8765 --bind 127.0.0.1` from the repo root.
- **Inside the Claude desktop app** (browser pane): it can't open `file://` pages.
  Start the `viewer` preview server from `.claude/launch.json` (port 8765) with
  `preview_start`, then go to `http://localhost:8765/<page>`; `preview_stop` after.
- **Check a page yourself** (always do this after a viewer change): headless Chrome,
  then crop with PIL to zoom in, and Read the PNG:
  ```bash
  OUT=<scratchpad>
  google-chrome --headless=new --disable-gpu --no-sandbox --user-data-dir=$OUT/chrome \
    --window-size=1500,1000 --force-device-scale-factor=2 --screenshot=$OUT/page.png "file://$PWD/<page>"
  python3 -c "from PIL import Image; Image.open('$OUT/page.png').crop((700,1050,1450,1550)).save('$OUT/crop.png')"
  ```
  The page starts fitted to the shown tiles. ImageMagick isn't installed.

## Sanity checks when changing the viewer

- North is up and odd rows sit half a hex east: (22,35) must appear up-right of
  (22,34).
- River edges: corner k is at 60k−30° clockwise from east on screen, so W = corners
  3–4, NW = 4–5, NE = 5–0.
- A masked area crossing the east–west wrap must draw in one piece (the page starts
  drawing at the widest run of empty columns).
- Tile radius is `R = 32`; glyph offsets are hand-placed for it. The yield row is
  drawn above the tack layer so the tack outline doesn't hide it.
