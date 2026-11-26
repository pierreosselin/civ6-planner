"""What the player already has on the map: cities, their districts and improvements."""
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
