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

Timing (optional, cfg.timing.periods > 0): see the Timing section below and
docs/model.html §15. Each city and district gets the period it is ready in, and the
objective counts yields over the horizon; "sequential" mode solves the static model
first and then only the timing.

`evaluate` scores any plan (the greedy one too) in plain Python. It counts every
planned district, so it can be above the MIP's objective when planned districts touch.
"""
from __future__ import annotations

import dataclasses
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
    timing: dict[XY, int] = field(default_factory=dict)  # timed model: tile -> period its city/district is built in


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
    Uses cfg, else the plan's own config. A timed plan (plan.timing) is scored as the
    timed model does: per-turn yields times the turns they count."""
    cfg = cfg or plan.config
    if plan.timing and cfg.timing.periods:
        return _evaluate_timed(gmap, rules, plan, cfg)
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


def _evaluate_timed(gmap: GameMap, rules: Rules, plan: Plan, cfg: Config) -> tuple[float, dict[str, Any]]:
    """evaluate() for a timed plan: something ready in period p counts T (P - p + 1) turns
    (improvements: from delay(r) periods after their city's founding; the player's
    existing cities' from period 1); without a period (after the horizon), nothing."""
    tm = cfg.timing
    T, P = tm.turns_per_period, tm.periods
    planned: dict[XY, str] = {xy: CITY_CENTER for xy in plan.cities}
    planned.update({xy: d for d, xy, _ in plan.districts})
    improved = {xy: i for i, xy, _ in plan.improvements}
    site = adjacency = lost = improvements = 0.0
    yields: dict[str, int] = {}
    later = P + 1   # no period: after the horizon, counts nothing
    for xy in plan.cities:
        site += T * (P + 1 - plan.timing.get(xy, later)) * site_value(gmap, gmap.tiles[xy], cfg)
    for d, xy, _ in plan.districts:
        turns = T * (P + 1 - plan.timing.get(xy, later))
        adj = rules.adjacency(gmap, gmap.tiles[xy], d, planned, improved)
        for y, v in adj.items():
            yields[y] = yields.get(y, 0) + v
        adjacency += turns * (tm.district_base_value + cfg.weighted(adj))
        lost += turns * cfg.loss_factor * cfg.weighted(gmap.tiles[xy])
    for i, xy, c in plan.improvements:
        if c in plan.cities:
            turns = T * max(0, P + 1 - plan.timing.get(c, later) - tm.delay(gmap.distance(c, xy)))
        else:
            turns = T * P   # the player's existing cities: their borders are there
        improvements += turns * improvement_value(rules, cfg, i, gmap.tiles[xy])
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
    # Timing (cfg.timing.periods > 0; see the Timing section):
    f: dict[tuple[XY, int], Var] = field(default_factory=dict)           # (c, p): city c founded in period p
    b: dict[tuple[str, XY, int], Var] = field(default_factory=dict)      # (d, c, p): c's district d built by p
    u: dict[tuple[str, XY, int], Var] = field(default_factory=dict)      # (d, c, p): its net yield counted in p
    # (i, c, t, p): improvement option w[i,c,t] of a new city c founded in period p
    wp: dict[tuple[str, XY, XY, int], Var] = field(default_factory=dict)

    @property
    def periods(self) -> int:
        return self.cfg.timing.periods


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
# Static model: each yield counted once. Timed model (periods > 0): per-turn yields times
# the turns they count (from the period the city/district is ready in), through f, u, wp.

def _adjacency_value(inst: Instance, d: str, c: XY, t: XY) -> float:
    """Weighted adjacency of city c's district d on t (existing districts and c's centre)."""
    return inst.cfg.weighted(inst.rules.adjacency(inst.gmap, inst.gmap.tiles[t], d, {c: CITY_CENTER}))


def _loss_value(inst: Instance, t: XY) -> float:
    """Weighted yields lost by covering t with a district (loss_factor of the tile's)."""
    return inst.cfg.loss_factor * inst.cfg.weighted(inst.gmap.tiles[t])


