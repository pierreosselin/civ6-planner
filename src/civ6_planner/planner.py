"""Placement decisions. First iteration: no real optimisation yet.

- City: a random tile where a city can be founded.
- Campus: within the city's district range, on the tile with the most adjacent
  revealed mountains; ties are broken at random.
"""
import random
from dataclasses import dataclass

CITY_ICON = "ICON_DISTRICT_CITY_CENTER"
CAMPUS_ICON = "ICON_DISTRICT_CAMPUS"


@dataclass
class Tack:
    x: int
    y: int
    icon: str
    name: str


def mountains_around(gmap, tile):
    return sum(1 for n in gmap.neighbours(tile) if n["mountain"])


def choose_city(gmap, rules, rng):
    candidates = [t for t in gmap if rules.can_found_city(gmap, t)]
    return rng.choice(candidates) if candidates else None


def choose_campus(gmap, rules, city, rng):
    candidates = [t for t in gmap.within(city, rules.district_range) if rules.can_place_district(gmap, t)]
    if not candidates:
        return None, 0
    best = max(mountains_around(gmap, t) for t in candidates)
    return rng.choice([t for t in candidates if mountains_around(gmap, t) == best]), best


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

    campus, mountains = choose_campus(gmap, rules, city, rng)
    if campus is None:
        notes.append("no valid Campus tile within range of the city")
    else:
        tacks.append(Tack(campus["x"], campus["y"], CAMPUS_ICON, f"Campus ({mountains} mountains)"))
        notes.append(f"campus at ({campus['x']}, {campus['y']}): {campus['terrain']}, "
                     f"{mountains} adjacent revealed mountain(s)")
    return tacks, notes
