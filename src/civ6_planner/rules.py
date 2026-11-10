"""Placement rules, read from the game's own database where it has them.

The game writes its full gameplay database to Cache/DebugGameplay.sqlite each time a
game loads, so it reflects the expansions and mods in use. Rules that are engine
behaviour rather than data are written out here and marked as such.
"""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from . import paths
from .gamemap import XY, GameMap, Tile

# One adjacency rule: {yield, change, tiles, and one condition}; it gives `change` of
# `yield` per `tiles` neighbours matching the condition. Conditions:
#   other_district: True      any district or city centre (existing or planned)
#   district: TYPE            that district
#   terrain: TYPE / feature: TYPE / improvement: TYPE
#   resource_class: CLASS     a resource of that class (e.g. RESOURCECLASS_STRATEGIC)
#   sea_resource: True        a water tile with a resource
#   wonder: True / natural_wonder: True
#   river: True               the district's own tile touches a river (counts once)
AdjacencyRule = dict[str, Any]

# Districts table flags used for placement: Coast (goes on a coast water tile),
# AdjacentToLand, NoAdjacentCity (not next to any city centre, e.g. Encampment),
# Aqueduct (next to its city centre and a fresh-water source: see fresh_water_source).
PLACEMENT_FLAGS = ("Coast", "AdjacentToLand", "NoAdjacentCity", "Aqueduct", "RequiresPopulation")

# Districts that count against the population limit (RequiresPopulation = 1), for when the
# database can't be read.
DEFAULT_SPECIALTY = ("DISTRICT_CAMPUS", "DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_COMMERCIAL_HUB",
                     "DISTRICT_HOLY_SITE", "DISTRICT_THEATER", "DISTRICT_ENCAMPMENT", "DISTRICT_HARBOR")

# Dam-like districts, an engine rule not in the database: on a tile with a river along at
# least two of its edges, and one per river (the floodplains requirement is in the
# database, District_RequiredFeatures).
DAM_DISTRICTS = ("DISTRICT_DAM",)
DAM_MIN_RIVER_EDGES = 2

# Placement flags of the special planned districts, for when the database can't be read.
DEFAULT_PLACEMENT: dict[str, dict[str, int]] = {
    "DISTRICT_HARBOR": {"Coast": 1, "AdjacentToLand": 1, "NoAdjacentCity": 0, "Aqueduct": 0},
    "DISTRICT_ENCAMPMENT": {"Coast": 0, "AdjacentToLand": 0, "NoAdjacentCity": 1, "Aqueduct": 0},
    "DISTRICT_AQUEDUCT": {"Coast": 0, "AdjacentToLand": 0, "NoAdjacentCity": 0, "Aqueduct": 1},
}
DEFAULT_REQUIRED_FEATURES: dict[str, set[str]] = {
    "DISTRICT_DAM": {"FEATURE_FLOODPLAINS", "FEATURE_FLOODPLAINS_GRASSLAND", "FEATURE_FLOODPLAINS_PLAINS"},
}

# Campus adjacency as in the Gathering Storm database, for when it can't be read.
DEFAULT_ADJACENCIES: dict[str, list[AdjacencyRule]] = {"DISTRICT_CAMPUS": [
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 1, "terrain": f"TERRAIN_{t}_MOUNTAIN"}
    for t in ("GRASS", "PLAINS", "DESERT", "TUNDRA", "SNOW")] + [
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 2, "other_district": True},
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 2, "feature": "FEATURE_JUNGLE"},
    {"yield": "YIELD_SCIENCE", "change": 2, "tiles": 1, "feature": "FEATURE_REEF"},
    {"yield": "YIELD_SCIENCE", "change": 2, "tiles": 1, "feature": "FEATURE_GEOTHERMAL_FISSURE"},
]}

LOCKED_RESOURCES = ("RESOURCECLASS_LUXURY", "RESOURCECLASS_STRATEGIC")


