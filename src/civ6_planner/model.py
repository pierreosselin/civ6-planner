"""The placement optimiser: which tiles get cities and districts, as a MIP.

Kept deliberately simple for now (it solves in about a second on the test maps):

Decision variables
  city[c]        found a city on candidate tile c
  dist[d,c,t]    district d of the city on c goes on tile t (t within district range of c)

Constraints
  sum(city) <= n_cities; cities closer than the game allows exclude each other
  each city has at most one of each district, only if it exists: sum_t dist[d,c,t] <= city[c]
  one thing per tile: city[t] + sum dist[·,·,t] <= 1

Objective (weights below are placeholders to be tuned)
  city site value: weighted yields of the centre and the tiles within 2
  + district adjacency, computed per (city, tile) as a constant: terrain/features,
    existing districts, and the district's own city centre
  - LOSS_FACTOR × the weighted yields of the tile a district covers
  + CITY_BONUS per city and DISTRICT_BONUS per district so they're placed when possible

Not modelled yet: adjacency between *planned* districts other than a district's own
city centre (e.g. Campus next to a planned Holy Site, or another city's centre). That
is exact for one city with one district; with more, it needs coupling variables
(k * tiles <= linked planned neighbours), which made HiGHS much slower, so it waits.

`evaluate` scores any plan (the greedy one too) in plain Python. It counts every
planned district, so it can be above the MIP's objective when planned districts touch.
"""
from dataclasses import dataclass, field

from .solver import Model

YIELDS = ["YIELD_FOOD", "YIELD_PRODUCTION", "YIELD_GOLD", "YIELD_SCIENCE", "YIELD_CULTURE", "YIELD_FAITH"]
WEIGHTS = {"YIELD_FOOD": 1.0, "YIELD_PRODUCTION": 1.0, "YIELD_GOLD": 0.5,
           "YIELD_SCIENCE": 1.0, "YIELD_CULTURE": 1.0, "YIELD_FAITH": 0.5}
SITE_RADIUS = 2          # tiles counted in a city's site value
LOSS_FACTOR = 0.5        # share of a covered tile's yields counted as lost
CITY_BONUS = 100.0       # found the cities asked for whenever possible
DISTRICT_BONUS = 10.0    # and build their districts

CITY_CENTER = "DISTRICT_CITY_CENTER"


@dataclass
class Plan:
    cities: list = field(default_factory=list)      # [(x, y)]
    districts: list = field(default_factory=list)   # [(district type, (x, y), city (x, y))]
    info: dict = field(default_factory=dict)        # solver status, timings, sizes
    log: str = ""                                   # the solver's log


def weighted(yields):
    """Weighted sum of a {YIELD_*: n} dict (a tile works too)."""
    return sum(WEIGHTS[y] * yields.get(y, 0) for y in YIELDS)


def site_value(gmap, tile):
    return weighted(tile) + sum(weighted(t) for t in gmap.within(tile, SITE_RADIUS))


def evaluate(gmap, rules, plan):
    """(score, breakdown) of a plan under the model's objective, bonuses left out."""
    planned = {xy: CITY_CENTER for xy in plan.cities}
    planned.update({xy: d for d, xy, _ in plan.districts})
    breakdown = {"site": 0.0, "adjacency": 0.0, "lost": 0.0, "yields": {}}
    for xy in plan.cities:
        breakdown["site"] += site_value(gmap, gmap.tiles[xy])
    for d, xy, _ in plan.districts:
        tile = gmap.tiles[xy]
        adj = rules.adjacency(gmap, tile, d, planned)
        for y, v in adj.items():
            breakdown["yields"][y] = breakdown["yields"].get(y, 0) + v
        breakdown["adjacency"] += weighted(adj)
        breakdown["lost"] += LOSS_FACTOR * weighted(tile)
    score = breakdown["site"] + breakdown["adjacency"] - breakdown["lost"]
    return score, breakdown


def optimise(gmap, rules, n_cities=1, districts=("DISTRICT_CAMPUS",), max_city_candidates=400,
             time_limit=60):
    """Best plan for n_cities new cities, each with one of each district."""
    city_tiles = [t for t in gmap if rules.can_found_city(gmap, t)]
    site = {(t["x"], t["y"]): site_value(gmap, t) for t in city_tiles}
    # On big maps keep the best sites only; the MIP then works on far fewer variables.
    city_tiles = sorted(city_tiles, key=lambda t: -site[(t["x"], t["y"])])[:max_city_candidates]
    cxy = [(t["x"], t["y"]) for t in city_tiles]

    m = Model()
    occ = {}  # tile (x, y) -> variables that put something on it
    for xy in cxy:
        m.var(("city", xy), obj=site[xy] + CITY_BONUS)
        occ.setdefault(xy, []).append(("city", xy))
    m.row([(("city", xy), 1) for xy in cxy], hi=n_cities)

    # Cities too close to each other.
    if n_cities > 1:
        for t in city_tiles:
            a = (t["x"], t["y"])
            for n in gmap.within(t, rules.city_min_range):
                b = (n["x"], n["y"])
                if b in site and a < b and ("city", b) in m.index:
                    m.row({("city", a): 1, ("city", b): 1}, hi=1)

    for d in districts:
        for t in city_tiles:
            c = (t["x"], t["y"])
            names = []
            for n in gmap.within(t, rules.district_range):
                xy = (n["x"], n["y"])
                if not rules.can_place_district(gmap, n):
                    continue
                # Adjacency with this district's own city centre counted as planned;
                # other planned districts aren't (see the module docstring).
                fixed = weighted(rules.adjacency(gmap, n, d, {c: CITY_CENTER}))
                name = m.var(("dist", d, c, xy), obj=fixed - LOSS_FACTOR * weighted(n) + DISTRICT_BONUS)
                names.append(name)
                occ.setdefault(xy, []).append(name)
            if names:
                m.row([(v, 1) for v in names] + [(("city", c), -1)], hi=0)

    for xy, names in occ.items():
        if len(names) > 1:
            m.row([(v, 1) for v in names], hi=1)

    sol = m.solve(time_limit=time_limit)
    plan = Plan(log=sol.log, info={"status": sol.status, "seconds": round(sol.seconds, 3), "objective": sol.objective,
                      "city_candidates": len(cxy), **sol.stats})
    for name, v in sol.values.items():
        if v < 0.5:
            continue
        if name[0] == "city":
            plan.cities.append(name[1])
        elif name[0] == "dist":
            plan.districts.append((name[1], name[3], name[2]))
    return plan
