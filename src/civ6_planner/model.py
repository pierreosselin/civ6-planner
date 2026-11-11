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

import time
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
    improvements: list[tuple[str, XY, XY]] = field(default_factory=list)  # (improvement, tile, its city)
    info: dict[str, Any] = field(default_factory=dict)                # solver status, timings, sizes
    log: str = ""                                                     # the solver's log
    model: dict[str, list[str]] = field(default_factory=dict)         # constraints and objective terms used
    config: Config = field(default_factory=config.default)          # the settings it was made with


def site_value(gmap: GameMap, tile: Tile, cfg: Config | None = None) -> float:
    """Weighted yields of a city centre and the tiles within cfg.site_radius."""
    cfg = cfg or config.default()
    return cfg.weighted(tile) + sum(cfg.weighted(t) for t in gmap.within(tile, cfg.site_radius))


def improvement_value(rules: Rules, cfg: Config, improvement: str, tile: Tile) -> float:
    """Value of improving `tile`: the improvement's gain, plus worked_tile_factor times the
    tile's own yields (an improved tile is one the city works)."""
    return cfg.weighted(rules.improvements[improvement].yields) + cfg.worked_tile_factor * cfg.weighted(tile)


def evaluate(gmap: GameMap, rules: Rules, plan: Plan, cfg: Config | None = None) -> tuple[float, dict[str, Any]]:
    """(score, breakdown) of a plan under the model's objective, bonuses left out.
    Uses cfg, else the plan's own config."""
    cfg = cfg or plan.config
    planned: dict[XY, str] = {xy: CITY_CENTER for xy in plan.cities}
    planned.update({xy: d for d, xy, _ in plan.districts})
    improved = {xy: i for i, xy, _ in plan.improvements}
    site = adjacency = lost = improvements = 0.0
    yields: dict[str, int] = {}
    for xy in plan.cities:
        site += site_value(gmap, gmap.tiles[xy], cfg)
    for d, xy, _ in plan.districts:
        tile = gmap.tiles[xy]
        adj = rules.adjacency(gmap, tile, d, planned, improved)
        for y, v in adj.items():
            yields[y] = yields.get(y, 0) + v
        adjacency += cfg.weighted(adj)
        lost += cfg.loss_factor * cfg.weighted(tile)
    for i, xy, _ in plan.improvements:
        improvements += improvement_value(rules, cfg, i, gmap.tiles[xy])
    return site + adjacency - lost + improvements, {"site": site, "adjacency": adjacency, "lost": lost,
                                                    "improvements": improvements, "yields": yields}


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
    own: list[XY]                        # E: the player's existing cities (always there)
    specialty_left: dict[XY, int]        # existing city -> specialty districts it may still get
    spots: dict[tuple[str, XY], list[XY]]  # (district, city) -> R_{d,c}: tiles it may go on
    # Planned-next-to-planned bonuses: (d, d2, yield, change), e.g. Industrial Zone +2
    # production per neighbouring Aqueduct.
    bonuses: list[tuple[str, str, str, int]] = field(default_factory=list)
    # Improvements: I, the types to plan; (i, city) -> tiles it may go on; how many an
    # existing city may still get; (d, i, yield, change per improvement) district bonuses.
    improvements: tuple[str, ...] = ()
    ispots: dict[tuple[str, XY], list[XY]] = field(default_factory=dict)
    improvements_left: dict[XY, int] = field(default_factory=dict)
    ibonuses: list[tuple[str, str, str, float]] = field(default_factory=list)
    x: dict[XY, Var] = field(default_factory=dict)                 # city c -> x[c]
    z: dict[tuple[str, XY, XY], Var] = field(default_factory=dict)  # (d, c, t) -> z[d,c,t]
    # (d, d2, c, t) -> y: district d of city c on t gets its bonus from c's district d2
    y: dict[tuple[str, str, XY, XY], Var] = field(default_factory=dict)
    w: dict[tuple[str, XY, XY], Var] = field(default_factory=dict)       # (i, c, t) -> improvement
    # (d, i, c, u) -> q: city c's improvement i on u touches c's district d
    q: dict[tuple[str, str, XY, XY], Var] = field(default_factory=dict)


