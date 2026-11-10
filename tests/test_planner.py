import dataclasses
import os
import random
import tempfile
import unittest
import zlib

from civ6_planner import config, dataset, dump, metrics, model, planner, solver
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


MOUNTAIN = {"mountain": 1, "terrain": "TERRAIN_PLAINS_MOUNTAIN"}


def varied_map(seed=0):
    """A 10x12 island with random food/production: unlike a flat map that wraps around,
    layouts don't all tie, as on real maps (those are the solver's worst case)."""
    rng = random.Random(seed)
    sea = {"water": 1, "terrain": "TERRAIN_OCEAN"}
    return full_map({(x, y): yields(food=rng.randint(0, 3), prod=rng.randint(0, 2)) if 2 <= x < 12 else dict(sea)
                     for x in range(W) for y in range(H)})


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
        gmap = full_map({(1, 1): MOUNTAIN, (2, 1): {"water": 1},
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
        mountains = {(n["x"], n["y"]): MOUNTAIN for n in base.neighbours(target)[:3]}
        gmap = full_map(mountains)
        campus, count = planner.choose_campus(gmap, Rules(), gmap.tiles[(9, 6)], random.Random(0))
        self.assertEqual((campus["x"], campus["y"], count), (11, 6, 3))

    def test_ties_are_random(self):
        gmap = full_map({(10, 6): MOUNTAIN})  # one mountain: its six neighbours tie
        city = gmap.tiles[(8, 6)]
        picks = set()
        for seed in range(40):
            campus, _ = planner.choose_campus(gmap, Rules(), city, random.Random(seed))
            picks.add((campus["x"], campus["y"]))
        expected = {(n["x"], n["y"]) for n in gmap.neighbours(gmap.tiles[(10, 6)])
                    if 0 < gmap.distance(city, n) <= 3}
        self.assertGreater(len(picks), 1)
        self.assertTrue(picks <= expected, picks - expected)


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


def yields(food=0, prod=0):
    return {"YIELD_FOOD": food, "YIELD_PRODUCTION": prod}


class SolverTest(unittest.TestCase):
    def test_knapsack(self):
        m = solver.Model()
        for name, value, weight in [("a", 5, 4), ("b", 4, 3), ("c", 3, 2)]:
            m.var(name, obj=value)
        m.row({"a": 4, "b": 3, "c": 2}, hi=5)
        sol = m.solve()
        self.assertEqual((sol.status, sol["a"], sol["b"], sol["c"], sol.objective), ("optimal", 0, 1, 1, 7))


CAMPUS = ("DISTRICT_CAMPUS",)


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
        plan = model.optimise(gmap, rules, n_cities=1, districts=CAMPUS)
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
        plan = model.optimise(gmap, rules, n_cities=1, districts=CAMPUS)
        [(d, xy, city)] = plan.districts
        planned = {city: model.CITY_CENTER}
        self.assertEqual(rules.adjacency(gmap, gmap.tiles[xy], d, planned), {"YIELD_SCIENCE": 1})
        self.check_score(gmap, rules, plan, 1)

    def test_cities_keep_their_distance(self):
        gmap = full_map()
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities=3, districts=())
        self.assertEqual(len(plan.cities), 3)
        for i, a in enumerate(plan.cities):
            for b in plan.cities[i + 1:]:
                self.assertGreater(gmap.distance(a, b), rules.city_min_range)

    def test_greedy_and_mip_tacks(self):
        gmap = full_map({(10, 6): MOUNTAIN})
        for method in planner.METHODS:
            cfg = dataclasses.replace(config.default(), n_cities=1, districts=CAMPUS)
            tacks, notes = planner.plan(gmap, Rules(), random.Random(0), method, cfg)
            self.assertEqual([t.icon for t in tacks], [planner.CITY_ICON, planner.CAMPUS_ICON], method)
            self.assertTrue(notes[0].startswith(method), notes)

    def test_as_many_cities_as_fit(self):
        # "max" packs cities more than 3 apart and gives each its district.
        gmap = varied_map()
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities="max", districts=CAMPUS)
        self.assertEqual(plan.info["status"], "optimal")
        self.assertGreater(len(plan.cities), 6)
        self.assertEqual(len(plan.districts), len(plan.cities))
        for i, a in enumerate(plan.cities):
            for b in plan.cities[i + 1:]:
                self.assertGreater(gmap.distance(a, b), rules.city_min_range)

    def test_encampment_never_touches_a_planned_city(self):
        gmap = varied_map(1)
        rules = Rules()
        plan = model.optimise(gmap, rules, n_cities="max", districts=("DISTRICT_ENCAMPMENT",))
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
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=districts)
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
        plan = model.optimise(gmap, Rules(), n_cities=0, districts=CAMPUS)
        self.assertEqual((plan.cities, [c for _, _, c in plan.districts]), ([], [(5, 5)]))

    def test_players_own_tacks_are_left_alone(self):
        # The best site (food everywhere around (5, 6)) holds one of the player's tacks.
        special = {(x, y): yields(food=2) for x in range(3, 8) for y in range(4, 9)}
        free = model.optimise(full_map(special), Rules(), n_cities=1, districts=CAMPUS)
        gmap = full_map(special)
        gmap.pins = [{"x": x, "y": y, "name": "mine", "icon": "ICON_MAP_PIN_STAR"}
                     for x, y in free.cities + [xy for _, xy, _ in free.districts]]
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=CAMPUS)
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
                              districts=("DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_AQUEDUCT"))
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
        plan = model.optimise(gmap, Rules(), n_cities=1, districts=specialty + ("DISTRICT_AQUEDUCT",))
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
                              districts=("DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_COMMERCIAL_HUB", "DISTRICT_THEATER"))
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
        plan = model.optimise(gmap, Rules(), n_cities=2, districts=("DISTRICT_DAM",))
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


