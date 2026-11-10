"""Statistics of a plan, for the logs: how many districts each city gets, how often each
district type is planned, and what adjacency the planned districts get.

Adjacency here is what the game would give with the whole plan built (every planned
city and district counted, as on the tacks), not the MIP's own coefficient.
"""
from __future__ import annotations

from typing import Any

from .gamemap import XY, GameMap
from .model import CITY_CENTER, Plan, improvement_value
from .rules import Rules


def plan_metrics(gmap: GameMap, rules: Rules, plan: Plan) -> dict[str, Any]:
    """Cities (new and existing), districts per city, and per district type: count,
    share of cities that have one, mean/min/max adjacency per yield and weighted."""
    own = [(c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles]
    cities: list[XY] = list(plan.cities) + [c for c in own if c not in plan.cities]
    planned: dict[XY, str] = {xy: CITY_CENTER for xy in plan.cities}
    planned.update({xy: d for d, xy, _ in plan.districts})
    improved = {xy: i for i, xy, _ in plan.improvements}

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
    }


def format_metrics(m: dict[str, Any]) -> list[str]:
    """The metrics as log lines."""
    dpc = m["districts_per_city"]
    lines = [f"cities {m['cities']} ({m['new_cities']} new, {m['existing_cities']} existing), "
             f"districts {m['districts']}",
             f"districts per city: mean {dpc['mean']}, min {dpc['min']}, max {dpc['max']}; "
             f"cities by number of districts {dpc['histogram']}",
             f"{'district':<18}{'count':>6}{'in cities':>11}{'share':>8}  mean adjacency (min-max)   weighted"]
    for d, t in m["by_type"].items():
        adj = ", ".join(f"+{t['adjacency_mean'][k]:g} {k[6:].lower()} ({lo}-{hi})"
                        for k, (lo, hi) in t["adjacency_min_max"].items()) or "none"
        lines.append(f"{d.removeprefix('DISTRICT_').replace('_', ' ').title():<18}{t['count']:>6}"
                     f"{t['cities_with']:>11}{t['share_of_cities']:>8.0%}  {adj:<26} {t['weighted_mean']:>6}")
    if m.get("improvements_by_type"):
        ipc = m["improvements_per_city"]
        lines += [f"improvements {m['improvements']}; per city mean {ipc['mean']}, min {ipc['min']}, max {ipc['max']}",
                  f"{'improvement':<18}{'count':>6}{'in cities':>11}{'share':>8}  mean value (gain + worked tile)"]
        for i, t in m["improvements_by_type"].items():
            lines.append(f"{i.removeprefix('IMPROVEMENT_').replace('_', ' ').title():<18}{t['count']:>6}"
                         f"{t['cities_with']:>11}{t['share_of_cities']:>8.0%}  {t['value_mean']}")
    return lines
