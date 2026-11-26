"""Reading the rules from the game's gameplay database (Cache/DebugGameplay.sqlite,
rewritten each time a game loads, so it reflects the expansions and mods in use)."""
from __future__ import annotations

import os
import sqlite3
from typing import Any

from .. import paths
from .tables import PLACEMENT_FLAGS, AdjacencyRule, ImprovementRule, RegionalBuilding


def read_rules(db_path: str = paths.GAMEPLAY_DB) -> dict[str, Any]:
    """The Rules constructor's arguments, from the database."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"{db_path} not found; load a game once so Civ VI writes it.")
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        params = dict(db.execute("SELECT Name, Value FROM GlobalParameters"))
        return dict(
            city_min_range=int(params.get("CITY_MIN_RANGE", 3)),
            district_range=int(params.get("CITY_MAX_BUY_PLOT_RANGE", 3)),
            resource_class=dict(db.execute("SELECT ResourceType, ResourceClassType FROM Resources")),
            no_settle_features=tuple(f for (f,) in db.execute("SELECT FeatureType FROM Features WHERE Settlement = 0")),
            adjacencies=read_adjacencies(db),
            placement={d: dict(zip(PLACEMENT_FLAGS, flags)) for d, *flags in
                       db.execute(f"SELECT DistrictType, {', '.join(PLACEMENT_FLAGS)} FROM Districts")},
            required_features=read_sets(db, "District_RequiredFeatures", "FeatureType"),
            valid_terrains=read_sets(db, "District_ValidTerrains", "TerrainType"),
            improvements=read_improvements(db),
            regional=read_regional(db),
        )
    finally:
        db.close()


def read_regional(db: sqlite3.Connection) -> dict[str, RegionalBuilding]:
    """Non-unique district buildings with a regional range and yields (Factory, power
    plants)."""
    out = {}
    for b, d, r in db.execute("SELECT BuildingType, PrereqDistrict, RegionalRange FROM Buildings "
                              "WHERE RegionalRange > 0 AND PrereqDistrict IS NOT NULL AND TraitType IS NULL"):
        ys = dict(db.execute("SELECT YieldType, YieldChange FROM Building_YieldChanges WHERE BuildingType = ?", (b,)))
        if ys:
            out[b] = RegionalBuilding(d, int(r), ys)
    return out


def read_improvements(db: sqlite3.Connection) -> dict[str, ImprovementRule]:
    """Buildable, non-unique improvements; placement rows needing a tech or civic
    (e.g. Farms on hills) are left out, like gated adjacency rules."""
    out = {i: ImprovementRule(sea=(dom == "DOMAIN_SEA")) for i, dom in db.execute(
        "SELECT ImprovementType, Domain FROM Improvements WHERE TraitType IS NULL AND Buildable = 1")}
    for i, y, n in db.execute("SELECT ImprovementType, YieldType, YieldChange FROM Improvement_YieldChanges"):
        if i in out and n:
            out[i].yields[y] = n
    for i, t in db.execute("SELECT ImprovementType, TerrainType FROM Improvement_ValidTerrains "
                           "WHERE PrereqTech IS NULL AND PrereqCivic IS NULL"):
        if i in out:
            out[i].terrains.add(t)
    for i, f in db.execute("SELECT ImprovementType, FeatureType FROM Improvement_ValidFeatures "
                           "WHERE PrereqTech IS NULL AND PrereqCivic IS NULL"):
        if i in out:
            out[i].features.add(f)
    for i, r in db.execute("SELECT ImprovementType, ResourceType FROM Improvement_ValidResources"):
        if i in out:
            out[i].resources.add(r)
    return out


def read_sets(db: sqlite3.Connection, table: str, column: str) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for district, value in db.execute(f"SELECT DistrictType, {column} FROM {table}"):
        out.setdefault(district, set()).add(value)
    return out


def read_adjacencies(db: sqlite3.Connection) -> dict[str, list[AdjacencyRule]]:
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
