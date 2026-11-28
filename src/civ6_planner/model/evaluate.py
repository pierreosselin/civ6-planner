"""Score any plan (the MIP's or the greedy stub's) in plain Python, under the model's
objective with the placement bonuses left out. It counts every planned district and
wonder in adjacency, so it can be above the MIP's objective when planned districts or
wonders touch (the MIP leaves most of that adjacency out). Tests require
MIP objective = evaluate + bonuses where they don't."""
from __future__ import annotations

from typing import Any

from ..config import Config
from ..gamemap import XY, GameMap
from ..rules import Rules
from .existing import existing_amenities, existing_cities, own_districts
from .plan import Plan
from .values import covered_value, improvement_value, regional_value, site_value


def evaluate(gmap: GameMap, rules: Rules, plan: Plan, cfg: Config | None = None) -> tuple[float, dict[str, Any]]:
    """(score, breakdown) of a plan, bonuses left out. Uses cfg, else the plan's own config."""
    cfg = cfg or plan.config
    planned, improved = plan.planned(), plan.improved()
    site = sum(site_value(gmap, gmap.tiles[xy], cfg) for xy in plan.cities)
    adjacency = lost = 0.0
    yields: dict[str, int] = {}
    for d, xy, _ in plan.districts:
        tile = gmap.tiles[xy]
        adj = rules.adjacency(gmap, tile, d, planned, improved)
        for y, v in adj.items():
            yields[y] = yields.get(y, 0) + v
        adjacency += cfg.weighted(adj)
        lost += covered_value(cfg, tile)
    improvements = sum(improvement_value(rules, cfg, i, gmap.tiles[xy]) for i, xy, _ in plan.improvements)
    regional = sum(regional_value(rules, cfg, b) * len(covered)
                   for b, covered in regional_cover(gmap, rules, plan, cfg).items())
    wonders = sum(cfg.weighted(rules.wonders[b].yields) for b, _, _ in plan.wonders)
    lost += sum(covered_value(cfg, gmap.tiles[xy]) for _, xy, _ in plan.wonders)
    amenities = cfg.amenity_value * sum(min(cfg.amenities_needed, n) for n in city_amenities(gmap, rules, plan).values())
    return site + adjacency - lost + improvements + regional + wonders + amenities, {
        "site": site, "adjacency": adjacency, "lost": lost, "improvements": improvements,
        "regional": regional, "wonders": wonders, "amenities": amenities, "yields": yields}


def _all_cities(gmap: GameMap, plan: Plan) -> list[XY]:
    """The plan's new cities, then the player's existing ones."""
    own, _ = existing_cities(gmap)
    return list(plan.cities) + [c for c in own if c not in plan.cities]


def city_amenities(gmap: GameMap, rules: Rules, plan: Plan) -> dict[XY, int]:
    """Amenities each city (new and existing) gets from districts and wonders, planned or
    built (not capped at amenities_needed)."""
    cities = _all_cities(gmap, plan)
    out = existing_amenities(gmap, rules, cities)
    for d, _, c in plan.districts:
        out[c] = out.get(c, 0) + rules.entertainment.get(d, 0)
    for b, xy, _ in plan.wonders:
        w = rules.wonders[b]
        if w.range > 0:
            for c in cities:
                if gmap.distance(c, xy) <= w.range:
                    out[c] += w.entertainment
    return out


def regional_cover(gmap: GameMap, rules: Rules, plan: Plan, cfg: Config | None = None) -> dict[str, list[XY]]:
    """Per regional building (cfg.regional_buildings), the cities (new and existing) it
    reaches: those with a planned or existing district of its type within its range."""
    cfg = cfg or plan.config
    cities = _all_cities(gmap, plan)
    out = {}
    for b in cfg.regional_buildings:
        if b not in rules.regional:
            continue
        rb = rules.regional[b]
        sources = {xy for d, xy, _ in plan.districts if d == rb.district} | own_districts(gmap, rb.district)
        out[b] = [c for c in cities if any(gmap.distance(c, t) <= rb.range for t in sources)]
    return out
