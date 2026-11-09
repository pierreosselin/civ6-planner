"""The placement optimiser: which tiles get cities and districts, as a MIP.

Kept deliberately simple for now (it solves in about a second on the test maps):

The MIP is assembled from the lists VARIABLES, CONSTRAINTS and OBJECTIVE near the end
of this file: one small function per variable family, constraint and objective term.
Comment out a line there to drop that constraint or term.

Decision variables (city_vars, district_vars)
  x[c]        found a city on candidate tile c
  z[d,c,t]    district d of the city on c goes on tile t (t within district range of c)

Constraints
  max_cities           sum x <= n_cities
  city_spacing         cities closer than the game allows exclude each other
  district_needs_city  at most one of each district per city, only if it exists
  one_thing_per_tile   x[t] + sum z[.,.,t] <= 1

Objective terms (weights and bonuses in config/default.toml; placeholders to tune)
  site_term            weighted yields of the centre and the tiles within 2
  adjacency_term       district adjacency, a constant per (city, tile): terrain/features,
                       existing districts, and the district's own city centre
  covered_tile_term    - loss_factor x the weighted yields of the tile a district covers
  city_bonus_term, district_bonus_term
                       city_bonus per city, district_bonus per district, so they're
                       placed whenever possible

Not modelled yet: adjacency between *planned* districts other than a district's own
city centre (e.g. Campus next to a planned Holy Site, or another city's centre). That
is exact for one city with one district; with more, it needs coupling variables
(k * tiles <= linked planned neighbours), which made HiGHS much slower, so it waits.

`evaluate` scores any plan (the greedy one too) in plain Python. It counts every
planned district, so it can be above the MIP's objective when planned districts touch.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from . import config
from .config import YIELDS, Config, Yields
from .gamemap import XY, GameMap, Tile
from .rules import Rules
from .solver import Model, Var

# Parameters (weights, bonuses, site radius, loss factor, solver options) are in
# config/default.toml; see config.py. Functions take a Config, None meaning the defaults.

CITY_CENTER = "DISTRICT_CITY_CENTER"


@dataclass
class Plan:
    cities: list[XY] = field(default_factory=list)                    # city centres
    districts: list[tuple[str, XY, XY]] = field(default_factory=list)  # (district type, tile, its city)
    info: dict[str, Any] = field(default_factory=dict)                # solver status, timings, sizes
    log: str = ""                                                     # the solver's log
    model: dict[str, list[str]] = field(default_factory=dict)         # constraints and objective terms used
    config: Config = field(default_factory=config.default)          # the settings it was made with


def site_value(gmap: GameMap, tile: Tile, cfg: Config | None = None) -> float:
    """Weighted yields of a city centre and the tiles within cfg.site_radius."""
    cfg = cfg or config.default()
    return cfg.weighted(tile) + sum(cfg.weighted(t) for t in gmap.within(tile, cfg.site_radius))


def evaluate(gmap: GameMap, rules: Rules, plan: Plan, cfg: Config | None = None) -> tuple[float, dict[str, Any]]:
    """(score, breakdown) of a plan under the model's objective, bonuses left out.
    Uses cfg, else the plan's own config."""
    cfg = cfg or plan.config
    planned: dict[XY, str] = {xy: CITY_CENTER for xy in plan.cities}
    planned.update({xy: d for d, xy, _ in plan.districts})
    site = adjacency = lost = 0.0
    yields: dict[str, int] = {}
    for xy in plan.cities:
        site += site_value(gmap, gmap.tiles[xy], cfg)
    for d, xy, _ in plan.districts:
        tile = gmap.tiles[xy]
        adj = rules.adjacency(gmap, tile, d, planned)
        for y, v in adj.items():
            yields[y] = yields.get(y, 0) + v
        adjacency += cfg.weighted(adj)
        lost += cfg.loss_factor * cfg.weighted(tile)
    return site + adjacency - lost, {"site": site, "adjacency": adjacency, "lost": lost, "yields": yields}