class Rules:
    def __init__(self, city_min_range: int = 3, district_range: int = 3,
                 resource_class: dict[str, str] | None = None, no_settle_features: tuple[str, ...] = (),
                 adjacencies: dict[str, list[AdjacencyRule]] | None = None,
                 placement: dict[str, dict[str, int]] | None = None,
                 required_features: dict[str, set[str]] | None = None,
                 valid_terrains: dict[str, set[str]] | None = None):
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

    @classmethod
    def from_game(cls, db_path: str = paths.GAMEPLAY_DB) -> Rules:
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"{db_path} not found; load a game once so Civ VI writes it.")
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            params = dict(db.execute("SELECT Name, Value FROM GlobalParameters"))
            return cls(
                city_min_range=int(params.get("CITY_MIN_RANGE", 3)),
                district_range=int(params.get("CITY_MAX_BUY_PLOT_RANGE", 3)),
                resource_class=dict(db.execute("SELECT ResourceType, ResourceClassType FROM Resources")),
                no_settle_features=tuple(f for (f,) in db.execute("SELECT FeatureType FROM Features WHERE Settlement = 0")),
                adjacencies=cls._read_adjacencies(db),
                placement={d: dict(zip(PLACEMENT_FLAGS, flags)) for d, *flags in
                           db.execute(f"SELECT DistrictType, {', '.join(PLACEMENT_FLAGS)} FROM Districts")},
                required_features=cls._read_sets(db, "District_RequiredFeatures", "FeatureType"),
                valid_terrains=cls._read_sets(db, "District_ValidTerrains", "TerrainType"),
            )
        finally:
            db.close()

    @staticmethod
    def _read_sets(db: sqlite3.Connection, table: str, column: str) -> dict[str, set[str]]:
        out: dict[str, set[str]] = {}
        for district, value in db.execute(f"SELECT DistrictType, {column} FROM {table}"):
            out.setdefault(district, set()).add(value)
        return out

    @staticmethod
    def _read_adjacencies(db: sqlite3.Connection) -> dict[str, list[AdjacencyRule]]:
        """The adjacency rules that hold from the start of the game: rules needing a tech
        or civic (or made obsolete by one), `Self` rules and rules naming one specific
        resource are left out."""
        out: dict[str, list[AdjacencyRule]] = {}
        rows = db.execute("""
            SELECT d.DistrictType, a.YieldType, a.YieldChange, a.TilesRequired, a.OtherDistrictAdjacent,
                   a.AdjacentTerrain, a.AdjacentFeature, a.AdjacentDistrict, a.AdjacentImprovement,
                   a.AdjacentResourceClass, a.AdjacentSeaResource, a.AdjacentWonder, a.AdjacentNaturalWonder,
                   a.AdjacentRiver
            FROM District_Adjacencies d JOIN Adjacency_YieldChanges a ON a.ID = d.YieldChangeId
            WHERE a.PrereqTech IS NULL AND a.PrereqCivic IS NULL AND a.ObsoleteTech IS NULL
              AND a.ObsoleteCivic IS NULL AND a.Self = 0 AND a.AdjacentResource = 0""")
        for (district, yld, change, tiles, other, terrain, feature, adj_district, improvement,
             res_class, sea, wonder, natural, river) in rows:
            rule: AdjacencyRule = {"yield": yld, "change": change, "tiles": tiles}
            if other:
                rule["other_district"] = True
            elif terrain:
                rule["terrain"] = terrain
            elif feature:
                rule["feature"] = feature
            elif adj_district:
                rule["district"] = adj_district
            elif improvement:
                rule["improvement"] = improvement
            elif res_class and res_class != "NO_RESOURCECLASS":
                rule["resource_class"] = res_class
            elif sea:
                rule["sea_resource"] = True
            elif wonder:
                rule["wonder"] = True
            elif natural:
                rule["natural_wonder"] = True
            elif river:
                rule["river"] = True
            else:
                continue
            out.setdefault(district, []).append(rule)
        return out

    def adjacency(self, gmap: GameMap, tile: Tile, district: str,
                  planned: dict[XY, str] | None = None) -> dict[str, int]:
        """{yield: bonus} the district would get on `tile`. planned: {(x, y): district
        type} of districts the plan adds (a planned city counts as DISTRICT_CITY_CENTER)."""
        planned = planned or {}

        def district_at(n: Tile) -> str:
            if (n["x"], n["y"]) in planned:
                return planned[(n["x"], n["y"])]
            if n.get("is_city"):
                return "DISTRICT_CITY_CENTER"
            return n.get("district", "NONE")

        neighbours = gmap.neighbours(tile)
        out: dict[str, int] = {}
        for rule in self.adjacencies.get(district, []):
            if rule.get("other_district"):
                count = sum(1 for n in neighbours if district_at(n) != "NONE")
            elif "terrain" in rule:
                count = sum(1 for n in neighbours if n["terrain"] == rule["terrain"])
            elif "feature" in rule:
                count = sum(1 for n in neighbours if n["feature"] == rule["feature"])
            elif "district" in rule:
                count = sum(1 for n in neighbours if district_at(n) == rule["district"])
            elif "improvement" in rule:
                count = sum(1 for n in neighbours if n.get("improvement") == rule["improvement"])
            elif "resource_class" in rule:
                count = sum(1 for n in neighbours
                            if self.resource_class.get(n.get("resource", "NONE")) == rule["resource_class"])
            elif rule.get("sea_resource"):
                count = sum(1 for n in neighbours if n["water"] and n.get("resource", "NONE") != "NONE")
            elif rule.get("wonder"):
                count = sum(1 for n in neighbours if n.get("wonder", "NONE") != "NONE")
            elif rule.get("natural_wonder"):
                count = sum(1 for n in neighbours if n.get("natural_wonder"))
            elif rule.get("river"):
                count = 1 if tile.get("river") else 0
            else:
                continue
            bonus = count // rule["tiles"] * rule["change"]
            if bonus:
                out[rule["yield"]] = out.get(rule["yield"], 0) + bonus
        return out

    @staticmethod
    def _open_land(tile: Tile, player: int) -> bool:
        """Land that nothing blocks: not water, mountain, impassable or a wonder,
        and unowned or owned by the player."""
        return not (tile["water"] or tile["mountain"] or tile["impassable"]
                    or tile["natural_wonder"] or tile["wonder"] != "NONE") \
            and tile["owner"] in (-1, player)

    def can_found_city(self, gmap: GameMap, tile: Tile) -> bool:
        if not self._open_land(tile, gmap.player) or tile["feature"] in self.no_settle_features:
            return False
        return all(gmap.distance(tile, c) > self.city_min_range for c in gmap.city_positions())

    def can_place_district(self, gmap: GameMap, tile: Tile, district: str = "DISTRICT_CAMPUS") -> bool:
        """Can `district` go on `tile`? Planned cities are handled in model.py.

        - Coast districts (Harbor): a coast or lake water tile next to land.
        - Others: open land (the planned districts have no terrain list of their own).
        - NoAdjacentCity districts (Encampment): not next to an existing city centre.
        - District_RequiredFeatures / District_ValidTerrains when the district has rows
          there (the Dam: floodplains).
        - Dams: a river along at least two of the tile's edges (engine rule; one per
          river is a constraint in model.py).
        Engine rule, not in the database: districts can't go on luxury or strategic
        resources (bonus resources are removed).
        """
        flags = self.placement.get(district, {})
        if tile["is_city"] or tile["district"] != "NONE":
            return False
        if flags.get("Coast"):
            if tile["terrain"] != "TERRAIN_COAST" or tile["natural_wonder"] or tile["wonder"] != "NONE" \
                    or tile["owner"] not in (-1, gmap.player):
                return False
            if flags.get("AdjacentToLand") and all(n["water"] for n in gmap.neighbours(tile)):
                return False
        elif not self._open_land(tile, gmap.player):
            return False
        if flags.get("NoAdjacentCity") and any(n["is_city"] for n in gmap.neighbours(tile)):
            return False
        if district in self.required_features and tile["feature"] not in self.required_features[district]:
            return False
        if district in self.valid_terrains and tile["terrain"] not in self.valid_terrains[district]:
            return False
        if self.is_dam(district) and len(gmap.river_edges(tile)) < DAM_MIN_RIVER_EDGES:
            return False
        return self.resource_class.get(tile["resource"]) not in LOCKED_RESOURCES

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

    @staticmethod
    def fresh_water_source(gmap: GameMap, tile: Tile) -> bool:
        """Engine rule for aqueducts: the tile touches a river, or is next to a lake, a
        mountain or an oasis."""
        if tile.get("river"):
            return True
        return any(n.get("lake") or n["mountain"] or n["feature"] == "FEATURE_OASIS"
                   for n in gmap.neighbours(tile))

    def neighbour_bonuses(self, districts: tuple[str, ...]) -> list[tuple[str, str, str, int]]:
        """(d, d2, yield, change) for every rule giving district d `change` of `yield` per
        neighbouring district d2, where both are planned (e.g. Industrial Zone next to an
        Aqueduct, Commercial Hub next to a Harbor). Only one-tile rules; city centres
        are handled separately."""
        out = []
        for d in districts:
            for rule in self.adjacencies.get(d, []):
                d2 = rule.get("district")
                if d2 in districts and d2 != d and rule["tiles"] == 1:
                    out.append((d, d2, rule["yield"], rule["change"]))
        return out
