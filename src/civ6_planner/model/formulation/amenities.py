"""Amenities: a[c], the amenities city c gets from districts and wonders, counted up to
amenities_needed (luxuries cover the rest; more are worth nothing) and worth
amenity_value each.

Sources: its own districts' Entertainment (Entertainment Complex +1, Dam +1), wonders
within their range of the city (Colosseum: +2 within 6 tiles), and what is already
built (existing districts and the player's wonders: inst.amenity_base).

Constraint (14) amenity_supply; objective term amenity_term."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model, Var
from ..instance import Instance


def amenity_sources(inst: Instance) -> dict[XY, list[tuple[Var, int]]]:
    """City -> the planned things that would give it amenities, with how many each gives."""
    rules, gmap = inst.rules, inst.gmap
    out: dict[XY, list[tuple[Var, int]]] = {c: [] for c in inst.sites + inst.own}
    for (d, c, t), v in inst.z.items():
        if rules.entertainment.get(d, 0) > 0:
            out[c].append((v, rules.entertainment[d]))
    reach = {b: (w.entertainment, w.range) for b in inst.wonders
             if (w := rules.wonders[b]).entertainment > 0 and w.range > 0}
    if inst.k and reach:
        widest = max(r for _, r in reach.values())
        for c, sources in out.items():
            for n in gmap.within(gmap.tiles[c], widest):
                t = (n["x"], n["y"])
                for b, (amount, r) in reach.items():
                    if (b, t) in inst.k and gmap.distance(c, t) <= r:
                        sources.append((inst.k[b, t], amount))
    return out


def amenity_vars(m: Model, inst: Instance) -> None:
    """a[c] in [0, amenities_needed]: amenities counted for city c (new or existing),
    for cities that have or may get any."""
    cap = inst.cfg.amenities_needed
    if cap <= 0 or inst.cfg.amenity_value == 0:
        return
    for c, sources in amenity_sources(inst).items():
        if sources or inst.amenity_base.get(c, 0) > 0:
            inst.a[c] = m.var(("amenities", c), ub=cap, integer=False)


def amenity_supply(m: Model, inst: Instance) -> None:
    """(14) A city counts only the amenities it gets, and only if it exists:
    a[c] <= base_c + sum_d e_d z[d,c,t] + sum_{b, t within range_b of c} e_b k[b,t],
    and a[c] <= amenities_needed x[c] for a new city."""
    if not inst.a:
        return
    cap = inst.cfg.amenities_needed
    sources = amenity_sources(inst)
    for c, v in inst.a.items():
        m.row([(v, 1)] + [(s, -n) for s, n in sources[c]], hi=inst.amenity_base.get(c, 0))
        if c in inst.x:
            m.row({v: 1, inst.x[c]: -cap}, hi=0)


def amenity_term(m: Model, inst: Instance) -> None:
    """+ amenity_value a[c]."""
    for v in inst.a.values():
        m.add_obj(v, inst.cfg.amenity_value)
