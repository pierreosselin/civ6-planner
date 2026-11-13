"""Placement decisions.

`plan(method="mip")` (default) asks the optimiser in model.py. `method="greedy"` is the
first stub, kept to compare against:
- City: a random tile where a city can be founded.
- Campus: within the city's district range, on the tile with the best science
  adjacency (mountains, rainforest, reefs, geothermal fissures, other districts,
  the planned city included); ties are broken at random.
"""
from __future__ import annotations

import random
from typing import Callable
from dataclasses import dataclass, field

from . import config, model
from .config import Config
from .gamemap import XY, GameMap, Tile
from .model import Plan
from .rules import Rules

CITY_ICON = "ICON_DISTRICT_CITY_CENTER"
CAMPUS_ICON = "ICON_DISTRICT_CAMPUS"


@dataclass
class Tack:
    x: int
    y: int
    icon: str
    name: str
    yields: dict[str, int] = field(default_factory=dict)  # what the district would give, e.g. adjacency


def choose_city(gmap: GameMap, rules: Rules, rng: random.Random) -> Tile | None:
    candidates = [t for t in gmap if rules.can_found_city(gmap, t)]
    return rng.choice(candidates) if candidates else None


def choose_campus(gmap: GameMap, rules: Rules, city: Tile, rng: random.Random) -> tuple[Tile | None, int]:
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


def plan_greedy(gmap: GameMap, rules: Rules, rng: random.Random) -> Plan:
    """The first stub: a random city, then the best Campus tile for it."""
    city = choose_city(gmap, rules, rng)
    if city is None:
        return model.Plan(info={"status": "no city site"})
    p = model.Plan(cities=[(city["x"], city["y"])], info={"status": "greedy"})
    campus, _ = choose_campus(gmap, rules, city, rng)
    if campus is not None:
        p.districts.append(("DISTRICT_CAMPUS", (campus["x"], campus["y"]), (city["x"], city["y"])))
    return p


METHODS = ("mip", "greedy")


def solve(gmap: GameMap, rules: Rules, rng: random.Random | None = None, method: str = "mip",
          cfg: Config | None = None, progress: model.Progress | None = None,
          record: model.Progress | None = None, live: bool | None = None) -> Plan:
    """The plan (a model.Plan) from the chosen method. cfg: a config.Config (None: defaults);
    the greedy stub ignores it but its plan is scored with it. progress: see model.optimise
    (stages, model size as it is built, HiGHS's log live)."""
    cfg = cfg or config.default()
    if method == "mip":
        return model.optimise(gmap, rules, cfg, progress=progress, record=record, live=live)
    p = plan_greedy(gmap, rules, rng or random.Random())
    p.config = cfg   # the stub ignores the settings, but its plan is scored with them
    return p


def plan(gmap: GameMap, rules: Rules, rng: random.Random | None = None, method: str = "mip",
         cfg: Config | None = None) -> tuple[list[Tack], list[str]]:
    """Returns the tacks to place, plus human-readable notes on the decisions."""
    p = solve(gmap, rules, rng, method, cfg)
    return to_tacks(gmap, rules, p), explain(gmap, rules, p, method)


