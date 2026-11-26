"""Preprocessing: the candidate sets the MIP chooses from (city sites, district tiles,
improvement options) and their values; no variables yet."""
from __future__ import annotations

from ..config import Config
from ..gamemap import XY, GameMap, Tile
from ..rules import Rules
from .existing import existing_cities, existing_improvements
from .instance import Instance
from .values import improvement_value, site_value


def reserved_tiles(gmap: GameMap) -> set[XY]:
    """The player's own map tacks: the planner leaves those tiles alone."""
    return {(p["x"], p["y"]) for p in gmap.pins}


def city_sites(gmap: GameMap, rules: Rules, cfg: Config, reserved: set[XY],
               max_city_candidates: int) -> dict[XY, float]:
    """The best `max_city_candidates` tiles a city may be founded on, by site value (on
    big maps the MIP then works on far fewer variables), best first, with their value."""
    tiles = [t for t in gmap if rules.can_found_city(gmap, t) and (t["x"], t["y"]) not in reserved]
    value = {(t["x"], t["y"]): site_value(gmap, t, cfg) for t in tiles}
    best = sorted(tiles, key=lambda t: -value[(t["x"], t["y"])])[:max_city_candidates]
    return {(t["x"], t["y"]): value[(t["x"], t["y"])] for t in best}


def _district_may_go(gmap: GameMap, rules: Rules, reserved: set[XY], d: str, c: XY, n: Tile) -> bool:
    """District d of the city on c may go on tile n (n within the district range of c)."""
    xy = (n["x"], n["y"])
    if not rules.can_place_district(gmap, n, d) or xy in reserved:
        return False
    if rules.no_adjacent_city(d) and gmap.distance(c, n) == 1:
        return False   # Encampment: not next to its own city centre
    if rules.is_aqueduct(d) and not (gmap.distance(c, n) == 1 and rules.fresh_water_source(gmap, n)):
        return False   # Aqueduct: next to its city centre and fresh water
    return True


def district_spots(gmap: GameMap, rules: Rules, reserved: set[XY], districts: tuple[str, ...],
                   cities: list[XY], built: dict[XY, set[str]]) -> dict[tuple[str, XY], list[XY]]:
    """(district, city) -> the tiles it may go on, for each city that lacks it."""
    spots = {}
    for d in districts:
        for c in cities:
            if d in built.get(c, set()):
                continue   # that city already has it
            spots[d, c] = [(n["x"], n["y"]) for n in gmap.within(gmap.tiles[c], rules.district_range)
                           if _district_may_go(gmap, rules, reserved, d, c, n)]
    return spots


def improvement_options(gmap: GameMap, rules: Rules, cfg: Config, reserved: set[XY], improvements: tuple[str, ...],
                        cities: list[XY]) -> dict[tuple[str, XY], list[XY]]:
    """(improvement, city) -> the tiles it may go on. Each city keeps only its best
    cfg.improvement_candidates options (by value): it gets at most max_improvements, and
    fewer variables keep the full maps fast."""
    ispots: dict[tuple[str, XY], list[XY]] = {}
    for c in cities:
        options = [(improvement_value(rules, cfg, i, n), i, (n["x"], n["y"]))
                   for n in gmap.within(gmap.tiles[c], rules.district_range) if (n["x"], n["y"]) not in reserved
                   for i in improvements if rules.can_place_improvement(gmap, n, i)]
        for _, i, t in sorted(options, key=lambda o: -o[0])[:cfg.improvement_candidates]:
            ispots.setdefault((i, c), []).append(t)
    return ispots


def prepare(gmap: GameMap, rules: Rules, cfg: Config, n_cities: int | str, districts: tuple[str, ...],
            max_city_candidates: int, improvements: tuple[str, ...] = ()) -> Instance:
    """The Instance a MIP is built from. n_cities "max": as many as fit."""
    reserved = reserved_tiles(gmap)
    site = city_sites(gmap, rules, cfg, reserved, max_city_candidates)
    sites = list(site)
    own, built = existing_cities(gmap)
    specialty_left = {e: max(0, cfg.max_specialty_districts - sum(rules.is_specialty(d) for d in built[e]))
                      for e in own}
    districts = tuple(districts)
    improvements = tuple(i for i in improvements if i in rules.improvements)
    improvements_left = {e: max(0, cfg.max_improvements - n) for e, n in existing_improvements(gmap, rules).items()}
    return Instance(
        gmap, rules, cfg, len(sites) if n_cities == "max" else int(n_cities), districts, sites, site,
        own, specialty_left, district_spots(gmap, rules, reserved, districts, sites + own, built),
        rules.neighbour_bonuses(districts), improvements,
        improvement_options(gmap, rules, cfg, reserved, improvements, sites + own),
        improvements_left, rules.improvement_bonuses(districts, improvements))
