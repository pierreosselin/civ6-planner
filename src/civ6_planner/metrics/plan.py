"""Statistics of a plan, for the logs: how many districts each city gets, how often each
district type is planned, what adjacency the planned districts get, how the cities are
spaced.

Adjacency here is what the game would give with the whole plan built (every planned
city and district counted, as on the tacks), not the MIP's own coefficient.
"""
from __future__ import annotations

from typing import Any

from .. import model
from ..gamemap import XY, GameMap
from ..model import Plan, improvement_value, site_value
from ..rules import Rules


def plan_metrics(gmap: GameMap, rules: Rules, plan: Plan) -> dict[str, Any]:
    """Cities (new and existing), districts per city, and per district type: count,
    share of cities that have one, mean/min/max adjacency per yield and weighted."""
    own = [(c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles]
    cities: list[XY] = list(plan.cities) + [c for c in own if c not in plan.cities]
    planned, improved = plan.planned(), plan.improved()

    per_city: dict[XY, list[str]] = {c: [] for c in cities}
    adjacency: dict[str, list[dict[str, int]]] = {}
    for d, xy, city in plan.districts:
        per_city.setdefault(city, []).append(d)
        adjacency.setdefault(d, []).append(rules.adjacency(gmap, gmap.tiles[xy], d, planned, improved))

    imps: dict[XY, list[str]] = {c: [] for c in cities}
    ivalue: dict[str, list[float]] = {}
    for i, xy, city in plan.improvements:
        imps.setdefault(city, []).append(i)
        ivalue.setdefault(i, []).append(improvement_value(rules, plan.config, i, gmap.tiles[xy]))
    icounts = [len(v) for v in imps.values()]
    itypes = {i: {"count": len(v), "cities_with": sum(1 for x in imps.values() if i in x),
                  "share_of_cities": round(sum(1 for x in imps.values() if i in x) / len(imps), 3) if imps else 0.0,
                  "value_mean": round(sum(v) / len(v), 2)}
              for i, v in sorted(ivalue.items(), key=lambda kv: -len(kv[1]))}

    counts = [len(ds) for ds in per_city.values()]
    histogram: dict[int, int] = {}
    for n in counts:
        histogram[n] = histogram.get(n, 0) + 1

    types: dict[str, Any] = {}
    for d in sorted(adjacency, key=lambda d: -len(adjacency[d])):
        adj = adjacency[d]
        cities_with = sum(1 for ds in per_city.values() if d in ds)
        yields = sorted({k for a in adj for k in a})
        weighted = [plan.config.weighted(a) for a in adj]
        types[d] = {
            "count": len(adj),
            "cities_with": cities_with,
            "share_of_cities": round(cities_with / len(per_city), 3) if per_city else 0.0,
            "adjacency_mean": {k: round(sum(a.get(k, 0) for a in adj) / len(adj), 2) for k in yields},
            "adjacency_min_max": {k: [min(a.get(k, 0) for a in adj), max(a.get(k, 0) for a in adj)] for k in yields},
            "weighted_mean": round(sum(weighted) / len(weighted), 2),
        }
    return {
        "cities": len(per_city),
        "new_cities": len(plan.cities),
        "existing_cities": len(cities) - len(plan.cities),
        "districts": len(plan.districts),
        "districts_per_city": {
            "mean": round(sum(counts) / len(counts), 2) if counts else 0.0,
            "min": min(counts, default=0),
            "max": max(counts, default=0),
            "histogram": dict(sorted(histogram.items())),
        },
        "by_type": types,
        "improvements": len(plan.improvements),
        "improvements_per_city": {
            "mean": round(sum(icounts) / len(icounts), 2) if icounts else 0.0,
            "min": min(icounts, default=0), "max": max(icounts, default=0),
        },
        "improvements_by_type": itypes,
        "spacing": city_spacing(gmap, plan, cities),
        "regional": regional(gmap, rules, plan, len(cities)),
    }


def regional(gmap: GameMap, rules: Rules, plan: Plan, n_cities: int) -> dict[str, Any]:
    """Per regional building (Factory), how many cities it reaches and from how many
    districts of its type."""
    out = {}
    for b, covered in model.regional_cover(gmap, rules, plan).items():
        d = rules.regional[b].district
        out[b] = {"cities_reached": len(covered), "share_of_cities": round(len(covered) / n_cities, 3) if n_cities else 0.0,
                  "districts": sum(1 for x, _, _ in plan.districts if x == d) + len(model.own_districts(gmap, d))}
    return out


def _stats(values: list[int] | list[float]) -> dict[str, float]:
    if not values:
        return {"min": 0, "mean": 0.0, "max": 0}
    return {"min": min(values), "mean": round(sum(values) / len(values), 2), "max": max(values)}


def city_spacing(gmap: GameMap, plan: Plan, cities: list[XY], top: int = 3) -> dict[str, Any]:
    """How tightly the cities are packed, in hex distance: to each city's nearest other
    city (min/mean/max and a histogram), over all pairs, among the `top` best sites (by
    site value), and to the nearest other player's city."""
    if len(cities) < 2:
        return {"cities": len(cities)}
    nearest = [min(gmap.distance(a, b) for b in cities if b != a) for a in cities]
    pairs = [gmap.distance(a, b) for i, a in enumerate(cities) for b in cities[i + 1:]]
    best = sorted(cities, key=lambda c: -site_value(gmap, gmap.tiles[c], plan.config))[:top]
    best_pairs = [gmap.distance(a, b) for i, a in enumerate(best) for b in best[i + 1:]]
    foreign = [(t["x"], t["y"]) for t in gmap if t["is_city"] and t["owner"] != gmap.player]
    histogram: dict[int, int] = {}
    for d in nearest:
        histogram[d] = histogram.get(d, 0) + 1
    return {
        "cities": len(cities),
        "nearest_city": {**_stats(nearest), "histogram": dict(sorted(histogram.items()))},
        "all_pairs": _stats(pairs),
        f"top_{top}_sites": {"cities": best, **_stats(best_pairs)},
        "nearest_foreign_city": _stats([min(gmap.distance(c, f) for f in foreign) for c in cities]) if foreign else None,
    }
