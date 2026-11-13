"""A small MIP modelling layer, so the placement model never deals with matrices.

Variables and linear rows are added by name; `solve()` maximises the objective with
HiGHS through scipy.optimize.milp. Another backend (CP-SAT, SCIP…) only needs another
`solve`.
"""
import contextlib
import math
import os
import pty
import sys
import termios
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Hashable, Iterable, Iterator, Mapping

Var = Hashable   # a variable is known by its name, e.g. ("city", (11, 17))


@dataclass
class Solution:
    status: str            # "optimal", "time limit", "infeasible", …
    objective: float
    values: dict[Var, float]   # variable -> value (rounded for integer variables)
    seconds: float
    stats: dict[str, Any] = field(default_factory=dict)
    log: str = ""          # HiGHS's own log of the run

    def __getitem__(self, name: Var) -> float:
        return self.values.get(name, 0)


class Model:
    def __init__(self) -> None:
        self.names: list[Var] = []
        self.lb: list[float] = []
        self.ub: list[float] = []
        self.integer: list[bool] = []
        self.obj: list[float] = []
        self.index: dict[Var, int] = {}
        self.rows: list[tuple[dict[int, float], float, float]] = []  # (coeffs {var index: a}, lo, hi)

    def var(self, name: Var, lb: float = 0, ub: float = 1, integer: bool = True, obj: float = 0.0) -> Var:
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

    def fix(self, name: Var, value: float) -> None:
        """Fix a variable to a value (its bounds)."""
        i = self.index[name]
        self.lb[i] = self.ub[i] = value

    def add_obj(self, name: Var, coef: float) -> None:
        self.obj[self.index[name]] += coef

    def row(self, coeffs: Mapping[Var, float] | Iterable[tuple[Var, float]],
            lo: float = -math.inf, hi: float = math.inf) -> None:
        """lo <= sum(a * var) <= hi; coeffs: {name: a} or [(name, a), …] (repeats add up)."""
        items = coeffs.items() if isinstance(coeffs, Mapping) else coeffs
        merged: dict[int, float] = {}
        for name, a in items:
            i = self.index[name]
            merged[i] = merged.get(i, 0) + a
        merged = {i: a for i, a in merged.items() if a}
        if merged:
            self.rows.append((merged, lo, hi))
        elif lo > 0 or hi < 0:
            raise ValueError("empty row that can't hold")

    def solve(self, options: dict[str, Any] | None = None, live: bool = False) -> Solution:
        """Maximise; HiGHS's log goes into Solution.log, and also to the terminal as it
        runs when live is True.
        options: scipy.optimize.milp options (time_limit, mip_rel_gap, presolve,
        node_limit); disp is forced on so there is a log to capture."""
        options = {"time_limit": 60.0, "mip_rel_gap": 1e-6, **(options or {}), "disp": True}
        with _capture_stdout(tee=live) as out:
            sol = self._solve(options)
        sol.log = out.read()
        return sol

    def _solve(self, options: dict[str, Any]) -> Solution:
        import numpy as np
        from scipy.optimize import Bounds, LinearConstraint, milp
        from scipy.sparse import coo_array

        n = len(self.names)
        start = time.perf_counter()
        if n == 0:
            return Solution("optimal", 0.0, {}, 0.0, {"variables": 0, "rows": 0})
        r: list[int] = []
        c: list[int] = []
        v: list[float] = []
        for k, (coeffs, _, _) in enumerate(self.rows):
            for i, a in coeffs.items():
                r.append(k)
                c.append(i)
                v.append(a)
        constraints = []
        if self.rows:
            a = coo_array((v, (r, c)), shape=(len(self.rows), n)).tocsr()
            constraints.append(LinearConstraint(a, [lo for _, lo, _ in self.rows], [hi for _, _, hi in self.rows]))
        res = milp(c=-np.array(self.obj, dtype=float), constraints=constraints,
                   integrality=np.array(self.integer, dtype=int), bounds=Bounds(self.lb, self.ub),
                   options=options)
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
def _capture_stdout(tee: bool = False) -> Iterator[_Captured]:
    """Capture what C code (HiGHS) prints to file descriptor 1; with tee, also pass it on
    to the real stdout as it comes. A pseudo-terminal, not a pipe, so the C library
    keeps line buffering and the log appears line by line."""
    out = _Captured()
    sys.stdout.flush()
    saved = os.dup(1)
    master, slave = pty.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[1] &= ~termios.ONLCR                      # keep "\n", don't turn it into "\r\n"
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    chunks: list[bytes] = []

    def pump() -> None:
        while True:
            try:
                data = os.read(master, 4096)
            except OSError:                         # EIO: the slave side is closed
                break
            if not data:
                break
            chunks.append(data)
            if tee:
                os.write(saved, data)

    reader = threading.Thread(target=pump, daemon=True)
    reader.start()
    os.dup2(slave, 1)
    os.close(slave)
    try:
        yield out
    finally:
        sys.stdout.flush()
        os.dup2(saved, 1)                           # closes the last handle on the slave side
        reader.join(timeout=5)
        os.close(master)
        os.close(saved)
        out.text = b"".join(chunks).decode("utf-8", "replace")
