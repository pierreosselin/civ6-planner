"""A results folder: the planner run on a set of test scenarios, so its decisions can be
read and checked on the map without opening Civ VI.

    results/<run>/
      index.html             every test case: tacks placed, notes, link to its map
      summary.json           the same, for comparing runs
      <case>/decisions.json  one folder per test case data/<case>/
      <case>/config.toml     the complete settings used for it (rerun with --config)
      <map>/map.html         the map with the tacks drawn
      <map>/optimisation.log model settings, the solver's log, the decisions
"""
from __future__ import annotations

import html
import json
import os
import random
from typing import Any, Callable

from . import config, dataset, model, planner, viewer
from .gamemap import GameMap
from .model import Plan
from .planner import Tack
from .rules import Rules

def describe(d: dict[str, Any]) -> str:
    sc = d.get("scenario")
    if not sc:
        return "whole map"
    if sc["mode"] == "revealed":
        what = f"tiles revealed at capture, from {sc.get('source')}"
    else:
        what = f"{sc['mode']} {sc['size']} around {tuple(sc['centre'])} of {sc.get('source')}"
    if sc.get("resources") == "visible":
        what += ", visible resources only"
    return what


def _tack_record(gmap: GameMap, t: Tack) -> dict[str, Any]:
    tile = gmap.tiles.get((t.x, t.y), {})
    return {"x": t.x, "y": t.y, "icon": t.icon, "name": t.name, "yields": t.yields,
            "tile": {k: tile.get(k) for k in ("terrain", "feature", "resource", "hills", "river", "coastal_land")}}


def run(out_dir: str, scenarios: list[str] | None = None, seed: int = 1, rules: Rules | None = None,
        method: str = "mip", echo: Callable[[str], Any] | None = None,
        config_file: str | None = None) -> dict[str, Any]:
    """Plan every test case and write the folder. Returns the summary dict.
    Settings per case: config/default.toml, the case's config.toml, then config_file.

    echo: a function such as print, called with each map's optimisation log as it
    finishes (None: silent)."""
    rules = rules or Rules.from_game()
    os.makedirs(out_dir, exist_ok=True)
    records: list[dict[str, Any]] = []
    summary = {"seed": seed, "method": method, "config_file": config_file, "scenarios": records}
    for name in scenarios or dataset.cases():
        d = dataset.load_map(name)
        cfg = config.load(dataset.config_path(name), config_file)
        original = dataset.source_of(d)
        gmap = GameMap(d)
        p = planner.solve(gmap, rules, random.Random(seed), method, cfg)
        planned, notes = planner.to_tacks(gmap, rules, p), planner.explain(gmap, rules, p, method)
        score, parts = model.evaluate(gmap, rules, p) if p.cities or p.districts else (0.0, {})
        sc_dir = os.path.join(out_dir, name)
        os.makedirs(sc_dir, exist_ok=True)
        viewer.write(d, os.path.join(sc_dir, "map.html"), title=name, tacks=planned,
                     notes=notes, hidden_from=original)
        record = {"name": name, "description": describe(d), "tiles": len(gmap),
                  "score": round(score, 2), "score_parts": parts,
                  "config": {"files": cfg.sources, **cfg.raw}, "solver": p.info,
                  "tacks": [_tack_record(gmap, t) for t in planned], "notes": notes,
                  "map": f"{name}/map.html", "log": f"{name}/optimisation.log"}
        with open(os.path.join(sc_dir, "decisions.json"), "w") as f:
            json.dump(record, f, indent=1)
        with open(os.path.join(sc_dir, "config.toml"), "w") as f:
            f.write(config.to_toml(cfg))
        log = _log(name, d, method, seed, p, record)
        with open(os.path.join(sc_dir, "optimisation.log"), "w") as f:
            f.write(log)
        if echo:
            echo(log)
        records.append(record)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(_index(summary, os.path.basename(os.path.normpath(out_dir))))
    return summary


