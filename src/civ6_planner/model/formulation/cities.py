"""New cities: x[c] = 1 founds a city on candidate tile c.

Constraints (1) max_cities and (2) city_spacing; objective terms site_term and
city_bonus_term (docs/model.html §7–9)."""
from __future__ import annotations

from ...gamemap import XY
from ...solver import Model
from ..instance import Instance


def city_vars(m: Model, inst: Instance) -> None:
    """x[c] = 1: found a city on candidate tile c."""
    for c in inst.sites:
        inst.x[c] = m.var(("city", c))


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


def site_term(m: Model, inst: Instance) -> None:
    """+ s_c x[c]: weighted yields of the city centre and the tiles within site_radius."""
    for c, v in inst.x.items():
        m.add_obj(v, inst.site[c])


def city_bonus_term(m: Model, inst: Instance) -> None:
    """+ city_bonus x[c]: found the cities asked for whenever possible."""
    for v in inst.x.values():
        m.add_obj(v, inst.cfg.city_bonus)
