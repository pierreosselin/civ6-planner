"""Placement rules, read from the game's own database where it has them.

The game writes its full gameplay database to Cache/DebugGameplay.sqlite each time a
game loads, so it reflects the expansions and mods in use. Rules that are engine
behaviour rather than data are written out and marked as such.

    rules.py       the Rules object (the tables, and the questions the planner asks)
    tables.py      the tables' types and their defaults when the database can't be read
    database.py    reading the tables from the database
    placement.py   where cities, districts and improvements may go
    adjacency.py   district adjacency bonuses
"""
from .rules import Rules
from .tables import AdjacencyRule, ImprovementRule, RegionalBuilding

__all__ = ["AdjacencyRule", "ImprovementRule", "RegionalBuilding", "Rules"]
