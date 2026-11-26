"""Regional buildings (the Factory)."""
import dataclasses
import unittest

from civ6_planner import config, model
from civ6_planner.rules import Rules
from helpers import W, H, full_map, yields, IZ


class RegionalTest(unittest.TestCase):
    def plan(self, **changes):
        """Two cities on 2-food tiles: an Industrial Zone loses its tile (-2) and gives no
        adjacency, so only the Factory's regional +3 production (weighted 6 per city) pays."""
        gmap, rules = full_map({(x, y): yields(food=2) for x in range(W) for y in range(H)}), Rules()
        cfg = dataclasses.replace(config.default(), district_bonus=0.0,
                                  **{"regional_buildings": ("BUILDING_FACTORY",), **changes})
        return gmap, rules, model.optimise(gmap, rules, cfg, n_cities=2, districts=IZ, improvements=())

    def test_one_industrial_zone_serves_both_cities(self):
        gmap, rules, plan = self.plan()
        self.assertEqual(len(plan.cities), 2)
        self.assertEqual(len(plan.districts), 1)
        score, parts = model.evaluate(gmap, rules, plan)
        self.assertEqual(parts["regional"], 2 * 6.0)
        self.assertEqual(sorted(model.regional_cover(gmap, rules, plan)["BUILDING_FACTORY"]), sorted(plan.cities))
        self.assertAlmostEqual(plan.info["objective"], score + 2 * plan.config.city_bonus, places=6)
        (_, t, _), = plan.districts
        self.assertTrue(all(gmap.distance(c, t) <= 6 for c in plan.cities))

    def test_off_no_industrial_zone(self):
        gmap, rules, plan = self.plan(regional_buildings=())
        self.assertEqual(plan.districts, [])
        self.assertEqual(model.evaluate(gmap, rules, plan)[1]["regional"], 0)


if __name__ == "__main__":
    unittest.main()
