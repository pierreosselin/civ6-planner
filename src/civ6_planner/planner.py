"""Placement decisions. First iteration: no real optimisation yet.

- City: a random tile where a city can be founded.
- Campus: within the city's district range, on the tile with the best science
  adjacency (mountains, rainforest, reefs, geothermal fissures, other districts,
  the planned city included); ties are broken at random.
"""
import random
from dataclasses import dataclass, field

CITY_ICON = "ICON_DISTRICT_CITY_CENTER"
CAMPUS_ICON = "ICON_DISTRICT_CAMPUS"


@dataclass
class Tack:
    x: int
    y: int
    icon: str
    name: str
    yields: dict = field(default_factory=dict)  # what the district would give, e.g. adjacency


def choose_city(gmap, rules, rng):
    candidates = [t for t in gmap if rules.can_found_city(gmap, t)]
    return rng.choice(candidates) if candidates else None


def choose_campus(gmap, rules, city, rng):
    """The Campus tile and its science adjacency."""
    candidates = [t for t in gmap.within(city, rules.district_range) if rules.can_place_district(gmap, t)
                  and (t["x"], t["y"]) != (city["x"], city["y"])]
    if not candidates:
        return None, 0
    planned = {(city["x"], city["y"]): "DISTRICT_CITY_CENTER"}
    science = {t["i"]: rules.adjacency(gmap, t, "DISTRICT_CAMPUS", planned).get("YIELD_SCIENCE", 0)
               for t in candidates}
    best = max(science.values())
    return rng.choice([t for t in candidates if science[t["i"]] == best]), best


def plan(gmap, rules, rng=None):
    """Returns the tacks to place, plus human-readable notes on the decisions."""
    rng = rng or random.Random()
    tacks, notes = [], []

    city = choose_city(gmap, rules, rng)
    if city is None:
        notes.append("no revealed tile where a city can be founded")
        return tacks, notes
    tacks.append(Tack(city["x"], city["y"], CITY_ICON, "City"))
    notes.append(f"city at ({city['x']}, {city['y']}): {city['terrain']}")

    campus, science = choose_campus(gmap, rules, city, rng)
    if campus is None:
        notes.append("no valid Campus tile within range of the city")
    else:
        tacks.append(Tack(campus["x"], campus["y"], CAMPUS_ICON, "Campus", {"YIELD_SCIENCE": science}))
        notes.append(f"campus at ({campus['x']}, {campus['y']}): {campus['terrain']}, +{science} science adjacency")
    return tacks, notes
