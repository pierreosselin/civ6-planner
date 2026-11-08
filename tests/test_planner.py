import os
import random
import tempfile
import unittest
import zlib

from civ6_planner import dump, planner
from civ6_planner.gamemap import GameMap
from civ6_planner.rules import Rules

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


def full_map(special=None):
    """Every tile revealed; special maps (x, y) -> field overrides."""
    special = special or {}
    return make_map([tile(x, y, **special.get((x, y), {})) for y in range(H) for x in range(W)])


class GeometryTest(unittest.TestCase):
    def test_reported_neighbours_are_distance_one(self):
        gmap = full_map()
        for t in gmap:
            for n in gmap.neighbours(t):
                self.assertEqual(gmap.distance(t, n), 1, (t["x"], t["y"], n["x"], n["y"]))

    def test_distance_wraps_east_west(self):
        gmap = full_map()
        self.assertEqual(gmap.distance((0, 5), (W - 1, 5)), 1)
        self.assertEqual(GameMap({"w": W, "h": H, "turn": 1, "player": 0, "tiles": [], "cities": []},
                                 wrap_x=False).distance((0, 5), (W - 1, 5)), W - 1)


class RulesTest(unittest.TestCase):
    def test_city_spacing(self):
        gmap = full_map({(10, 6): {"is_city": 1}})
        rules = Rules(city_min_range=3)
        self.assertFalse(rules.can_found_city(gmap, gmap.tiles[(13, 6)]))  # distance 3
        self.assertTrue(rules.can_found_city(gmap, gmap.tiles[(14, 6)]))   # distance 4

    def test_district_blockers(self):
        gmap = full_map({(1, 1): {"mountain": 1}, (2, 1): {"water": 1},
                           (3, 1): {"resource": "RESOURCE_IRON"}, (4, 1): {"resource": "RESOURCE_WHEAT"}})
        rules = Rules(resource_class={"RESOURCE_IRON": "RESOURCECLASS_STRATEGIC",
                                      "RESOURCE_WHEAT": "RESOURCECLASS_BONUS"})
        allowed = {xy: rules.can_place_district(gmap, gmap.tiles[xy]) for xy in [(1, 1), (2, 1), (3, 1), (4, 1)]}
        self.assertEqual(allowed, {(1, 1): False, (2, 1): False, (3, 1): False, (4, 1): True})


class CampusTest(unittest.TestCase):
    def test_picks_most_mountains(self):
        # Put mountains on three of (11, 6)'s neighbours; no other tile touches all three.
        base = full_map()
        target = base.tiles[(11, 6)]
        mountains = {(n["x"], n["y"]): {"mountain": 1} for n in base.neighbours(target)[:3]}
        gmap = full_map(mountains)
        campus, count = planner.choose_campus(gmap, Rules(), gmap.tiles[(9, 6)], random.Random(0))
        self.assertEqual((campus["x"], campus["y"], count), (11, 6, 3))

    def test_ties_are_random(self):
        gmap = full_map({(10, 6): {"mountain": 1}})  # one mountain: its six neighbours tie
        city = gmap.tiles[(8, 6)]
        picks = set()
        for seed in range(40):
            campus, _ = planner.choose_campus(gmap, Rules(), city, random.Random(seed))
            picks.add((campus["x"], campus["y"]))
        expected = {(n["x"], n["y"]) for n in gmap.neighbours(gmap.tiles[(10, 6)])
                    if 0 < gmap.distance(city, n) <= 3}
        self.assertGreater(len(picks), 1)
        self.assertTrue(picks <= expected, picks - expected)


class SaveParsingTest(unittest.TestCase):
    def test_dump_inside_compressed_save(self):
        text = ("MAPDUMP|BEGIN|id=1-1|turn=1|player=0|w=20|h=12\n"
                "MAPDUMP|TILE|i=0|x=0|y=0|terrain=TERRAIN_PLAINS|neighbours=1,-1\n"
                "MAPDUMP|END|id=1-1|tiles=1\n")
        blob = b"CIV6header\x00" + zlib.compress(b"\x05junk" + text.encode() + b"\x00\x00tail")
        with tempfile.NamedTemporaryFile(suffix=".Civ6Save", delete=False) as f:
            f.write(blob)
        try:
            d = dump.latest_dump_from_save(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual((d["turn"], len(d["tiles"]), d["tiles"][0]["neighbours"]), (1, 1, [1, -1]))


if __name__ == "__main__":
    unittest.main()
