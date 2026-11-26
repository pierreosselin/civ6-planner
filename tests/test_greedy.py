"""The greedy stub."""
import random
import unittest

from civ6_planner import greedy
from civ6_planner.rules import Rules
from helpers import MOUNTAIN, full_map


class CampusTest(unittest.TestCase):
    def test_picks_most_mountains(self):
        # Put mountains on three of (11, 6)'s neighbours; no other tile touches all three.
        base = full_map()
        target = base.tiles[(11, 6)]
        mountains = {(n["x"], n["y"]): MOUNTAIN for n in base.neighbours(target)[:3]}
        gmap = full_map(mountains)
        campus, count = greedy.choose_campus(gmap, Rules(), gmap.tiles[(9, 6)], random.Random(0))
        self.assertEqual((campus["x"], campus["y"], count), (11, 6, 3))

    def test_ties_are_random(self):
        gmap = full_map({(10, 6): MOUNTAIN})  # one mountain: its six neighbours tie
        city = gmap.tiles[(8, 6)]
        picks = set()
        for seed in range(40):
            campus, _ = greedy.choose_campus(gmap, Rules(), city, random.Random(seed))
            picks.add((campus["x"], campus["y"]))
        expected = {(n["x"], n["y"]) for n in gmap.neighbours(gmap.tiles[(10, 6)])
                    if 0 < gmap.distance(city, n) <= 3}
        self.assertGreater(len(picks), 1)
        self.assertTrue(picks <= expected, picks - expected)


if __name__ == "__main__":
    unittest.main()
