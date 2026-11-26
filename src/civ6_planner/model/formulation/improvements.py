"""Tile improvements: w[i,c,t] = 1 puts city c's improvement i on tile t.

Constraint (9) improvement_limit; objective term improvement_term."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance
from ..values import improvement_value


def improvement_vars(m: Model, inst: Instance) -> None:
    """w[i,c,t] = 1: city c's improvement i goes on tile t (within 3 of c)."""
    for (i, c), tiles in inst.ispots.items():
        for t in tiles:
            inst.w[i, c, t] = m.var(("imp", i, c, t))


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


def improvement_term(m: Model, inst: Instance) -> None:
    """+ (v(gain_i) + worked_tile_factor v(t)) w[i,c,t]: an improved tile is worked."""
    for (i, c, t), v in inst.w.items():
        m.add_obj(v, improvement_value(inst.rules, inst.cfg, i, inst.gmap.tiles[t]))