Step = Callable[[Model, "Instance"], None]   # a variable, constraint or objective function


def prepare(gmap: GameMap, rules: Rules, cfg: Config, n_cities: int | str, districts: tuple[str, ...],
            max_city_candidates: int, improvements: tuple[str, ...] = ()) -> Instance:
    """Candidate sets and site values; no variables yet. n_cities "max": as many as fit."""
    reserved = {(p["x"], p["y"]) for p in gmap.pins}   # the player's own tacks: leave those tiles alone
    tiles = [t for t in gmap if rules.can_found_city(gmap, t) and (t["x"], t["y"]) not in reserved]
    site = {(t["x"], t["y"]): site_value(gmap, t, cfg) for t in tiles}
    # On big maps keep the best sites only; the MIP then works on far fewer variables.
    tiles = sorted(tiles, key=lambda t: -site[(t["x"], t["y"])])[:max_city_candidates]
    sites = [(t["x"], t["y"]) for t in tiles]
    own, built = existing_cities(gmap)
    specialty_left = {e: max(0, cfg.max_specialty_districts - sum(rules.is_specialty(d) for d in built[e]))
                      for e in own}
    spots = {}
    for d in districts:
        for c in sites + own:
            if d in built.get(c, set()):
                continue   # that city already has it
            spots[d, c] = [(n["x"], n["y"]) for n in gmap.within(gmap.tiles[c], rules.district_range)
                           if rules.can_place_district(gmap, n, d) and (n["x"], n["y"]) not in reserved
                           and not (rules.no_adjacent_city(d) and gmap.distance(c, n) == 1)
                           and not (rules.is_aqueduct(d) and not (gmap.distance(c, n) == 1
                                                                  and rules.fresh_water_source(gmap, n)))]
    improvements = tuple(i for i in improvements if i in rules.improvements)
    ispots: dict[tuple[str, XY], list[XY]] = {}
    for c in sites + own:
        # Each city keeps only its best improvement candidates (by value): it gets at most
        # max_improvements, and fewer variables keep the full maps fast.
        options = [(improvement_value(rules, cfg, i, n), i, (n["x"], n["y"]))
                   for n in gmap.within(gmap.tiles[c], rules.district_range) if (n["x"], n["y"]) not in reserved
                   for i in improvements if rules.can_place_improvement(gmap, n, i)]
        for _, i, t in sorted(options, key=lambda o: -o[0])[:cfg.improvement_candidates]:
            ispots.setdefault((i, c), []).append(t)
    improvements_left = {e: max(0, cfg.max_improvements - n) for e, n in existing_improvements(gmap, rules).items()}
    if n_cities == "max":
        n_cities = len(sites)
    return Instance(gmap, rules, cfg, int(n_cities), tuple(districts), sites, {c: site[c] for c in sites},
                    own, specialty_left, spots, rules.neighbour_bonuses(tuple(districts)),
                    improvements, ispots, improvements_left,
                    rules.improvement_bonuses(tuple(districts), improvements))


