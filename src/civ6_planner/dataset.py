"""Test cases and partial views of their maps.

Each test case is a folder data/<name>/ with
  map.json     the map: a full capture from a real game (the mod's Ctrl+Shift+F, then
               `dump --full`), or a masked map cut from one with `make-map`. Each tile
               keeps `revealed` and `resource_visible` from the moment of capture.
  config.toml  settings for this case, overlaid on config/default.toml (may be empty).

A scenario is such a map with most tiles hidden. It has the same shape as a regular
dump, so the planner and the viewer take it like any other map; hidden tiles are
simply absent, as they are in a real game's dump.
"""
import json
import os
import random

from . import paths
from .gamemap import GameMap

DATA_DIR = os.path.join(paths.REPO_ROOT, "data")
MAP_FILE, CONFIG_FILE = "map.json", "config.toml"
CONFIG_TEMPLATE = """# Settings for this test case, overlaid on config/default.toml.
# Set only what differs here; an empty file means the defaults. For example:
#
# [problem]
# n_cities = 2
#
# [objective.weights]
# science = 2.0
"""


def cases():
    """Names of the test cases: folders in data/ holding a map.json."""
    return sorted(n for n in os.listdir(DATA_DIR) if os.path.isfile(os.path.join(DATA_DIR, n, MAP_FILE)))


def map_path(name_or_path):
    """map.json of a case name, a case folder, or a map JSON path as given."""
    if os.path.isdir(name_or_path):
        return os.path.join(name_or_path, MAP_FILE)
    if os.path.exists(name_or_path):
        return name_or_path
    return os.path.join(DATA_DIR, name_or_path, MAP_FILE)


def config_path(name_or_path):
    """The case's config.toml next to its map.json, or None if it has none."""
    path = os.path.join(os.path.dirname(map_path(name_or_path)), CONFIG_FILE)
    return path if os.path.exists(path) else None


def load_map(name_or_path):
    """A map JSON by case name (data/<name>/map.json), case folder, or path."""
    with open(map_path(name_or_path)) as f:
        return json.load(f)


def save_case(name, d):
    """Write data/<name>/map.json, and an empty config.toml if there isn't one yet."""
    folder = os.path.join(DATA_DIR, name)
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, MAP_FILE), "w") as f:
        json.dump(d, f, separators=(",", ":"))
    if not os.path.exists(os.path.join(folder, CONFIG_FILE)):
        with open(os.path.join(folder, CONFIG_FILE), "w") as f:
            f.write(CONFIG_TEMPLATE)
    return folder


def source_of(d):
    """The full map a masked map was cut from (to show its hidden tiles), or None."""
    name = (d.get("scenario") or {}).get("source")
    return load_map(name) if name else None


def player_centre(full):
    """(x, y) of the middle of what the player had revealed at capture: the revealed
    tile closest to all the others (test maps have no player city yet)."""
    gmap = GameMap({**full, "cities": []})
    shown = [t for t in gmap if t.get("revealed", 1)]
    best = min(shown, key=lambda t: (max(gmap.distance(t, s) for s in shown),
                                     sum(gmap.distance(t, s) for s in shown)))
    return best["x"], best["y"]


def mask(full,mode="blob", size=60, centre=None, seed=None, resources="all"):
    """A scenario from a full map.

    mode:
      "blob"     – `size` tiles grown at random outwards from the centre, like an
                   explored area (the default).
      "radius"   – every tile within `size` of the centre.
      "revealed" – exactly the tiles the player had revealed when the map was captured.
    centre: (x, y), or a random land tile.
    resources: "all" keeps every resource on shown tiles; "visible" keeps only those
               the player's techs showed at capture time.
    """
    rng = random.Random(seed)
    gmap = GameMap({**full, "cities": []})

    start = None
    if mode == "revealed":
        shown = [t for t in full["tiles"] if t.get("revealed", 1)]
    else:
        if centre:
            start = gmap.tiles[tuple(centre)]
        else:
            start = rng.choice([t for t in gmap if not t["water"] and not t["mountain"]])
        if mode == "radius":
            shown = [t for t in gmap if gmap.distance(start, t) <= size]
        elif mode == "blob":
            shown = _grow_blob(gmap, start, size, rng)
        else:
            raise ValueError(f"unknown mode {mode!r}")

    def view(t):
        t = dict(t, revealed=1)
        if resources == "visible" and not t.get("resource_visible", 1):
            t["resource"], t["resource_count"] = "NONE", 0
        return t

    return {
        "id": f"{full.get('id', 'map')}-{mode}-{size}-{seed}",
        "turn": full["turn"], "player": full["player"], "w": full["w"], "h": full["h"],
        "scope": "revealed", "tiles": [view(t) for t in shown], "cities": [],
        "scenario": {"mode": mode, "size": size, "seed": seed, "resources": resources,
                     "centre": [start["x"], start["y"]] if start else None},
    }


def _grow_blob(gmap, start, size, rng):
    """Random frontier growth: repeatedly reveal a random tile bordering the shown area."""
    shown = {start["i"]: start}
    frontier = list(gmap.neighbours(start))
    while frontier and len(shown) < size:
        t = frontier.pop(rng.randrange(len(frontier)))
        if t["i"] not in shown:
            shown[t["i"]] = t
            frontier += [n for n in gmap.neighbours(t) if n["i"] not in shown]
    return list(shown.values())