def _bonus_values(inst: Instance) -> dict[tuple[str, str], float]:
    """(d, d2) -> weighted bonus of district d touching its city's district d2."""
    value: dict[tuple[str, str], float] = {}
    for d, d2, k, change in inst.bonuses:
        value[d, d2] = value.get((d, d2), 0.0) + inst.cfg.weights[k] * change
    return value


def _ibonus_values(inst: Instance) -> dict[tuple[str, str], float]:
    """(d, i) -> weighted bonus of district d per touching improvement i."""
    value: dict[tuple[str, str], float] = {}
    for d, i, k, change in inst.ibonuses:
        value[d, i] = value.get((d, i), 0.0) + inst.cfg.weights[k] * change
    return value


def site_term(m: Model, inst: Instance) -> None:
    """+ s_c x[c]: weighted yields of the city centre and the tiles within site_radius.
    Timed: + T (P - p + 1) s_c f[c,p], counted from the founding period on."""
    if inst.periods:
        T, P = inst.cfg.timing.turns_per_period, inst.periods
        for (c, p), v in inst.f.items():
            m.add_obj(v, T * (P - p + 1) * inst.site[c])
        return
    for c, v in inst.x.items():
        m.add_obj(v, inst.site[c])


def adjacency_term(m: Model, inst: Instance) -> None:
    """+ a[d,c,t] z[d,c,t]: the district's adjacency, a constant per (city, tile).
    Counts existing districts and the district's own city centre as planned; other
    planned districts aren't (see the module docstring).
    Timed: + T u[d,c,p], the district's net yield (base, adjacency, bonuses, minus the
    covered tile) in each period from the one it is ready in."""
    if inst.periods:
        for v in inst.u.values():
            m.add_obj(v, inst.cfg.timing.turns_per_period)
        return
    for (d, c, t), v in inst.z.items():
        m.add_obj(v, _adjacency_value(inst, d, c, t))


def covered_tile_term(m: Model, inst: Instance) -> None:
    """- loss_factor v(t) z[d,c,t]: part of the yields of the tile a district covers.
    Timed: inside u (adjacency_term), from the period the district is ready in."""
    if inst.periods:
        return
    for (d, c, t), v in inst.z.items():
        m.add_obj(v, -_loss_value(inst, t))


def neighbour_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change y[d,d2,c,t]: e.g. +2 production (weighted) for an Industrial Zone
    next to its city's Aqueduct. At most one d2 per city, so the count is 0 or 1.
    Timed: inside u (adjacency_term), from the period d is ready in."""
    if inst.periods:
        return
    value = _bonus_values(inst)
    for (d, d2, c, t), v in inst.y.items():
        m.add_obj(v, value[d, d2])


def improvement_term(m: Model, inst: Instance) -> None:
    """+ (v(gain_i) + worked_tile_factor v(t)) w[i,c,t]: an improved tile is worked.
    Timed: value x T x the periods it counts: from delay(r) periods after the city's
    founding period on, r = distance to the city (the player's existing cities: every
    period, their borders are there)."""
    if inst.periods:
        T, P = inst.cfg.timing.turns_per_period, inst.periods
        for (i, c, t), v in inst.w.items():
            value = improvement_value(inst.rules, inst.cfg, i, inst.gmap.tiles[t])
            delay = inst.cfg.timing.delay(inst.gmap.distance(c, t))
            if c in inst.x:
                for p in range(1, P + 1):
                    m.add_obj(inst.wp[i, c, t, p], value * T * max(0, P - p - delay + 1))
            else:
                m.add_obj(v, value * T * P)
        return
    for (i, c, t), v in inst.w.items():
        m.add_obj(v, improvement_value(inst.rules, inst.cfg, i, inst.gmap.tiles[t]))


def improvement_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change q[d,i,c,t]: e.g. +1 production (weighted) per quarry next to an
    Industrial Zone, +0.5 per mine (the game's +1 per 2, taken linearly).
    Timed: inside u (adjacency_term), from the period d is ready in."""
    if inst.periods:
        return
    value = _ibonus_values(inst)
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


