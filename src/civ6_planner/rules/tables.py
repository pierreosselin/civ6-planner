"""The rule tables' types, and the values used when the game database can't be read
(as in Gathering Storm). Rules that are engine behaviour rather than data are marked."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

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


@dataclass
class ImprovementRule:
    """Where an improvement may go and what it adds, from the game database (rows that
    need a technology or civic are left out)."""
    yields: dict[str, int] = field(default_factory=dict)   # Improvement_YieldChanges
    terrains: set[str] = field(default_factory=set)        # Improvement_ValidTerrains
    features: set[str] = field(default_factory=set)        # Improvement_ValidFeatures
    resources: set[str] = field(default_factory=set)       # Improvement_ValidResources
    sea: bool = False                                      # Domain = DOMAIN_SEA


# The classic improvements, as in the Gathering Storm database, for when it can't be read.
DEFAULT_IMPROVEMENTS: dict[str, ImprovementRule] = {
    "IMPROVEMENT_FARM": ImprovementRule({"YIELD_FOOD": 1}, {"TERRAIN_GRASS", "TERRAIN_PLAINS"},
                                        {"FEATURE_FLOODPLAINS", "FEATURE_FLOODPLAINS_GRASSLAND",
                                         "FEATURE_FLOODPLAINS_PLAINS", "FEATURE_VOLCANIC_SOIL"},
                                        {"RESOURCE_MAIZE", "RESOURCE_RICE", "RESOURCE_WHEAT"}),
    "IMPROVEMENT_MINE": ImprovementRule({"YIELD_PRODUCTION": 1},
                                        {f"TERRAIN_{t}_HILLS" for t in ("GRASS", "PLAINS", "DESERT", "TUNDRA", "SNOW")},
                                        {"FEATURE_VOLCANIC_SOIL"},
                                        {"RESOURCE_IRON", "RESOURCE_COPPER", "RESOURCE_SALT", "RESOURCE_SILVER",
                                         "RESOURCE_DIAMONDS", "RESOURCE_JADE", "RESOURCE_MERCURY", "RESOURCE_NITER",
                                         "RESOURCE_COAL", "RESOURCE_ALUMINUM", "RESOURCE_URANIUM", "RESOURCE_AMBER"}),
    "IMPROVEMENT_QUARRY": ImprovementRule({"YIELD_PRODUCTION": 1}, set(), set(),
                                          {"RESOURCE_STONE", "RESOURCE_MARBLE", "RESOURCE_GYPSUM"}),
    "IMPROVEMENT_LUMBER_MILL": ImprovementRule({"YIELD_PRODUCTION": 2}, set(), {"FEATURE_FOREST"}, set()),
}


@dataclass
class RegionalBuilding:
    """A building whose yields reach every one of the player's city centres within
    `range` tiles (Buildings.RegionalRange); a city gets each building's effect once."""
    district: str                                          # Buildings.PrereqDistrict
    range: int
    yields: dict[str, int] = field(default_factory=dict)   # Building_YieldChanges


# As in the Gathering Storm database, for when it can't be read.
DEFAULT_REGIONAL: dict[str, RegionalBuilding] = {
    "BUILDING_FACTORY": RegionalBuilding("DISTRICT_INDUSTRIAL_ZONE", 6, {"YIELD_PRODUCTION": 3}),
}
