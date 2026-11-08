"""A small MIP modelling layer, so the placement model never deals with matrices.

Variables and linear rows are added by name; `solve()` maximises the objective with
HiGHS through scipy.optimize.milp. Another backend (CP-SAT, SCIP…) only needs another
`solve`.
"""
import contextlib
import math
import os
import sys
import tempfile
import time
from dataclasses import dataclass, field


@dataclass
class Solution:
    status: str            # "optimal", "time limit", "infeasible", …
    objective: float
    values: dict           # variable name -> value (rounded for integer variables)
    seconds: float
    stats: dict = field(default_factory=dict)
    log: str = ""          # HiGHS's own log of the run

    def __getitem__(self, name):
        return self.values.get(name, 0)


class Model:
    def __init__(self):
        self.names, self.lb, self.ub, self.integer, self.obj = [], [], [], [], []
        self.index = {}
        self.rows = []  # (coeffs {var index: a}, lo, hi)

    def var(self, name, lb=0, ub=1, integer=True, obj=0.0):
        """Add a variable (binary by default) with objective coefficient `obj`."""
        if name in self.index:
            raise ValueError(f"duplicate variable {name!r}")
        self.index[name] = len(self.names)
        self.names.append(name)
        self.lb.append(lb)
        self.ub.append(ub)
        self.integer.append(integer)
        self.obj.append(obj)
        return name

    def add_obj(self, name, coef):
        self.obj[self.index[name]] += coef

    def row(self, coeffs, lo=-math.inf, hi=math.inf):
        """lo <= sum(a * var) <= hi; coeffs: {name: a} or [(name, a), …] (repeats add up)."""
        items = coeffs.items() if isinstance(coeffs, dict) else coeffs
        merged = {}
        for name, a in items:
            i = self.index[name]
            merged[i] = merged.get(i, 0) + a
        merged = {i: a for i, a in merged.items() if a}
        if merged:
            self.rows.append((merged, lo, hi))
        elif lo > 0 or hi < 0:
            raise ValueError("empty row that can't hold")

    def solve(self, time_limit=60, gap=1e-6):
        """Maximise; HiGHS's log goes into Solution.log (not to the terminal)."""
        with _capture_stdout() as out:
            sol = self._solve(time_limit, gap)
        sol.log = out.read()
        return sol

    def _solve(self, time_limit, gap):
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array

        n = len(self.names)
        start = time.perf_counter()
        if n == 0:
            return Solution("optimal", 0.0, {}, 0.0, {"variables": 0, "rows": 0})
        r, c, v = [], [], []
        for k, (coeffs, _, _) in enumerate(self.rows):
            for i, a in coeffs.items():
                r.append(k), c.append(i), v.append(a)
        constraints = []
        if self.rows:
            a = coo_array((v, (r, c)), shape=(len(self.rows), n)).tocsr()
            constraints.append(LinearConstraint(a, [lo for _, lo, _ in self.rows], [hi for _, _, hi in self.rows]))
        res = milp(c=-np.array(self.obj, dtype=float), constraints=constraints,
                   integrality=np.array(self.integer, dtype=int), bounds=Bounds(self.lb, self.ub),
                   options={"time_limit": time_limit, "mip_rel_gap": gap, "disp": True})
        seconds = time.perf_counter() - start
        status = {0: "optimal", 1: "time limit", 2: "infeasible", 3: "unbounded"}.get(res.status, res.message)
        stats = {"variables": n, "integer": sum(self.integer), "rows": len(self.rows),
                 "gap": getattr(res, "mip_gap", None)}
        if res.x is None:
            return Solution(status, float("nan"), {}, seconds, stats)
        values = {name: (round(x) if integer else x)
                  for name, x, integer in zip(self.names, res.x, self.integer)}
        return Solution(status, -res.fun, values, seconds, stats)


class _Captured:
    def __init__(self):
        self.text = ""

    def read(self):
        return self.text


@contextlib.contextmanager
def _capture_stdout():
    """Capture what C code (HiGHS) prints to file descriptor 1."""
    out = _Captured()
    sys.stdout.flush()
    saved = os.dup(1)
    with tempfile.TemporaryFile(mode="w+b") as tmp:
        os.dup2(tmp.fileno(), 1)
        try:
            yield out
        finally:
            sys.stdout.flush()
            os.dup2(saved, 1)
            os.close(saved)
            tmp.seek(0)
            out.text = tmp.read().decode("utf-8", "replace")