# --- Timing (cfg.timing.periods = P > 0; every step does nothing when P = 0) ---------
# Periods p = 1..P of T turns; something ready in period p counts in periods p..P,
# T (P - p + 1) turns. "Where" stays in x, z, w; "when" is per city and per
# (district, city), without a tile index, so the model grows by a few variables per
# city and period only:
#   f[c,p]    binary, city c founded in period p        sum_p f[c,p] <= x[c]
#   b[d,c,p]  binary, c's district d built by period p  monotone, b[d,c,P] <= sum_t z[d,c,t]
#   (a placement with no period comes after the horizon: only its placement bonus counts)
#   u[d,c,p]  continuous, d's net per-turn yield counted in period p:
#             u <= A[d,c] + L(1 - b[d,c,p]),  u <= M b[d,c,p],  -L <= u <= M
#             with A = sum_t (base + adjacency - covered tile) z + bonuses (y, q): u = A once
#             built, else 0 (base = district_base_value, for the district's buildings)
#   wp[i,c,t,p]  improvement option w[i,c,t] of a new city founded in p (exact, no big M);
#             it counts from delay(distance) periods after founding
# F[c,q] = sum_{p<=q} f[c,p] (founded by q; 1 for the player's existing cities).

def _founded_by(inst: Instance, c: XY, q: int) -> tuple[list[tuple[Var, float]], float]:
    """F[c,q] as (terms, constant)."""
    if c not in inst.x:
        return [], 1.0 if q >= 0 else 0.0
    return [(inst.f[c, p], 1.0) for p in range(1, q + 1)], 0.0


def _district_net(inst: Instance) -> dict[tuple[str, XY], tuple[list[tuple[Var, float]], float, float]]:
    """(d, c) -> (A's terms, M = largest A, L = largest loss)."""
    bonus, ibonus = _bonus_values(inst), _ibonus_values(inst)
    out: dict[tuple[str, XY], tuple[list[tuple[Var, float]], float, float]] = {}
    for (d, c), tiles in inst.spots.items():
        if not tiles:
            continue
        base = inst.cfg.timing.district_base_value
        terms = [(inst.z[d, c, t], base + _adjacency_value(inst, d, c, t) - _loss_value(inst, t)) for t in tiles]
        best = base + max(_adjacency_value(inst, d, c, t) for t in tiles)
        out[d, c] = (terms, best, max(_loss_value(inst, t) for t in tiles))
    extra: dict[tuple[str, XY], float] = {}
    for (d, d2, c, t), v in inst.y.items():
        out[d, c][0].append((v, bonus[d, d2]))
        extra.setdefault((d, c), 0.0)
    for d, d2, c in {(d, d2, c) for d, d2, c, _ in inst.y}:
        extra[d, c] += bonus[d, d2]
    for (d, i, c, u), v in inst.q.items():
        out[d, c][0].append((v, ibonus[d, i]))
    for d, i, c in {(d, i, c) for d, i, c, _ in inst.q}:
        n = inst.improvements_left.get(c, inst.cfg.max_improvements)
        extra[d, c] = extra.get((d, c), 0.0) + ibonus[d, i] * n
    return {k: (terms, m + extra.get(k, 0.0), loss) for k, (terms, m, loss) in out.items()}