def existing_improvements(gmap: GameMap, rules: Rules) -> dict[XY, int]:
    """Number of (plannable) improvements on the tiles each of the player's cities owns."""
    by_id = {c["id"]: (c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles}
    count = {xy: 0 for xy in by_id.values()}
    for t in gmap:
        if t["owner"] == gmap.player and t.get("city") in by_id and t.get("improvement", "NONE") in rules.improvements:
            count[by_id[t["city"]]] += 1
    return count


def existing_cities(gmap: GameMap) -> tuple[list[XY], dict[XY, set[str]]]:
    """The player's cities on the map, and the districts each already has (tiles the
    city owns holding a district)."""
    own = [(c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles]
    by_id = {c["id"]: (c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles}
    built: dict[XY, set[str]] = {xy: set() for xy in own}
    for t in gmap:
        if t["owner"] == gmap.player and t.get("city") in by_id and t["district"] not in ("NONE", CITY_CENTER):
            built[by_id[t["city"]]].add(t["district"])
    return own, built


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


def neighbour_bonus_vars(m: Model, inst: Instance) -> None:
    """y[d,d2,c,t] in [0,1]: city c's district d on t gets the bonus for touching c's
    district d2 (only where d2 can go next to t). Continuous: at an optimum it equals
    min(z[d,c,t], sum of z[d2,c,u] next to t), which is 0 or 1."""
    for d, d2, _, _ in inst.bonuses:
        for (dd, c), tiles in inst.spots.items():
            if dd != d or (d2, c) not in inst.spots:
                continue
            for t in tiles:
                if _partner_vars(inst, d2, c, t):
                    inst.y[d, d2, c, t] = m.var(("bonus", d, d2, c, t), integer=False)


def _partner_vars(inst: Instance, d2: str, c: XY, t: XY) -> list[Var]:
    """z[d2,c,u] for the tiles u next to t where city c's district d2 may go."""
    return [inst.z[d2, c, u] for u in inst.spots.get((d2, c), [])
            if inst.gmap.distance(t, u) == 1]


def improvement_vars(m: Model, inst: Instance) -> None:
    """w[i,c,t] = 1: city c's improvement i goes on tile t (within 3 of c)."""
    for (i, c), tiles in inst.ispots.items():
        for t in tiles:
            inst.w[i, c, t] = m.var(("imp", i, c, t))


def improvement_bonus_vars(m: Model, inst: Instance) -> None:
    """q[d,i,c,u] in [0,1]: city c's improvement i on u touches c's district d, for
    districts with a per-improvement bonus (Industrial Zone: quarries, mines, lumber
    mills). One d per city, so the count of improvements next to it is sum_u q.
    At an optimum q = min(w[i,c,u], sum of z[d,c,t] next to u)."""
    for d, i, _, _ in inst.ibonuses:
        for (ii, c), tiles in inst.ispots.items():
            if ii != i or (d, c) not in inst.spots:
                continue
            for u in tiles:
                if _district_next_to(inst, d, c, u):
                    inst.q[d, i, c, u] = m.var(("ibonus", d, i, c, u), integer=False)


def _district_next_to(inst: Instance, d: str, c: XY, u: XY) -> list[Var]:
    """z[d,c,t] for the tiles t next to u where city c's district d may go."""
    return [inst.z[d, c, t] for t in inst.spots.get((d, c), []) if inst.gmap.distance(t, u) == 1]


# --- Constraints -------------------------------------------------------------

def max_cities(m: Model, inst: Instance) -> None:
    """(1) At most n cities: sum_c x[c] <= n."""
    m.row([(v, 1) for v in inst.x.values()], hi=inst.n_cities)


def city_spacing(m: Model, inst: Instance) -> None:
    """(2) Cities too close to each other exclude each other.

    Pairwise x[a] + x[b] <= 1 is a weak relaxation when many cities fit, so it is
    written with cliques: for every triangle of three touching tiles, the candidates
    on or next to it are all within 3 of each other (max one city among them):
        sum_{c in K} x[c] <= 1
    These cover every conflicting pair whose shortest path is revealed; the pairs
    left (around unrevealed tiles) keep a pairwise row."""
    if inst.n_cities < 2:
        return  # one city can't clash with itself
    gmap, limit = inst.gmap, inst.rules.city_min_range
    covered: set[tuple[XY, XY]] = set()
    seen: set[frozenset[XY]] = set()
    for t in gmap:
        ring = gmap.neighbours(t)
        for a in ring:
            for b in ring:
                tri = frozenset({(t["x"], t["y"]), (a["x"], a["y"]), (b["x"], b["y"])})
                if len(tri) < 3 or tri in seen or gmap.distance(a, b) != 1:
                    continue
                seen.add(tri)
                clique = sorted({xy for v in tri for xy in
                                 [v] + [(n["x"], n["y"]) for n in gmap.neighbours(gmap.tiles[v])]
                                 if xy in inst.x})
                if len(clique) < 2 or any(gmap.distance(p, q) > limit for p in clique for q in clique):
                    continue
                m.row([(inst.x[c], 1) for c in clique], hi=1)
                covered.update((p, q) for p in clique for q in clique if p < q)
    for c in inst.sites:
        for n in gmap.within(gmap.tiles[c], limit):
            other = (n["x"], n["y"])
            if other in inst.x and c < other and (c, other) not in covered:
                m.row({inst.x[c]: 1, inst.x[other]: 1}, hi=1)


def district_needs_city(m: Model, inst: Instance) -> None:
    """(3) At most one of each district per city, and only if the city is founded:
    sum_t z[d,c,t] <= x[c] for a new city, <= 1 for an existing one."""
    for (d, c), tiles in inst.spots.items():
        if not tiles:
            continue
        if c in inst.x:
            m.row([(inst.z[d, c, t], 1) for t in tiles] + [(inst.x[c], -1)], hi=0)
        else:
            m.row([(inst.z[d, c, t], 1) for t in tiles], hi=1)


def specialty_limit(m: Model, inst: Instance) -> None:
    """(8) Population limit: at most K specialty districts per city (those with
    RequiresPopulation; not the Aqueduct or Dam):
    sum_{d specialty, t} z[d,c,t] <= K x[c] for a new city, <= K - (already built) for
    an existing one. K = problem.max_specialty_districts."""
    k = inst.cfg.max_specialty_districts
    per_city: dict[XY, list[Var]] = {}
    for (d, c, t), v in inst.z.items():
        if inst.rules.is_specialty(d):
            per_city.setdefault(c, []).append(v)
    for c, vs in per_city.items():
        if c in inst.x:
            m.row([(v, 1) for v in vs] + [(inst.x[c], -k)], hi=0)
        else:
            m.row([(v, 1) for v in vs], hi=inst.specialty_left.get(c, k))


def improvement_limit(m: Model, inst: Instance) -> None:
    """(9) At most L improvements per city (problem.max_improvements), only if it exists:
    sum_{i,t} w[i,c,t] <= L x[c] for a new city, <= L - (already improved) for an existing one.
    Also, per new city and tile, sum_i w[i,c,t] <= x[c]: implied, but much tighter."""
    k = inst.cfg.max_improvements
    per_city: dict[XY, list[Var]] = {}
    per_tile: dict[tuple[XY, XY], list[Var]] = {}
    for (i, c, t), v in inst.w.items():
        per_city.setdefault(c, []).append(v)
        if c in inst.x:
            per_tile.setdefault((c, t), []).append(v)
    for (c, t), vs in per_tile.items():
        m.row([(v, 1) for v in vs] + [(inst.x[c], -1)], hi=0)
    for c, vs in per_city.items():
        if c in inst.x:
            m.row([(v, 1) for v in vs] + [(inst.x[c], -k)], hi=0)
        else:
            m.row([(v, 1) for v in vs], hi=inst.improvements_left.get(c, k))


def improvement_bonus_link(m: Model, inst: Instance) -> None:
    """(10) q[d,i,c,u] <= w[i,c,u] and q[d,i,c,u] <= sum_{t next to u} z[d,c,t]: the
    improvement is there and touches the city's district d (at most one per city)."""
    for (d, i, c, u), v in inst.q.items():
        m.row({v: 1, inst.w[i, c, u]: -1}, hi=0)
        m.row([(v, 1)] + [(z, -1) for z in _district_next_to(inst, d, c, u)], hi=0)


def not_next_to_planned_city(m: Model, inst: Instance) -> None:
    """(5) Districts that may not touch a city centre (Encampment) stay off tiles next to
    another planned city: z[d,c,t] + x[c'] <= 1 for c' next to t. (Its own city c is
    already left out of R_c.)"""
    for (d, c, t), v in inst.z.items():
        if not inst.rules.no_adjacent_city(d):
            continue
        for n in inst.gmap.neighbours(inst.gmap.tiles[t]):
            other = (n["x"], n["y"])
            if other != c and other in inst.x:
                m.row({v: 1, inst.x[other]: 1}, hi=1)


def one_dam_per_river(m: Model, inst: Instance) -> None:
    """(7) At most one Dam per river, over all cities; none on a river that already has
    one: sum of z[dam,c,t] over the tiles t of river r <= 1 (or 0)."""
    river = inst.gmap.rivers()
    taken = {river[(t["x"], t["y"])] for t in inst.gmap
             if inst.rules.is_dam(t["district"]) and (t["x"], t["y"]) in river}
    on: dict[int, list[Var]] = {}
    for (d, c, t), v in inst.z.items():
        if inst.rules.is_dam(d) and t in river:
            on.setdefault(river[t], []).append(v)
    for r, vs in on.items():
        if len(vs) > 1 or r in taken:
            m.row([(v, 1) for v in vs], hi=0 if r in taken else 1)


def neighbour_bonus_link(m: Model, inst: Instance) -> None:
    """(6) The bonus only counts when both districts are there:
    y[d,d2,c,t] <= z[d,c,t] and y[d,d2,c,t] <= sum_{u next to t} z[d2,c,u]."""
    for (d, d2, c, t), v in inst.y.items():
        m.row({v: 1, inst.z[d, c, t]: -1}, hi=0)
        m.row([(v, 1)] + [(w, -1) for w in _partner_vars(inst, d2, c, t)], hi=0)
    # Per city, the bonus counts at most once per partner district placed (at most one):
    # sum_t y[d,d2,c,t] <= sum_u z[d2,c,u]. Implied for integer z; tightens the relaxation.
    per_city: dict[tuple[str, str, XY], list[Var]] = {}
    for (d, d2, c, t), v in inst.y.items():
        per_city.setdefault((d, d2, c), []).append(v)
    for (d, d2, c), ys in per_city.items():
        m.row([(v, 1) for v in ys] + [(inst.z[d2, c, u], -1) for u in inst.spots[d2, c]], hi=0)


def one_thing_per_tile(m: Model, inst: Instance) -> None:
    """(4) A tile holds at most one city or district: x[t] + sum z[.,.,t] <= 1."""
    occ: dict[XY, list[Var]] = {}
    for c, v in inst.x.items():
        occ.setdefault(c, []).append(v)
    for (d, c, t), v in inst.z.items():
        occ.setdefault(t, []).append(v)
    for (i, c, t), v in inst.w.items():
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


def neighbour_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change y[d,d2,c,t]: e.g. +2 production (weighted) for an Industrial Zone
    next to its city's Aqueduct. At most one d2 per city, so the count is 0 or 1."""
    value = {(d, d2): 0.0 for d, d2, _, _ in inst.bonuses}
    for d, d2, k, change in inst.bonuses:
        value[d, d2] += inst.cfg.weights[k] * change
    for (d, d2, c, t), v in inst.y.items():
        m.add_obj(v, value[d, d2])


def improvement_term(m: Model, inst: Instance) -> None:
    """+ (v(gain_i) + worked_tile_factor v(t)) w[i,c,t]: an improved tile is worked."""
    for (i, c, t), v in inst.w.items():
        m.add_obj(v, improvement_value(inst.rules, inst.cfg, i, inst.gmap.tiles[t]))


def improvement_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change q[d,i,c,t]: e.g. +1 production (weighted) per quarry next to an
    Industrial Zone, +0.5 per mine (the game's +1 per 2, taken linearly)."""
    value: dict[tuple[str, str], float] = {}
    for d, i, k, change in inst.ibonuses:
        value[d, i] = value.get((d, i), 0.0) + inst.cfg.weights[k] * change
    for (d, i, c, t), v in inst.q.items():
        m.add_obj(v, value[d, i])


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
    neighbour_bonus_vars,
    improvement_vars,
    improvement_bonus_vars,
]
CONSTRAINTS: list[Step] = [
    max_cities,
    city_spacing,
    district_needs_city,
    one_thing_per_tile,
    not_next_to_planned_city,
    one_dam_per_river,
    neighbour_bonus_link,
    specialty_limit,
    improvement_limit,
    improvement_bonus_link,
]
OBJECTIVE: list[Step] = [
    site_term,
    adjacency_term,
    covered_tile_term,
    neighbour_bonus_term,
    improvement_term,
    improvement_bonus_term,
    city_bonus_term,
    district_bonus_term,
]


Progress = Callable[[str], Any]   # e.g. print; receives one line per stage of a run


def build(inst: Instance, progress: Progress | None = None) -> Model:
    """Run the VARIABLES, CONSTRAINTS and OBJECTIVE steps; with progress, report what each
    adds (variables, rows, objective coefficients) as it goes."""
    m = Model()
    for kind, steps in (("variables", VARIABLES), ("constraints", CONSTRAINTS), ("objective", OBJECTIVE)):
        for step in steps:
            n_vars, n_rows, obj = len(m.names), len(m.rows), list(m.obj)
            step(m, inst)
            if progress is None:
                continue
            if kind == "variables":
                progress(f"  variables    {step.__name__:<26}{len(m.names) - n_vars:>8,} variables"
                         f"   total {len(m.names):>8,}")
            elif kind == "constraints":
                progress(f"  constraints  {step.__name__:<26}{len(m.rows) - n_rows:>8,} rows     "
                         f"   total {len(m.rows):>8,}")
            else:
                changed = sum(1 for a, b in zip(obj, m.obj) if a != b)
                progress(f"  objective    {step.__name__:<26}{changed:>8,} coefficients")
    return m


def optimise(gmap: GameMap, rules: Rules, cfg: Config | None = None, n_cities: int | str | None = None,
             districts: tuple[str, ...] | None = None, improvements: tuple[str, ...] | None = None,
             progress: Progress | None = None, record: Progress | None = None,
             live: bool | None = None) -> Plan:
    """Best plan for n_cities new cities with their districts and improvements, plus the
    districts and improvements the player's existing cities can still get.
    cfg: a Config (None: config/default.toml); n_cities, districts, improvements override it."""
    cfg = cfg or config.default()
    say = progress or (lambda line: None)
    start = time.perf_counter()
    say("[2/5] Candidates")
    inst = prepare(gmap, rules, cfg, cfg.n_cities if n_cities is None else n_cities,
                   cfg.districts if districts is None else districts, cfg.max_city_candidates,
                   cfg.improvements if improvements is None else improvements)
    say(f"  {len(inst.sites)} city sites (best {cfg.max_city_candidates} by site value), "
        f"{len(inst.own)} existing cities, up to {inst.n_cities} new cities")
    say(f"  {sum(len(v) for v in inst.spots.values()):,} district options over {len(inst.districts)} types, "
        f"{sum(len(v) for v in inst.ispots.values()):,} improvement options "
        f"({cfg.improvement_candidates} best per city)   {time.perf_counter() - start:.1f} s")
    say("[3/5] Building the model")
    start = time.perf_counter()
    m = build(inst, progress)
    say(f"  {len(m.names):,} variables ({sum(m.integer):,} integer), {len(m.rows):,} rows"
        f"   {time.perf_counter() - start:.1f} s")
    say(f"[4/5] Solving with HiGHS (time limit {cfg.solver.get('time_limit')} s, "
        f"gap {cfg.solver.get('mip_rel_gap')}); it minimises -objective")
    sol = m.solve(cfg.solver, live=progress is not None if live is None else live)
    if record:
        record(sol.log.rstrip())   # for a log file (the terminal shows it live when live)
    say(f"  -> {sol.status} in {sol.seconds:.1f} s, objective {sol.objective:,.2f}")
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
    for (i, c, t), v in inst.w.items():
        if sol[v] > 0.5:
            plan.improvements.append((i, t, c))
    return plan
