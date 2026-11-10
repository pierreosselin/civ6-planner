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
class Config:
    n_cities: int | str            # a number, or "max": as many as fit
    districts: tuple[str, ...]     # district types, e.g. DISTRICT_CAMPUS
    max_city_candidates: int
    max_specialty_districts: int   # per city, districts that need population (RequiresPopulation)
    site_radius: int
    loss_factor: float
    city_bonus: float
    district_bonus: float
    weights: dict[str, float]      # YIELD_* -> value of one unit
    solver: dict[str, Any]         # scipy.optimize.milp options
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
        site_radius=o["site_radius"], loss_factor=o["loss_factor"],
        city_bonus=o["city_bonus"], district_bonus=o["district_bonus"],
        weights={"YIELD_" + k.upper(): float(v) for k, v in o["weights"].items()},
        solver=dict(raw["solver"]), sources=files, raw=raw)


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
