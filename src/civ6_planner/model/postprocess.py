"""Postprocessing: read the plan back from a solution."""
from __future__ import annotations

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
    return plan
