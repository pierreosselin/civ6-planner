"""Planner settings from TOML: config/default.toml, overlaid by an optional user file.

    cfg = config.load()                             # defaults
    cfg = config.load("data/x/config.toml", "my.toml")  # defaults, then each file in turn

Each file sets only the values it changes (later files win) and may be empty; None
entries are skipped. `to_toml(cfg)` writes the complete
settings a run used, which `load()` reads back to repeat the run.
"""
from __future__ import annotations

import copy
import os
import tomllib
from dataclasses import dataclass, field
from typing import Any, Mapping

Yields = Mapping[str, float]   # YIELD_* -> amount (a tile dict works too)

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "config", "default.toml")
YIELDS = ["YIELD_FOOD", "YIELD_PRODUCTION", "YIELD_GOLD", "YIELD_SCIENCE", "YIELD_CULTURE", "YIELD_FAITH"]


@dataclass
class Timing:
    """The [timing] table: periods = 0 is the static model (everything at once). Speeds
    are in turns; the model turns them into periods of turns_per_period turns."""
    periods: int = 0
    mode: str = "sequential"            # "sequential": where (static) then when; "joint": both at once
    turns_per_period: int = 20
    settlers_base: float = 1.0          # new cities per period on top of the per-city rate
    turns_per_settler: float = 40.0     # turns one city needs to train a settler
    turns_per_district: float = 20.0    # turns one city needs to build a district
    turns_per_specialty: float = 30.0   # city age (turns) for each specialty district beyond the first
    ring_delay_turns: tuple[float, ...] = (0, 0, 15, 35)   # by distance from the city: turns before usable
    district_base_value: float = 4.0    # weighted yield per turn of a built district (its buildings)
    build_speedup: tuple[float, ...] = ()   # per period, multiplies settler and district rates (empty: 1)

    def delay(self, r: int) -> int:
        """Periods after founding before a tile at distance r is usable (rounded up)."""
        turns = self.ring_delay_turns[min(r, len(self.ring_delay_turns) - 1)]
        return -int(-turns // self.turns_per_period)

    def speedup(self, p: int) -> float:
        """Rate multiplier in period p (1-based)."""
        return self.build_speedup[p - 1] if p - 1 < len(self.build_speedup) else 1.0


@dataclass
class Config:
    n_cities: int | str            # a number, or "max": as many as fit
    districts: tuple[str, ...]     # district types, e.g. DISTRICT_CAMPUS
    max_city_candidates: int
    max_specialty_districts: int   # per city, districts that need population (RequiresPopulation)
    improvements: tuple[str, ...]  # improvement types to plan
    max_improvements: int          # per city
    improvement_candidates: int    # per city, best (improvement, tile) options kept as variables
    worked_tile_factor: float      # share of an improved tile's own yields counted (it is worked)
    site_radius: int
    loss_factor: float
    city_bonus: float
    district_bonus: float
    weights: dict[str, float]      # YIELD_* -> value of one unit
    solver: dict[str, Any]         # scipy.optimize.milp options
    timing: Timing = field(default_factory=Timing)          # periods = 0: static model
    sources: list[str] = field(default_factory=list)       # files read, in order
    raw: dict[str, Any] = field(default_factory=dict)      # the merged TOML, for logs

    def weighted(self, yields: Yields) -> float:
        """Weighted sum of a {YIELD_*: n} dict (a tile works too)."""
        return sum(self.weights[y] * yields.get(y, 0) for y in YIELDS)


def _merge(base: dict[str, Any], over: dict[str, Any], where: str = "") -> None:
    for k, v in over.items():
        if k not in base and where != "solver.":   # [solver] takes any milp option
            raise KeyError(f"unknown setting {where}{k!r} (see {DEFAULT_PATH})")
        if isinstance(v, dict):
            _merge(base[k], v, f"{where}{k}.")
        else:
            base[k] = v


def load(*paths: str | None) -> Config:
    files = [os.path.relpath(os.path.normpath(DEFAULT_PATH))] + [os.path.relpath(p) for p in paths if p]
    with open(files[0], "rb") as f:
        raw = tomllib.load(f)
    for path in files[1:]:
        with open(path, "rb") as f:
            _merge(raw, tomllib.load(f))
    raw = copy.deepcopy(raw)
    p, o = raw["problem"], raw["objective"]
    return Config(
        n_cities=p["n_cities"], districts=tuple(p["districts"]),
        max_city_candidates=p["max_city_candidates"],
        max_specialty_districts=p["max_specialty_districts"],
        improvements=tuple(p["improvements"]), max_improvements=p["max_improvements"],
        improvement_candidates=p["improvement_candidates"],
        worked_tile_factor=o["worked_tile_factor"],
        site_radius=o["site_radius"], loss_factor=o["loss_factor"],
        city_bonus=o["city_bonus"], district_bonus=o["district_bonus"],
        weights={"YIELD_" + k.upper(): float(v) for k, v in o["weights"].items()},
        solver=dict(raw["solver"]), sources=files, raw=raw,
        timing=_timing(raw["timing"]))


def _timing(t: dict[str, Any]) -> Timing:
    if t["mode"] not in ("sequential", "joint"):
        raise ValueError(f"timing.mode must be sequential or joint, not {t['mode']!r}")
    return Timing(periods=int(t["periods"]), mode=t["mode"], turns_per_period=int(t["turns_per_period"]),
                  settlers_base=float(t["settlers_base"]), turns_per_settler=float(t["turns_per_settler"]),
                  turns_per_district=float(t["turns_per_district"]),
                  turns_per_specialty=float(t["turns_per_specialty"]),
                  ring_delay_turns=tuple(float(v) for v in t["ring_delay_turns"]),
                  district_base_value=float(t["district_base_value"]),
                  build_speedup=tuple(float(v) for v in t["build_speedup"]))


def _value(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(_value(x) for x in v) + "]"
    return repr(v)


def to_toml(cfg: Config) -> str:
    """The complete settings as TOML (every value, not just the overrides)."""
    lines = ["# Settings used for this run: " + " + ".join(cfg.sources),
             "# Rerun with: --config <this file>"]

    def table(name, d):
        lines.extend(["", f"[{name}]"])
        lines.extend(f"{k} = {_value(v)}" for k, v in d.items() if not isinstance(v, dict))
        for k, v in d.items():
            if isinstance(v, dict):
                table(f"{name}.{k}", v)

    for name, d in cfg.raw.items():
        table(name, d)
    return "\n".join(lines) + "\n"


_default = None


def default() -> Config:
    """The defaults, read once."""
    global _default
    if _default is None:
        _default = load()
    return _default
