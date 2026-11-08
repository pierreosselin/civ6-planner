"""Placement rules, read from the game's own database where it has them.

The game writes its full gameplay database to Cache/DebugGameplay.sqlite each time a
game loads, so it reflects the expansions and mods in use. Rules that are engine
behaviour rather than data are written out here and marked as such.
"""
import os
import sqlite3

from . import paths


# Campus adjacency as in the Gathering Storm database, for when it can't be read.
DEFAULT_ADJACENCIES = {"DISTRICT_CAMPUS": [
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 1, "terrain": f"TERRAIN_{t}_MOUNTAIN"}
    for t in ("GRASS", "PLAINS", "DESERT", "TUNDRA", "SNOW")] + [
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 2, "other_district": True},
    {"yield": "YIELD_SCIENCE", "change": 1, "tiles": 2, "feature": "FEATURE_JUNGLE"},
    {"yield": "YIELD_SCIENCE", "change": 2, "tiles": 1, "feature": "FEATURE_REEF"},
    {"yield": "YIELD_SCIENCE", "change": 2, "tiles": 1, "feature": "FEATURE_GEOTHERMAL_FISSURE"},
]}


class Rules:
    def __init__(self, city_min_range=3, district_range=3, resource_class=None, no_settle_features=(),
                 adjacencies=None):
        # A new city centre must be more than city_min_range tiles from any other.
        self.city_min_range = city_min_range
        # Districts go within district_range tiles of their city centre.
        self.district_range = district_range
        self.resource_class = dict(resource_class or {})
        self.no_settle_features = set(no_settle_features)
        # District -> adjacency rules: {yield, change, tiles, and one of terrain, feature,
        # district, other_district}. Each gives change per `tiles` matching neighbours.
        self.adjacencies = DEFAULT_ADJACENCIES if adjacencies is None else adjacencies

    @classmethod
    def from_game(cls, db_path=paths.GAMEPLAY_DB):
        if not os.path.exists(db_path):
            raise FileNotFoundError(f"{db_path} not found; load a game once so Civ VI writes it.")
        db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            params = dict(db.execute("SELECT Name, Value FROM GlobalParameters"))
            return cls(
                city_min_range=int(params.get("CITY_MIN_RANGE", 3)),
                district_range=int(params.get("CITY_MAX_BUY_PLOT_RANGE", 3)),
                resource_class=db.execute("SELECT ResourceType, ResourceClassType FROM Resources"),
                no_settle_features=[f for (f,) in db.execute("SELECT FeatureType FROM Features WHERE Settlement = 0")],
                adjacencies=cls._read_adjacencies(db),
            )
        finally:
            db.close()

    @staticmethod
    def _read_adjacencies(db):
        """The simple adjacency rules (by neighbouring terrain, feature or district).
        Rules needing a tech/civic, rivers, wonders or resources aren't modelled yet."""
        out = {}
        rows = db.execute("""
            SELECT d.DistrictType, a.YieldType, a.YieldChange, a.TilesRequired, a.OtherDistrictAdjacent,
                   a.AdjacentTerrain, a.AdjacentFeature, a.AdjacentDistrict
            FROM District_Adjacencies d JOIN Adjacency_YieldChanges a ON a.ID = d.YieldChangeId
            WHERE a.PrereqTech IS NULL AND a.PrereqCivic IS NULL AND a.Self = 0 AND a.AdjacentRiver = 0
              AND a.AdjacentWonder = 0 AND a.AdjacentNaturalWonder = 0 AND a.AdjacentResource = 0
              AND a.AdjacentSeaResource = 0 AND a.AdjacentImprovement IS NULL
              AND a.AdjacentResourceClass = 'NO_RESOURCECLASS'""")
        for district, yld, change, tiles, other, terrain, feature, adj_district in rows:
            rule = {"yield": yld, "change": change, "tiles": tiles}
            if other:
                rule["other_district"] = True
            elif terrain:
                rule["terrain"] = terrain
            elif feature:
                rule["feature"] = feature
            elif adj_district:
                rule["district"] = adj_district
            else:
                continue
            out.setdefault(district, []).append(rule)
        return out

    def adjacency(self, gmap, tile, district, planned=None):
        """{yield: bonus} the district would get on `tile`. planned: {(x, y): district
        type} of districts the plan adds (a planned city counts as DISTRICT_CITY_CENTER)."""
        planned = planned or {}

        def district_at(n):
            if (n["x"], n["y"]) in planned:
                return planned[(n["x"], n["y"])]
            if n.get("is_city"):
                return "DISTRICT_CITY_CENTER"
            return n.get("district", "NONE")

        neighbours = gmap.neighbours(tile)
        out = {}
        for rule in self.adjacencies.get(district, []):
            if rule.get("other_district"):
                count = sum(1 for n in neighbours if district_at(n) != "NONE")
            elif "terrain" in rule:
                count = sum(1 for n in neighbours if n["terrain"] == rule["terrain"])
            elif "feature" in rule:
                count = sum(1 for n in neighbours if n["feature"] == rule["feature"])
            else:
                count = sum(1 for n in neighbours if district_at(n) == rule["district"])
            bonus = count // rule["tiles"] * rule["change"]
            if bonus:
                out[rule["yield"]] = out.get(rule["yield"], 0) + bonus
        return out

    @staticmethod
    def _open_land(tile, player):
        """Land that nothing blocks: not water, mountain, impassable or a wonder,
        and unowned or owned by the player."""
        return not (tile["water"] or tile["mountain"] or tile["impassable"]
                    or tile["natural_wonder"] or tile["wonder"] != "NONE") \
            and tile["owner"] in (-1, player)

    def can_found_city(self, gmap, tile):
        if not self._open_land(tile, gmap.player) or tile["feature"] in self.no_settle_features:
            return False
        return all(gmap.distance(tile, c) > self.city_min_range for c in gmap.city_positions())

    def can_place_district(self, gmap, tile):
        """Generic district tile (Campus has no terrain restrictions of its own).

        Engine rule, not in the database: districts can't go on luxury or strategic
        resources (bonus resources are removed).
        """
        if not self._open_land(tile, gmap.player) or tile["is_city"] or tile["district"] != "NONE":
            return False
        res_class = self.resource_class.get(tile["resource"])
        return res_class not in ("RESOURCECLASS_LUXURY", "RESOURCECLASS_STRATEGIC")
