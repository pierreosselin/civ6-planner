"""Placement decisions: run a planner (`mip`, the optimiser in model/, or the `greedy`
stub in greedy.py, kept to compare against), and turn its plan into named map tacks
and notes."""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import config, greedy, model
from .config import Config
from .gamemap import XY, GameMap
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
    p = greedy.plan_greedy(gmap, rules, rng or random.Random())
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
    score, parts = model.evaluate(gmap, rules, p)
    notes.append(f"{method}: score {score:.1f} = site {parts['site']:.1f} + adjacency {parts['adjacency']:.1f}"
                 f" + improvements {parts['improvements']:.1f} + regional {parts['regional']:.1f}"
                 f" - covered tiles {parts['lost']:.1f}")
    if method == "mip":
        i = p.info
        notes.append(f"HiGHS {i['status']} in {i['seconds']}s: {i['variables']} variables, {i['rows']} rows, "
                     f"{i['city_candidates']} city sites considered")
    for xy in p.cities:
        notes.append(f"city {label[xy]} at {xy}: {gmap.tiles[xy]['terrain']}, "
                     f"site value {model.site_value(gmap, gmap.tiles[xy], p.config):.1f}")
    for d, xy, city in p.districts:
        adj = ", ".join(f"+{v} {y[6:].lower()}" for y, v in _district_yields(gmap, rules, p, d, xy).items())
        notes.append(f"{district_name(d).lower()} of {label[city]} at {xy}: {gmap.tiles[xy]['terrain']}, "
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
    return rules.adjacency(gmap, gmap.tiles[xy], district, p.planned(), p.improved())


def to_tacks(gmap: GameMap, rules: Rules, p: Plan) -> list[Tack]:
    """City tacks named "City C1", district tacks "Campus C1" (or "Campus Rome" for one
    of the player's cities), so it's clear which city a district belongs to."""
    label = city_labels(gmap, p)
    tacks = [Tack(x, y, CITY_ICON, f"City {label[(x, y)]}") for x, y in p.cities]
    for d, (x, y), city in p.districts:
        tacks.append(Tack(x, y, "ICON_" + d, f"{district_name(d)} {label[city]}",
                          _district_yields(gmap, rules, p, d, (x, y))))
    for i, (x, y), city in p.improvements:
        tacks.append(Tack(x, y, "ICON_" + i, f"{improvement_name(i)} {label[city]}",
                          dict(rules.improvements[i].yields)))
    return tacks
