"""The MIP formulation, assembled from three lists of small functions:

    VARIABLES    create the decision variables (no objective coefficients)
    CONSTRAINTS  one function per constraint family, numbered as in docs/model.html §9
    OBJECTIVE    one function per objective term (adds coefficients to variables)

Every function takes (m, inst): the Model being built and the Instance (instance.py).
Comment out a line to drop that constraint or term; the log lists what was on. Each
feature has its own file (variables, constraints and terms together):

    cities.py             x[c]           (1) max_cities, (2) city_spacing
    districts.py          z[d,c,t]       (3) district_needs_city, (8) specialty_limit
    district_rules.py                    (5) not_next_to_planned_city, (7) one_dam_per_river
    tiles.py                             (4) one_thing_per_tile
    neighbour_bonus.py    y[d,d2,c,t]    (6) neighbour_bonus_link
    improvements.py       w[i,c,t]       (9) improvement_limit
    improvement_bonus.py  q[d,i,c,u]     (10) improvement_bonus_link
    regional.py           r[b,c], on[d,t] (11) regional_reach (off unless configured)
    wonders.py            k[b,t]         (12) wonder_needs_district, (13) one_of_each_wonder
    amenities.py          a[c]           (14) amenity_supply

Not modelled on purpose: adjacency between planned districts other than a district's
own city centre and the y/q bonuses (e.g. Campus next to a planned Holy Site, or
another city's centre). It needs coupling variables (k * tiles <= linked planned
neighbours), which made HiGHS much slower.
"""
from __future__ import annotations

from typing import Any, Callable

from ...solver import Model
from ..instance import Instance, Step
from .amenities import amenity_supply, amenity_term, amenity_vars
from .cities import city_bonus_term, city_spacing, city_vars, max_cities, site_term
from .district_rules import not_next_to_planned_city, one_dam_per_river
from .districts import (adjacency_term, covered_tile_term, district_bonus_term, district_needs_city,
                        district_vars, specialty_limit)
from .improvement_bonus import improvement_bonus_link, improvement_bonus_term, improvement_bonus_vars
from .improvements import improvement_limit, improvement_term, improvement_vars
from .neighbour_bonus import neighbour_bonus_link, neighbour_bonus_term, neighbour_bonus_vars
from .regional import regional_reach, regional_term, regional_vars
from .tiles import one_thing_per_tile
from .wonders import one_of_each_wonder, wonder_needs_district, wonder_term, wonder_vars

VARIABLES: list[Step] = [
    city_vars,
    district_vars,
    neighbour_bonus_vars,
    improvement_vars,
    improvement_bonus_vars,
    regional_vars,
    wonder_vars,
    amenity_vars,       # after the districts and wonders it counts
]
CONSTRAINTS: list[Step] = [
    max_cities,
    city_spacing,
    district_needs_city,
    one_thing_per_tile,
    not_next_to_planned_city,
    one_dam_per_river,
    neighbour_bonus_link,
    specialty_limit,
    improvement_limit,
    improvement_bonus_link,
    regional_reach,
    wonder_needs_district,
    one_of_each_wonder,
    amenity_supply,
]
OBJECTIVE: list[Step] = [
    site_term,
    adjacency_term,
    covered_tile_term,
    neighbour_bonus_term,
    improvement_term,
    improvement_bonus_term,
    regional_term,
    wonder_term,
    amenity_term,
    city_bonus_term,
    district_bonus_term,
]

Progress = Callable[[str], Any]   # e.g. print; receives one line per stage of a run


def build(inst: Instance, progress: Progress | None = None) -> Model:
    """Run the VARIABLES, CONSTRAINTS and OBJECTIVE steps; with progress, report what each
    adds (variables, rows, objective coefficients) as it goes."""
    m = Model()
    for kind, steps in (("variables", VARIABLES), ("constraints", CONSTRAINTS), ("objective", OBJECTIVE)):
        for step in steps:
            n_vars, n_rows, obj = len(m.names), len(m.rows), list(m.obj)
            step(m, inst)
            if progress is not None:
                progress(_added(kind, step, m, n_vars, n_rows, obj))
    return m


def _added(kind: str, step: Step, m: Model, n_vars: int, n_rows: int, obj: list[float]) -> str:
    """One log line: what a step added to the model."""
    name = step.__name__
    if kind == "variables":
        return f"  variables    {name:<26}{len(m.names) - n_vars:>8,} variables   total {len(m.names):>8,}"
    if kind == "constraints":
        return f"  constraints  {name:<26}{len(m.rows) - n_rows:>8,} rows        total {len(m.rows):>8,}"
    changed = sum(1 for a, b in zip(obj, m.obj) if a != b)
    return f"  objective    {name:<26}{changed:>8,} coefficients"
