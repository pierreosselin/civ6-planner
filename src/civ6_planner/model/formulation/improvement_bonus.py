"""Bonuses between a city's district and its planned improvements (Industrial Zone next
to quarries, mines, lumber mills): q[d,i,c,u].

Constraint (10) improvement_bonus_link; objective term improvement_bonus_term."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance


def _district_next_to(inst: Instance, d: str, c: XY, u: XY) -> list[Var]:
    """z[d,c,t] for the tiles t next to u where city c's district d may go."""
    return [inst.z[d, c, t] for t in inst.spots.get((d, c), []) if inst.gmap.distance(t, u) == 1]


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


def improvement_bonus_link(m: Model, inst: Instance) -> None:
    """(10) q[d,i,c,u] <= w[i,c,u] and q[d,i,c,u] <= sum_{t next to u} z[d,c,t]: the
    improvement is there and touches the city's district d (at most one per city)."""
    for (d, i, c, u), v in inst.q.items():
        m.row({v: 1, inst.w[i, c, u]: -1}, hi=0)
        m.row([(v, 1)] + [(z, -1) for z in _district_next_to(inst, d, c, u)], hi=0)


def improvement_bonus_term(m: Model, inst: Instance) -> None:
    """+ w_k change q[d,i,c,t]: e.g. +1 production (weighted) per quarry next to an
    Industrial Zone, +0.5 per mine (the game's +1 per 2, taken linearly)."""
    value: dict[tuple[str, str], float] = {}
    for d, i, k, change in inst.ibonuses:
        value[d, i] = value.get((d, i), 0.0) + inst.cfg.weights[k] * change
    for (d, i, c, t), v in inst.q.items():
        m.add_obj(v, value[d, i])
