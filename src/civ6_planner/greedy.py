"""The first planner stub, kept to compare against the MIP:
- City: a random tile where a city can be founded.
- Campus: within the city's district range, on the tile with the best science
  adjacency (mountains, rainforest, reefs, geothermal fissures, other districts,
  the planned city included); ties are broken at random.
"""
from __future__ import annotations

import random

from .gamemap import GameMap, Tile
from .model import CITY_CENTER, Plan
from .rules import Rules


def choose_city(gmap: GameMap, rules: Rules, rng: random.Random) -> Tile | None:
    candidates = [t for t in gmap if rules.can_found_city(gmap, t)]
    return rng.choice(candidates) if candidates else None


def choose_campus(gmap: GameMap, rules: Rules, city: Tile, rng: random.Random) -> tuple[Tile | None, int]:
    """The Campus tile and its science adjacency."""
    candidates = [t for t in gmap.within(city, rules.district_range) if rules.can_place_district(gmap, t)
                  and (t["x"], t["y"]) != (city["x"], city["y"])]
    if not candidates:
        return None, 0
    planned = {(city["x"], city["y"]): CITY_CENTER}
    science = {t["i"]: rules.adjacency(gmap, t, "DISTRICT_CAMPUS", planned).get("YIELD_SCIENCE", 0)
               for t in candidates}
    best = max(science.values())
    return rng.choice([t for t in candidates if science[t["i"]] == best]), best


def plan_greedy(gmap: GameMap, rules: Rules, rng: random.Random) -> Plan:
    """The first stub: a random city, then the best Campus tile for it."""
    city = choose_city(gmap, rules, rng)
    if city is None:
        return Plan(info={"status": "no city site"})
    p = Plan(cities=[(city["x"], city["y"])], info={"status": "greedy"})
    campus, _ = choose_campus(gmap, rules, city, rng)
    if campus is not None:
        p.districts.append(("DISTRICT_CAMPUS", (campus["x"], campus["y"]), (city["x"], city["y"])))
    return p