def timing_vars(m: Model, inst: Instance) -> None:
    """f[c,p], b[d,c,p], u[d,c,p] (only where the district has some value), and
    wp[i,c,t,p] for each improvement option of a new city."""
    P = inst.periods
    if not P:
        return
    for c in inst.sites:
        for p in range(1, P + 1):
            inst.f[c, p] = m.var(("found", c, p))
    for (d, c), (terms, best, loss) in _district_net(inst).items():
        for p in range(1, P + 1):
            inst.b[d, c, p] = m.var(("built", d, c, p))
        if best > 0 or loss > 0:
            for p in range(1, P + 1):
                inst.u[d, c, p] = m.var(("dyield", d, c, p), lb=-loss, ub=best, integer=False)
    for (i, c, t), w in inst.w.items():
        if c in inst.x:
            for p in range(1, P + 1):
                inst.wp[i, c, t, p] = m.var(("imp_when", i, c, t, p), integer=False)


def timing_link(m: Model, inst: Instance) -> None:
    """(T1) sum_p f[c,p] <= x[c]; b[d,c,p-1] <= b[d,c,p]; b[d,c,P] <= sum_t z[d,c,t];
    sum_p wp[i,c,t,p] <= w[i,c,t] and wp[i,c,t,p] <= f[c,p] (the improvement takes its
    city's founding period; continuous, as f is binary). <=, not =: a placement may come
    after the horizon (no period), where it counts nothing but its placement bonus."""
    P = inst.periods
    if not P:
        return
    for c, x in inst.x.items():
        m.row([(inst.f[c, p], 1) for p in range(1, P + 1)] + [(x, -1)], hi=0)
    for (d, c) in {(d, c) for d, c, _ in inst.b}:
        for p in range(2, P + 1):
            m.row({inst.b[d, c, p - 1]: 1, inst.b[d, c, p]: -1}, hi=0)
        m.row([(inst.b[d, c, P], 1)] + [(inst.z[d, c, t], -1) for t in inst.spots[d, c]], hi=0)
    for (i, c, t), w in inst.w.items():
        if c in inst.x:
            m.row([(inst.wp[i, c, t, p], 1) for p in range(1, P + 1)] + [(w, -1)], hi=0)
            for p in range(1, P + 1):
                m.row({inst.wp[i, c, t, p]: 1, inst.f[c, p]: -1}, hi=0)


def settler_schedule(inst: Instance) -> list[int]:
    """N_p, p = 0..P: the most new cities founded by the end of period p, whole settlers
    only: N_p = N_{p-1} + floor(a + k_p (existing cities + N_{p-1})),
    k_p = T / turns_per_settler x speedup(p)."""
    tm = inst.cfg.timing
    n = [0]
    for p in range(1, inst.periods + 1):
        k = tm.turns_per_period / tm.turns_per_settler * tm.speedup(p)
        n.append(n[-1] + int(tm.settlers_base + k * (len(inst.own) + n[-1]) + 1e-9))
    return n


def settler_capacity(m: Model, inst: Instance) -> None:
    """(T2) Cities take time: at most N_p new cities founded by the end of period p
    (settler_schedule): sum_c F[c,p] <= N_p. The schedule assumes the earlier periods
    founded as many as they could, so it is an upper bound, not tied to the plan."""
    if not inst.periods or not inst.f:
        return
    n = settler_schedule(inst)
    for p in range(1, inst.periods + 1):
        if n[p] < len(inst.sites):
            m.row([(inst.f[c, q], 1) for c in inst.sites for q in range(1, p + 1)], hi=n[p])


def district_after_city(m: Model, inst: Instance) -> None:
    """(T3) A district is built at least one period after its city: b[d,c,p] <= F[c,p-1]."""
    if not inst.periods:
        return
    for (d, c, p), v in inst.b.items():
        if c in inst.x:
            terms, _ = _founded_by(inst, c, p - 1)
            m.row([(v, 1)] + [(f, -a) for f, a in terms], hi=0)


