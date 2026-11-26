"""The plan statistics (plan.py) as lines of text for the logs and the terminal."""
from __future__ import annotations

from typing import Any


def _wrap(items: list[str], width: int = 96, indent: str = "    ") -> list[str]:
    lines, line = [], ""
    for item in items:
        if line and len(line) + 3 + len(item) > width:
            lines.append(indent + line)
            line = ""
        line = f"{line} · {item}" if line else item
    return lines + ([indent + line] if line else [])


def format_summary(m: dict[str, Any]) -> list[str]:
    """The metrics in a few lines: totals, then each district and improvement type with
    the share of cities that get one."""
    dpc, ipc = m["districts_per_city"], m.get("improvements_per_city", {"mean": 0})
    lines = [f"  {m['cities']} cities ({m['new_cities']} new, {m['existing_cities']} existing) · "
             f"{m['districts']} districts ({dpc['mean']} per city) · "
             f"{m.get('improvements', 0)} improvements ({ipc['mean']} per city)"]
    districts = []
    for d, t in m["by_type"].items():
        adj = ", ".join(f"+{v:g} {k[6:].lower()}" for k, v in t["adjacency_mean"].items())
        districts.append(f"{d.removeprefix('DISTRICT_').replace('_', ' ').title()} {t['share_of_cities']:.0%}"
                         + (f" ({adj})" if adj else ""))
    lines += ["  districts: share of cities (mean adjacency)"] + _wrap(districts)
    imps = [f"{i.removeprefix('IMPROVEMENT_').replace('_', ' ').title()} {t['share_of_cities']:.0%} ({t['count']})"
            for i, t in m.get("improvements_by_type", {}).items()]
    if imps:
        lines += ["  improvements: share of cities (count)"] + _wrap(imps)
    for b, r in m.get("regional", {}).items():
        lines.append(f"  regional: {b.removeprefix('BUILDING_').replace('_', ' ').title()} reaches "
                     f"{r['cities_reached']} cities ({r['share_of_cities']:.0%}) from {r['districts']} "
                     f"{'district' if r['districts'] == 1 else 'districts'}")
    s = m.get("spacing", {})
    if s.get("nearest_city"):
        nc, ap = s["nearest_city"], s["all_pairs"]
        top = next(v for k, v in s.items() if k.startswith("top_"))
        lines += [f"  spacing (tiles): nearest other city min {nc['min']}, mean {nc['mean']}, max {nc['max']} "
                  f"{nc['histogram']} · all pairs min {ap['min']}, mean {ap['mean']}, max {ap['max']}",
                  f"    best {len(top['cities'])} sites {top['cities']}: mean distance {top['mean']} "
                  f"(min {top['min']}, max {top['max']})"
                  + (f" · nearest other player's city: mean {s['nearest_foreign_city']['mean']}, "
                     f"min {s['nearest_foreign_city']['min']}" if s.get("nearest_foreign_city") else "")]
    return lines


def format_metrics(m: dict[str, Any]) -> list[str]:
    """The metrics as log lines."""
    dpc = m["districts_per_city"]
    lines = [f"cities {m['cities']} ({m['new_cities']} new, {m['existing_cities']} existing), "
             f"districts {m['districts']}",
             f"districts per city: mean {dpc['mean']}, min {dpc['min']}, max {dpc['max']}; "
             f"cities by number of districts {dpc['histogram']}",
             f"{'district':<18}{'count':>6}{'in cities':>11}{'share':>8}  mean adjacency (min-max)   weighted"]
    for d, t in m["by_type"].items():
        adj = ", ".join(f"+{t['adjacency_mean'][k]:g} {k[6:].lower()} ({lo}-{hi})"
                        for k, (lo, hi) in t["adjacency_min_max"].items()) or "none"
        lines.append(f"{d.removeprefix('DISTRICT_').replace('_', ' ').title():<18}{t['count']:>6}"
                     f"{t['cities_with']:>11}{t['share_of_cities']:>8.0%}  {adj:<26} {t['weighted_mean']:>6}")
    if m.get("improvements_by_type"):
        ipc = m["improvements_per_city"]
        lines += [f"improvements {m['improvements']}; per city mean {ipc['mean']}, min {ipc['min']}, max {ipc['max']}",
                  f"{'improvement':<18}{'count':>6}{'in cities':>11}{'share':>8}  mean value (gain + worked tile)"]
        for i, t in m["improvements_by_type"].items():
            lines.append(f"{i.removeprefix('IMPROVEMENT_').replace('_', ' ').title():<18}{t['count']:>6}"
                         f"{t['cities_with']:>11}{t['share_of_cities']:>8.0%}  {t['value_mean']}")
    return lines
