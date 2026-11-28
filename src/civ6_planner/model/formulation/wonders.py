"""World wonders (problem.wonders, e.g. the Colosseum): k[b,t] = 1 builds wonder b on
tile t, by a city that has t within range and, if the wonder needs one, its district
next to t (the Colosseum: an Entertainment Complex).

Constraints (12) wonder_needs_district and (13) one_of_each_wonder; objective term
wonder_term. A wonder's amenities are counted in amenities.py.

k has no city index: the city is the one whose district enables it (read back in
postprocess.py), which keeps the amenity rows short (one term per tile)."""
from __future__ import annotations

from ...solver import Model, Var
from ..instance import Instance
from ..values import wonder_value


def wonder_vars(m: Model, inst: Instance) -> None:
    """k[b,t] = 1: wonder b goes on tile t."""
    for b, t in inst.wspots:
        inst.k[b, t] = m.var(("wonder", b, t))


def wonder_needs_district(m: Model, inst: Instance) -> None:
    """(12) A wonder goes only where one of the cities in range can build it: next to that
    city's district of the type it needs (z[d,c,u], u next to t), or simply in the city's
    range if it needs none (x[c]):  k[b,t] <= sum over those of z[d,c,u] (or x[c]).
    No row when an existing city already qualifies (its district is built)."""
    for (b, t), support in inst.wspots.items():
        d = inst.rules.wonders[b].adjacent_district
        terms: list[Var] = []
        for c, u in support:
            var = inst.x.get(c) if u is None else inst.z.get((d, c, u)) if d else None
            if var is None:
                break   # an existing city with the district built (or no district needed)
            terms.append(var)
        else:
            m.row([(inst.k[b, t], 1)] + [(v, -1) for v in dict.fromkeys(terms)], hi=0)


def one_of_each_wonder(m: Model, inst: Instance) -> None:
    """(13) One of each wonder in the world, and no more than the districts that could
    enable it:  sum_t k[b,t] <= 1  and  sum_t k[b,t] <= sum of the z[d,c,u] in (12).
    The second is implied for integers, but without it the LP puts a whole wonder next
    to a fraction of a district (one z supports k on each of its six neighbours)."""
    per: dict[str, list[Var]] = {}
    for (b, t), v in inst.k.items():
        per.setdefault(b, []).append(v)
    for b, vs in per.items():
        if len(vs) > 1:
            m.row([(v, 1) for v in vs], hi=1)
        enablers = _enablers(inst, b)
        if enablers is not None:
            m.row([(v, 1) for v in vs] + [(z, -1) for z in enablers], hi=0)


def _enablers(inst: Instance, b: str) -> list[Var] | None:
    """The variables of (12) for wonder b over all its tiles, each once; None if an
    existing city already qualifies somewhere."""
    d = inst.rules.wonders[b].adjacent_district
    out: dict[Var, None] = {}
    for (w, t), support in inst.wspots.items():
        if w != b:
            continue
        for c, u in support:
            var = inst.x.get(c) if u is None else inst.z.get((d, c, u)) if d else None
            if var is None:
                return None
            out[var] = None
    return list(out)


def wonder_term(m: Model, inst: Instance) -> None:
    """+ (g_b - loss_factor v(t)) k[b,t]: the wonder's own weighted yields (Colosseum:
    +2 culture), less the tile it covers."""
    for (b, t), v in inst.k.items():
        m.add_obj(v, wonder_value(inst.rules, inst.cfg, b, inst.gmap.tiles[t]))
