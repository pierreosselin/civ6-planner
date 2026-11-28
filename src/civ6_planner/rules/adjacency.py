"""District adjacency: what a district gets from its neighbours (District_Adjacencies +
Adjacency_YieldChanges, see tables.AdjacencyRule), and the bonuses the model links
between planned districts and improvements."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..gamemap import XY, GameMap, Tile
from .tables import AdjacencyRule

if TYPE_CHECKING:
    from .rules import Rules


def adjacency(rules: Rules, gmap: GameMap, tile: Tile, district: str,
              planned: dict[XY, str] | None = None, improved: dict[XY, str] | None = None) -> dict[str, int]:
    """{yield: bonus} the district would get on `tile`. planned: {(x, y): district type}
    of districts the plan adds (a planned city counts as DISTRICT_CITY_CENTER, a planned
    wonder as DISTRICT_WONDER);
    improved: {(x, y): improvement type} the plan adds."""
    planned = planned or {}
    improved = improved or {}
    neighbours = gmap.neighbours(tile)
    out: dict[str, int] = {}
    for rule in rules.adjacencies.get(district, []):
        count = _matches(rules, tile, neighbours, rule, planned, improved)
        if count is None:
            continue
        bonus = count // rule["tiles"] * rule["change"]
        if bonus:
            out[rule["yield"]] = out.get(rule["yield"], 0) + bonus
    return out


def _district_at(n: Tile, planned: dict[XY, str]) -> str:
    """The district on a neighbour, planned or existing ("NONE" if none)."""
    if (n["x"], n["y"]) in planned:
        return planned[(n["x"], n["y"])]
    if n.get("is_city"):
        return "DISTRICT_CITY_CENTER"
    return n.get("district", "NONE")


def _matches(rules: Rules, tile: Tile, neighbours: list[Tile], rule: AdjacencyRule,
             planned: dict[XY, str], improved: dict[XY, str]) -> int | None:
    """How many neighbours meet the rule's condition (None: a condition not handled)."""
    if rule.get("other_district"):
        return sum(1 for n in neighbours if _district_at(n, planned) != "NONE")
    if "terrain" in rule:
        return sum(1 for n in neighbours if n["terrain"] == rule["terrain"])
    if "feature" in rule:
        return sum(1 for n in neighbours if n["feature"] == rule["feature"])
    if "district" in rule:
        return sum(1 for n in neighbours if _district_at(n, planned) == rule["district"])
    if "improvement" in rule:
        return sum(1 for n in neighbours
                   if improved.get((n["x"], n["y"]), n.get("improvement")) == rule["improvement"])
    if "resource_class" in rule:
        return sum(1 for n in neighbours
                   if rules.resource_class.get(n.get("resource", "NONE")) == rule["resource_class"])
    if rule.get("sea_resource"):
        return sum(1 for n in neighbours if n["water"] and n.get("resource", "NONE") != "NONE")
    if rule.get("wonder"):
        return sum(1 for n in neighbours
                   if n.get("wonder", "NONE") != "NONE" or planned.get((n["x"], n["y"])) == "DISTRICT_WONDER")
    if rule.get("natural_wonder"):
        return sum(1 for n in neighbours if n.get("natural_wonder"))
    if rule.get("river"):
        return 1 if tile.get("river") else 0
    return None


def neighbour_bonuses(rules: Rules, districts: tuple[str, ...]) -> list[tuple[str, str, str, int]]:
    """(d, d2, yield, change) for every rule giving district d `change` of `yield` per
    neighbouring district d2, where both are planned (e.g. Industrial Zone next to an
    Aqueduct, Commercial Hub next to a Harbor). Only one-tile rules; city centres
    are handled separately."""
    out = []
    for d in districts:
        for rule in rules.adjacencies.get(d, []):
            d2 = rule.get("district")
            if d2 in districts and d2 != d and rule["tiles"] == 1:
                out.append((d, d2, rule["yield"], rule["change"]))
    return out


def improvement_bonuses(rules: Rules, districts: tuple[str, ...],
                        improvements: tuple[str, ...]) -> list[tuple[str, str, str, float]]:
    """(d, i, yield, change per improvement) for every rule giving planned district d a
    bonus per neighbouring improvement i (e.g. Industrial Zone +1 per quarry, +1 per 2
    mines: 0.5 per mine, the floor taken linearly)."""
    return [(d, rule["improvement"], rule["yield"], rule["change"] / rule["tiles"])
            for d in districts for rule in rules.adjacencies.get(d, [])
            if rule.get("improvement") in improvements]