# ---------------------------------------------------------------------------
# The MIP. Built in three steps, each a list of small functions:
#   VARIABLES    create the decision variables (no objective coefficients)
#   CONSTRAINTS  one function per constraint family
#   OBJECTIVE    one function per objective term (adds coefficients to variables)
# To switch a constraint or a term off, comment out its line in the list.
# Every function takes (m, inst): the Model being built and the Instance below.
# ---------------------------------------------------------------------------

@dataclass
class Instance:
    """The data the MIP is built from, plus its variables once created."""
    gmap: GameMap
    rules: Rules
    cfg: Config                          # weights, bonuses, … (config/default.toml)
    n_cities: int
    districts: tuple[str, ...]           # D: district types to place per city
    sites: list[XY]                      # C: candidate city tiles, best site value first
    site: dict[XY, float]                # c -> site value s_c
    spots: dict[tuple[str, XY], list[XY]]  # (district, city) -> R_c: tiles it may go on
    x: dict[XY, Var] = field(default_factory=dict)                 # city c -> x[c]
    z: dict[tuple[str, XY, XY], Var] = field(default_factory=dict)  # (d, c, t) -> z[d,c,t]


Step = Callable[[Model, "Instance"], None]   # a variable, constraint or objective function


def prepare(gmap: GameMap, rules: Rules, cfg: Config, n_cities: int, districts: tuple[str, ...],
            max_city_candidates: int) -> Instance:
    """Candidate sets and site values; no variables yet."""
    tiles = [t for t in gmap if rules.can_found_city(gmap, t)]
    site = {(t["x"], t["y"]): site_value(gmap, t, cfg) for t in tiles}
    # On big maps keep the best sites only; the MIP then works on far fewer variables.
    tiles = sorted(tiles, key=lambda t: -site[(t["x"], t["y"])])[:max_city_candidates]
    sites = [(t["x"], t["y"]) for t in tiles]
    spots = {}
    for d in districts:
        for c in sites:
            spots[d, c] = [(n["x"], n["y"]) for n in gmap.within(gmap.tiles[c], rules.district_range)
                           if rules.can_place_district(gmap, n)]
    return Instance(gmap, rules, cfg, n_cities, tuple(districts), sites, {c: site[c] for c in sites}, spots)


# --- Variables ---------------------------------------------------------------

def city_vars(m: Model, inst: Instance) -> None:
    """x[c] = 1: found a city on candidate tile c."""
    for c in inst.sites:
        inst.x[c] = m.var(("city", c))


def district_vars(m: Model, inst: Instance) -> None:
    """z[d,c,t] = 1: district d of the city on c goes on tile t (t within its range)."""
    for (d, c), tiles in inst.spots.items():
        for t in tiles:
            inst.z[d, c, t] = m.var(("dist", d, c, t))


# --- Constraints -------------------------------------------------------------

def max_cities(m: Model, inst: Instance) -> None:
    """(1) At most n cities: sum_c x[c] <= n."""
    m.row([(v, 1) for v in inst.x.values()], hi=inst.n_cities)


def city_spacing(m: Model, inst: Instance) -> None:
    """(2) Cities too close to each other exclude each other: x[a] + x[b] <= 1."""
    if inst.n_cities < 2:
        return  # one city can't clash with itself
    for a in inst.sites:
        for n in inst.gmap.within(inst.gmap.tiles[a], inst.rules.city_min_range):
            b = (n["x"], n["y"])
            if b in inst.x and a < b:
                m.row({inst.x[a]: 1, inst.x[b]: 1}, hi=1)


def district_needs_city(m: Model, inst: Instance) -> None:
    """(3) At most one of each district per city, and only if the city is founded:
    sum_t z[d,c,t] <= x[c]."""
    for (d, c), tiles in inst.spots.items():
        if tiles:
            m.row([(inst.z[d, c, t], 1) for t in tiles] + [(inst.x[c], -1)], hi=0)


