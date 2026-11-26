"""Bonuses between a city's own planned districts (Industrial Zone next to its Aqueduct
or Dam, Commercial Hub next to its Harbor): y[d,d2,c,t].

Constraint (6) neighbour_bonus_link; objective term neighbour_bonus_term."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance


def _partner_vars(inst: Instance, d2: str, c: XY, t: XY) -> list[Var]:
    """z[d2,c,u] for the tiles u next to t where city c's district d2 may go."""
    return [inst.z[d2, c, u] for u in inst.spots.get((d2, c), []) if inst.gmap.distance(t, u) == 1]


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


def neighbour_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change y[d,d2,c,t]: e.g. +2 production (weighted) for an Industrial Zone
    next to its city's Aqueduct. At most one d2 per city, so the count is 0 or 1."""
    value: dict[tuple[str, str], float] = {}
    for d, d2, k, change in inst.bonuses:
        value[d, d2] = value.get((d, d2), 0.0) + inst.cfg.weights[k] * change
    for (d, d2, c, t), v in inst.y.items():
        m.add_obj(v, value[d, d2])
