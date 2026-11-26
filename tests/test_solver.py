"""The MIP modelling layer."""
import unittest

from civ6_planner import solver


class SolverTest(unittest.TestCase):
    def test_knapsack(self):
        m = solver.Model()
        for name, value, weight in [("a", 5, 4), ("b", 4, 3), ("c", 3, 2)]:
            m.var(name, obj=value)
        m.row({"a": 4, "b": 3, "c": 2}, hi=5)
        sol = m.solve()
        self.assertEqual((sol.status, sol["a"], sol["b"], sol["c"], sol.objective), ("optimal", 0, 1, 1, 7))


if __name__ == "__main__":
    unittest.main()