def one_thing_per_tile(m: Model, inst: Instance) -> None:
    """(4) A tile holds at most one city or district: x[t] + sum z[.,.,t] <= 1."""
    occ: dict[XY, list[Var]] = {}
    for c, v in inst.x.items():
        occ.setdefault(c, []).append(v)
    for (d, c, t), v in inst.z.items():
        occ.setdefault(t, []).append(v)
    for names in occ.values():
        if len(names) > 1:
            m.row([(v, 1) for v in names], hi=1)


# --- Objective terms (maximised) ---------------------------------------------

def site_term(m: Model, inst: Instance) -> None:
    """+ s_c x[c]: weighted yields of the city centre and the tiles within site_radius."""
    for c, v in inst.x.items():
        m.add_obj(v, inst.site[c])


def adjacency_term(m: Model, inst: Instance) -> None:
    """+ a[d,c,t] z[d,c,t]: the district's adjacency, a constant per (city, tile).
    Counts existing districts and the district's own city centre as planned; other
    planned districts aren't (see the module docstring)."""
    for (d, c, t), v in inst.z.items():
        adj = inst.rules.adjacency(inst.gmap, inst.gmap.tiles[t], d, {c: CITY_CENTER})
        m.add_obj(v, inst.cfg.weighted(adj))


def covered_tile_term(m: Model, inst: Instance) -> None:
    """- loss_factor v(t) z[d,c,t]: part of the yields of the tile a district covers."""
    for (d, c, t), v in inst.z.items():
        m.add_obj(v, -inst.cfg.loss_factor * inst.cfg.weighted(inst.gmap.tiles[t]))


def city_bonus_term(m: Model, inst: Instance) -> None:
    """+ city_bonus x[c]: found the cities asked for whenever possible."""
    for v in inst.x.values():
        m.add_obj(v, inst.cfg.city_bonus)


def district_bonus_term(m: Model, inst: Instance) -> None:
    """+ district_bonus z[d,c,t]: build the districts whenever possible."""
    for v in inst.z.values():
        m.add_obj(v, inst.cfg.district_bonus)


VARIABLES: list[Step] = [
    city_vars,
    district_vars,
]
CONSTRAINTS: list[Step] = [
    max_cities,
    city_spacing,
    district_needs_city,
    one_thing_per_tile,
]
OBJECTIVE: list[Step] = [
    site_term,
    adjacency_term,
    covered_tile_term,
    city_bonus_term,
    district_bonus_term,
]


def build(inst: Instance) -> Model:
    m = Model()
    for step in VARIABLES + CONSTRAINTS + OBJECTIVE:
        step(m, inst)
    return m


def optimise(gmap: GameMap, rules: Rules, cfg: Config | None = None, n_cities: int | None = None,
             districts: tuple[str, ...] | None = None) -> Plan:
    """Best plan for n_cities new cities, each with one of each district.
    cfg: a Config (None: config/default.toml); n_cities, districts override it."""
    cfg = cfg or config.default()
    inst = prepare(gmap, rules, cfg, cfg.n_cities if n_cities is None else n_cities,
                   cfg.districts if districts is None else districts, cfg.max_city_candidates)
    m = build(inst)
    sol = m.solve(cfg.solver)
    plan = Plan(log=sol.log, info={"status": sol.status, "seconds": round(sol.seconds, 3), "objective": sol.objective,
                                   "city_candidates": len(inst.sites), **sol.stats})
    plan.config = cfg
    plan.model = {"constraints": [f.__name__ for f in CONSTRAINTS],
                  "objective": [f.__name__ for f in OBJECTIVE]}
    for c, v in inst.x.items():
        if sol[v] > 0.5:
            plan.cities.append(c)
    for (d, c, t), v in inst.z.items():
        if sol[v] > 0.5:
            plan.districts.append((d, t, c))
    return plan
