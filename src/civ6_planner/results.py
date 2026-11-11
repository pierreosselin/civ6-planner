"""A results folder: the planner run on a set of test scenarios, so its decisions can be
read and checked on the map without opening Civ VI.

    results/<run>/
      index.html             every test case: tacks placed, notes, link to its map
      summary.json           the same, for comparing runs
      run.log                everything the run printed (all cases, HiGHS logs, summaries)
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
import time
from typing import Any, Callable

from . import config, dataset, metrics, model, paths, planner, validate, viewer
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

    echo: a function such as print, called with each line of the run as it happens
    (stages, model size, HiGHS's log live, results); None: silent. The same text goes
    into each case's optimisation.log."""
    os.makedirs(out_dir, exist_ok=True)
    run_lines: list[str] = []
    if rules is None:
        start = time.perf_counter()
        rules = Rules.from_game()
        line = f"Game rules: {paths.GAMEPLAY_DB}   loaded in {time.perf_counter() - start:.1f} s"
        run_lines.append(line)
        if echo:
            echo(line)
    records: list[dict[str, Any]] = []
    summary = {"seed": seed, "method": method, "config_file": config_file, "scenarios": records}
    for name in scenarios or dataset.cases():
        start = time.perf_counter()
        d = dataset.load_map(name)
        cfg = config.load(dataset.config_path(name), config_file)
        original = dataset.source_of(d)
        gmap = GameMap(d)
        lines: list[str] = []

        def say(line: str) -> None:
            lines.append(line)
            if echo:
                echo(line)

        for line in _header(name, d, len(gmap), method, seed, cfg):
            say(line)
        say(f"[1/5] Map: {os.path.relpath(dataset.map_path(name), paths.REPO_ROOT)}   "
            f"loaded in {time.perf_counter() - start:.1f} s")
        for line in metrics.map_summary(gmap, rules, d):
            say(line)
        p = planner.solve(gmap, rules, random.Random(seed), method, cfg,
                          progress=say, record=lines.append, live=bool(echo))
        planned, notes = planner.to_tacks(gmap, rules, p), planner.explain(gmap, rules, p, method)
        score, parts = model.evaluate(gmap, rules, p) if p.cities or p.districts else (0.0, {})
        stats = metrics.plan_metrics(gmap, rules, p)
        check = validate.check_plan(gmap, rules, p)
        sc_dir = os.path.join(out_dir, name)
        os.makedirs(sc_dir, exist_ok=True)
        viewer.write(d, os.path.join(sc_dir, "map.html"), title=name, tacks=planned,
                     hidden_from=original)
        record = {"name": name, "description": describe(d), "tiles": len(gmap),
                  "score": round(score, 2), "score_parts": parts,
                  "config": {"files": cfg.sources, **cfg.raw}, "solver": p.info,
                  "metrics": stats, "validation": check,
                  "tacks": [_tack_record(gmap, t) for t in planned], "notes": notes,
                  "map": f"{name}/map.html", "log": f"{name}/optimisation.log"}
        with open(os.path.join(sc_dir, "decisions.json"), "w") as f:
            json.dump(record, f, indent=1)
        with open(os.path.join(sc_dir, "config.toml"), "w") as f:
            f.write(config.to_toml(cfg))
        say("[5/5] Result")
        if parts:
            say(f"  score {score:.1f} = site {parts['site']:.1f} + adjacency {parts['adjacency']:.1f}"
                f" + improvements {parts['improvements']:.1f} - covered tiles {parts['lost']:.1f}")
        for line in metrics.format_summary(stats):
            say(line)
        for line in validate.format_check(check):
            say(line)
        for line in _where(sc_dir):
            say(line)
        say("")
        with open(os.path.join(sc_dir, "optimisation.log"), "w") as f:
            f.write("\n".join(lines) + "\n")
        run_lines += lines
        records.append(record)
    with open(os.path.join(out_dir, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1)
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(_index(summary, os.path.basename(os.path.normpath(out_dir))))
    with open(os.path.join(out_dir, "run.log"), "w") as f:
        f.write("\n".join(run_lines + summary_lines(summary, out_dir)) + "\n")
    return summary


def summary_lines(summary: dict[str, Any], out_dir: str) -> list[str]:
    """One line per case (score, solver status and time, what was placed), then the index
    page. Printed at the end of a run, also when quiet, and the end of run.log."""
    lines = []
    for r in summary["scenarios"]:
        counts: dict[str, int] = {}
        for t in r["tacks"]:
            icon = t["icon"].removeprefix("ICON_")
            kind = ("City" if t["icon"] == planner.CITY_ICON else
                    planner.improvement_name(icon) if icon.startswith("IMPROVEMENT_") else planner.district_name(icon))
            counts[kind] = counts.get(kind, 0) + 1
        placed = ", ".join(f"{n} {name}" for name, n in counts.items()) or "nothing"
        solver = r["solver"]
        lines.append(f"  {r['name']:<22} score {r['score']:>8}  {solver.get('status', '')} "
                     f"{solver.get('seconds', '')}s  {placed}")
    lines.append(f"-> {os.path.join(out_dir, 'index.html')}   (whole run: {os.path.join(out_dir, 'run.log')})")
    return lines


def _header(name: str, d: dict[str, Any], tiles: int, method: str, seed: int, cfg: config.Config) -> list[str]:
    """Which case, and the settings that matter, before the run starts."""
    rule = "=" * 96
    return [rule, f"{name}: {describe(d)}, {tiles} tiles · planner {method}"
            + (f", seed {seed}" if method != "mip" else ""), rule,
            "Settings (" + " + ".join(cfg.sources) + ")",
            f"  cities {cfg.n_cities}, {len(cfg.districts)} district types (at most {cfg.max_specialty_districts}"
            f" specialty per city), {len(cfg.improvements)} improvement types (at most {cfg.max_improvements} per city)",
            "  weights " + ", ".join(f"{k[6:].lower()} {v:g}" for k, v in cfg.weights.items())
            + f"; site radius {cfg.site_radius}, loss {cfg.loss_factor}, worked tile {cfg.worked_tile_factor}"]


def _where(sc_dir: str) -> list[str]:
    """Where to look at the map with its tacks."""
    page = os.path.join(sc_dir, "map.html")
    rel = os.path.relpath(page, paths.REPO_ROOT)
    out = ["Map with the tacks (every placement is listed in decisions.json and index.html):",
           f"  {page}", f"  xdg-open {page}"]
    if not rel.startswith(".."):
        out.append(f"  Live Server: http://127.0.0.1:5500/{rel}")
    return out


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
