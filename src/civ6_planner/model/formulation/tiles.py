"""(4) one_thing_per_tile: a tile holds at most one city, district or improvement."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance


def one_thing_per_tile(m: Model, inst: Instance) -> None:
    """(4) A tile holds at most one thing: x[t] + sum z[.,.,t] + sum w[.,.,t] <= 1."""
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
