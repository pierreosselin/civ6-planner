"""The hex grid and rivers."""
import unittest

from civ6_planner.gamemap import GameMap
from helpers import W, H, full_map


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


class RiverTest(unittest.TestCase):
    def test_flags_mean_the_plot_is_west_of_the_river(self):
        # (5, 6) is W of a river: the river runs between it and its east neighbour (6, 6).
        gmap = full_map({(5, 6): {"river_w": 1}})
        a, b = gmap.tiles[(5, 6)], gmap.tiles[(6, 6)]
        self.assertEqual(gmap.river_edges(a), [1])          # E edge of (5, 6)
        self.assertEqual(gmap.river_edges(b), [4])          # W edge of (6, 6)
        self.assertEqual(gmap.neighbour_at(a, 1)["x"], 6)
        # river_nw: the SE edge; river_ne: the SW edge.
        gmap = full_map({(5, 6): {"river_nw": 1, "river_ne": 1}})
        self.assertEqual(gmap.river_edges(gmap.tiles[(5, 6)]), [2, 3])

    def test_tiles_along_one_river_share_an_id(self):
        # A river along the E edges of (5, 6) and (5, 7)... joined through the tiles across.
        gmap = full_map({(5, 6): {"river_w": 1}, (5, 7): {"river_w": 1}, (15, 2): {"river_w": 1}})
        r = gmap.rivers()
        self.assertEqual(r[(5, 6)], r[(6, 6)])
        self.assertNotEqual(r[(5, 6)], r[(15, 2)])


if __name__ == "__main__":
    unittest.main()
