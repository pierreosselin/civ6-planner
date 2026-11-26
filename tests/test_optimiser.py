"""The optimiser: cities and districts."""
import dataclasses
import random
import unittest

from civ6_planner import config, metrics, model, planner
from civ6_planner.rules import Rules
from helpers import MOUNTAIN, varied_map, full_map, yields, CAMPUS


class OptimiserTest(unittest.TestCase):
    def check_score(self, gmap, rules, plan, n_districts):
        """The MIP's own objective must equal evaluate() plus the placement bonuses."""
        score, _ = model.evaluate(gmap, rules, plan)
        cfg = plan.config
        expected = score + cfg.city_bonus * len(plan.cities) + cfg.district_bonus * n_districts
        self.assertAlmostEqual(plan.info["objective"], expected, places=6)

    def test_city_on_best_site_and_campus_by_mountains(self):
        # Food only around (5, 6); three mountains around (12, 6). Site value pulls the
        # city to (5, 6)... unless the Campus is worth more: here it isn't in range, so
        # the city goes where the food is and the Campus takes the best tile it can reach.
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        base = full_map()
        for n in base.neighbours(base.tiles[(7, 6)])[:3]:
            special[(n["x"], n["y"])] = dict(MOUNTAIN)
        gmap = full_map(special)
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities=1, districts=CAMPUS, improvements=())
        self.assertEqual(plan.info["status"], "optimal")
        self.assertEqual(len(plan.cities), 1)
        [(d, xy, city)] = plan.districts
        self.assertEqual((d, city), ("DISTRICT_CAMPUS", plan.cities[0]))
        self.assertEqual(rules.adjacency(gmap, gmap.tiles[xy], d).get("YIELD_SCIENCE"), 3)
        self.check_score(gmap, rules, plan, 1)

    def test_planned_city_counts_as_adjacent_district(self):
        # An existing district at (10, 6): a Campus touching both it and the new city
        # gets +1 from "+1 per 2 districts"; everything else is flat.
        gmap = full_map({(10, 6): {"district": "DISTRICT_HOLY_SITE"}})
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities=1, districts=CAMPUS, improvements=())
        [(d, xy, city)] = plan.districts
        planned = {city: model.CITY_CENTER}
        self.assertEqual(rules.adjacency(gmap, gmap.tiles[xy], d, planned), {"YIELD_SCIENCE": 1})
        self.check_score(gmap, rules, plan, 1)

    def test_cities_keep_their_distance(self):
        gmap = full_map()
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities=3, districts=(), improvements=())
        self.assertEqual(len(plan.cities), 3)
        for i, a in enumerate(plan.cities):
            for b in plan.cities[i + 1:]:
                self.assertGreater(gmap.distance(a, b), rules.city_min_range)

    def test_greedy_and_mip_tacks(self):
        gmap = full_map({(10, 6): MOUNTAIN})
        for method in planner.METHODS:
            cfg = dataclasses.replace(config.default(), n_cities=1, districts=CAMPUS, improvements=())
            tacks, notes = planner.plan(gmap, Rules(), random.Random(0), method, cfg)
            self.assertEqual([t.icon for t in tacks], [planner.CITY_ICON, planner.CAMPUS_ICON], method)
            self.assertTrue(notes[0].startswith(method), notes)

    def test_as_many_cities_as_fit(self):
        # "max" packs cities more than 3 apart and gives each its district.
        gmap = varied_map()
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities="max", districts=CAMPUS, improvements=())
        self.assertEqual(plan.info["status"], "optimal")
        self.assertGreater(len(plan.cities), 6)
        self.assertEqual(len(plan.districts), len(plan.cities))
        for i, a in enumerate(plan.cities):
            for b in plan.cities[i + 1:]:
                self.assertGreater(gmap.distance(a, b), rules.city_min_range)

    def test_encampment_never_touches_a_planned_city(self):
        gmap = varied_map(1)
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities="max", districts=("DISTRICT_ENCAMPMENT",), improvements=())
        self.assertEqual(len(plan.districts), len(plan.cities))
        for _, xy, _ in plan.districts:
            self.assertTrue(all(gmap.distance(xy, c) > 1 for c in plan.cities), xy)

    def test_existing_city_gets_the_districts_it_lacks(self):
        # The player's city at (5, 5) already has a Campus at (6, 5): it should get a
        # Holy Site but no second Campus; a new city gets both.
        gmap = full_map({(5, 5): {"is_city": 1, "owner": 0, "city": 7, "district": "DISTRICT_CITY_CENTER"},
                         (6, 5): {"owner": 0, "city": 7, "district": "DISTRICT_CAMPUS"}})
        gmap.own_cities = [{"id": 7, "name": "Rome", "x": 5, "y": 5}]
        districts = ("DISTRICT_CAMPUS", "DISTRICT_HOLY_SITE")
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=districts, improvements=())
        rome = [d for d, _, c in plan.districts if c == (5, 5)]
        new = [d for d, _, c in plan.districts if c == plan.cities[0]]
        self.assertEqual(rome, ["DISTRICT_HOLY_SITE"])
        self.assertEqual(sorted(new), sorted(districts))
        self.check_score(gmap, Rules(), plan, len(plan.districts))
        names = sorted(t.name for t in planner.to_tacks(gmap, Rules(), plan))
        self.assertEqual(names, ["Campus C1", "City C1", "Holy Site C1", "Holy Site Rome"])

    def test_no_new_city_still_plans_existing_ones(self):
        gmap = full_map({(5, 5): {"is_city": 1, "owner": 0, "city": 1, "district": "DISTRICT_CITY_CENTER"}})
        gmap.own_cities = [{"id": 1, "name": "Rome", "x": 5, "y": 5}]
        plan = model.optimise(gmap, Rules(), n_cities=0, districts=CAMPUS, improvements=())
        self.assertEqual((plan.cities, [c for _, _, c in plan.districts]), ([], [(5, 5)]))

    def test_players_own_tacks_are_left_alone(self):
        # The best site (food everywhere around (5, 6)) holds one of the player's tacks.
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        free = model.optimise(full_map(special), Rules(), n_cities=1, districts=CAMPUS, improvements=())
        gmap = full_map(special)
        gmap.pins = [{"x": x, "y": y, "name": "mine", "icon": "ICON_MAP_PIN_STAR"}
                     for x, y in free.cities + [xy for _, xy, _ in free.districts]]
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=CAMPUS, improvements=())
        taken = {(p["x"], p["y"]) for p in gmap.pins}
        self.assertTrue(plan.cities)
        self.assertFalse(taken & (set(plan.cities) | {xy for _, xy, _ in plan.districts}))

    def test_industrial_zone_goes_next_to_its_aqueduct(self):
        # Food around (5, 6) puts the city there; rivers on (6, 6) and (4, 6) make those the
        # only Aqueduct tiles. The +2 production bonus should pull the Industrial Zone
        # next to the Aqueduct, and the MIP's objective should count it exactly.
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        special[(6, 6)] = {**special[(6, 6)], "river": 1}
        special[(4, 6)] = {**special[(4, 6)], "river": 1}
        gmap = full_map(special)
        rules = Rules(adjacencies={"DISTRICT_INDUSTRIAL_ZONE": [
            {"yield": "YIELD_PRODUCTION", "change": 2, "tiles": 1, "district": "DISTRICT_AQUEDUCT"}]})
        plan = model.optimise(gmap, rules, n_cities=1,
                              districts=("DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_AQUEDUCT"), improvements=())
        [city] = plan.cities
        at = {d: xy for d, xy, _ in plan.districts}
        self.assertEqual(gmap.distance(at["DISTRICT_AQUEDUCT"], city), 1)
        self.assertIn(at["DISTRICT_AQUEDUCT"], {(6, 6), (4, 6)})
        self.assertEqual(gmap.distance(at["DISTRICT_INDUSTRIAL_ZONE"], at["DISTRICT_AQUEDUCT"]), 1)
        self.check_score(gmap, rules, plan, 2)

    def test_three_specialty_districts_per_city_aqueduct_free(self):
        # Five specialty districts asked for, plus an Aqueduct (river next to the city).
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        special[(6, 6)] = {**special[(6, 6)], "river": 1}
        gmap = full_map(special)
        specialty = ("DISTRICT_CAMPUS", "DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_COMMERCIAL_HUB",
                     "DISTRICT_HOLY_SITE", "DISTRICT_THEATER")
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=specialty + ("DISTRICT_AQUEDUCT",), improvements=())
        kinds = [d for d, _, _ in plan.districts]
        self.assertEqual(sum(d in specialty for d in kinds), 3)
        self.assertIn("DISTRICT_AQUEDUCT", kinds)

    def test_existing_city_specialty_districts_count(self):
        # Rome has a Campus and a Holy Site: one specialty district left under the limit of 3.
        gmap = full_map({(5, 5): {"is_city": 1, "owner": 0, "city": 1, "district": "DISTRICT_CITY_CENTER"},
                         (6, 5): {"owner": 0, "city": 1, "district": "DISTRICT_CAMPUS"},
                         (4, 5): {"owner": 0, "city": 1, "district": "DISTRICT_HOLY_SITE"}})
        gmap.own_cities = [{"id": 1, "name": "Rome", "x": 5, "y": 5}]
        plan = model.optimise(gmap, Rules(), n_cities=0,
                              districts=("DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_COMMERCIAL_HUB", "DISTRICT_THEATER"), improvements=())
        self.assertEqual(len(plan.districts), 1)

    def test_metrics_count_districts_per_city_and_type(self):
        gmap = full_map({(5, 5): {"is_city": 1, "owner": 0, "city": 1, "district": "DISTRICT_CITY_CENTER"}})
        gmap.own_cities = [{"id": 1, "name": "Rome", "x": 5, "y": 5}]
        plan = model.Plan(cities=[(12, 6)], districts=[
            ("DISTRICT_CAMPUS", (13, 6), (12, 6)), ("DISTRICT_HOLY_SITE", (11, 6), (12, 6)),
            ("DISTRICT_CAMPUS", (6, 5), (5, 5))])
        m = metrics.plan_metrics(gmap, Rules(), plan)
        self.assertEqual((m["cities"], m["new_cities"], m["existing_cities"], m["districts"]), (2, 1, 1, 3))
        self.assertEqual(m["districts_per_city"]["histogram"], {1: 1, 2: 1})
        campus = m["by_type"]["DISTRICT_CAMPUS"]
        self.assertEqual((campus["count"], campus["cities_with"], campus["share_of_cities"]), (2, 2, 1.0))
        self.assertEqual(m["by_type"]["DISTRICT_HOLY_SITE"]["share_of_cities"], 0.5)
        # Each Campus touches its city centre only: +1 per 2 districts gives 0.
        self.assertTrue(metrics.format_metrics(m))


if __name__ == "__main__":
    unittest.main()
