"""Statistics of a plan, for the logs: how many districts each city gets, how often each
district type is planned, and what adjacency the planned districts get.

Adjacency here is what the game would give with the whole plan built (every planned
city and district counted, as on the tacks), not the MIP's own coefficient.
"""
from __future__ import annotations

from typing import Any

from .gamemap import XY, GameMap
from .model import CITY_CENTER, Plan, improvement_value, site_value
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
        "spacing": city_spacing(gmap, plan, cities),
    }


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


def _wrap(items: list[str], width: int = 96, indent: str = "    ") -> list[str]:
    lines, line = [], ""
    for item in items:
        if line and len(line) + 3 + len(item) > width:
            lines.append(indent + line)
            line = ""
        line = f"{line} · {item}" if line else item
    return lines + ([indent + line] if line else [])


def format_summary(m: dict[str, Any]) -> list[str]:
    """The metrics in a few lines: totals, then each district and improvement type with
    the share of cities that get one."""
    dpc, ipc = m["districts_per_city"], m.get("improvements_per_city", {"mean": 0})
    lines = [f"  {m['cities']} cities ({m['new_cities']} new, {m['existing_cities']} existing) · "
             f"{m['districts']} districts ({dpc['mean']} per city) · "
             f"{m.get('improvements', 0)} improvements ({ipc['mean']} per city)"]
    districts = []
    for d, t in m["by_type"].items():
        adj = ", ".join(f"+{v:g} {k[6:].lower()}" for k, v in t["adjacency_mean"].items())
        districts.append(f"{d.removeprefix('DISTRICT_').replace('_', ' ').title()} {t['share_of_cities']:.0%}"
                         + (f" ({adj})" if adj else ""))
    lines += ["  districts: share of cities (mean adjacency)"] + _wrap(districts)
    imps = [f"{i.removeprefix('IMPROVEMENT_').replace('_', ' ').title()} {t['share_of_cities']:.0%} ({t['count']})"
            for i, t in m.get("improvements_by_type", {}).items()]
    if imps:
        lines += ["  improvements: share of cities (count)"] + _wrap(imps)
    s = m.get("spacing", {})
    if s.get("nearest_city"):
        nc, ap = s["nearest_city"], s["all_pairs"]
        top = next(v for k, v in s.items() if k.startswith("top_"))
        lines += [f"  spacing (tiles): nearest other city min {nc['min']}, mean {nc['mean']}, max {nc['max']} "
                  f"{nc['histogram']} · all pairs min {ap['min']}, mean {ap['mean']}, max {ap['max']}",
                  f"    best {len(top['cities'])} sites {top['cities']}: mean distance {top['mean']} "
                  f"(min {top['min']}, max {top['max']})"
                  + (f" · nearest other player's city: mean {s['nearest_foreign_city']['mean']}, "
                     f"min {s['nearest_foreign_city']['min']}" if s.get("nearest_foreign_city") else "")]
    return lines


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


def _name(type_name: str) -> str:
    """TERRAIN_GRASS_HILLS -> grass hills; FEATURE_JUNGLE -> jungle."""
    return type_name.split("_", 1)[-1].replace("_", " ").lower()


def _counts(counter: dict[str, int], limit: int = 8) -> str:
    items = sorted(counter.items(), key=lambda kv: -kv[1])
    text = " · ".join(f"{k} {v:,}" for k, v in items[:limit])
    return text + (f" · {len(items) - limit} more" if len(items) > limit else "") if items else "none"


def map_summary(gmap: GameMap, rules: Rules, dump: dict[str, Any]) -> list[str]:
    """Basic statistics of the map a run plans on, for the logs."""
    tiles = list(gmap)
    land = [t for t in tiles if not t["water"]]
    water = [t for t in tiles if t["water"]]
    terrain: dict[str, int] = {}
    for t in land:
        if not t["mountain"]:
            base = _name(t["terrain"]).removesuffix(" hills")
            terrain[base] = terrain.get(base, 0) + 1
    features: dict[str, int] = {}
    for t in tiles:
        if t["feature"] != "NONE" and not t["natural_wonder"]:
            features[_name(t["feature"])] = features.get(_name(t["feature"]), 0) + 1
    resources: dict[str, int] = {}
    for t in tiles:
        if t["resource"] != "NONE":
            cls = rules.resource_class.get(t["resource"], "RESOURCECLASS_UNKNOWN").removeprefix("RESOURCECLASS_").lower()
            resources[cls] = resources.get(cls, 0) + 1
    own = [c for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles]
    others = [t for t in tiles if t["is_city"] and t["owner"] != gmap.player]
    rivers = gmap.rivers()
    scope = dump.get("scope", "revealed")
    total = gmap.width * gmap.height
    planned_rules = sum(len(rules.adjacencies.get(d, [])) for d in rules.adjacencies)
    return [
        f"  turn {gmap.turn} · player {gmap.player} · {gmap.width}x{gmap.height} map · {len(tiles):,} tiles "
        f"({len(tiles) / total:.0%} of the map, scope {scope})",
        f"  land {len(land):,} (hills {sum(t['hills'] for t in land):,}, mountains {sum(t['mountain'] for t in land):,})"
        f" · water {len(water):,} (coast {sum(t['terrain'] == 'TERRAIN_COAST' for t in water):,}, "
        f"lake {sum(bool(t.get('lake')) for t in water):,})",
        f"  terrain (land, excl. mountains): {_counts(terrain)}",
        f"  features: {_counts(features)}",
        f"  rivers: {len(set(rivers.values())):,} touching {len(rivers):,} tiles · "
        f"natural wonder tiles {sum(bool(t['natural_wonder']) for t in tiles):,}",
        f"  resources (visible): {_counts(resources)}",
        f"  cities: {len(own)} yours" + (f" ({', '.join(str(c.get('name')) for c in own)})" if own else "")
        + f" · {len(others)} of other players ({len({t['owner'] for t in others})} owners)"
        + f" · your map tacks {len(gmap.pins)}",
        f"  rules: {planned_rules} adjacency rules for {len(rules.adjacencies)} district types, "
        f"{len(rules.improvements)} improvement types, cities more than {rules.city_min_range} apart, "
        f"districts within {rules.district_range}",
    ]
