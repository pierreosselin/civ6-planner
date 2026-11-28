"""Amenities: the Entertainment Complex and the Colosseum next to it."""
import dataclasses
import os
import unittest

from helpers import CAMPUS, H, W, full_map, varied_map, yields

from civ6_planner import config, metrics, model, paths, planner
from civ6_planner.rules import Rules, WonderRule

EC = "DISTRICT_ENTERTAINMENT_COMPLEX"
COLOSSEUM = "BUILDING_COLOSSEUM"


class WonderPlacementTest(unittest.TestCase):
    def test_colosseum_tiles(self):
        # Flat land with no feature, or a removable one; not hills, floodplains, luxuries.
        gmap, rules = full_map({
            (1, 1): {"terrain": "TERRAIN_PLAINS_HILLS"},
            (2, 1): {"feature": "FEATURE_FOREST"},
            (3, 1): {"feature": "FEATURE_FLOODPLAINS_PLAINS"},
            (4, 1): {"resource": "RESOURCE_SILK"},
            (5, 1): {"district": "DISTRICT_CAMPUS"},
        }), Rules(resource_class={"RESOURCE_SILK": "RESOURCECLASS_LUXURY"})
        ok = {x: rules.can_place_wonder(gmap, gmap.tiles[(x, 1)], COLOSSEUM) for x in range(7)}
        self.assertEqual(ok, {0: True, 1: False, 2: True, 3: False, 4: False, 5: False, 6: True})

    def test_wonder_with_unread_requirements_never_goes(self):
        rules = Rules(wonders={"BUILDING_X": WonderRule(requires=("RequiresRiver",))})
        self.assertFalse(rules.can_place_wonder(full_map(), full_map().tiles[(5, 5)], "BUILDING_X"))

    @unittest.skipUnless(os.path.exists(paths.GAMEPLAY_DB), "no game database")
    def test_rules_from_the_game(self):
        rules = Rules.from_game()
        w = rules.wonders[COLOSSEUM]
        self.assertEqual((w.adjacent_district, w.entertainment, w.range, w.requires), (EC, 2, 6, ()))
        self.assertNotIn("TERRAIN_PLAINS_HILLS", w.terrains)
        self.assertEqual(rules.entertainment[EC], 1)
        self.assertTrue(rules.is_specialty(EC))


class ColosseumTest(unittest.TestCase):
    def plan(self, gmap=None, wonders=(COLOSSEUM,), **changes):
        """As many cities as fit on the island, one specialty district each: a Campus (no
        adjacency here, worth its district bonus) or an Entertainment Complex (no bonus:
        worth its amenity, and the Colosseum it allows)."""
        gmap = gmap or varied_map()
        rules = Rules(adjacencies={})
        cfg = dataclasses.replace(config.default(), max_specialty_districts=1, **changes)
        return gmap, rules, model.optimise(gmap, rules, cfg, n_cities="max", districts=CAMPUS + (EC,),
                                           improvements=(), wonders=wonders)

    def test_one_entertainment_complex_and_its_colosseum(self):
        gmap, rules, plan = self.plan()
        self.assertEqual(plan.info["status"], "optimal")
        [(b, t, city)] = plan.wonders
        ecs = [(xy, c) for d, xy, c in plan.districts if d == EC]
        self.assertEqual(len(ecs), 1)           # only where the Colosseum needs one
        [(ec, ec_city)] = ecs
        self.assertEqual((b, city), (COLOSSEUM, ec_city))
        self.assertEqual(gmap.distance(t, ec), 1)
        self.assertLessEqual(gmap.distance(t, city), rules.district_range)
        self.assertEqual(gmap.tiles[t]["terrain"], "TERRAIN_PLAINS")
        self.assertNotIn(t, set(plan.cities) | {xy for _, xy, _ in plan.districts})
        # Its +2 reaches every city within 6 tiles; the MIP counts amenities as evaluate does.
        amenities = model.city_amenities(gmap, rules, plan)
        for c in plan.cities:
            self.assertEqual(amenities[c], 2 * (gmap.distance(c, t) <= 6) + (c == city), c)
        score, parts = model.evaluate(gmap, rules, plan)
        cfg = plan.config
        self.assertEqual(parts["amenities"], cfg.amenity_value * sum(min(2, n) for n in amenities.values()))
        bonus = cfg.city_bonus * len(plan.cities) + cfg.district_bonus * (len(plan.districts) - 1)
        self.assertAlmostEqual(plan.info["objective"], score + bonus, places=6)
        # Tacks and notes name it after its city.
        label = planner.city_labels(gmap, plan)
        names = [k.name for k in planner.to_tacks(gmap, rules, plan) if k.icon == "ICON_" + COLOSSEUM]
        self.assertEqual(names, [f"Colosseum {label[city]}"])
        self.assertEqual(metrics.plan_metrics(gmap, rules, plan)["wonders"][0]["tile"], t)

    def test_no_colosseum_no_entertainment_complex(self):
        _, _, plan = self.plan(wonders=())
        self.assertEqual(plan.wonders, [])
        self.assertEqual([d for d, _, _ in plan.districts if d == EC], [])

    def test_one_in_the_world(self):
        # Already built by another player: none planned.
        gmap = varied_map()
        gmap.tiles[(3, 3)]["wonder"], gmap.tiles[(3, 3)]["owner"] = COLOSSEUM, 1
        _, _, plan = self.plan(gmap)
        self.assertEqual(plan.wonders, [])

    def test_players_own_colosseum_counts(self):
        # The player's Colosseum at (5, 5) next to Rome's Entertainment Complex: every city
        # within 6 tiles already gets its 2 amenities, so no new one is planned.
        gmap = full_map({(x, y): yields(food=1) for x in range(W) for y in range(H)})
        for xy, extra in {(4, 5): {"is_city": 1, "district": "DISTRICT_CITY_CENTER"},
                          (5, 5): {"wonder": COLOSSEUM, "district": "DISTRICT_WONDER"},
                          (4, 6): {"district": EC}}.items():
            gmap.tiles[xy].update(owner=0, city=7, **extra)
        gmap.own_cities = [{"id": 7, "name": "Rome", "x": 4, "y": 5}]
        rules = Rules(adjacencies={})
        self.assertEqual(model.existing_amenities(gmap, rules, [(4, 5), (9, 5), (15, 5)]),
                         {(4, 5): 3, (9, 5): 2, (15, 5): 0})
        plan = model.optimise(gmap, rules, n_cities=0, districts=CAMPUS + (EC,), improvements=())
        self.assertEqual(plan.wonders, [])


if __name__ == "__main__":
    unittest.main()
