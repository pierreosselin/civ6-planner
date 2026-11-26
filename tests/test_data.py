"""Test maps (masks) and reading dumps out of saves."""
import os
import tempfile
import unittest
import zlib

from civ6_planner import dataset, dump
from civ6_planner.gamemap import GameMap
from helpers import W, H, full_map


class MaskTest(unittest.TestCase):
    def full(self):
        gmap = full_map({(5, 5): {"water": 1}, (6, 6): {"resource": "RESOURCE_IRON", "resource_visible": 0}})
        return {"w": W, "h": H, "turn": 1, "player": 0, "tiles": list(gmap), "cities": []}

    def test_blob_is_connected_and_sized(self):
        full = self.full()
        scenario = dataset.mask(full, "blob", size=30, centre=(10, 6), seed=1)
        gmap = GameMap(scenario)
        self.assertEqual(len(gmap), 30)
        seen, todo = set(), [gmap.tiles[(10, 6)]]
        while todo:
            t = todo.pop()
            if t["i"] not in seen:
                seen.add(t["i"])
                todo += gmap.neighbours(t)
        self.assertEqual(len(seen), 30)

    def test_blob_is_repeatable_per_seed(self):
        full = self.full()
        a = {t["i"] for t in dataset.mask(full, "blob", 25, seed=7)["tiles"]}
        b = {t["i"] for t in dataset.mask(full, "blob", 25, seed=7)["tiles"]}
        c = {t["i"] for t in dataset.mask(full, "blob", 25, seed=8)["tiles"]}
        self.assertEqual(a, b)
        self.assertNotEqual(a, c)

    def test_radius_and_resources(self):
        full = self.full()
        scenario = dataset.mask(full, "radius", 2, centre=(6, 6), resources="visible")
        self.assertEqual(len(scenario["tiles"]), 19)
        iron = [t for t in scenario["tiles"] if (t["x"], t["y"]) == (6, 6)][0]
        self.assertEqual(iron["resource"], "NONE")
        self.assertEqual(full["tiles"][6 * W + 6]["resource"], "RESOURCE_IRON")  # source untouched


class SaveParsingTest(unittest.TestCase):
    def test_dump_inside_compressed_save(self):
        text = ("MAPDUMP|BEGIN|id=1-1|turn=1|player=0|w=20|h=12\n"
                "MAPDUMP|TILE|i=0|x=0|y=0|terrain=TERRAIN_PLAINS|neighbours=1,-1\n"
                "MAPDUMP|PIN|x=0|y=0|name=2026|icon=ICON_MAP_PIN_STAR\n"
                "MAPDUMP|END|id=1-1|tiles=1\n")
        blob = b"CIV6header\x00" + zlib.compress(b"\x05junk" + text.encode() + b"\x00\x00tail")
        with tempfile.NamedTemporaryFile(suffix=".Civ6Save", delete=False) as f:
            f.write(blob)
        try:
            d = dump.latest_dump_from_save(f.name)
        finally:
            os.unlink(f.name)
        self.assertEqual((d["turn"], len(d["tiles"]), d["tiles"][0]["neighbours"]), (1, 1, [1, -1]))
        self.assertEqual(d["pins"], [{"x": 0, "y": 0, "name": "2026", "icon": "ICON_MAP_PIN_STAR"}])


if __name__ == "__main__":
    unittest.main()
