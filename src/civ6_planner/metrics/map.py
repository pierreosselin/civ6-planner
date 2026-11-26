"""Basic statistics of the map a run plans on, for the logs ([1/5] of a results run)."""
from __future__ import annotations

from typing import Any

from ..gamemap import GameMap
from ..rules import Rules


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
