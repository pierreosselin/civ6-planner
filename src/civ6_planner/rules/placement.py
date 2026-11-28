"""Where cities, districts and improvements may go, from the database tables plus the
engine rules written out here."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ..gamemap import GameMap, Tile
from .tables import DAM_MIN_RIVER_EDGES, LOCKED_RESOURCES

if TYPE_CHECKING:
    from .rules import Rules


def open_land(tile: Tile, player: int) -> bool:
    """Land that nothing blocks: not water, mountain, impassable or a wonder,
    and unowned or owned by the player."""
    return not (tile["water"] or tile["mountain"] or tile["impassable"]
                or tile["natural_wonder"] or tile["wonder"] != "NONE") \
        and tile["owner"] in (-1, player)


def can_found_city(rules: Rules, gmap: GameMap, tile: Tile) -> bool:
    """Open land, a feature that allows settling, and more than city_min_range tiles from
    every city."""
    if not open_land(tile, gmap.player) or tile["feature"] in rules.no_settle_features:
        return False
    return all(gmap.distance(tile, c) > rules.city_min_range for c in gmap.city_positions())


def can_place_district(rules: Rules, gmap: GameMap, tile: Tile, district: str = "DISTRICT_CAMPUS") -> bool:
    """Can `district` go on `tile`? Planned cities are handled in the model.

    - Coast districts (Harbor): a coast or lake water tile next to land.
    - Others: open land (the planned districts have no terrain list of their own).
    - NoAdjacentCity districts (Encampment): not next to an existing city centre.
    - District_RequiredFeatures / District_ValidTerrains when the district has rows
      there (the Dam: floodplains).
    - Dams: a river along at least two of the tile's edges (engine rule; one per
      river is a constraint in the model).
    Engine rule, not in the database: districts can't go on luxury or strategic
    resources (bonus resources are removed).
    """
    flags = rules.placement.get(district, {})
    if tile["is_city"] or tile["district"] != "NONE":
        return False
    if flags.get("Coast"):
        if tile["terrain"] != "TERRAIN_COAST" or tile["natural_wonder"] or tile["wonder"] != "NONE" \
                or tile["owner"] not in (-1, gmap.player):
            return False
        if flags.get("AdjacentToLand") and all(n["water"] for n in gmap.neighbours(tile)):
            return False
    elif not open_land(tile, gmap.player):
        return False
    if flags.get("NoAdjacentCity") and any(n["is_city"] for n in gmap.neighbours(tile)):
        return False
    if district in rules.required_features and tile["feature"] not in rules.required_features[district]:
        return False
    if district in rules.valid_terrains and tile["terrain"] not in rules.valid_terrains[district]:
        return False
    if rules.is_dam(district) and len(gmap.river_edges(tile)) < DAM_MIN_RIVER_EDGES:
        return False
    return rules.resource_class.get(tile["resource"]) not in LOCKED_RESOURCES


def can_place_wonder(rules: Rules, gmap: GameMap, tile: Tile, wonder: str) -> bool:
    """Can `wonder` go on `tile`, as far as the tile itself goes? (Next to its district
    and within its city's range: in the model.)

    - Open land, no city or district.
    - A terrain from Building_ValidTerrains (the Colosseum: flat, no hills).
    - No feature, a removable one (woods, rainforest, marsh: cleared), or one the wonder
      lists (Building_ValidFeatures, e.g. floodplains for the Pyramids).
    - Not on a luxury or strategic resource (as districts, engine rule).
    A wonder with placement requirements not checked yet (WonderRule.requires) never goes.
    """
    rule = rules.wonders.get(wonder)
    if rule is None or rule.requires or tile["is_city"] or tile["district"] != "NONE":
        return False
    if not open_land(tile, gmap.player) or (rule.terrains and tile["terrain"] not in rule.terrains):
        return False
    feature = tile["feature"]
    if feature != "NONE" and feature not in rule.features and feature not in rules.removable_features:
        return False
    return rules.resource_class.get(tile["resource"]) not in LOCKED_RESOURCES


def can_place_improvement(rules: Rules, gmap: GameMap, tile: Tile, improvement: str) -> bool:
    """Can `improvement` go on `tile`? A tile with a (visible) resource only takes that
    resource's improvements; otherwise a feature must be one the improvement allows,
    and a bare tile's terrain one it allows. Never on a city, district, wonder,
    mountain, existing improvement, or a tile owned by someone else."""
    rule = rules.improvements.get(improvement)
    if rule is None or tile["is_city"] or tile["district"] != "NONE" or tile.get("improvement", "NONE") != "NONE":
        return False
    if tile["mountain"] or tile["impassable"] or tile["natural_wonder"] or tile["wonder"] != "NONE":
        return False
    if tile["owner"] not in (-1, gmap.player) or bool(tile["water"]) != rule.sea:
        return False
    if tile["resource"] != "NONE":
        return tile["resource"] in rule.resources
    if tile["feature"] != "NONE":
        return tile["feature"] in rule.features
    return tile["terrain"] in rule.terrains


def fresh_water_source(gmap: GameMap, tile: Tile) -> bool:
    """Engine rule for aqueducts: the tile touches a river, or is next to a lake, a
    mountain or an oasis."""
    if tile.get("river"):
        return True
    return any(n.get("lake") or n["mountain"] or n["feature"] == "FEATURE_OASIS"
               for n in gmap.neighbours(tile))
