"""Checks of a plan against rules the model leaves out."""
import unittest

from civ6_planner import metrics, model, validate
from civ6_planner.rules import Rules
from helpers import full_map


class ValidateTest(unittest.TestCase):
    def test_flags_tiles_another_city_claims_and_owns(self):
        # Rome (5, 5) owns (6, 5); new cities C1 (12, 6) and C2 (16, 6).
        gmap = full_map({(5, 5): {"is_city": 1, "owner": 0, "city": 1, "district": "DISTRICT_CITY_CENTER"},
                         (6, 5): {"owner": 0, "city": 1}})
        gmap.own_cities = [{"id": 1, "name": "Rome", "x": 5, "y": 5}]
        plan = model.Plan(cities=[(12, 6), (16, 6)], districts=[
            ("DISTRICT_CAMPUS", (15, 6), (12, 6)),      # next to C2's centre: C2 claims it
            ("DISTRICT_CAMPUS", (11, 6), (12, 6))],     # fine
            improvements=[("IMPROVEMENT_FARM", (6, 5), (12, 6))])   # Rome's tile, 6 away
        v = validate.check_plan(gmap, Rules(), plan)
        self.assertEqual(v["counts"], {"ring": 2, "owned": 1, "foreign": 0, "range": 1, "shared": 0, "spacing": 0})
        self.assertTrue(any("C1" in x for x in v["issues"]["ring"]))
        self.assertTrue(validate.format_check(v))

    def test_spacing_metrics(self):
        gmap = full_map()
        plan = model.Plan(cities=[(2, 2), (6, 2), (14, 2)])
        s = metrics.city_spacing(gmap, plan, plan.cities)
        self.assertEqual((s["nearest_city"]["min"], s["nearest_city"]["max"]), (4, 8))
        self.assertEqual(s["nearest_city"]["histogram"], {4: 2, 8: 1})
        self.assertEqual((s["all_pairs"]["min"], s["all_pairs"]["max"]), (4, 8))   # 2->14 wraps: 8
        self.assertEqual(len(s["top_3_sites"]["cities"]), 3)


if __name__ == "__main__":
    unittest.main()
