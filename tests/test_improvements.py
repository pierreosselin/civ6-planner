"""Tile improvements."""
import unittest

from civ6_planner import model
from civ6_planner.rules import Rules
from helpers import full_map, yields


class ImprovementTest(unittest.TestCase):
    def test_placement_rules(self):
        gmap = full_map({(3, 3): {"terrain": "TERRAIN_PLAINS_HILLS"},
                         (4, 3): {"resource": "RESOURCE_STONE"},
                         (5, 3): {"feature": "FEATURE_FOREST"},
                         (6, 3): {"resource": "RESOURCE_IRON", "terrain": "TERRAIN_PLAINS_HILLS"},
                         (7, 3): {"improvement": "IMPROVEMENT_FARM"}})
        r = Rules()
        ok = lambda xy: sorted(i[12:] for i in r.improvements if r.can_place_improvement(gmap, gmap.tiles[xy], i))
        self.assertEqual(ok((2, 3)), ["FARM"])                  # bare plains
        self.assertEqual(ok((3, 3)), ["MINE"])                  # hills
        self.assertEqual(ok((4, 3)), ["QUARRY"])                # a resource: only its improvement
        self.assertEqual(ok((5, 3)), ["LUMBER_MILL"])           # a feature must be allowed
        self.assertEqual(ok((6, 3)), ["MINE"])
        self.assertEqual(ok((7, 3)), [])                        # already improved

    def test_five_per_city_on_the_best_tiles(self):
        # Plains everywhere (Farm: 1 food + the tile's 1 food); five 3-food tiles near the
        # food site: the improvements should go on those (improve the good tiles).
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        rich = [(4, 5), (6, 5), (4, 7), (6, 7), (5, 8)]
        for xy in rich:
            special[xy] = yields(food=3)
        gmap = full_map(special)
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=(), improvements=None)
        self.assertEqual(len(plan.improvements), 5)
        self.assertEqual({xy for _, xy, _ in plan.improvements}, set(rich))
        self.check_score(gmap, plan)

    def test_industrial_zone_next_to_quarry(self):
        # A stone tile near the city: the Industrial Zone (+1 production per quarry) should
        # sit next to the planned quarry.
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        special[(7, 6)] = {**special[(7, 6)], "resource": "RESOURCE_STONE"}
        gmap = full_map(special)
        rules = Rules(adjacencies={"DISTRICT_INDUSTRIAL_ZONE": [
            {"yield": "YIELD_PRODUCTION", "change": 1, "tiles": 1, "improvement": "IMPROVEMENT_QUARRY"}]})
        plan = model.optimise(gmap, rules, n_cities=1, districts=("DISTRICT_INDUSTRIAL_ZONE",),
                              improvements=("IMPROVEMENT_QUARRY",))
        [(_, iz, _)] = plan.districts
        self.assertEqual([xy for _, xy, _ in plan.improvements], [(7, 6)])
        self.assertEqual(gmap.distance(iz, (7, 6)), 1)
        self.check_score(gmap, plan, rules)

    def check_score(self, gmap, plan, rules=None):
        score, _ = model.evaluate(gmap, rules or Rules(), plan)
        cfg = plan.config
        expected = score + cfg.city_bonus * len(plan.cities) + cfg.district_bonus * len(plan.districts)
        self.assertAlmostEqual(plan.info["objective"], expected, places=6)


if __name__ == "__main__":
    unittest.main()
