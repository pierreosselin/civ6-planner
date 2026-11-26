"""The data a MIP is built from (made by preprocess.prepare), plus its variables once the
formulation's variable steps have created them."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from ..config import Config
from ..gamemap import XY, GameMap
from ..rules import Rules
from ..solver import Model, Var


@dataclass
class Instance:
    gmap: GameMap
    rules: Rules
    cfg: Config                            # weights, bonuses, … (config/default.toml)
    n_cities: int
    districts: tuple[str, ...]             # D: district types to place per city
    sites: list[XY]                        # C: candidate city tiles, best site value first
    site: dict[XY, float]                  # c -> site value s_c
    own: list[XY]                          # E: the player's existing cities (always there)
    specialty_left: dict[XY, int]          # existing city -> specialty districts it may still get
    spots: dict[tuple[str, XY], list[XY]]  # (district, city) -> R_{d,c}: tiles it may go on
    # Planned-next-to-planned bonuses: (d, d2, yield, change), e.g. Industrial Zone +2
    # production per neighbouring Aqueduct.
    bonuses: list[tuple[str, str, str, int]] = field(default_factory=list)
    # Improvements: I, the types to plan; (i, city) -> tiles it may go on; how many an
    # existing city may still get; (d, i, yield, change per improvement) district bonuses.
    improvements: tuple[str, ...] = ()
    ispots: dict[tuple[str, XY], list[XY]] = field(default_factory=dict)
    improvements_left: dict[XY, int] = field(default_factory=dict)
    ibonuses: list[tuple[str, str, str, float]] = field(default_factory=list)
    # Variables, filled by the formulation's variable steps.
    x: dict[XY, Var] = field(default_factory=dict)                  # city c -> x[c]
    z: dict[tuple[str, XY, XY], Var] = field(default_factory=dict)  # (d, c, t) -> z[d,c,t]
    # (d, d2, c, t) -> y: district d of city c on t gets its bonus from c's district d2
    y: dict[tuple[str, str, XY, XY], Var] = field(default_factory=dict)
    w: dict[tuple[str, XY, XY], Var] = field(default_factory=dict)  # (i, c, t) -> improvement
    # (d, i, c, u) -> q: city c's improvement i on u touches c's district d
    q: dict[tuple[str, str, XY, XY], Var] = field(default_factory=dict)
    # Regional buildings (cfg.regional_buildings): (building, city) -> r, the city gets
    # the building's effect from a district of its type within range; (district, tile) ->
    # on, a planned district of that type is on the tile (any city's).
    r: dict[tuple[str, XY], Var] = field(default_factory=dict)
    on: dict[tuple[str, XY], Var] = field(default_factory=dict)


Step = Callable[[Model, Instance], None]   # a variable, constraint or objective function
