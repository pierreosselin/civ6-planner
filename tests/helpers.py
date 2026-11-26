"""Small test maps: a 20x12 grid in the game's layout (odd rows shifted east, y north,
wrapping east-west), with every tile revealed unless a test says otherwise."""
import random

from civ6_planner.gamemap import GameMap

W, H = 20, 12


def tile(x, y, **overrides):
    t = {"i": y * W + x, "x": x, "y": y, "terrain": "TERRAIN_PLAINS", "feature": "NONE",
         "resource": "NONE", "wonder": "NONE", "district": "NONE", "owner": -1, "is_city": 0,
         "water": 0, "mountain": 0, "impassable": 0, "natural_wonder": 0}
    t.update(overrides)
    return t


def odd_r_neighbours(x, y):
    """Neighbour indices in the game's direction order (NE, E, SE, SW, W, NW), y north."""
    if y % 2:
        offsets = [(1, 1), (1, 0), (1, -1), (0, -1), (-1, 0), (0, 1)]
    else:
        offsets = [(0, 1), (1, 0), (0, -1), (-1, -1), (-1, 0), (-1, 1)]
    out = []
    for dx, dy in offsets:
        nx, ny = (x + dx) % W, y + dy
        out.append(ny * W + nx if 0 <= ny < H else -1)
    return out


def make_map(tiles):
    for t in tiles:
        t["neighbours"] = odd_r_neighbours(t["x"], t["y"])
    return GameMap({"w": W, "h": H, "turn": 1, "player": 0, "tiles": tiles, "cities": []})


MOUNTAIN = {"mountain": 1, "terrain": "TERRAIN_PLAINS_MOUNTAIN"}


def varied_map(seed=0):
    """A 10x12 island with random food/production: unlike a flat map that wraps around,
    layouts don't all tie, as on real maps (those are the solver's worst case)."""
    rng = random.Random(seed)
    sea = {"water": 1, "terrain": "TERRAIN_OCEAN"}
    return full_map({(x, y): yields(food=rng.randint(0, 3), prod=rng.randint(0, 2)) if 2 <= x < 12 else dict(sea)
                     for x in range(W) for y in range(H)})


def full_map(special=None):
    """Every tile revealed; special maps (x, y) -> field overrides."""
    special = special or {}
    return make_map([tile(x, y, **special.get((x, y), {})) for y in range(H) for x in range(W)])


def yields(food=0, prod=0):
    return {"YIELD_FOOD": food, "YIELD_PRODUCTION": prod}


CAMPUS = ("DISTRICT_CAMPUS",)

IZ = ("DISTRICT_INDUSTRIAL_ZONE",)
