"""Placement rules for districts that involve other cities or whole rivers:
(5) not_next_to_planned_city (Encampment) and (7) one_dam_per_river."""
from __future__ import annotations

from ...solver import Model, Var
from ..instance import Instance


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