def explain(gmap: GameMap, rules: Rules, p: Plan, method: str) -> list[str]:
    """Human-readable notes on a plan: its score, the solver's run, each placement."""
    notes = []
    if not p.cities and not p.districts and not p.improvements:
        return [f"{method}: nothing to place: no city site and no district spot ({p.info.get('status')})"]
    label = city_labels(gmap, p)
    when = period_labels(p)
    score, parts = model.evaluate(gmap, rules, p)
    notes.append(f"{method}: score {score:.1f} = site {parts['site']:.1f} + adjacency {parts['adjacency']:.1f}"
                 f" + improvements {parts['improvements']:.1f} - covered tiles {parts['lost']:.1f}")
    if method == "mip":
        i = p.info
        notes.append(f"HiGHS {i['status']} in {i['seconds']}s: {i['variables']} variables, {i['rows']} rows, "
                     f"{i['city_candidates']} city sites considered")
    for xy in p.cities:
        notes.append(f"city {label[xy]}{when(xy)} at {xy}: {gmap.tiles[xy]['terrain']}, "
                     f"site value {model.site_value(gmap, gmap.tiles[xy], p.config):.1f}")
    for d, xy, city in p.districts:
        adj = ", ".join(f"+{v} {y[6:].lower()}" for y, v in _district_yields(gmap, rules, p, d, xy).items())
        notes.append(f"{district_name(d).lower()} of {label[city]}{when(xy)} at {xy}: {gmap.tiles[xy]['terrain']}, "
                     f"{adj or 'no adjacency'}")
    for imp, xy, city in p.improvements:
        gain = ", ".join(f"+{v} {y[6:].lower()}" for y, v in rules.improvements[imp].yields.items())
        notes.append(f"{improvement_name(imp).lower()} of {label[city]} at {xy}: {gmap.tiles[xy]['terrain']}"
                     f"{', ' + gmap.tiles[xy]['resource'] if gmap.tiles[xy]['resource'] != 'NONE' else ''}, "
                     f"{gain}, value {model.improvement_value(rules, p.config, imp, gmap.tiles[xy]):.1f}")
    return notes


def improvement_name(improvement: str) -> str:
    """IMPROVEMENT_LUMBER_MILL -> Lumber Mill."""
    return improvement.removeprefix("IMPROVEMENT_").replace("_", " ").title()


def city_labels(gmap: GameMap, p: Plan) -> dict[XY, str]:
    """A short name per city in the plan: the player's cities by their name, new ones
    C1, C2, … (best site first)."""
    labels = {(c["x"], c["y"]): c.get("name") or "city" for c in gmap.own_cities}
    labels.update({xy: f"C{i}" for i, xy in enumerate(p.cities, 1)})
    return labels


def district_name(district: str) -> str:
    """DISTRICT_HOLY_SITE -> Holy Site."""
    return district.removeprefix("DISTRICT_").replace("_", " ").title()


def _district_yields(gmap: GameMap, rules: Rules, p: Plan, district: str, xy: XY) -> dict[str, int]:
    planned = {c: model.CITY_CENTER for c in p.cities}
    planned.update({t: d for d, t, _ in p.districts})
    improved = {t: i for i, t, _ in p.improvements}
    return rules.adjacency(gmap, gmap.tiles[xy], district, planned, improved)


def period_labels(p: Plan) -> Callable[[XY], str]:
    """For timed plans, a suffix per city/district tile: " p2" (built in period 2) or
    " later" (after the horizon); "" for static plans."""
    if not (p.config.timing.periods and (p.timing or p.info.get("where"))):
        return lambda xy: ""
    return lambda xy: f" p{p.timing[xy]}" if xy in p.timing else " later"


def to_tacks(gmap: GameMap, rules: Rules, p: Plan) -> list[Tack]:
    """City tacks named "City C1", district tacks "Campus C1" (or "Campus Rome" for one
    of the player's cities), so it's clear which city a district belongs to. Timed
    plans add the period: "Campus C1 p3", or "later" after the horizon."""
    label = city_labels(gmap, p)
    when = period_labels(p)
    tacks = [Tack(x, y, CITY_ICON, f"City {label[(x, y)]}{when((x, y))}") for x, y in p.cities]
    for d, (x, y), city in p.districts:
        tacks.append(Tack(x, y, "ICON_" + d, f"{district_name(d)} {label[city]}{when((x, y))}",
                          _district_yields(gmap, rules, p, d, (x, y))))
    for i, (x, y), city in p.improvements:
        tacks.append(Tack(x, y, "ICON_" + i, f"{improvement_name(i)} {label[city]}",
                          dict(rules.improvements[i].yields)))
    return tacks
