"""The Rules object: the rule tables (from the database, or the defaults in tables.py)
and the questions the planner asks about them; the answers are in placement.py and
adjacency.py."""
from __future__ import annotations

from .. import paths
from ..gamemap import XY, GameMap, Tile
from . import adjacency as _adjacency
from . import placement as _placement
from .database import read_rules
from .tables import (DAM_DISTRICTS, DEFAULT_ADJACENCIES, DEFAULT_IMPROVEMENTS, DEFAULT_PLACEMENT,
                     DEFAULT_REGIONAL, DEFAULT_REQUIRED_FEATURES, DEFAULT_SPECIALTY, AdjacencyRule,
                     ImprovementRule, RegionalBuilding)


class Rules:
    def __init__(self, city_min_range: int = 3, district_range: int = 3,
                 resource_class: dict[str, str] | None = None, no_settle_features: tuple[str, ...] = (),
                 adjacencies: dict[str, list[AdjacencyRule]] | None = None,
                 placement: dict[str, dict[str, int]] | None = None,
                 required_features: dict[str, set[str]] | None = None,
                 valid_terrains: dict[str, set[str]] | None = None,
                 improvements: dict[str, ImprovementRule] | None = None,
                 regional: dict[str, RegionalBuilding] | None = None):
        # A new city centre must be more than city_min_range tiles from any other.
        self.city_min_range = city_min_range
        # Districts go within district_range tiles of their city centre.
        self.district_range = district_range
        self.resource_class = dict(resource_class or {})
        self.no_settle_features = set(no_settle_features)
        # District -> adjacency rules (see AdjacencyRule).
        self.adjacencies = DEFAULT_ADJACENCIES if adjacencies is None else adjacencies
        # District -> placement flags (see PLACEMENT_FLAGS).
        self.placement = dict(DEFAULT_PLACEMENT if placement is None else placement)
        # District -> features it must go on / terrains it may go on (empty: no rule).
        self.required_features = dict(DEFAULT_REQUIRED_FEATURES if required_features is None else required_features)
        self.valid_terrains = dict(valid_terrains or {})
        # Improvement -> where it may go and its yields.
        self.improvements = dict(DEFAULT_IMPROVEMENTS if improvements is None else improvements)
        # Building -> its regional effect (district, range, yields).
        self.regional = dict(DEFAULT_REGIONAL if regional is None else regional)

    @classmethod
    def from_game(cls, db_path: str = paths.GAMEPLAY_DB) -> Rules:
        """The rules of the game last loaded (its DebugGameplay.sqlite)."""
        return cls(**read_rules(db_path))

    # --- Placement (placement.py) ---------------------------------------------------

    def can_found_city(self, gmap: GameMap, tile: Tile) -> bool:
        return _placement.can_found_city(self, gmap, tile)

    def can_place_district(self, gmap: GameMap, tile: Tile, district: str = "DISTRICT_CAMPUS") -> bool:
        return _placement.can_place_district(self, gmap, tile, district)

    def can_place_improvement(self, gmap: GameMap, tile: Tile, improvement: str) -> bool:
        return _placement.can_place_improvement(self, gmap, tile, improvement)

    @staticmethod
    def fresh_water_source(gmap: GameMap, tile: Tile) -> bool:
        return _placement.fresh_water_source(gmap, tile)

    # --- Adjacency (adjacency.py) ---------------------------------------------------

    def adjacency(self, gmap: GameMap, tile: Tile, district: str,
                  planned: dict[XY, str] | None = None,
                  improved: dict[XY, str] | None = None) -> dict[str, int]:
        return _adjacency.adjacency(self, gmap, tile, district, planned, improved)

    def neighbour_bonuses(self, districts: tuple[str, ...]) -> list[tuple[str, str, str, int]]:
        return _adjacency.neighbour_bonuses(self, districts)

    def improvement_bonuses(self, districts: tuple[str, ...],
                            improvements: tuple[str, ...]) -> list[tuple[str, str, str, float]]:
        return _adjacency.improvement_bonuses(self, districts, improvements)

    # --- District kinds -------------------------------------------------------------

    def no_adjacent_city(self, district: str) -> bool:
        """The district may not touch any city centre (Encampment)."""
        return bool(self.placement.get(district, {}).get("NoAdjacentCity"))

    def is_specialty(self, district: str) -> bool:
        """Counts against the city's population limit (Districts.RequiresPopulation): every
        planned district but the Aqueduct and the Dam."""
        flags = self.placement.get(district, {})
        if "RequiresPopulation" in flags:
            return bool(flags["RequiresPopulation"])
        return district in DEFAULT_SPECIALTY

    @staticmethod
    def is_dam(district: str) -> bool:
        """One per river, on a tile with a river along at least two edges (engine rule)."""
        return district in DAM_DISTRICTS

    def is_aqueduct(self, district: str) -> bool:
        """Aqueduct-like districts (Aqueduct, Bath): next to their own city centre and a
        fresh-water source. The flag is in the Districts table; the rule itself is engine
        behaviour, not data."""
        return bool(self.placement.get(district, {}).get("Aqueduct"))
