"""Regional buildings (objective.regional_buildings, off by default, e.g. the Factory:
+3 production to every city within 6 tiles of an Industrial Zone, across cities):
r[b,c] and on[d,t].

Constraint (11) regional_reach; objective term regional_term. Slows the big maps: on,
continents and shuffle end 7–30% from optimal at 60 s."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..existing import own_districts
from ..instance import Instance
from ..values import regional_value


def regional_vars(m: Model, inst: Instance) -> None:
    """r[b,c] in [0, 1]: city c (new or existing) gets regional building b's effect;
    on[d,t] in [0, 1]: a planned district d is on tile t, whichever city it belongs to
    (keeps the reach rows short: one term per tile, not per city). An existing city
    already in range of one of the player's districts gets it for sure (r fixed to 1)."""
    for b in inst.cfg.regional_buildings:
        rb = inst.rules.regional.get(b)
        if rb is None:
            continue
        existing = own_districts(inst.gmap, rb.district)
        for c in inst.sites + inst.own:
            sure = c in inst.own and any(inst.gmap.distance(c, t) <= rb.range for t in existing)
            inst.r[b, c] = m.var(("regional", b, c), lb=1 if sure else 0, integer=False)
        for (d, c, t) in inst.z:
            if d == rb.district and (d, t) not in inst.on:
                inst.on[d, t] = m.var(("on", d, t), integer=False)


def regional_reach(m: Model, inst: Instance) -> None:
    """(11) A city gets a regional building's effect only if it exists and a district of
    the building's type is within range: r[b,c] <= x[c] (new city) and
    r[b,c] <= sum_{t within range of c} on[d,t] (unless an existing district already
    reaches it), with on[d,t] <= sum_{c'} z[d,c',t]."""
    by_tile: dict[tuple[str, XY], list[Var]] = {}
    for (d, c, t), v in inst.z.items():
        if (d, t) in inst.on:
            by_tile.setdefault((d, t), []).append(v)
    for key, zs in by_tile.items():
        m.row([(inst.on[key], 1)] + [(z, -1) for z in zs], hi=0)
    for (b, c), v in inst.r.items():
        rb = inst.rules.regional[b]
        if c in inst.x:
            m.row({v: 1, inst.x[c]: -1}, hi=0)
        if any(inst.gmap.distance(c, t) <= rb.range for t in own_districts(inst.gmap, rb.district)):
            continue
        near = [inst.on[rb.district, (n["x"], n["y"])] for n in inst.gmap.within(c, rb.range)
                if (rb.district, (n["x"], n["y"])) in inst.on]
        m.row([(v, 1)] + [(o, -1) for o in near], hi=0)


def regional_term(m: Model, inst: Instance) -> None:
    """+ g_b r[b,c]: the building's weighted yields for each city it reaches (Factory:
    +3 production)."""
    for (b, c), v in inst.r.items():
        m.add_obj(v, regional_value(inst.rules, inst.cfg, b))