def build_capacity(m: Model, inst: Instance) -> None:
    """(T4) Districts take time: per city and period at most k_p new districts,
    k_p = T / turns_per_district x speedup(p):
    sum_d (b[d,c,p] - b[d,c,p-1]) <= k_p F[c,p-1]."""
    tm = inst.cfg.timing
    if not inst.periods:
        return
    per_city: dict[XY, set[str]] = {}
    for d, c, _ in inst.b:
        per_city.setdefault(c, set()).add(d)
    for c, ds in per_city.items():
        for p in range(1, inst.periods + 1):
            k = tm.turns_per_period / tm.turns_per_district * tm.speedup(p)
            terms, const = _founded_by(inst, c, p - 1)
            row = [(inst.b[d, c, p], 1) for d in ds] + [(inst.b[d, c, p - 1], -1) for d in ds if p > 1]
            m.row(row + [(f, -k * a) for f, a in terms], hi=k * const)


def _specialty_cap(inst: Instance, age: int) -> int:
    """Specialty districts a city may have after `age` periods: 1 + one per
    turns_per_specialty turns, at most max_specialty_districts (the population limit)."""
    tm = inst.cfg.timing
    return min(inst.cfg.max_specialty_districts, 1 + int(age * tm.turns_per_period // tm.turns_per_specialty))


def population_by_age(m: Model, inst: Instance) -> None:
    """(T5) Specialty districts built by p are limited by the city's age (population):
    sum_{d specialty} b[d,c,p] <= sum_{q<p} cap(p - q) f[c,q], for new cities (existing
    ones keep specialty_limit)."""
    if not inst.periods:
        return
    per_city: dict[XY, list[str]] = {}
    for d, c, p in inst.b:
        if p == 1 and c in inst.x and inst.rules.is_specialty(d):
            per_city.setdefault(c, []).append(d)
    for c, ds in per_city.items():
        for p in range(1, inst.periods + 1):
            m.row([(inst.b[d, c, p], 1) for d in ds]
                  + [(inst.f[c, q], -_specialty_cap(inst, p - q)) for q in range(1, p)], hi=0)


def ring_delay(m: Model, inst: Instance) -> None:
    """(T6) Farther tiles are usable later: a tile at distance r from a new city is
    usable delay(r) periods after its founding period, so a district there is ready in
    p >= founding + max(1, delay(r)) (one period is already district_after_city):
    b[d,c,p] + sum_{t at r} z[d,c,t] - F[c, p - delay(r)] <= 1, for delay(r) >= 2."""
    tm = inst.cfg.timing
    if not inst.periods:
        return
    for (d, c), tiles in inst.spots.items():
        if c not in inst.x or not tiles:
            continue
        by_ring: dict[int, list[XY]] = {}
        for t in tiles:
            by_ring.setdefault(inst.gmap.distance(c, t), []).append(t)
        for r, ts in by_ring.items():
            delay = tm.delay(r)
            if delay < 2:
                continue
            for p in range(1, inst.periods + 1):
                terms, _ = _founded_by(inst, c, p - delay)
                m.row([(inst.b[d, c, p], 1)] + [(inst.z[d, c, t], 1) for t in ts]
                      + [(f, -a) for f, a in terms], hi=1)


def timed_value_link(m: Model, inst: Instance) -> None:
    """(T7) u = the district's net yield A once built, else 0:
    u[d,c,p] <= A + L (1 - b[d,c,p]) and u[d,c,p] <= M b[d,c,p]."""
    if not inst.periods:
        return
    net = _district_net(inst)
    for (d, c, p), u in inst.u.items():
        terms, best, loss = net[d, c]
        b = inst.b[d, c, p]
        m.row([(u, 1), (b, loss)] + [(v, -a) for v, a in terms], hi=loss)
        m.row({u: 1, b: -best}, hi=0)



VARIABLES: list[Step] = [
    city_vars,
    district_vars,
    neighbour_bonus_vars,
    improvement_vars,
    improvement_bonus_vars,
    timing_vars,
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
    timing_link,
    settler_capacity,
    district_after_city,
    build_capacity,
    population_by_age,
    ring_delay,
    timed_value_link,
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
    cfg: a Config (None: config/default.toml); n_cities, districts, improvements override it.
    Timed (cfg.timing.periods > 0): mode "sequential" solves the static model (where),
    then the timed one with those placements fixed (when); "joint" solves the timed model
    alone, where and when together (slow beyond small maps)."""
    cfg = cfg or config.default()
    say = progress or (lambda line: None)
    live = progress is not None if live is None else live
    start = time.perf_counter()
    say("[2/5] Candidates")
    n = cfg.n_cities if n_cities is None else n_cities
    ds = cfg.districts if districts is None else districts
    imps = cfg.improvements if improvements is None else improvements
    inst = prepare(gmap, rules, cfg, n, ds, cfg.max_city_candidates, imps)
    say(f"  {len(inst.sites)} city sites (best {cfg.max_city_candidates} by site value), "
        f"{len(inst.own)} existing cities, up to {inst.n_cities} new cities")
    say(f"  {sum(len(v) for v in inst.spots.values()):,} district options over {len(inst.districts)} types, "
        f"{sum(len(v) for v in inst.ispots.values()):,} improvement options "
        f"({cfg.improvement_candidates} best per city)   {time.perf_counter() - start:.1f} s")
    tm = cfg.timing
    if tm.periods and tm.mode == "sequential":
        static = dataclasses.replace(cfg, timing=dataclasses.replace(tm, periods=0))
        say(f"  timed, sequential: first where (the static model), then when ({tm.periods} periods "
            f"of {tm.turns_per_period} turns) with those placements fixed")
        where = _solve(prepare(gmap, rules, static, n, ds, cfg.max_city_candidates, imps), static,
                       say, progress, record, live, "where: ")
        if where.info["status"] not in ("optimal", "time limit") or not (where.cities or where.districts
                                                                            or where.improvements):
            return where
        plan = _solve(inst, cfg, say, progress, record, live, "when: ", fixed=where)
        plan.info["where"] = {k: where.info.get(k) for k in ("status", "seconds", "objective", "mip_gap")}
        return plan
    return _solve(inst, cfg, say, progress, record, live, "")


def _solve(inst: Instance, cfg: Config, say: Progress, progress: Progress | None, record: Progress | None,
           live: bool, stage: str, fixed: Plan | None = None) -> Plan:
    """Build and solve one model; with `fixed`, its cities, districts and improvements are
    fixed (x, z, w set to the plan's), so only the timing is left to decide."""
    say(f"[3/5] {stage}Building the model")
    start = time.perf_counter()
    m = build(inst, progress)
    if fixed is not None:
        chosen = ({("city", c) for c in fixed.cities} | {("dist", d, c, t) for d, t, c in fixed.districts}
                  | {("imp", i, c, t) for i, t, c in fixed.improvements})
        for v in list(inst.x.values()) + list(inst.z.values()) + list(inst.w.values()):
            m.fix(v, 1.0 if v in chosen else 0.0)
    say(f"  {len(m.names):,} variables ({sum(m.integer):,} integer), {len(m.rows):,} rows"
        + (", placements fixed" if fixed is not None else "") + f"   {time.perf_counter() - start:.1f} s")
    say(f"[4/5] {stage}Solving with HiGHS (time limit {cfg.solver.get('time_limit')} s, "
        f"gap {cfg.solver.get('mip_rel_gap')}); it minimises -objective")
    sol = m.solve(cfg.solver, live=live)
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
    if inst.periods:
        for (c, p), v in inst.f.items():
            if sol[v] > 0.5:
                plan.timing[c] = p
        for d, t, c in plan.districts:
            built = [p for p in range(1, inst.periods + 1) if sol[inst.b[d, c, p]] > 0.5]
            if built:
                plan.timing[t] = built[0]
        # C1 is founded first; cities after the horizon last
        plan.cities.sort(key=lambda c: plan.timing.get(c, inst.periods + 1))
    return plan
