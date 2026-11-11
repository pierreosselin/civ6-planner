"""Checks a plan against game rules the model leaves out, after solving.

The model guarantees range, one thing per tile and city spacing; the checks below
confirm that, and measure what it does not model:

- ring: a district or improvement of city c on a tile next to another city's centre.
  A city claims the unowned tiles around its centre when it is founded, so that tile
  would most likely belong to the other city (unless c owned it first: founding order).
- owned: a tile already owned by one of the player's cities, used by another city
  (tiles can't move between cities).
- foreign: a tile owned by another player (the model excludes these).
- range: farther than the district range (3) from its own city.
- shared: a tile holding two planned things.
- spacing: two cities closer than the game allows.
"""
from __future__ import annotations

from typing import Any

from .gamemap import XY, GameMap
from .model import Plan
from .rules import Rules


def check_plan(gmap: GameMap, rules: Rules, plan: Plan) -> dict[str, Any]:
    """Every rule violation found, by check: {check: [description, ...]}, plus counts."""
    own = {(c["x"], c["y"]): c for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles}
    own_id = {c["id"]: xy for xy, c in own.items()}
    centres = set(plan.cities) | gmap.city_positions()
    items = [(d, t, c) for d, t, c in plan.districts] + [(i, t, c) for i, t, c in plan.improvements]
    label = {xy: f"C{n}" for n, xy in enumerate(plan.cities, 1)}
    label.update({xy: str(c.get("name")) for xy, c in own.items()})

    def name(kind: str, city: XY) -> str:
        return f"{kind.split('_', 1)[1].replace('_', ' ').title()} {label.get(city, city)}"

    issues: dict[str, list[str]] = {k: [] for k in ("ring", "owned", "foreign", "range", "shared", "spacing")}
    used: dict[XY, int] = {}
    for kind, t, c in items:
        tile = gmap.tiles[t]
        used[t] = used.get(t, 0) + 1
        others = sorted(o for o in centres if o != c and gmap.distance(o, t) == 1)
        if others:
            issues["ring"].append(f"{name(kind, c)} at {t}: next to the city centre at {others[0]}")
        if tile["owner"] == gmap.player and tile.get("city") in own_id and own_id[tile["city"]] != c:
            issues["owned"].append(f"{name(kind, c)} at {t}: owned by {label[own_id[tile['city']]]}")
        if tile["owner"] not in (-1, gmap.player):
            issues["foreign"].append(f"{name(kind, c)} at {t}: owned by player {tile['owner']}")
        if gmap.distance(c, t) > rules.district_range:
            issues["range"].append(f"{name(kind, c)} at {t}: {gmap.distance(c, t)} tiles from its city")
    issues["shared"] = [f"{t}: {n} planned things" for t, n in used.items() if n > 1]
    cities = list(plan.cities) + [xy for xy in own if xy not in plan.cities]
    issues["spacing"] = [f"{a} and {b}: {gmap.distance(a, b)} apart"
                         for i, a in enumerate(cities) for b in cities[i + 1:]
                         if gmap.distance(a, b) <= rules.city_min_range]
    return {"placements": len(items), "counts": {k: len(v) for k, v in issues.items()}, "issues": issues}


def format_check(v: dict[str, Any], examples: int = 3) -> list[str]:
    """The checks as log lines: a count per check, then a few examples of each problem."""
    n, c = v["placements"], v["counts"]
    share = f" ({c['ring'] / n:.0%})" if n else ""
    lines = ["  validation (rules the model leaves out, checked on the solution):",
             f"    {c['ring']} of {n} placements{share} on a tile next to another city's centre "
             f"(claimed by that city when founded)",
             f"    {c['owned']} on tiles another of your cities owns · {c['foreign']} on other players' tiles · "
             f"{c['range']} out of range · {c['shared']} tiles used twice · {c['spacing']} cities too close"]
    for check, found in v["issues"].items():
        for text in found[:examples]:
            lines.append(f"      {check}: {text}")
        if len(found) > examples:
            lines.append(f"      {check}: … {len(found) - examples} more (all in decisions.json)")
    return lines
