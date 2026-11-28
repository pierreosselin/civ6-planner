"""What the player already has on the map: cities, their districts, improvements and
wonders, and the amenities those give."""
from __future__ import annotations

from ..gamemap import XY, GameMap
from ..rules import Rules
from .plan import CITY_CENTER


def _own_city_ids(gmap: GameMap) -> dict[int, XY]:
    """City id -> centre, for the player's cities on the map."""
    return {c["id"]: (c["x"], c["y"]) for c in gmap.own_cities if (c["x"], c["y"]) in gmap.tiles}


def existing_cities(gmap: GameMap) -> tuple[list[XY], dict[XY, set[str]]]:
    """The player's cities on the map, and the districts each already has (tiles the
    city owns holding a district)."""
    by_id = _own_city_ids(gmap)
    own = list(by_id.values())
    built: dict[XY, set[str]] = {xy: set() for xy in own}
    for t in gmap:
        if t["owner"] == gmap.player and t.get("city") in by_id and t["district"] not in ("NONE", CITY_CENTER):
            built[by_id[t["city"]]].add(t["district"])
    return own, built


def existing_improvements(gmap: GameMap, rules: Rules) -> dict[XY, int]:
    """Number of (plannable) improvements on the tiles each of the player's cities owns."""
    by_id = _own_city_ids(gmap)
    count = {xy: 0 for xy in by_id.values()}
    for t in gmap:
        if t["owner"] == gmap.player and t.get("city") in by_id and t.get("improvement", "NONE") in rules.improvements:
            count[by_id[t["city"]]] += 1
    return count


def own_districts(gmap: GameMap, district: str) -> set[XY]:
    """Tiles holding one of the player's existing districts of this type."""
    return {(t["x"], t["y"]) for t in gmap if t["owner"] == gmap.player and t["district"] == district}


def district_cities(gmap: GameMap) -> dict[XY, XY]:
    """Tile of each of the player's districts -> the centre of the city it belongs to."""
    by_id = _own_city_ids(gmap)
    return {(t["x"], t["y"]): by_id[t["city"]] for t in gmap
            if t["owner"] == gmap.player and t.get("city") in by_id and t["district"] not in ("NONE", CITY_CENTER)}


def wonders_on_map(gmap: GameMap) -> dict[XY, tuple[str, int]]:
    """Tile -> (wonder, owner) of every wonder built, the player's or not (one per world)."""
    return {(t["x"], t["y"]): (t["wonder"], t["owner"]) for t in gmap if t.get("wonder", "NONE") != "NONE"}


def existing_amenities(gmap: GameMap, rules: Rules, cities: list[XY]) -> dict[XY, int]:
    """Amenities each city (new or existing) already gets from what is built: its own
    districts (Districts.Entertainment, existing cities only) and the player's wonders
    within their range."""
    _, built = existing_cities(gmap)
    mine = [(w, xy) for xy, (w, owner) in wonders_on_map(gmap).items()
            if owner == gmap.player and w in rules.wonders and rules.wonders[w].range > 0]
    out = {}
    for c in cities:
        n = sum(rules.entertainment.get(d, 0) for d in built.get(c, ()))
        n += sum(rules.wonders[w].entertainment for w, xy in mine if gmap.distance(c, xy) <= rules.wonders[w].range)
        out[c] = n
    return out
