"""The placement optimiser: which tiles get cities, districts and improvements, as a MIP
(maths in docs/model.html, kept in step with this package).

    preprocess.py    candidate sets (sites, district tiles, improvements, wonder tiles) -> Instance
    formulation/     variables, constraints, objective terms; build() assembles them
    solve.py         optimise(): preprocess, build, solve with HiGHS (solver.py)
    postprocess.py   the Plan (plan.py) read back from the solution
    evaluate.py      scores any plan in plain Python (the MIP's or the greedy stub's)
    values.py        what a site, an improvement, a covered tile, a wonder, a regional building is worth
    existing.py      what the player already has (cities, districts, improvements, wonders, amenities)
"""
from .evaluate import city_amenities, evaluate, regional_cover
from .existing import (
    existing_amenities,
    existing_cities,
    existing_improvements,
    own_districts,
)
from .formulation import CONSTRAINTS, OBJECTIVE, VARIABLES, Progress, build
from .instance import Instance, Step
from .plan import CITY_CENTER, WONDER, Plan
from .preprocess import prepare
from .solve import optimise, solve_instance
from .values import (
    covered_value,
    improvement_value,
    regional_value,
    site_value,
    wonder_value,
)

__all__ = [
    "CITY_CENTER", "CONSTRAINTS", "OBJECTIVE", "VARIABLES", "WONDER", "Instance", "Plan", "Progress", "Step",
    "build", "city_amenities", "covered_value", "evaluate", "existing_amenities", "existing_cities",
    "existing_improvements", "improvement_value", "optimise", "own_districts", "prepare", "regional_cover",
    "regional_value", "site_value", "solve_instance", "wonder_value",
]
