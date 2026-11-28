"""Postprocessing: read the plan back from a solution."""
from __future__ import annotations

from ..gamemap import XY
from ..solver import Solution
from .formulation import CONSTRAINTS, OBJECTIVE
from .instance import Instance
from .plan import Plan


def read_plan(inst: Instance, sol: Solution) -> Plan:
    """The cities, districts and improvements the solution picks, with the solver's
    status and the model's size in `info` and its log."""
    plan = Plan(log=sol.log, config=inst.cfg,
                info={"status": sol.status, "seconds": round(sol.seconds, 3), "objective": sol.objective,
                      "city_candidates": len(inst.sites), **sol.stats},
                model={"constraints": [f.__name__ for f in CONSTRAINTS],
                       "objective": [f.__name__ for f in OBJECTIVE]})
    plan.cities = [c for c, v in inst.x.items() if sol[v] > 0.5]
    plan.districts = [(d, t, c) for (d, c, t), v in inst.z.items() if sol[v] > 0.5]
    plan.improvements = [(i, t, c) for (i, c, t), v in inst.w.items() if sol[v] > 0.5]
    plan.wonders = [(b, t, _builder(inst, sol, b, t)) for (b, t), v in inst.k.items() if sol[v] > 0.5]
    return plan


def _builder(inst: Instance, sol: Solution, b: str, t: XY) -> XY:
    """The city that builds wonder b on t: the first that may (constraint (12)) in the
    solution: its district next to t is planned or built, or it exists."""
    d = inst.rules.wonders[b].adjacent_district
    for c, u in inst.wspots[b, t]:
        var = inst.x.get(c) if u is None else inst.z.get((d, c, u)) if d else None
        if var is None or sol[var] > 0.5:
            return c
    raise ValueError(f"no city builds {b} on {t}")
