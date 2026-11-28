"""Districts: z[d,c,t] = 1 puts district d of the city on c on tile t.

Constraints (3) district_needs_city and (8) specialty_limit; objective terms
adjacency_term, covered_tile_term and district_bonus_term. The placement rules that
involve other cities or rivers are in district_rules.py."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance
from ..plan import CITY_CENTER
from ..values import covered_value


def district_vars(m: Model, inst: Instance) -> None:
    """z[d,c,t] = 1: district d of the city on c goes on tile t (t within its range)."""
    for (d, c), tiles in inst.spots.items():
        for t in tiles:
            inst.z[d, c, t] = m.var(("dist", d, c, t))


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


def adjacency_term(m: Model, inst: Instance) -> None:
    """+ a[d,c,t] z[d,c,t]: the district's adjacency, a constant per (city, tile).
    Counts existing districts and the district's own city centre as planned; other
    planned districts aren't (left out on purpose: coupling them made HiGHS slow)."""
    for (d, c, t), v in inst.z.items():
        adj = inst.rules.adjacency(inst.gmap, inst.gmap.tiles[t], d, {c: CITY_CENTER})
        m.add_obj(v, inst.cfg.weighted(adj))


def covered_tile_term(m: Model, inst: Instance) -> None:
    """- loss_factor v(t) z[d,c,t]: part of the yields of the tile a district covers."""
    for (d, c, t), v in inst.z.items():
        m.add_obj(v, -covered_value(inst.cfg, inst.gmap.tiles[t]))


def district_bonus_term(m: Model, inst: Instance) -> None:
    """+ district_bonus z[d,c,t]: build the districts whenever possible, except those in
    no_bonus_districts (the Entertainment Complex: only where its amenities, or the
    Colosseum next to it, pay for the slot)."""
    for (d, c, t), v in inst.z.items():
        if d not in inst.cfg.no_bonus_districts:
            m.add_obj(v, inst.cfg.district_bonus)
