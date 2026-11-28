"""What things are worth, in weighted yields (weights in config/default.toml): shared by
the preprocessing, the objective terms and `evaluate`."""
from __future__ import annotations

from .. import config
from ..config import Config
from ..gamemap import GameMap, Tile
from ..rules import Rules


def site_value(gmap: GameMap, tile: Tile, cfg: Config | None = None) -> float:
    """Weighted yields of a city centre and the tiles within cfg.site_radius."""
    cfg = cfg or config.default()
    return cfg.weighted(tile) + sum(cfg.weighted(t) for t in gmap.within(tile, cfg.site_radius))


def improvement_value(rules: Rules, cfg: Config, improvement: str, tile: Tile) -> float:
    """Value of improving `tile`: the improvement's gain, plus worked_tile_factor times the
    tile's own yields (an improved tile is one the city works)."""
    return cfg.weighted(rules.improvements[improvement].yields) + cfg.worked_tile_factor * cfg.weighted(tile)


def covered_value(cfg: Config, tile: Tile) -> float:
    """Weighted yields lost by covering a tile with a district (loss_factor of the tile's)."""
    return cfg.loss_factor * cfg.weighted(tile)


def wonder_value(rules: Rules, cfg: Config, wonder: str, tile: Tile) -> float:
    """A wonder's own weighted yields (Colosseum: +2 culture), less the tile it covers;
    its amenities are counted per city (amenity_value)."""
    return cfg.weighted(rules.wonders[wonder].yields) - covered_value(cfg, tile)


def regional_value(rules: Rules, cfg: Config, building: str) -> float:
    """Weighted yields a regional building gives each city it reaches."""
    return cfg.weighted(rules.regional[building].yields)
