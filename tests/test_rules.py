"""Placement and adjacency rules."""
import unittest

from civ6_planner import model
from civ6_planner.rules import Rules
from helpers import W, H, MOUNTAIN, full_map


class RulesTest(unittest.TestCase):
    def test_city_spacing(self):
        gmap = full_map({(10, 6): {"is_city": 1}})
        rules = Rules(city_min_range=3)
        self.assertFalse(rules.can_found_city(gmap, gmap.tiles[(13, 6)]))  # distance 3
        self.assertTrue(rules.can_found_city(gmap, gmap.tiles[(14, 6)]))   # distance 4

    def test_district_blockers(self):
        gmap = full_map({(1, 1): MOUNTAIN, (2, 1): {"water": 1},
                           (3, 1): {"resource": "RESOURCE_IRON"}, (4, 1): {"resource": "RESOURCE_WHEAT"}})
        rules = Rules(resource_class={"RESOURCE_IRON": "RESOURCECLASS_STRATEGIC",
                                      "RESOURCE_WHEAT": "RESOURCECLASS_BONUS"})
        allowed = {xy: rules.can_place_district(gmap, gmap.tiles[xy]) for xy in [(1, 1), (2, 1), (3, 1), (4, 1)]}
        self.assertEqual(allowed, {(1, 1): False, (2, 1): False, (3, 1): False, (4, 1): True})


class AdjacencyTest(unittest.TestCase):
    def test_campus_science(self):
        base = full_map()
        n = base.neighbours(base.tiles[(10, 6)])
        gmap = full_map({(n[0]["x"], n[0]["y"]): MOUNTAIN,
                         (n[1]["x"], n[1]["y"]): {"feature": "FEATURE_JUNGLE"},
                         (n[2]["x"], n[2]["y"]): {"feature": "FEATURE_JUNGLE"},
                         (n[3]["x"], n[3]["y"]): {"feature": "FEATURE_REEF", "water": 1},
                         (n[4]["x"], n[4]["y"]): {"district": "DISTRICT_HOLY_SITE"}})
        t = gmap.tiles[(10, 6)]
        # 1 mountain + 2 rainforest (+1) + reef (+2); one district alone gives nothing...
        self.assertEqual(Rules().adjacency(gmap, t, "DISTRICT_CAMPUS"), {"YIELD_SCIENCE": 4})
        # ...but with a planned city next to it, two districts give +1.
        planned = {(n[5]["x"], n[5]["y"]): "DISTRICT_CITY_CENTER"}
        self.assertEqual(Rules().adjacency(gmap, t, "DISTRICT_CAMPUS", planned), {"YIELD_SCIENCE": 5})


