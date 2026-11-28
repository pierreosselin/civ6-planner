"""The optimiser's entry point: preprocess, build the MIP, solve it, read the plan back.
Reports each stage through `progress` (stages [2/5]–[4/5] of a results run)."""
from __future__ import annotations

import time

from .. import config
from ..config import Config
from ..gamemap import GameMap
from ..rules import Rules
from .formulation import Progress, build
from .instance import Instance
from .plan import Plan
from .postprocess import read_plan
from .preprocess import prepare


def optimise(gmap: GameMap, rules: Rules, cfg: Config | None = None, n_cities: int | str | None = None,
             districts: tuple[str, ...] | None = None, improvements: tuple[str, ...] | None = None,
             progress: Progress | None = None, record: Progress | None = None,
             live: bool | None = None, wonders: tuple[str, ...] | None = None) -> Plan:
    """Best plan for n_cities new cities with their districts and improvements, plus the
    districts and improvements the player's existing cities can still get.
    cfg: a Config (None: config/default.toml); n_cities, districts, improvements, wonders
    override it.
    progress: called with each line of the run (stages, model size); record: with HiGHS's
    log once solved; live: stream HiGHS's log to the terminal (default: with progress)."""
    cfg = cfg or config.default()
    say = progress or (lambda line: None)
    live = progress is not None if live is None else live
    start = time.perf_counter()
    say("[2/5] Candidates")
    inst = prepare(gmap, rules, cfg, cfg.n_cities if n_cities is None else n_cities,
                   cfg.districts if districts is None else districts, cfg.max_city_candidates,
                   cfg.improvements if improvements is None else improvements,
                   cfg.wonders if wonders is None else wonders)
    _report_candidates(inst, say, time.perf_counter() - start)
    return solve_instance(inst, progress, record, live)


def _report_candidates(inst: Instance, say: Progress, seconds: float) -> None:
    cfg = inst.cfg
    say(f"  {len(inst.sites)} city sites (best {cfg.max_city_candidates} by site value), "
        f"{len(inst.own)} existing cities, up to {inst.n_cities} new cities")
    say(f"  {sum(len(v) for v in inst.spots.values()):,} district options over {len(inst.districts)} types, "
        f"{sum(len(v) for v in inst.ispots.values()):,} improvement options "
        f"({cfg.improvement_candidates} best per city)   {seconds:.1f} s")
    if inst.wonders:
        tiles = {b: sum(1 for w, _ in inst.wspots if w == b) for b in inst.wonders}
        say("  wonder tiles: " + ", ".join(f"{b.removeprefix('BUILDING_').replace('_', ' ').title()} {n:,}"
                                           for b, n in tiles.items())
            + f" (the {cfg.wonder_candidates} with the most city sites in range)")


def solve_instance(inst: Instance, progress: Progress | None = None, record: Progress | None = None,
                   live: bool = False) -> Plan:
    """Build and solve the MIP of a prepared instance."""
    cfg = inst.cfg
    say = progress or (lambda line: None)
    say("[3/5] Building the model")
    start = time.perf_counter()
    m = build(inst, progress)
    say(f"  {len(m.names):,} variables ({sum(m.integer):,} integer), {len(m.rows):,} rows"
        f"   {time.perf_counter() - start:.1f} s")
    say(f"[4/5] Solving with HiGHS (time limit {cfg.solver.get('time_limit')} s, "
        f"gap {cfg.solver.get('mip_rel_gap')}); it minimises -objective")
    sol = m.solve(cfg.solver, live=live)
    if record:
        record(sol.log.rstrip())   # for a log file (the terminal shows it live when live)
    say(f"  -> {sol.status} in {sol.seconds:.1f} s, objective {sol.objective:,.2f}")
    return read_plan(inst, sol)