class ConfigTest(unittest.TestCase):
    def write(self, text):
        f = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
        f.write(text)
        f.close()
        self.addCleanup(os.remove, f.name)
        return f.name

    def test_override_only_changes_what_it_sets(self):
        cfg = config.load(self.write("[objective.weights]\nscience = 3.0\n[solver]\ntime_limit = 5.0\n"))
        self.assertEqual(cfg.weights["YIELD_SCIENCE"], 3.0)
        self.assertEqual(cfg.weights["YIELD_FOOD"], config.default().weights["YIELD_FOOD"])
        self.assertEqual(cfg.solver["time_limit"], 5.0)
        self.assertEqual(cfg.city_bonus, config.default().city_bonus)

    def test_empty_file_gives_the_defaults(self):
        cfg = config.load(self.write(""))
        self.assertEqual(cfg.raw, config.default().raw)

    def test_written_settings_load_back_the_same(self):
        cfg = config.load(self.write("[problem]\ndistricts = [\"DISTRICT_CAMPUS\", \"DISTRICT_HOLY_SITE\"]\n"
                                     "[solver]\npresolve = false\n"))
        self.assertEqual(config.load(self.write(config.to_toml(cfg))).raw, cfg.raw)

    def test_case_config_then_command_line_config(self):
        # data/<case>/config.toml overlays the defaults; --config overlays both.
        folder = tempfile.mkdtemp()
        self.addCleanup(__import__("shutil").rmtree, folder)
        with open(os.path.join(folder, "map.json"), "w") as f:
            f.write("{}")
        with open(os.path.join(folder, "config.toml"), "w") as f:
            f.write("[objective.weights]\nscience = 2.0\nfood = 3.0\n")
        self.assertEqual(dataset.config_path(folder), os.path.join(folder, "config.toml"))
        cfg = config.load(dataset.config_path(folder), self.write("[objective.weights]\nscience = 5.0\n"))
        self.assertEqual((cfg.weights["YIELD_SCIENCE"], cfg.weights["YIELD_FOOD"]), (5.0, 3.0))

    def test_case_template_is_empty_settings(self):
        self.assertEqual(config.load(self.write(dataset.CONFIG_TEMPLATE)).raw, config.default().raw)

    def test_unknown_setting_is_an_error(self):
        with self.assertRaises(KeyError):
            config.load(self.write("[objective]\nsite_radios = 3\n"))

    def test_weights_change_the_plan_score(self):
        # Every tile gives 1 food; with food weighted 2 the site value doubles.
        gmap = full_map({(x, y): yields(food=1) for x in range(20) for y in range(12)})
        rules = Rules()
        cfg = config.load(self.write("[objective.weights]\nfood = 2.0\n"))
        a = model.optimise(gmap, rules, n_cities=1, districts=())
        b = model.optimise(gmap, rules, cfg, n_cities=1, districts=())
        self.assertAlmostEqual(model.evaluate(gmap, rules, b)[0], 2 * model.evaluate(gmap, rules, a)[0])


if __name__ == "__main__":
    unittest.main()