class DistrictRulesTest(unittest.TestCase):
    def test_dam_on_floodplains_with_two_river_edges(self):
        flood = {"feature": "FEATURE_FLOODPLAINS"}
        gmap = full_map({(5, 6): {**flood, "river_w": 1, "river_nw": 1},   # E and SE edges
                         (8, 6): {**flood, "river_w": 1},                   # one edge only
                         (11, 6): {"river_w": 1, "river_nw": 1}})           # no floodplains
        rules = Rules()
        ok = {(t["x"], t["y"]) for t in gmap if rules.can_place_district(gmap, t, "DISTRICT_DAM")}
        self.assertEqual(ok, {(5, 6)})

    def test_one_dam_per_river(self):
        # Two dam-able tiles on one river, far apart: only one Dam, even with two cities.
        flood = {"feature": "FEATURE_FLOODPLAINS"}
        river = {(x, 6): {**flood, "river_w": 1, "river_nw": 1} for x in range(2, 18)}
        gmap = full_map(river)
        plan = model.optimise(gmap, Rules(), n_cities=2, districts=("DISTRICT_DAM",), improvements=())
        dams = [xy for d, xy, _ in plan.districts if d == "DISTRICT_DAM"]
        self.assertEqual(len(plan.cities), 2)
        self.assertEqual(len(dams), 1)

    def test_aqueduct_next_to_city_and_fresh_water(self):
        gmap = full_map({(6, 5): {"river": 1}, (3, 3): MOUNTAIN})
        rules = Rules()
        self.assertTrue(rules.is_aqueduct("DISTRICT_AQUEDUCT"))
        self.assertTrue(rules.fresh_water_source(gmap, gmap.tiles[(6, 5)]))       # river
        self.assertTrue(rules.fresh_water_source(gmap, gmap.tiles[(4, 3)]))       # next to a mountain
        self.assertFalse(rules.fresh_water_source(gmap, gmap.tiles[(10, 8)]))

    def test_harbor_goes_on_coast_next_to_land(self):
        coast = {"water": 1, "terrain": "TERRAIN_COAST"}
        special = {(x, y): dict(coast) for x in range(W) for y in range(6, H)}   # north half is sea
        special.update({(x, y): {"water": 1, "terrain": "TERRAIN_OCEAN"} for x in range(W) for y in range(9, H)})
        gmap = full_map(special)
        rules = Rules()
        ok = {(t["x"], t["y"]) for t in gmap if rules.can_place_district(gmap, t, "DISTRICT_HARBOR")}
        self.assertEqual(ok, {(x, 6) for x in range(W)})          # coast touching land only
        self.assertFalse(rules.can_place_district(gmap, gmap.tiles[(3, 6)], "DISTRICT_CAMPUS"))
        self.assertFalse(rules.can_place_district(gmap, gmap.tiles[(3, 3)], "DISTRICT_HARBOR"))

    def test_encampment_not_next_to_existing_city(self):
        gmap = full_map({(5, 5): {"is_city": 1}})
        rules = Rules()
        self.assertFalse(rules.can_place_district(gmap, gmap.tiles[(6, 5)], "DISTRICT_ENCAMPMENT"))
        self.assertTrue(rules.can_place_district(gmap, gmap.tiles[(7, 5)], "DISTRICT_ENCAMPMENT"))
        self.assertTrue(rules.can_place_district(gmap, gmap.tiles[(6, 5)], "DISTRICT_CAMPUS"))

    def test_river_sea_resource_and_strategic_adjacency(self):
        rules = Rules(resource_class={"RESOURCE_IRON": "RESOURCECLASS_STRATEGIC", "RESOURCE_FISH": "RESOURCECLASS_BONUS"},
                      adjacencies={
                          "DISTRICT_COMMERCIAL_HUB": [{"yield": "YIELD_GOLD", "change": 2, "tiles": 1, "river": True}],
                          "DISTRICT_HARBOR": [{"yield": "YIELD_GOLD", "change": 1, "tiles": 1, "sea_resource": True}],
                          "DISTRICT_INDUSTRIAL_ZONE": [{"yield": "YIELD_PRODUCTION", "change": 1, "tiles": 1,
                                                        "resource_class": "RESOURCECLASS_STRATEGIC"}]})
        gmap = full_map({(5, 5): {"river": 1}, (6, 5): {"resource": "RESOURCE_IRON"},
                         (4, 5): {"water": 1, "terrain": "TERRAIN_COAST", "resource": "RESOURCE_FISH"}})
        t = gmap.tiles[(5, 5)]
        self.assertEqual(rules.adjacency(gmap, t, "DISTRICT_COMMERCIAL_HUB"), {"YIELD_GOLD": 2})
        self.assertEqual(rules.adjacency(gmap, t, "DISTRICT_HARBOR"), {"YIELD_GOLD": 1})
        self.assertEqual(rules.adjacency(gmap, t, "DISTRICT_INDUSTRIAL_ZONE"), {"YIELD_PRODUCTION": 1})
        self.assertEqual(rules.adjacency(gmap, gmap.tiles[(9, 9)], "DISTRICT_COMMERCIAL_HUB"), {})


if __name__ == "__main__":
    unittest.main()