def _log(name: str, d: dict[str, Any], method: str, seed: int, p: Plan, record: dict[str, Any]) -> str:
    """The run in text: model settings, the solver's own log, then the decisions."""
    rule = "=" * 72
    lines = [f"{name}: {describe(d)}, {record['tiles']} tiles", f"planner: {method}, seed {seed}", ""]
    if method == "mip":
        c = p.config
        lines += ["Model settings (" + " + ".join(c.sources) + ")",
                  f"  problem        {c.n_cities} cities, districts {', '.join(c.districts)},"
                  f" best {c.max_city_candidates} city sites",
                  f"  weights        " + ", ".join(f"{k[6:].lower()} {v:g}" for k, v in c.weights.items()),
                  f"  site radius    {c.site_radius}   loss factor {c.loss_factor}"
                  f"   city bonus {c.city_bonus}   district bonus {c.district_bonus}",
                  f"  solver         " + ", ".join(f"{k} {v}" for k, v in c.solver.items()),
                  f"  constraints    {', '.join(p.model.get('constraints', []))}",
                  f"  objective      {', '.join(p.model.get('objective', []))}",
                  f"  size           " + ", ".join(f"{k} {v}" for k, v in p.info.items() if k != "objective"),
                  "", rule, "HiGHS log (it minimises -objective; objective = score + bonuses)", rule,
                  p.log.rstrip(), rule, ""]
    lines += ["Decisions"] + [f"  {n}" for n in record["notes"]]
    lines += ["", "Tacks"] + [f"  {t['name']:<8} ({t['x']}, {t['y']})  {t['tile']}  adds {t['yields'] or '-'}"
                              for t in record["tacks"]]
    return "\n".join(lines) + "\n"


def _index(summary: dict[str, Any], run_name: str) -> str:
    e = html.escape
    cards = []
    for r in summary["scenarios"]:
        rows = "".join(
            f"<tr><td>{e(t['name'])}{''.join(f' +{v} {_short(k).lower()}' for k, v in t.get('yields', {}).items())}</td><td>({t['x']}, {t['y']})</td>"
            f"<td>{e(_short(t['tile'].get('terrain')))}{' · ' + e(_short(t['tile']['feature'])) if t['tile'].get('feature') not in (None, 'NONE') else ''}"
            f"{' · ' + e(_short(t['tile']['resource'])) if t['tile'].get('resource') not in (None, 'NONE') else ''}</td></tr>"
            for t in r["tacks"]) or '<tr><td colspan="3" class="muted">no tacks placed</td></tr>'
        notes = "".join(f"<li>{e(n)}</li>" for n in r["notes"])
        cards.append(f"""<section class="card">
  <div class="head"><h2>{e(r['name'])}</h2><span><a class="btn" href="{e(r['log'])}">Log</a> · <a class="btn" href="{e(r['map'])}">Open map →</a></span></div>
  <p class="muted">{e(r['description'])} · {r['tiles']} tiles · <b>score {r['score']}</b></p>
  <table><thead><tr><th>Tack</th><th>Tile</th><th>Terrain</th></tr></thead><tbody>{rows}</tbody></table>
  <ul>{notes}</ul>
</section>""")
    return _INDEX.replace("__RUN__", e(run_name)).replace("__SEED__", e(f'{summary["method"]} planner, seed {summary["seed"]}')) \
        .replace("__CARDS__", "\n".join(cards))


def _short(type_name: str | None) -> str:
    """TERRAIN_GRASS_HILLS -> Grass hills."""
    if not type_name:
        return ""
    return type_name.split("_", 1)[-1].replace("_", " ").capitalize()


_INDEX = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Planner results</title>
<style>
  :root { --bg:#f7f6f2; --panel:#ffffff; --ink:#1f1e1b; --muted:#6b6963; --line:#dddbd3; --accent:#2f5fb3; }
  @media (prefers-color-scheme: dark) { :root { --bg:#1a1a19; --panel:#242422; --ink:#f0efec; --muted:#a3a29b; --line:#3a3a37; --accent:#8fb0ec; } }
  * { box-sizing: border-box; }
  body { margin:0; padding:24px 16px; font:14px/1.5 system-ui, sans-serif; background:var(--bg); color:var(--ink); }
  main { max-width:1100px; margin:0 auto; }
  h1 { font-size:20px; margin:0 0 4px; }
  h2 { font-size:15px; margin:0; }
  .muted { color:var(--muted); font-size:12px; }
  .grid { display:grid; grid-template-columns:repeat(auto-fill, minmax(320px, 1fr)); gap:14px; margin-top:18px; }
  .card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:14px 16px; }
  .head { display:flex; justify-content:space-between; align-items:center; gap:8px; }
  .btn { color:var(--accent); text-decoration:none; font-size:13px; white-space:nowrap; }
  .btn:hover { text-decoration:underline; }
  table { width:100%; border-collapse:collapse; font-size:13px; margin:8px 0; }
  th, td { text-align:left; padding:4px 6px; border-bottom:1px solid var(--line); }
  th { font-weight:600; color:var(--muted); font-size:12px; }
  ul { padding-left:18px; margin:6px 0 0; font-size:12px; color:var(--muted); }
</style></head>
<body><main>
<h1>Planner results</h1>
<p class="muted">Run <b>__RUN__</b> · __SEED__ · each map opens with the tacks drawn (red C city, blue S campus)</p>
<div class="grid">
__CARDS__
</div>
</main></body></html>
"""
