"""The optimiser's result: where the new cities, districts and improvements go."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .. import config
from ..config import Config
from ..gamemap import XY

CITY_CENTER = "DISTRICT_CITY_CENTER"


@dataclass
class Plan:
    cities: list[XY] = field(default_factory=list)                        # city centres
    districts: list[tuple[str, XY, XY]] = field(default_factory=list)     # (district type, tile, its city)
    improvements: list[tuple[str, XY, XY]] = field(default_factory=list)  # (improvement, tile, its city)
    info: dict[str, Any] = field(default_factory=dict)                    # solver status, timings, sizes
    log: str = ""                                                         # the solver's log
    model: dict[str, list[str]] = field(default_factory=dict)             # constraints and objective terms used
    config: Config = field(default_factory=config.default)                # the settings it was made with

    def planned(self) -> dict[XY, str]:
        """Tile -> district type of everything the plan builds (a city: its centre)."""
        out: dict[XY, str] = {xy: CITY_CENTER for xy in self.cities}
        out.update({xy: d for d, xy, _ in self.districts})
        return out

    def improved(self) -> dict[XY, str]:
        """Tile -> improvement the plan builds there."""
        return {xy: i for i, xy, _ in self.improvements}
